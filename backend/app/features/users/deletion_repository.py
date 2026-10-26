"""Short, owner-scoped transactions; external calls never hold row locks."""

from sqlalchemy import delete, select

from app.core.exceptions import AuthenticationRequiredError
from app.features.memos.models import ApprovedMemo
from app.features.payments.models import PaymentRow, UserEntitlementRow
from app.features.users.models import User


class DeletionBlocked(Exception):
    pass


class DeletionRepository:
    def __init__(self, factory):
        self.factory = factory

    async def begin(self, uid: str, *, recovery: bool = False):
        async with self.factory() as session, session.begin():
            user = (
                await session.execute(
                    select(User).where(User.firebase_uid == uid).with_for_update()
                )
            ).scalar_one_or_none()
            if user is None:
                raise AuthenticationRequiredError
            if recovery and user.status != "deleting":
                raise DeletionBlocked
            if user.status not in ("active", "deleting"):
                raise RuntimeError("Unexpected account status")
            creating = (
                await session.execute(
                    select(PaymentRow.id).where(
                        PaymentRow.user_id == user.id, PaymentRow.status == "creating"
                    )
                )
            ).first()
            if creating:
                raise DeletionBlocked
            user.status = "deleting"
            user_id = user.id
        return user_id

    async def delete_memos(self, user_id):
        async with self.factory() as session, session.begin():
            await self._locked_user(session, user_id)
            await session.execute(delete(ApprovedMemo).where(ApprovedMemo.user_id == user_id))

    async def finish(self, user_id):
        async with self.factory() as session, session.begin():
            await self._locked_user(session, user_id)
            unfinished = (
                await session.execute(
                    select(PaymentRow.id).where(
                        PaymentRow.user_id == user_id,
                        PaymentRow.status.in_(("creating", "pending")),
                    )
                )
            ).first()
            if unfinished:
                raise DeletionBlocked
            await session.execute(
                delete(UserEntitlementRow).where(UserEntitlementRow.user_id == user_id)
            )
            await session.execute(delete(PaymentRow).where(PaymentRow.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))

    async def recovery_uid(self, user_id):
        async with self.factory() as session:
            user = await session.get(User, user_id)
            if user is None or user.status != "deleting":
                raise DeletionBlocked
            return user.firebase_uid

    @staticmethod
    async def _locked_user(session, user_id):
        user = (
            await session.execute(select(User).where(User.id == user_id).with_for_update())
        ).scalar_one_or_none()
        if user is None or user.status != "deleting":
            raise DeletionBlocked
        return user
