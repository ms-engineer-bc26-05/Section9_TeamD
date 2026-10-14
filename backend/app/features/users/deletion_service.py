"""Restartable account deletion; success means every required step committed."""

from asyncio import to_thread

from app.core.database import get_session_factory
from app.core.database_errors import is_database_connection_error
from app.core.exceptions import (
    AuthenticationRequiredError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)
from app.features.consultations.public import discard_user_consultations
from app.features.payments.public import settle_unfinished_payments
from app.features.usage.limiter import get_usage_limiter
from app.features.users.deletion_repository import DeletionBlocked, DeletionRepository
from app.features.users.lifecycle_lock import lifecycle_lock
from app.integrations.firebase import client, deletion


class DeletionService:
    def __init__(self, repository, discard, settle, clear_usage, remove_firebase, absent, verify):
        self.repository = repository
        self.discard = discard
        self.settle = settle
        self.clear_usage = clear_usage
        self.remove_firebase = remove_firebase
        self.absent = absent
        self.verify = verify

    async def delete(self, token):
        uid = await self.verify(token)
        async with lifecycle_lock(uid, deletion=True):
            # Recheck after waiting for registration or other lifecycle work.
            if await self.verify(token) != uid:
                raise AuthenticationRequiredError
            await self._run(uid)

    async def recover(self, user_id):
        uid = await self.repository.recovery_uid(user_id)
        async with lifecycle_lock(uid, deletion=True):
            if not await self.absent(uid):
                raise DeletionBlocked
            await self._run(uid, recovery=True)

    async def _run(self, uid, *, recovery=False):
        user_id = await self.repository.begin(uid, recovery=recovery)
        await self.repository.delete_memos(user_id)
        await self.discard(user_id)
        await self.settle(user_id)
        await self.clear_usage(user_id)
        await self.remove_firebase(uid)
        await self.clear_usage(user_id)
        await self.repository.finish(user_id)


async def verify_deletion_token(token):
    try:
        return await to_thread(client.verify_token, token, check_revoked=True)
    except client.InvalidTokenError:
        raise AuthenticationRequiredError from None
    except client.AuthServiceUnavailableError:
        raise AuthServiceUnavailableError from None


async def remove_firebase(uid):
    try:
        await to_thread(deletion.delete_user, uid)
    except client.AuthServiceUnavailableError:
        raise AuthServiceUnavailableError from None


async def firebase_absent(uid):
    try:
        return await to_thread(deletion.user_is_absent, uid)
    except client.AuthServiceUnavailableError:
        raise AuthServiceUnavailableError from None


def get_deletion_service():
    return DeletionService(
        DeletionRepository(get_session_factory()),
        discard_user_consultations,
        settle_unfinished_payments,
        get_usage_limiter().delete_user_usage,
        remove_firebase,
        firebase_absent,
        verify_deletion_token,
    )


async def delete_account(token, service):
    try:
        await service.delete(token)
    except Exception as error:
        if is_database_connection_error(error):
            raise DatabaseUnavailableError from None
        raise
