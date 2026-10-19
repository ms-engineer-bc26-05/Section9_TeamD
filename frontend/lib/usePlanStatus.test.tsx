import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

const { handleAuthFailure, billing } = vi.hoisted(() => ({
  handleAuthFailure: vi.fn(),
  billing: {
    confirmPayment: vi.fn(),
    createCheckoutSession: vi.fn(),
    fetchCurrentPlan: vi.fn(),
    fetchUsage: vi.fn(),
    BILLING_ERROR_CODES: {
      VALIDATION_ERROR: "VALIDATION_ERROR",
      PLAN_NOT_AVAILABLE: "PLAN_NOT_AVAILABLE",
    },
  },
}));

vi.mock("@/lib/firebase", () => ({
  getFirebaseAuth: () => ({ currentUser: null }),
}));
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ profileStatus: "ready", handleAuthFailure }),
}));
vi.mock("@/lib/billing", () => billing);

import { ApiError } from "@/lib/apiClient";
import { usePlanStatus } from "@/lib/usePlanStatus";

const USAGE = {
  plan_code: "free",
  consultation_count: 1,
  consultation_limit: 3,
  can_start_consultation: true,
  consultation_resets_at: null,
  memo_count: 2,
  memo_limit: 10,
};

beforeEach(() => {
  handleAuthFailure.mockReset().mockResolvedValue(false);
  billing.fetchCurrentPlan.mockReset().mockResolvedValue({ plan_code: "free" });
  billing.fetchUsage.mockReset().mockResolvedValue(USAGE);
  billing.confirmPayment.mockReset();
  billing.createCheckoutSession.mockReset();
});

