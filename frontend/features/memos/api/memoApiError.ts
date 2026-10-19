export type SharedApiErrorKind =
  | "bad_request"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "validation"
  | "ai_failed"
  | "aborted"
  | "network"
  | "server";

interface SharedApiErrorLike {
  kind: SharedApiErrorKind;
  code?: string;
}

export type MemoErrorCode =
  | "UNAUTHORIZED"
  | "ACCOUNT_DELETING"
  | "AUTH_UNAVAILABLE"
  | "DB_UNAVAILABLE"
  | "MEMO_NOT_FOUND"
  | "VALIDATION_ERROR"
  | "NETWORK_ERROR"
  | "SERVER_ERROR"
  | "UNKNOWN_ERROR";

export type MemoApiFailure =
  | { type: "aborted" }
  | { type: "failed"; code: MemoErrorCode };

const FIXED_ERROR_CODES = new Set<MemoErrorCode>([
  "UNAUTHORIZED",
  "ACCOUNT_DELETING",
  "AUTH_UNAVAILABLE",
  "DB_UNAVAILABLE",
  "MEMO_NOT_FOUND",
  "VALIDATION_ERROR",
]);

function isSharedApiErrorLike(error: unknown): error is SharedApiErrorLike {
  if (typeof error !== "object" || error === null) return false;
  const kind = Reflect.get(error, "kind");
  return (
    kind === "bad_request" ||
    kind === "unauthenticated" ||
    kind === "forbidden" ||
    kind === "not_found" ||
    kind === "conflict" ||
    kind === "validation" ||
    kind === "ai_failed" ||
    kind === "aborted" ||
    kind === "network" ||
    kind === "server"
  );
}

function fixedErrorCode(code: unknown): MemoErrorCode | null {
  return typeof code === "string" &&
    FIXED_ERROR_CODES.has(code as MemoErrorCode)
    ? (code as MemoErrorCode)
    : null;
}

/** APIのmessageやレスポンス本文を参照せず、画面用の固定コードへ変換する。 */
export function toMemoApiFailure(error: unknown): MemoApiFailure {
  if (!isSharedApiErrorLike(error)) {
    return { type: "failed", code: "UNKNOWN_ERROR" };
  }
  if (error.kind === "aborted") return { type: "aborted" };

  const code = fixedErrorCode(error.code);
  if (code !== null) return { type: "failed", code };

  switch (error.kind) {
    case "unauthenticated":
      return { type: "failed", code: "UNAUTHORIZED" };
    case "not_found":
      return { type: "failed", code: "MEMO_NOT_FOUND" };
    case "validation":
      return { type: "failed", code: "VALIDATION_ERROR" };
    case "network":
      return { type: "failed", code: "NETWORK_ERROR" };
    case "server":
      return { type: "failed", code: "SERVER_ERROR" };
    case "bad_request":
    case "forbidden":
    case "conflict":
    case "ai_failed":
      return { type: "failed", code: "UNKNOWN_ERROR" };
  }
}
