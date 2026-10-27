"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PhaseMessage } from "@/components/plan/PhaseMessage";
import { PurchaseGuide } from "@/components/plan/PurchaseGuide";
import { UsageSummary } from "@/components/plan/UsageSummary";
import styles from "@/components/plan/plan.module.css";
import { usePlanStatus } from "@/lib/usePlanStatus";

// UI-012 利用回数・プラン画面(F-04 / #58)
function PlanContent() {
  const { plan, usage, phase, errorKind, startCheckout, confirm, retry } =
    usePlanStatus();

  // Stripe Checkoutのキャンセルから戻ったとき(キャンセルURLに ?checkout=cancelled を付ける)
  const cancelled = useSearchParams().get("checkout") === "cancelled";

  // 購入の案内は、無料で、途中状態のメッセージが出ていないときだけ表示する
  // (pending・confirming では再購入を促さない)
  const showPurchase =
    plan === "free" &&
    (phase === "idle" || phase === "starting" || phase === "not_found");

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <header className={styles.header}>
          <Link className={styles.back} href="/home" aria-label="戻る">
            ‹
          </Link>
          <h1 className={styles.pageTitle}>プラン</h1>
        </header>

        {phase === "loading" && (
          <p className={styles.muted} role="status">
            読み込み中です。
          </p>
        )}

        {plan !== null && phase !== "loading" && (
          <UsageSummary plan={plan} usage={usage} />
        )}

        {plan === "premium" && phase === "idle" && (
          <p className={styles.message}>有料プランをご利用中です。</p>
        )}

        {cancelled && phase === "idle" && (
          <p className={styles.message} role="status">
            手続きはキャンセルされました。プランは変更されていません。
          </p>
        )}

        <PhaseMessage
          phase={phase}
          errorKind={errorKind}
          onConfirm={() => void confirm()}
          onPurchase={() => void startCheckout()}
          onRetry={() => void retry()}
        />

        {showPurchase && (
          <PurchaseGuide
            starting={phase === "starting"}
            onPurchase={() => void startCheckout()}
            onConfirm={() => void confirm()}
          />
        )}
      </div>
    </main>
  );
}

// useSearchParams は、ビルド時の静的生成のためにSuspenseで包む必要がある
export default function PlanPage() {
  return (
    <Suspense fallback={<p role="status">読み込み中です。</p>}>
      <PlanContent />
    </Suspense>
  );
}