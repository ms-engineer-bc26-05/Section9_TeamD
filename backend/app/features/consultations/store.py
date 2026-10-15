"""相談の一時状態を保持するストアと、相談ID単位のロック。

- 一時状態はAPIプロセスのメモリ上の dict で保持する（1ワーカー前提）
- 取得時に user_id を照合し、本人のものでなければ存在しない場合と同じ扱いにする
- 同じ相談への更新は相談IDごとの asyncio.Lock で直列化する
- ロック中の相談へのリクエストは待たずに ConsultationBusy とする（二重送信とみなす）

保持時間（TTL。I-03Bで決定）：
- 最後に更新が成功してから CONSULTATION_TTL が経過した相談は、存在しない相談と同じ扱い（404）
- GETでは延長しない（更新が成功したときの touch() だけが時刻を進める）
- 常駐の見回り処理は作らず、その相談へのアクセス時と、新しい相談の登録時に消す
- ロック中（AIの応答待ちなど）の相談は、処理中のため期限切れとして扱わない

破棄（I-03Bで決定）：
- 1ユーザーが保持できる相談は1件まで。新しい相談を登録したら、その人の既存の相談を破棄する
- 破棄はロックを取らない（AIの応答待ち中でもすぐに破棄できる）。応答待ちだった処理は、
  応答後に相談が残っているかを確認し直し、残っていなければ書き込まずに404とする
- 破棄は、その相談の登録を外すだけで、相談の中身には触れない。ロック中の例外で中身を
  控えへ戻しても（ST-19）、登録には戻らないため、破棄した相談は復活しない
- 退会処理の破棄（discard_withdrawn_user）では、そのユーザーを記録し、以後の相談開始を拒否する。
  破棄の後に予約を取られて相談が登録されるのを防ぐため（#96）。
  新しい相談の登録時の破棄（discard_user）では記録しない

相談の開始（I-03Bで決定）：
- 開始はAIの応答後に登録するため、ユーザー単位で「開始処理中」の予約を持つ
- 開始処理中に同じユーザーから2つ目の開始が届いたら ConsultationBusy（409。二重送信の扱い）
- 開始処理中にユーザー単位の破棄（退会）が呼ばれたら予約を取り消し、AIの応答後も登録しない
- 退会処理で破棄したユーザーからの開始は、予約をとらずに ConsultationNotFound（404）とする（#96）
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from uuid import UUID

from app.features.consultations import state as state_module
from app.features.consultations.exceptions import ConsultationBusy, ConsultationNotFound
from app.features.consultations.state import ConsultationState

# 一時状態の保持時間（最後に更新が成功してから）
CONSULTATION_TTL = timedelta(minutes=30)

__all__ = [
    "CONSULTATION_TTL",
    "ConsultationBusy",
    "ConsultationNotFound",
    "ConsultationStore",
    "get_consultation_store",
]


class StartReservation:
    """相談の開始処理中であることを示す予約。commit() で相談を登録する"""

    def __init__(self, store: "ConsultationStore", user_id: UUID) -> None:
        self._store = store
        self._user_id = user_id

    @property
    def active(self) -> bool:
        """予約が取り消されていないか（開始処理中にユーザー単位の破棄が呼ばれていないか）"""
        return self._store._starting.get(self._user_id) is self

    def commit(self, state: ConsultationState) -> None:
        """新しい相談を登録し、同じユーザーの既存の相談を破棄する。

        await を挟まずに確認と登録を行う。予約が取り消されていた場合は登録せず、
        ConsultationNotFound（404）とする。
        """
        if not self.active:
            raise ConsultationNotFound
        self._store.replace_user_consultations(state)


class ConsultationStore:
    def __init__(self) -> None:
        self._states: dict[UUID, ConsultationState] = {}
        # 相談の開始処理中のユーザーと、その予約
        self._starting: dict[UUID, StartReservation] = {}
        # 退会処理で破棄したユーザー。以後の相談開始を受け付けない
        # （usersは物理削除され、UUIDは再利用されないため、記録は消さない）
        self._withdrawn_users: set[UUID] = set()

    @contextmanager
    def reserve_start(self, user_id: UUID) -> Iterator[StartReservation]:
        """相談の開始処理中の予約をとる。

        - 退会処理で破棄したユーザーなら ConsultationNotFound
          （開始処理中に予約を取り消された場合と同じ扱い）
        - 同じユーザーが開始処理中なら ConsultationBusy
        """
        if user_id in self._withdrawn_users:
            raise ConsultationNotFound
        if user_id in self._starting:
            raise ConsultationBusy
        reservation = StartReservation(self, user_id)
        self._starting[user_id] = reservation
        try:
            yield reservation
        finally:
            # 取り消し後に別の予約がとられている場合は、その予約を消さない
            if self._starting.get(user_id) is reservation:
                del self._starting[user_id]

    def add(self, state: ConsultationState) -> None:
        """一時状態を登録する。AI呼び出しが成功した後に呼び、失敗時に状態を残さない。

        登録のついでに、期限切れの一時状態をまとめて消す。
        """
        self.purge_expired()
        self._states[state.consultation_id] = state

    def replace_user_consultations(self, state: ConsultationState) -> None:
        """新しい相談を登録し、同じユーザーの既存の相談を破棄する（1ユーザー1件）。

        フロントが相談IDを失っても、新しい相談を始めれば古い一時状態は残らない。
        """
        self.discard_user(state.user_id)
        self.add(state)

    def get(self, user_id: UUID, consultation_id: UUID) -> ConsultationState:
        state = self._find(user_id, consultation_id)
        if state is None:
            # 他人の相談・存在しない相談・期限切れの相談を区別しない
            raise ConsultationNotFound
        return state

    def purge_expired(self) -> None:
        """期限切れの一時状態をすべて消す"""
        now = state_module.utc_now()
        for consultation_id, state in list(self._states.items()):
            if self._is_expired(state, now):
                del self._states[consultation_id]

    def _find(self, user_id: UUID, consultation_id: UUID) -> ConsultationState | None:
        """本人の一時状態を返す。期限切れの場合は消してから None を返す"""
        state = self._states.get(consultation_id)
        if state is None or state.user_id != user_id:
            return None
        if self._is_expired(state, state_module.utc_now()):
            del self._states[consultation_id]
            return None
        return state

    @staticmethod
    def _is_expired(state: ConsultationState, now) -> bool:
        if state.lock.locked():
            return False
        return now - state.updated_at >= CONSULTATION_TTL

    def discard(self, user_id: UUID, consultation_id: UUID) -> None:
        """一時状態を破棄する。存在しない・本人のものでない場合も何もせず終わる（冪等）"""
        state = self._states.get(consultation_id)
        if state is not None and state.user_id == user_id:
            del self._states[consultation_id]

    def discard_user(self, user_id: UUID) -> None:
        """そのユーザーの一時状態をすべて破棄し、開始処理中の予約も取り消す。

        新しい相談の登録時（replace_user_consultations）にも呼ぶため、ユーザーの記録はしない。
        対象がない・すでに破棄済みの場合も、正常に終了する（冪等）。
        """
        self._starting.pop(user_id, None)
        for consultation_id, state in list(self._states.items()):
            if state.user_id == user_id:
                del self._states[consultation_id]

    def discard_withdrawn_user(self, user_id: UUID) -> None:
        """退会処理（F-06）用。そのユーザーを記録したうえで、一時状態と開始処理中の予約を破棄する。

        記録したユーザーからの相談開始は、以後 reserve_start で拒否する（#96）。
        新しい相談の登録時の破棄（replace_user_consultations）では呼ばない。
        対象がない・すでに破棄済みの場合も、正常に終了する（冪等）。
        """
        self._withdrawn_users.add(user_id)
        self.discard_user(user_id)

    def exists(self, user_id: UUID, consultation_id: UUID) -> bool:
        return self._find(user_id, consultation_id) is not None

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
