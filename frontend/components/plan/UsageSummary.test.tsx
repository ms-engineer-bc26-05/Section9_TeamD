import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { UsageSummary } from "@/components/plan/UsageSummary";
import type { UsageResponse } from "@/lib/billing";

afterEach(cleanup);

const base: UsageResponse = {
  plan_code: "free",
  consultation_count: 1,
  consultation_limit: 3,
  can_start_consultation: true,
  consultation_resets_at: null,
  memo_count: 2,
  memo_limit: 10,
};

describe("UsageSummary", () => {
  it("無料プランの残り回数と保存件数を表示する", () => {
    render(<UsageSummary plan="free" usage={base} />);

    expect(screen.getByText("現在のプラン:無料プラン")).toBeTruthy();
    expect(screen.getByText("相談回数:残り2回(上限 3回)")).toBeTruthy();
    expect(screen.getByText("保存したメモ:2件(上限 10件)")).toBeTruthy();
  });

  it("有料プランは有料プランと表示する", () => {
    render(
      <UsageSummary
        plan="premium"
        usage={{ ...base, plan_code: "premium", consultation_limit: 30 }}
      />,
    );

    expect(screen.getByText("現在のプラン:有料プラン")).toBeTruthy();
    expect(screen.getByText("相談回数:残り29回(上限 30回)")).toBeTruthy();
  });

  it("上限が null のときは、上限はないと表示する", () => {
    render(
      <UsageSummary
        plan="premium"
        usage={{ ...base, consultation_limit: null, memo_limit: null }}
      />,
    );

    expect(screen.getByText("相談回数:上限はありません。")).toBeTruthy();
    expect(screen.getByText("保存したメモ:2件")).toBeTruthy();
  });

  it("回数が null(Redisから取得できない)のときは、確認できないと表示する", () => {
    render(
      <UsageSummary plan="free" usage={{ ...base, consultation_count: null }} />,
    );

    expect(screen.getByText(/現在の回数を確認できません/)).toBeTruthy();
  });

  it("使用回数が上限を超えていても、残りは0回と表示する", () => {
    render(
      <UsageSummary plan="free" usage={{ ...base, consultation_count: 4 }} />,
    );

    expect(screen.getByText("相談回数:残り0回(上限 3回)")).toBeTruthy();
  });

  it("上限に達したときは、リセット日とあわせて案内する", () => {
    render(
      <UsageSummary
        plan="free"
        usage={{
          ...base,
          consultation_count: 3,
          can_start_consultation: false,
          consultation_resets_at: "2026-11-10T12:00:00Z",
        }}
      />,
    );

    expect(screen.getByText(/この期間の相談回数の上限に達しました/)).toBeTruthy();
    expect(screen.getByText(/以降に、また相談できます/)).toBeTruthy();
  });

  it("利用状況を取得できなかったときは、その旨を表示する", () => {
    render(<UsageSummary plan="free" usage={null} />);

    expect(screen.getByText("利用状況を取得できませんでした。")).toBeTruthy();
  });

  it("相談を開始できるときは、開始できると表示する", () => {
    render(<UsageSummary plan="free" usage={base} />);

    expect(screen.getByText("相談を始められます。")).toBeTruthy();
  });

  it("上限に達したときは、開始できるとは表示しない", () => {
    render(
      <UsageSummary
        plan="free"
        usage={{ ...base, consultation_count: 3, can_start_consultation: false }}
      />,
    );

    expect(screen.queryByText("相談を始められます。")).toBeNull();
  });
});