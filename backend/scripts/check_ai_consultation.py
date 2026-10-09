"""I-03A 正常系の実API確認（OpenRouter）。

架空の相談文で、AIを呼ぶ4つの場面を1回ずつ確認する。最大5リクエストで打ち切る。
  1. 相談開始（最初の質問）
  2. 出来事の対話（回答）
  3. 感情入力の後
  4. 本音・背景・望み（次の質問）
  5. 本音・背景・望み（整理完了）

3〜5は、AIの呼び出し回数を抑えるため、前の段階の内容を架空のデータで補ってから実行する。

実行方法（リポジトリのルート、PowerShell）：
  docker compose run --rm -e OPENROUTER_API_KEY backend python -m scripts.check_ai_consultation

停止条件：
  - AIの呼び出しに失敗（HTTPエラー・タイムアウト）した時点で中断する
  - AIの出力がSchemaを満たさない場合は同じ場面を1回だけ再実行し、再び満たさなければ中断する
  - 合計5リクエストに達したら中断する

出力には架空の相談文とAIの出力を表示する。実際の相談内容は使わない。
"""

import asyncio
import json
from dataclasses import dataclass, field
from uuid import uuid4

from app.features.consultations import prompts
from app.features.consultations.ai_schemas import AIOutputInvalid
from app.features.consultations.schemas import (
    ConsultationStatus,
    EmotionInput,
    EventDetailsDraft,
    ThemeCategory,
)
from app.features.consultations.service import ConsultationService
from app.features.consultations.store import ConsultationStore
from app.integrations.openrouter.client import AIClientError, get_ai_client

MAX_REQUESTS = 5

# Issue #4の通常例1（架空）
FICTIONAL_DETAIL = (
    "話しかけても「うん」「そうだね」しか返ってこない日が続いている。"
    "今日も夕食後に「話したいことがある」と伝えたら「あとでね」と言われたまま、"
    "そのままスマホを見て寝てしまった。"
)


class RequestLimitReached(Exception):
    pass


@dataclass
class RecordingClient:
    """呼び出し回数を数え、model・provider・usageを記録するクライアント"""

    inner: object
    records: list[dict] = field(default_factory=list)

    async def complete_json(self, messages, schema, schema_name):
        if len(self.records) >= MAX_REQUESTS:
            raise RequestLimitReached
        record = {"no": len(self.records) + 1, "schema": schema_name}
        self.records.append(record)
        try:
            result = await self.inner.complete_json(messages, schema, schema_name)
        except AIClientError:
            record["result"] = "AI呼び出し失敗"
            raise
        record.update(
            model=result.model,
            provider=result.provider,
            usage=result.usage,
            elapsed_seconds=result.elapsed_seconds,
            output=result.content,
        )
        return result


async def run_step(name, client, call):
    """1つの場面を実行する。Schema不正の場合は1回だけ再実行する"""
    for attempt in (1, 2):
        try:
            value = await call()
            client.records[-1]["result"] = "Schema検証OK"
            print(f"[OK] {name}")
            state = value[0] if isinstance(value, tuple) else value
            if state.status is ConsultationStatus.SAFETY_GUIDANCE:
                # 架空の通常例で安全案内になった場合は、誤検知として記録して中断する
                client.records[-1]["result"] = "Schema検証OK（kind=safety：通常例での誤検知）"
                raise SystemExit(f"中断：{name}で安全案内になったため（I-03B・I-07へ引き継ぐ）")
            return value
        except AIOutputInvalid:
            client.records[-1]["result"] = "Schema不正"
            print(f"[NG] {name}: Schema不正（{attempt}回目）")
    raise SystemExit(f"中断：{name}でSchema不正が続いたため（I-07へ引き継ぐ）")


async def main() -> None:
    client = RecordingClient(get_ai_client())
    store = ConsultationStore()
    service = ConsultationService(store, client)
    user_id = uuid4()

    try:
        # 1. 相談開始
        state = await run_step(
            "1. 相談開始",
            client,
            lambda: service.start(user_id, ThemeCategory.COMMUNICATION, FICTIONAL_DETAIL),
        )
        cid = state.consultation_id

        # 2. 出来事の対話（回答）
        state = await run_step(
            "2. 出来事の対話",
            client,
            lambda: service.event_dialogue(
                user_id, cid, "answer", "3日くらい、ほとんど会話がない状態です。"
            ),
        )

        # 3. 感情入力の後（出来事の要約までを架空のデータで補う）
        state.event_details = EventDetailsDraft(
            what_happened="話しかけても短い返事しかなく、話したいと伝えても後回しにされた",
            what_bothered_me="話を聞いてもらえないまま寝てしまったこと",
        )
        state.messages.append(prompts.assistant_turn("（出来事の要約は確認済み）"))
        state.status = ConsultationStatus.EMOTION_SELECTION
        await run_step(
            "3. 感情入力の後",
            client,
            lambda: service.submit_emotion(
                user_id,
                cid,
                EmotionInput(category="lonely", detail="ちゃんと向き合ってもらえていない気がする"),
            ),
        )

        # 4. 本音・背景・望み（次の質問）
        await run_step(
            "4. 本音（次の質問）",
            client,
            lambda: service.guided_dialogue(
                user_id, cid, "本当は少しの時間でいいから話を聞いてほしかった", skipped=False
            ),
        )

        # 5. 本音・背景・望み（整理完了）。背景の質問と回答を架空のデータで補う
        state.messages.extend(
            [
                prompts.assistant_turn("そう感じる背景には、どんなことがありそうですか？"),
                prompts.user_turn(prompts.SKIPPED_ANSWER_TEXT),
                prompts.assistant_turn("相手にどうしてほしいと思っていますか？"),
            ]
        )
        state.guided_turn_count = 2
        state = await run_step(
            "5. 望み（整理完了）",
            client,
            lambda: service.guided_dialogue(
                user_id, cid, "週に一度でいいので、落ち着いて話す時間がほしい", skipped=False
            ),
        )
        print(f"最終状態：{state.status.value}")
    except AIClientError:
        print("中断：AIの呼び出しに失敗したため（I-07へ引き継ぐ）")
    except RequestLimitReached:
        print(f"中断：最大{MAX_REQUESTS}リクエストに達したため")
    finally:
        print("\n===== 記録（Issueへ転記する） =====")
        print(json.dumps(client.records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
