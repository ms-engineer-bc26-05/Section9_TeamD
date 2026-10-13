import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

const { handleAuthFailure, billing } = vi.hoisted(() => ({
  handleAuthFailure: vi.fn(),
  billing: {
    confirmPayment: vi.fn(),
    createCheckoutSession: vi.fn(),
    fetchCurrentPlan: vi.fn(),
    fetchUsage: vi.fn(),
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

const USAGE = { can_start_consultation: true, consultation_resets_at: null };

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
});