describe("usePlanStatus", () => {
  it("初回にプランと利用状況を取得して、idle になる", async () => {
    const { result } = renderHook(() => usePlanStatus());

    expect(result.current.phase).toBe("loading");
    await waitFor(() => expect(result.current.phase).toBe("idle"));
    expect(result.current.plan).toBe("free");
    expect(result.current.usage).toEqual(USAGE);
  });

  it("paid を受け取り、プランを再取得できてから premium にする", async () => {
    billing.confirmPayment.mockResolvedValue({ status: "paid" });
    billing.fetchCurrentPlan.mockResolvedValue({ plan_code: "premium" });

    const { result } = renderHook(() =>
      usePlanStatus({ confirmSessionId: "cs_test_1" }),
    );

    await waitFor(() => expect(result.current.phase).toBe("idle"));
    expect(billing.confirmPayment).toHaveBeenCalledWith("cs_test_1");
    expect(result.current.plan).toBe("premium");
  });

  it("pending のあいだは有料表示にしない", async () => {
    billing.confirmPayment.mockResolvedValue({ status: "pending" });

    const { result } = renderHook(() =>
      usePlanStatus({ confirmSessionId: "cs_test_1" }),
    );

    await waitFor(() => expect(result.current.phase).toBe("pending"));
    expect(result.current.plan).not.toBe("premium");
    expect(billing.fetchCurrentPlan).not.toHaveBeenCalled();
  });

  it("expired は expired として扱う", async () => {
    billing.confirmPayment.mockResolvedValue({ status: "expired" });

    const { result } = renderHook(() =>
      usePlanStatus({ confirmSessionId: "cs_test_1" }),
    );

    await waitFor(() => expect(result.current.phase).toBe("expired"));
    expect(result.current.plan).not.toBe("premium");
  });

  it("confirm が 404 相当(not_found)なら、プランを再取得して not_found にする", async () => {
    billing.confirmPayment.mockResolvedValue({ status: "not_found" });

    const { result } = renderHook(() =>
      usePlanStatus({ confirmSessionId: "cs_test_1" }),
    );

    await waitFor(() => expect(result.current.phase).toBe("not_found"));
    expect(billing.fetchCurrentPlan).toHaveBeenCalledTimes(1);
    expect(result.current.plan).toBe("free");
  });

  it("購入で confirmation_required なら、エラーにせず session_id を省略して confirm へ進む", async () => {
    billing.createCheckoutSession.mockResolvedValue({
      type: "confirmation_required",
    });
    billing.confirmPayment.mockResolvedValue({ status: "pending" });

    const { result } = renderHook(() => usePlanStatus());
    await waitFor(() => expect(result.current.phase).toBe("idle"));

    await act(async () => {
      await result.current.startCheckout();
    });

    expect(billing.confirmPayment).toHaveBeenCalledWith(undefined);
    expect(result.current.phase).toBe("pending");
  });

  it("購入で in_progress なら、in_progress にして手動の再試行を待つ", async () => {
    billing.createCheckoutSession.mockResolvedValue({ type: "in_progress" });

    const { result } = renderHook(() => usePlanStatus());
    await waitFor(() => expect(result.current.phase).toBe("idle"));

    await act(async () => {
      await result.current.startCheckout();
    });

    expect(result.current.phase).toBe("in_progress");
  });

  it("購入で already_paid なら、プランを再取得して idle に戻る", async () => {
    billing.createCheckoutSession.mockResolvedValue({ type: "already_paid" });

    const { result } = renderHook(() => usePlanStatus());
    await waitFor(() => expect(result.current.phase).toBe("idle"));
    billing.fetchCurrentPlan.mockResolvedValue({ plan_code: "premium" });

    await act(async () => {
      await result.current.startCheckout();
    });

    expect(result.current.phase).toBe("idle");
    expect(result.current.plan).toBe("premium");
  });

  it("退会処理中(403 ACCOUNT_DELETING)は AuthProvider に任せ、error にしない", async () => {
    billing.fetchCurrentPlan.mockRejectedValue(
      new ApiError("forbidden", { status: 403, code: "ACCOUNT_DELETING" }),
    );
    handleAuthFailure.mockResolvedValue(true);

    const { result } = renderHook(() => usePlanStatus());

    await waitFor(() => expect(handleAuthFailure).toHaveBeenCalledTimes(1));
    expect(result.current.phase).not.toBe("error");
  });

  it("通信失敗は error(network)、サーバー障害は error(server) にする", async () => {
    billing.fetchCurrentPlan.mockRejectedValueOnce(new ApiError("network"));
    const first = renderHook(() => usePlanStatus());
    await waitFor(() => expect(first.result.current.phase).toBe("error"));
    expect(first.result.current.errorKind).toBe("network");

    billing.fetchCurrentPlan.mockRejectedValueOnce(
      new ApiError("server", { status: 503 }),
    );
    const second = renderHook(() => usePlanStatus());
    await waitFor(() => expect(second.result.current.phase).toBe("error"));
    expect(second.result.current.errorKind).toBe("server");
  });

  it("PAYMENT_CONFIRMATION_REQUIRED の session_id を、confirm へ渡す", async () => {
    billing.createCheckoutSession.mockResolvedValue({
      type: "confirmation_required",
      sessionId: "cs_test_9",
    });
    billing.confirmPayment.mockResolvedValue({ status: "pending" });

    const { result } = renderHook(() => usePlanStatus());
    await waitFor(() => expect(result.current.phase).toBe("idle"));

    await act(async () => {
      await result.current.startCheckout();
    });

    expect(billing.confirmPayment).toHaveBeenCalledWith("cs_test_9");
    expect(result.current.phase).toBe("pending");
  });

  it("購入の失敗後の再試行は、購入処理をやり直す(プランの再取得ではない)", async () => {
    billing.createCheckoutSession
      .mockRejectedValueOnce(new ApiError("server", { status: 503 }))
      .mockResolvedValueOnce({ type: "in_progress" });

    const { result } = renderHook(() => usePlanStatus());
    await waitFor(() => expect(result.current.phase).toBe("idle"));

    await act(async () => {
      await result.current.startCheckout();
    });
    expect(result.current.phase).toBe("error");

    await act(async () => {
      await result.current.retry();
    });

    expect(billing.createCheckoutSession).toHaveBeenCalledTimes(2);
    expect(billing.fetchCurrentPlan).toHaveBeenCalledTimes(1);
    expect(result.current.phase).toBe("in_progress");
  });

  it("成功URLでの決済確認の失敗後は、同じ session_id で確認をやり直す", async () => {
    billing.confirmPayment
      .mockRejectedValueOnce(new ApiError("network"))
      .mockResolvedValueOnce({ status: "pending" });

    const { result } = renderHook(() =>
      usePlanStatus({ confirmSessionId: "cs_test_1" }),
    );
    await waitFor(() => expect(result.current.phase).toBe("error"));

    await act(async () => {
      await result.current.retry();
    });

    expect(billing.confirmPayment).toHaveBeenNthCalledWith(2, "cs_test_1");
    expect(result.current.phase).toBe("pending");
  });

  it("プラン画面での決済確認の失敗後は、session_id を省略して確認をやり直す", async () => {
    billing.confirmPayment
      .mockRejectedValueOnce(new ApiError("network"))
      .mockResolvedValueOnce({ status: "pending" });

    const { result } = renderHook(() => usePlanStatus());
    await waitFor(() => expect(result.current.phase).toBe("idle"));

    await act(async () => {
      await result.current.confirm();
    });
    expect(result.current.phase).toBe("error");

    await act(async () => {
      await result.current.retry();
    });

    expect(billing.confirmPayment).toHaveBeenNthCalledWith(2, undefined);
    expect(result.current.phase).toBe("pending");
  });

  it("初回の取得の失敗後は、プランと利用状況を取得し直す", async () => {
    billing.fetchCurrentPlan
      .mockRejectedValueOnce(new ApiError("network"))
      .mockResolvedValueOnce({ plan_code: "free" });

    const { result } = renderHook(() => usePlanStatus());
    await waitFor(() => expect(result.current.phase).toBe("error"));

    await act(async () => {
      await result.current.retry();
    });

    await waitFor(() => expect(result.current.phase).toBe("idle"));
    expect(billing.fetchCurrentPlan).toHaveBeenCalledTimes(2);
    expect(result.current.plan).toBe("free");
  });

  it("422 は、内容に応じて validation と plan_unavailable に分ける", async () => {
    billing.createCheckoutSession.mockRejectedValueOnce(
      new ApiError("validation", { status: 422, code: "PLAN_NOT_AVAILABLE" }),
    );
    const first = renderHook(() => usePlanStatus());
    await waitFor(() => expect(first.result.current.phase).toBe("idle"));
    await act(async () => {
      await first.result.current.startCheckout();
    });
    expect(first.result.current.errorKind).toBe("plan_unavailable");

    billing.createCheckoutSession.mockRejectedValueOnce(
      new ApiError("validation", { status: 422, code: "VALIDATION_ERROR" }),
    );
    const second = renderHook(() => usePlanStatus());
    await waitFor(() => expect(second.result.current.phase).toBe("idle"));
    await act(async () => {
      await second.result.current.startCheckout();
    });
    expect(second.result.current.errorKind).toBe("validation");
  });
});