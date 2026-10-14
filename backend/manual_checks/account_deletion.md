# Issue #60: account deletion and recovery

## Implementation plan for Issue discussion

The proposed UID-scoped lock is shared by initial registration and deletion.
It covers Firebase revalidation and all deletion steps, but does not hold a DB
transaction during external calls. Registration revalidates after acquiring the
lock, so a registration delayed until after deletion cannot recreate the user.
Normal API authentication is unchanged. Initial registration now verifies twice;
external verification budgets must include these calls.

This plan still needs to be posted to Issue #60 before formal review. No external
verification or Firebase permission changes have been performed by this work.

## Order and public behavior

1. Authenticate the caller, acquire the UID lock, and revalidate.
2. Lock the users row. A creating payment blocks with 409 without changing active.
   Otherwise commit deleting. A previous deleting state is resumable.
3. Delete owned memos and commit, then discard owned consultations.
4. Settle payments using payments/public.py. A blocked settlement returns 409
   and leaves deleting. Connection failures return 503; other failures return 500.
5. Delete Redis usage, then delete the Firebase user (absence is success).
6. Delete Redis usage again BEFORE removing the recovery anchor in users.
7. Lock the user, recheck there are no creating/pending payments, then delete
   entitlements, payments, and users in one transaction. Return bodyless 204 only
   after commit. Never infer successful deletion from 401.

Concurrent DELETE returns ACCOUNT_DELETION_IN_PROGRESS only while another DELETE
is executing. A failed request releases the lock and can be retried. If Firebase
is already removed, the API can return 401 and manual recovery is required.

## Recovery runbook

Owner: Moe (#60); reviewer: Jima. This is NOT a bulk deletion tool.

- Obtain human approval for the exact environment and one synthetic account.
- Stop ALL API processes and other account-writing jobs before recovery. The
  process-local lock does not coordinate a separate command or multiple replicas.
- Verify target DB, Redis, Firebase project, and the application's Stripe sandbox
  configuration against the approved environment. Do not display credentials.
- Use separately approved credentials with Firebase user read/delete permissions.
  Never reuse or recreate the removed Issue #47 key without new approval.
- Plan and approve external request counts, deadline, cost ceiling, and stop
  conditions in the Issue before executing. This command does not enforce a
  request/cost budget and is NOT approved for live execution by unit tests.
- Run `python -m manual_checks.recover_account --approved --api-stopped
  --project <approved-project-id>` with the project's configured runtime.
  Enter only the approved internal UUID in the hidden prompt.
- It requires a deleting DB row AND a confirmed absent Firebase user. A network
  or permissions error is never treated as absence. It repeats the mandatory
  cleanup, including payment settlement and final Redis deletion.
- On STOP, retain deleting, investigate without printing data, and seek approval
  before another run. On PASS, restart the API after confirming the outcome.

## Constraints and handoff

- Single API process/event loop only (current run.py workers=1). No multi-instance
  guarantee. Review this design before changing deployment topology.
- Redis keys recreated by a concurrent usage request can remain if its own
  cleanup fails. They contain internal user ID in the key, count and period only,
  and expire within USAGE_PERIOD_SECONDS from recreation (default 30 days).
  Mandatory deletion failures never produce 204.
- Router registration in main.py remains #53 responsibility; the users router
  already has /users prefix. Frontend handling and resume flow belong to #61.
- Shared API/DB/test design documents are not edited until ownership/order is
  agreed. New Redis error code USAGE_UNAVAILABLE is a proposal for review.
- Firebase live calls, Stripe live calls, frontend integration, operational
  recovery and production deployment are unverified. Recovery flags are operator
  acknowledgements, not proof that the API is stopped.

## Local verification (2026-10-14)

- `python -m pytest -q -p no:cacheprovider`: 830 passed, 21 skipped,
  14 deprecation warnings. RUN_DB_TESTS=1 used a disposable PostgreSQL 17
  container on an internal-only network, with no published ports.
- The 21 skipped tests require Redis. Firebase and Stripe were mocked; no
  credentials or real account data were used.
- Deletion DB cases cover owner isolation, creating/pending barriers, rollback,
  recovery, and an HTTP-to-DB deletion with external dependencies replaced.
- Concurrency tests cover delayed registration, overlapping DELETE, cancellation
  and lock release. Failure tests confirm that required cleanup cannot be skipped.
- Ruff 0.16.10 with the fetched PR #81 configuration: lint and format checks pass
  for the 12 changed Python files. No project dependencies were changed.
- Container/frontend builds and live services were not tested. The recovery
  service is tested, but the operator CLI has not been exercised against services.
