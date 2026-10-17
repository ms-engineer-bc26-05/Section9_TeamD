"use client";

import Link from "next/link";
import { PhaseMessage } from "@/components/plan/PhaseMessage";
import { UsageSummary } from "@/components/plan/UsageSummary";
import { usePlanStatus } from "@/lib/usePlanStatus";

// UI-012 利用回数・プラン画面(F-04 / #58)
export default function PlanPage() {
  const { plan, usage, phase, errorKind, startCheckout, confirm, reload } =
    usePlanStatus();

  // 購入の案内は、無料で、途中状態のメッセージが出ていないときだけ表示する
  // (pending・confirming では再購入を促さない)
  const showPurchase =
    plan === "free" &&
    (phase === "idle" || phase === "starting" || phase === "not_found");

  return (
    <main>
      <h1>プラン</h1>

      {phase === "loading" && <p role="status">読み込み中です。</p>}

      {plan !== null && phase !== "loading" && (
        <UsageSummary plan={plan} usage={usage} />
      )}

      {plan === "premium" && phase === "idle" && (
        <p>有料プランをご利用中です。</p>
      )}

      <PhaseMessage
        phase={phase}
        errorKind={errorKind}
        onConfirm={() => void confirm()}
        onPurchase={() => void startCheckout()}
        onRetry={() => void reload()}
      />

      {showPurchase && (
        <section aria-label="プランの違い">
          <h2>プランの違いを確認</h2>
          <h3>有料プラン</h3>
          <ul>
            <li>相談できる回数が増えます</li>
            <li>保存できるメモの件数が増えます</li>
          </ul>
          <p>必要なときだけ、ご検討ください。</p>
          <p>テスト環境のため、実際の請求は発生しません。</p>
          <button
            type="button"
            onClick={() => void startCheckout()}
            disabled={phase === "starting"}
          >
            購入手続きへ進む
          </button>
          <p>
            決済結果を確認してから反映します。確認できない場合は成功として扱いません。
          </p>
          <p>キャンセル時はプランを更新しません。</p>
          <p>
            お支払い後に反映されない場合は、
            <button type="button" onClick={() => void confirm()}>
              決済を確認する
            </button>
          </p>
        </section>
      )}

      <Link href="/home">戻る</Link>
    </main>
  );
}