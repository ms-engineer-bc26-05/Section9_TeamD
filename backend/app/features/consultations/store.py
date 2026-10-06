"""相談の一時状態を保持するストアと、相談ID単位のロック。

- 一時状態はAPIプロセスのメモリ上の dict で保持する（1ワーカー前提）
- 取得時に user_id を照合し、本人のものでなければ存在しない場合と同じ扱いにする
- 同じ相談への更新は相談IDごとの asyncio.Lock で直列化する
- ロック中の相談へのリクエストは待たずに ConsultationBusy とする（二重送信とみなす）
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.features.consultations.exceptions import ConsultationBusy, ConsultationNotFound
from app.features.consultations.state import ConsultationState

__all__ = [
    "ConsultationBusy",
    "ConsultationNotFound",
    "ConsultationStore",
    "get_consultation_store",
]


class ConsultationStore:
    def __init__(self) -> None:
        self._states: dict[UUID, ConsultationState] = {}

    def add(self, state: ConsultationState) -> None:
        """一時状態を登録する。AI呼び出しが成功した後に呼び、失敗時に状態を残さない"""
        self._states[state.consultation_id] = state

    def get(self, user_id: UUID, consultation_id: UUID) -> ConsultationState:
        state = self._states.get(consultation_id)
        if state is None or state.user_id != user_id:
            # 他人の相談と存在しない相談を区別しない
            raise ConsultationNotFound
        return state

    def discard(self, user_id: UUID, consultation_id: UUID) -> None:
        """一時状態を破棄する。存在しない・本人のものでない場合も何もせず終わる（冪等）"""
        state = self._states.get(consultation_id)
        if state is not None and state.user_id == user_id:
            del self._states[consultation_id]

    def exists(self, user_id: UUID, consultation_id: UUID) -> bool:
        state = self._states.get(consultation_id)
        return state is not None and state.user_id == user_id

    @asynccontextmanager
    async def locked(
        self, user_id: UUID, consultation_id: UUID
    ) -> AsyncIterator[ConsultationState]:
        """相談のロックを取得して一時状態を返す。

        ロック中であれば待たずに ConsultationBusy を送出する。
        locked() の確認からロック取得までの間に await を挟まないため、
        1つのイベントループ内では確認と取得の間に別のリクエストが割り込まない。

        ロックの中で例外が起きた場合は、ロック取得時の状態へ戻してから解放する。
        状態を書き換えた後に想定外のエラー（500）が起きても、回数や段階が進んだまま
        残らないようにするため（テスト設計書 ST-19）。
        """
        state = self.get(user_id, consultation_id)
        if state.lock.locked():
            raise ConsultationBusy
        async with state.lock:
            before = state.snapshot()
            try:
                yield state
            except BaseException:
                state.restore(before)
                raise


# APIプロセスで共有するストア。テストでは get_consultation_store を差し替える
_store = ConsultationStore()


def get_consultation_store() -> ConsultationStore:
    return _store
