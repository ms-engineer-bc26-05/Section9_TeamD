"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PhaseMessage } from "@/components/plan/PhaseMessage";
import styles from "@/components/plan/plan.module.css";
import { usePlanStatus } from "@/lib/usePlanStatus";

// Stripe Checkoutからの戻り先(成功URL)。URLの session_id で決済を確認する(F-04 / #58)
// 最終的なプラン表示は UI-012(/plan)で行う
function SuccessContent({ sessionId }: { sessionId: string }) {
  const { plan, phase, errorKind, startCheckout, confirm, retry } =
    usePlanStatus({ confirmSessionId: sessionId });

  // 有料表示にするのは、決済の確認とプランの再取得が終わってから
  const done = phase === "idle" && plan === "premium";
  const unconfirmed = phase === "idle" && plan !== "premium";

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <header className={styles.header}>
          <Link className={styles.back} href="/plan" aria-label="プラン画面へ戻る">
            ‹
          </Link>
          <h1 className={styles.pageTitle}>決済の確認</h1>
        </header>

        {phase === "loading" && (
          <p className={styles.muted} role="status">
            読み込み中です。
          </p>
        )}

        {done && (
          <p className={styles.message} role="status">
            有料プランをご利用いただけるようになりました。
          </p>
        )}

        {unconfirmed && (
          <p className={`${styles.message} ${styles.messageError}`} role="alert">
            決済を確認できませんでした。プラン画面でご確認ください。
          </p>
        )}

        {/* 再試行は、同じ session_id での確認をやり直す */}
        <PhaseMessage
          phase={phase}
          errorKind={errorKind}
          onConfirm={() => void confirm(sessionId)}
          onPurchase={() => void startCheckout()}
          onRetry={() => void retry()}
        />

        <Link className={styles.outlineLink} href="/plan">
          プラン画面へ
        </Link>
      </div>
    </main>
  );
}

function SuccessRoute() {
  const sessionId = useSearchParams().get("session_id");

  if (!sessionId) {
    return (
      <main className={styles.page}>
        <div className={styles.panel}>
          <header className={styles.header}>
            <Link className={styles.back} href="/plan" aria-label="プラン画面へ戻る">
              ‹
            </Link>
            <h1 className={styles.pageTitle}>決済の確認</h1>
          </header>
          <p className={`${styles.message} ${styles.messageError}`} role="alert">
            決済の情報を確認できませんでした。
          </p>
          <Link className={styles.outlineLink} href="/plan">
            プラン画面へ
          </Link>
        </div>
      </main>
    );
  }

  return <SuccessContent sessionId={sessionId} />;
}

export default function PlanSuccessPage() {
  return (
    <Suspense fallback={<p role="status">読み込み中です。</p>}>
      <SuccessRoute />
    </Suspense>
  );
}