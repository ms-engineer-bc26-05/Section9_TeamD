"""UID-scoped coordination for the single-process API deployment."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


class DeletionInProgress(Exception):
    pass


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    references: int = 0
    deleting: bool = False


_entries: dict[str, _Entry] = {}


@asynccontextmanager
async def lifecycle_lock(uid: str, *, deletion: bool = False):
    entry = _entries.setdefault(uid, _Entry())
    if deletion and entry.deleting:
        raise DeletionInProgress
    entry.references += 1
    if deletion:
        entry.deleting = True
    try:
        async with entry.lock:
            yield
    finally:
        if deletion:
            entry.deleting = False
        entry.references -= 1
        if not entry.references:
            del _entries[uid]
