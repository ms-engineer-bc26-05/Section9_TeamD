import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PhaseMessage } from "@/components/plan/PhaseMessage";
import type { PlanErrorKind, PlanPhase } from "@/lib/usePlanStatus";

afterEach(cleanup);

function setup(phase: PlanPhase, errorKind: PlanErrorKind | null = null) {
  const handlers = {
    onConfirm: vi.fn(),
    onPurchase: vi.fn(),
    onRetry: vi.fn(),
  };
  render(<PhaseMessage phase={phase} errorKind={errorKind} {...handlers} />);
  return handlers;
}

describe("PhaseMessage", () => {
  it("pending は再確認だけを案内し、購入は促さない", () => {
    const { onConfirm } = setup("pending");

    expect(screen.getByText(/決済状態をまだ確認できません/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /購入/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "決済を確認する" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("expired は、もう一度購入できる導線を出す", () => {
    const { onPurchase } = setup("expired");

    expect(screen.getByText(/決済手続きは完了していません/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "購入手続きへ進む" }));
    expect(onPurchase).toHaveBeenCalledTimes(1);
  });

  it("in_progress は、少し待ってから手動で再試行できる", () => {
    const { onPurchase } = setup("in_progress");

    expect(screen.getByText(/決済画面を準備しています/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "もう一度試す" }));
    expect(onPurchase).toHaveBeenCalledTimes(1);
  });

  it("not_found は固定文言を表示する", () => {
    setup("not_found");

    expect(screen.getByRole("alert").textContent).toBe(
      "確認できる決済がありません。",
    );
  });

  it("error は種類ごとの文言で、再試行できる", () => {
    const { onRetry } = setup("error", "network");

    expect(screen.getByRole("alert").textContent).toContain("通信できませんでした");

    fireEvent.click(screen.getByRole("button", { name: "再試行する" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("APIの状態名・エラーコードは表示しない", () => {
    for (const phase of ["pending", "expired", "in_progress", "not_found"] as const) {
      cleanup();
      setup(phase);
      const text = document.body.textContent ?? "";
      expect(text).not.toMatch(/CHECKOUT_IN_PROGRESS|PAYMENT_CONFIRMATION_REQUIRED|ALREADY_PAID|expired|pending|stripe/i);
    }
  });

  it("idle・loading では何も表示しない", () => {
    setup("idle");
    expect(document.body.textContent).toBe("");
  });
});