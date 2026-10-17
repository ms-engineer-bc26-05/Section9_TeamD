"""Explicit, one-account recovery. Run only with the API stopped."""

import argparse
import asyncio
import os
from getpass import getpass
from uuid import UUID

from app.core.database import dispose_engine
from app.features.usage.limiter import close_usage_limiter
from app.features.users.deletion_service import get_deletion_service


async def recover(user_id):
    try:
        await get_deletion_service().recover(user_id)
    finally:
        await close_usage_limiter()
        await dispose_engine()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--api-stopped", action="store_true")
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    if not args.approved or not args.api_stopped:
        parser.error("Explicit approval and stopped API are required")
    if args.project != os.environ.get("FIREBASE_PROJECT_ID"):
        parser.error("Project mismatch")
    if input("Type RECOVER to process one approved account: ") != "RECOVER":
        return 1
    try:
        user_id = UUID(getpass("Internal test user UUID (hidden): "))
        asyncio.run(recover(user_id))
    except (Exception, KeyboardInterrupt):
        print("STOP: recovery incomplete; do not assume account deletion succeeded.")
        return 1
    print("PASS: account recovery completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
