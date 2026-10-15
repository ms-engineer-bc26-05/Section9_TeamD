import type { ConsultationErrorCode } from "../model/state";

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

export interface SharedApiErrorLike {
  kind: SharedApiErrorKind;
  status?: number;
  code?: string;
}

export type ConsultationApiFailure =
  | { type: "aborted" }
  | { type: "failed"; code: ConsultationErrorCode };

const FIXED_ERROR_CODES = new Set<ConsultationErrorCode>([
  "UNAUTHORIZED",
  "ACCOUNT_DELETING",
  "AUTH_UNAVAILABLE",
  "DB_UNAVAILABLE",
  "USAGE_LIMIT_EXCEEDED",
  "MEMO_LIMIT_EXCEEDED",
  "CONSULTATION_NOT_FOUND",
  "CONSULTATION_BUSY",
  "CONSULTATION_STATE_CONFLICT",
  "RESULT_NOT_READY",
  "VALIDATION_ERROR",
  "AI_UNAVAILABLE",
  "AI_OUTPUT_INVALID",
  "NETWORK_ERROR",
  "SERVER_ERROR",
  "UNKNOWN_ERROR",
]);

function isSharedApiErrorLike(error: unknown): error is SharedApiErrorLike {
  if (typeof error !== "object" || error === null) {
    return false;
  }

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

function fixedErrorCode(code: unknown): ConsultationErrorCode | null {
  return typeof code === "string" &&
    FIXED_ERROR_CODES.has(code as ConsultationErrorCode)
    ? (code as ConsultationErrorCode)
    : null;
}

/**
 * 共通apiClientの失敗を、Issue #51が扱う固定コードへ変換する。
 * error.message・レスポンス本文・入力内容は参照しない。
 */
export function toConsultationApiFailure(
  error: unknown,
): ConsultationApiFailure {
  if (!isSharedApiErrorLike(error)) {
    return { type: "failed", code: "UNKNOWN_ERROR" };
  }

  if (error.kind === "aborted") {
    return { type: "aborted" };
  }

  const code = fixedErrorCode(error.code);
  if (code !== null) {
    return { type: "failed", code };
  }

  switch (error.kind) {
    case "unauthenticated":
      return { type: "failed", code: "UNAUTHORIZED" };
    case "not_found":
      return { type: "failed", code: "CONSULTATION_NOT_FOUND" };
    case "conflict":
      return { type: "failed", code: "CONSULTATION_STATE_CONFLICT" };
    case "validation":
      return { type: "failed", code: "VALIDATION_ERROR" };
    case "ai_failed":
      return { type: "failed", code: "AI_UNAVAILABLE" };
    case "network":
      return { type: "failed", code: "NETWORK_ERROR" };
    case "server":
      return { type: "failed", code: "SERVER_ERROR" };
    case "bad_request":
    case "forbidden":
      return { type: "failed", code: "UNKNOWN_ERROR" };
  }
}
