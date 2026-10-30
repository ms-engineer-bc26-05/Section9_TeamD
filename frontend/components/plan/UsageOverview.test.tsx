import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const { usePlanStatusMock } = vi.hoisted(() => ({
  usePlanStatusMock: vi.fn(),
}));

vi.mock("@/lib/usePlanStatus", () => ({ usePlanStatus: usePlanStatusMock }));

import { UsageOverview } from "@/components/plan/UsageOverview";

const usage = {
  plan_code: "free",
  consultation_count: 1,
  consultation_limit: 3,
  can_start_consultation: true,
  consultation_resets_at: null,
  memo_count: 2,
  memo_limit: 10,
};

beforeEach(() => {
  usePlanStatusMock.mockReset();
});

afterEach(cleanup);

describe("UsageOverview", () => {
  it("読み込み中は、その旨と /plan への導線を表示する", () => {
    usePlanStatusMock.mockReturnValue({ plan: null, usage: null, phase: "loading" });

    render(<UsageOverview />);

    expect(screen.getByText("利用状況を読み込んでいます。")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "プランを確認する" }).getAttribute("href"),
    ).toBe("/plan");
  });

  it("取得できたときは、利用状況の概要と /plan への導線を表示する", () => {
    usePlanStatusMock.mockReturnValue({ plan: "free", usage, phase: "idle" });

    render(<UsageOverview />);

    expect(screen.getByText("現在のプラン:無料プラン")).toBeTruthy();
    expect(screen.getByText("相談回数:残り2回(上限 3回)")).toBeTruthy();
    expect(screen.getByText("相談を始められます。")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "プランを確認する" }).getAttribute("href"),
    ).toBe("/plan");
  });

  it("取得できなかったときは、固定文言だけを表示し、導線は残す(相談開始は止めない)", () => {
    usePlanStatusMock.mockReturnValue({ plan: null, usage: null, phase: "error" });

    render(<UsageOverview />);

    expect(screen.getByText("利用状況を取得できませんでした。")).toBeTruthy();
    expect(screen.getByRole("link", { name: "プランを確認する" })).toBeTruthy();
  });
});