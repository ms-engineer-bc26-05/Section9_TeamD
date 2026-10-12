/**
 * 認証済みAPI呼び出し(I-02 / #48)
 *
 * - path は "/api/v1" より後ろから書く(例: "/users/me")。接頭辞は内部で付与する
 * - 成功時: レスポンスJSONを T として返す(DELETE・204は戻り値なし)
 * - 失敗時: ApiError を投げる。呼び出し側は error.kind / error.code で分岐する
 * - IDトークンの付与・更新は内部で行う(呼び出し側は意識不要)
 * - 401のときだけ、トークンを強制更新して1回だけ再試行する(500・503では何もしない)
 * - 生のレスポンス本文は message・ログに入れない
 */

import { getFirebaseAuth } from "@/lib/firebase";

export type ApiErrorKind =
  | "bad_request" // 400
  | "unauthenticated" // 401・トークン無効(再ログインが必要なFirebaseエラー)
  | "forbidden" // 403(codeで分岐する。一律に退会扱いしない)
  | "not_found" // 404(他人のリソースも含む)
  | "conflict" // 409(相談状態と操作の矛盾)
  | "validation" // 422
  | "ai_failed" // 502(AI呼び出し失敗・AI出力不正)
  | "network" // 通信失敗
  | "aborted" // AbortSignal による意図的なキャンセル
  | "server"; // 500・503・その他(トークン取得の一時的な制限・想定外のエラーも含む)

export type ApiErrorDetail = { field: string; reason: string };

export type RequestOptions = { signal?: AbortSignal };

const FIXED_MESSAGES: Record<ApiErrorKind, string> = {
  bad_request: "リクエストが正しくありません。",
  unauthenticated: "ログインしてください。",
  forbidden: "この操作は利用できません。",
  not_found: "対象が見つかりません。",
  conflict: "現在の状態ではこの操作を行えません。",
  validation: "入力内容を確認してください。",
  ai_failed: "AIの応答を取得できませんでした。",
  network: "通信できませんでした。接続を確認してもう一度お試しください。",
  aborted: "処理を中断しました。",
  server: "サーバーで問題が発生しました。時間をおいてもう一度お試しください。",
};

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly code?: string; // error.code。例: "ACCOUNT_DELETING" / "AI_OUTPUT_INVALID"
  readonly details?: ApiErrorDetail[]; // 422のときのみ

  constructor(
    kind: ApiErrorKind,
    options: {
      status?: number;
      code?: string;
      message?: string;
      details?: ApiErrorDetail[];
    } = {},
  ) {
    // 相談内容・トークン・AI出力・生の本文は入れない
    super(options.message ?? FIXED_MESSAGES[kind]);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
  }
}

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1`;

function kindFromStatus(status: number): ApiErrorKind {
  if (status === 400) return "bad_request";
  if (status === 401) return "unauthenticated";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "validation";
  if (status === 502) return "ai_failed";
  return "server";
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

// 設計書3.5の {"error": {code, message, details}} 形のときだけ code / details を読む。
// 旧形式 {"detail": ...} や想定外の本文は読まず、固定メッセージに任せる
async function readErrorBody(
  response: Response,
): Promise<{ code?: string; details?: ApiErrorDetail[] }> {
  try {
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null || !("error" in body)) {
      return {};
    }
    const error = (body as { error: unknown }).error;
    if (typeof error !== "object" || error === null) return {};

    const { code, details } = error as { code?: unknown; details?: unknown };
    return {
      code: typeof code === "string" ? code : undefined,
      details: Array.isArray(details)
        ? details.filter(
            (d): d is ApiErrorDetail =>
              typeof d === "object" &&
              d !== null &&
              typeof (d as ApiErrorDetail).field === "string" &&
              typeof (d as ApiErrorDetail).reason === "string",
          )
        : undefined,
    };
  } catch {
    return {};
  }
}

function firebaseErrorCode(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null) return undefined;
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" ? code : undefined;
}

// 再ログインが必要と分かっているコードだけを「認証無効」として扱う
const REAUTH_REQUIRED_CODES = new Set([
  "auth/invalid-user-token",
  "auth/user-token-expired",
  "auth/user-disabled",
  "auth/user-not-found",
  "auth/requires-recent-login",
]);

async function getToken(forceRefresh: boolean): Promise<string> {
  const user = getFirebaseAuth().currentUser;
  if (!user) throw new ApiError("unauthenticated");
  try {
    return await user.getIdToken(forceRefresh);
  } catch (error) {
    const code = firebaseErrorCode(error);
    // 通信失敗・一時的な制限・想定外のエラーは、ログアウトにつなげず再試行できるようにする
    if (code === "auth/network-request-failed") throw new ApiError("network");
    if (code !== undefined && REAUTH_REQUIRED_CODES.has(code)) {
      throw new ApiError("unauthenticated");
    }
    throw new ApiError("server");
  }
}

async function send(
  method: string,
  path: string,
  body: unknown,
  options: RequestOptions | undefined,
  forceRefresh: boolean,
): Promise<Response> {
  const token = await getToken(forceRefresh);
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  try {
    return await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: options?.signal,
    });
  } catch (error) {
    throw new ApiError(isAbortError(error) ? "aborted" : "network");
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  let response = await send(method, path, body, options, false);

  // 401のときだけ、トークンを強制更新して1回だけ再試行する
  if (response.status === 401) {
    response = await send(method, path, body, options, true);
  }

  if (!response.ok) {
    const { code, details } = await readErrorBody(response);
    throw new ApiError(kindFromStatus(response.status), {
      status: response.status,
      code,
      details,
    });
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const apiClient = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>("GET", path, undefined, options);
  },
  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>("POST", path, body, options);
  },
  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>("PATCH", path, body, options);
  },
  async delete(path: string, options?: RequestOptions): Promise<void> {
    await request<void>("DELETE", path, undefined, options);
  },
};