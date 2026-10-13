/**
 * 利用状況・プラン・一回払いのAPI呼び出し(F-04 / #58)
 *
 * - 契約: Issue #59(F-05)のコメントのAPI契約。code名の「仮」はF-05のPRで確定する
 * - 仮のcode名は BILLING_ERROR_CODES に集約する(変わったらここだけ直す)
 * - NEXT_PUBLIC_BILLING_MOCK=true のとき、実APIを呼ばずモックで動く(F-05マージ前の開発用)
 * - 認証・/api/v1の付与・エラー変換は apiClient に任せる
 */

import { apiClient, ApiError } from "@/lib/apiClient";

// ---------- 型 ----------

export type PlanCode = "free" | "premium";

// GET /payments/me
export type PlanResponse = { plan_code: PlanCode };

// GET /usage(#57)。項目は仮。API設計書6.7・PR #90に合わせて確定する
export type UsageResponse = {
  can_start_consultation: boolean;
  consultation_resets_at: string | null;
};

// POST /payments/checkout-session の200
type CheckoutSessionResponse = { checkout_url: string; session_id: string };

// 画面側で扱う結果。409は「エラー」ではなく画面ごとの分岐として返す
export type CheckoutResult =
  | { type: "redirect"; checkoutUrl: string; sessionId: string }
  | { type: "already_paid" } // 409 ALREADY_PAID(仮) → プランを再取得して表示
  | { type: "in_progress" } // 409 CHECKOUT_IN_PROGRESS(仮) → 少し待って再試行
  | { type: "confirmation_required" }; // 409 PAYMENT_CONFIRMATION_REQUIRED(仮) → confirmへ進む

// POST /payments/confirm の結果。404は画面側で扱いやすいよう not_found として返す
export type ConfirmResult = {
  status: "paid" | "pending" | "expired" | "not_found";
};

// ---------- 仮のcode名(F-05のPRで確定) ----------

export const BILLING_ERROR_CODES = {
  ALREADY_PAID: "ALREADY_PAID",
  CHECKOUT_IN_PROGRESS: "CHECKOUT_IN_PROGRESS",
  PAYMENT_CONFIRMATION_REQUIRED: "PAYMENT_CONFIRMATION_REQUIRED",
  ACCOUNT_DELETING: "ACCOUNT_DELETING", // 403。確定済み
} as const;

// ---------- 実API ----------

async function createCheckoutSessionReal(
  planCode: PlanCode,
): Promise<CheckoutResult> {
  try {
    const res = await apiClient.post<CheckoutSessionResponse>(
      "/payments/checkout-session",
      { plan_code: planCode },
    );
    return {
      type: "redirect",
      checkoutUrl: res.checkout_url,
      sessionId: res.session_id,
    };
  } catch (error) {
    if (error instanceof ApiError && error.kind === "conflict") {
      switch (error.code) {
        case BILLING_ERROR_CODES.ALREADY_PAID:
          return { type: "already_paid" };
        case BILLING_ERROR_CODES.CHECKOUT_IN_PROGRESS:
          return { type: "in_progress" };
        case BILLING_ERROR_CODES.PAYMENT_CONFIRMATION_REQUIRED:
          return { type: "confirmation_required" };
      }
    }
    // 403 ACCOUNT_DELETING・422・503などは、呼び出し側が error.kind / error.code で分岐する
    throw error;
  }
}

async function confirmPaymentReal(sessionId?: string): Promise<ConfirmResult> {
  try {
    // session_id省略時は、サーバー側で本人の未確認の決済(pending)を探す
    const res = await apiClient.post<{ status: "paid" | "pending" | "expired" }>(
      "/payments/confirm",
      sessionId ? { session_id: sessionId } : {},
    );
    return { status: res.status };
  } catch (error) {
    if (error instanceof ApiError && error.kind === "not_found") {
      return { status: "not_found" };
    }
    throw error;
  }
}

function fetchCurrentPlanReal(): Promise<PlanResponse> {
  return apiClient.get<PlanResponse>("/payments/me");
}

function fetchUsageReal(): Promise<UsageResponse> {
  return apiClient.get<UsageResponse>("/usage");
}

// ---------- モック(F-05マージ前の開発用) ----------

// 購入後はページ遷移(全体の再読み込み)が起きるため、モックの状態はsessionStorageに持つ
const MOCK_PLAN_KEY = "billing-mock-plan";

function readMockPlan(): PlanCode {
  try {
    return sessionStorage.getItem(MOCK_PLAN_KEY) === "premium"
      ? "premium"
      : "free";
  } catch {
    return "free";
  }
}

function writeMockPlan(plan: PlanCode): void {
  try {
    sessionStorage.setItem(MOCK_PLAN_KEY, plan);
  } catch {
    // 保存できなくても、モックなので無視する
  }
}

async function createCheckoutSessionMock(): Promise<CheckoutResult> {
  if (readMockPlan() === "premium") return { type: "already_paid" };
  return {
    type: "redirect",
    // Stripeへは行かず、成功URLへ直接戻る
    checkoutUrl: "/plan/success?session_id=cs_test_mock",
    sessionId: "cs_test_mock",
  };
}

async function confirmPaymentMock(): Promise<ConfirmResult> {
  writeMockPlan("premium");
  return { status: "paid" };
}

async function fetchCurrentPlanMock(): Promise<PlanResponse> {
  return { plan_code: readMockPlan() };
}

async function fetchUsageMock(): Promise<UsageResponse> {
  return { can_start_consultation: true, consultation_resets_at: null };
}

// ---------- 公開関数 ----------

const USE_MOCK = process.env.NEXT_PUBLIC_BILLING_MOCK === "true";

export const createCheckoutSession = USE_MOCK
  ? createCheckoutSessionMock
  : createCheckoutSessionReal;
export const confirmPayment = USE_MOCK ? confirmPaymentMock : confirmPaymentReal;
export const fetchCurrentPlan = USE_MOCK
  ? fetchCurrentPlanMock
  : fetchCurrentPlanReal;
export const fetchUsage = USE_MOCK ? fetchUsageMock : fetchUsageReal;