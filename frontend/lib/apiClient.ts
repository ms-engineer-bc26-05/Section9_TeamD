/**
 * 認証済みAPI呼び出し(I-02 / #48)
 * 型・シグネチャの先行共有版。実装は10/6頃の予定。
 *
 * - path は "/api/v1" より後ろから書く(例: "/users/me")。接頭辞は内部で付与する
 * - 成功時: レスポンスJSONを T として返す(DELETEは戻り値なし)
 * - 失敗時: ApiError を投げる。呼び出し側は error.kind で分岐する
 * - IDトークンの付与・更新は内部で行う(呼び出し側は意識不要)
 */

export type ApiErrorKind =
  | "bad_request" // 400
  | "unauthenticated" // 401・トークン取得失敗
  | "forbidden" // 403(利用上限・退会処理中。区別方法は未定)
  | "not_found" // 404(他人のリソースも含む)
  | "conflict" // 409(相談状態と操作の矛盾)
  | "validation" // 422
  | "ai_failed" // 502(AI呼び出し失敗・AI出力不正)
  | "network" // 通信失敗
  | "server"; // 500・その他

export type ApiErrorDetail = { field: string; reason: string };

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly code?: string; // error.code。例: "VALIDATION_ERROR" / "AI_OUTPUT_INVALID"
  readonly details?: ApiErrorDetail[]; // 422のときのみ

  constructor(
    kind: ApiErrorKind,
    options: {
      status?: number;
      code?: string;
      message?: string; // サーバーの定型文(安全)。なければkindを使う
      details?: ApiErrorDetail[];
    } = {},
  ) {
    // 相談内容・トークン・AI出力は入れない
    super(options.message ?? kind);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
  }
}

  
export const apiClient = {
  get<T>(path: string): Promise<T> {
    throw new Error("not implemented");
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    throw new Error("not implemented");
  },
  patch<T>(path: string, body?: unknown): Promise<T> {
    throw new Error("not implemented");
  },
  delete(path: string): Promise<void> {
    throw new Error("not implemented");
  },
};