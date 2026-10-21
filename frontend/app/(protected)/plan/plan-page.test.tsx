import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const { search, usePlanStatusMock } = vi.hoisted(() => ({
  search: { value: "" },
  usePlanStatusMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search.value),
}));
vi.mock("@/lib/usePlanStatus", () => ({ usePlanStatus: usePlanStatusMock }));

import PlanPage from "./page";

function state(overrides: Record<string, unknown> = {}) {
  return {
    plan: "free",
    usage: null,
    phase: "idle",
    errorKind: null,
    startCheckout: vi.fn(),
    confirm: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  search.value = "";
  usePlanStatusMock.mockReset().mockReturnValue(state());
});

afterEach(cleanup);

describe("PlanPage", () => {
  it("キャンセルから戻ったとき(?checkout=cancelled)は、固定文言を表示する", () => {
    search.value = "checkout=cancelled";

    render(<PlanPage />);

    expect(screen.getByText(/手続きはキャンセルされました/)).toBeTruthy();
  });

  it("通常の表示では、キャンセルの文言を表示しない", () => {
    render(<PlanPage />);

    expect(screen.queryByText(/手続きはキャンセルされました/)).toBeNull();
  });

  it("無料プランの通常表示では、購入の案内と注記を表示する", () => {
    render(<PlanPage />);

    expect(screen.getByRole("button", { name: "購入手続きへ進む" })).toBeTruthy();
    expect(
      screen.getByText("テスト環境のため、実際の請求は発生しません。"),
    ).toBeTruthy();
  });

  it("pending のときは、購入の案内を表示せず、再購入を促さない", () => {
    usePlanStatusMock.mockReturnValue(state({ phase: "pending" }));

    render(<PlanPage />);

    expect(screen.queryByRole("button", { name: "購入手続きへ進む" })).toBeNull();
    expect(screen.getByRole("button", { name: "決済を確認する" })).toBeTruthy();
  });

  it("有料プランでは、購入の案内を表示しない", () => {
    usePlanStatusMock.mockReturnValue(state({ plan: "premium" }));

    render(<PlanPage />);

    expect(screen.queryByRole("button", { name: "購入手続きへ進む" })).toBeNull();
    expect(screen.getByText("有料プランをご利用中です。")).toBeTruthy();
  });
});