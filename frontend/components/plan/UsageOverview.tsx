"use client";

import Link from "next/link";
import { UsageSummary } from "@/components/plan/UsageSummary";
import { usePlanStatus } from "@/lib/usePlanStatus";

// UI-002(ホーム)に置く、利用状況の概要と /plan への導線(F-04 / #58)
// - 利用状況を取得できなくても、相談の開始は止めない(内部の技術名は表示しない)
export function UsageOverview() {
  const { plan, usage, phase } = usePlanStatus();

  return (
    <section aria-label="利用状況の概要">
      {phase === "loading" && <p role="status">利用状況を読み込んでいます。</p>}

      {phase !== "loading" && plan !== null && (
        <UsageSummary plan={plan} usage={usage} />
      )}

      {phase !== "loading" && plan === null && (
        <p>利用状況を取得できませんでした。</p>
      )}

      <Link href="/plan">プランを確認する</Link>
    </section>
  );
}