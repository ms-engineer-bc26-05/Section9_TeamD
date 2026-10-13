"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PhaseMessage } from "@/components/plan/PhaseMessage";
import { usePlanStatus } from "@/lib/usePlanStatus";

// Stripe Checkoutからの戻り先(成功URL)。URLの session_id で決済を確認する(F-04 / #58)
// 最終的なプラン表示は UI-012(/plan)で行う
function SuccessContent({ sessionId }: { sessionId: string }) {
  const { plan, phase, errorKind, startCheckout, confirm } = usePlanStatus({
    confirmSessionId: sessionId,
  });

  // 有料表示にするのは、決済の確認とプランの再取得が終わってから
  const done = phase === "idle" && plan === "premium";
  const unconfirmed = phase === "idle" && plan !== "premium";

  return (
    <main>
      <h1>決済の確認</h1>

      {phase === "loading" && <p role="status">読み込み中です。</p>}

      {done && <p role="status">有料プランをご利用いただけるようになりました。</p>}

      {unconfirmed && (
        <p role="alert">決済を確認できませんでした。プラン画面でご確認ください。</p>
      )}

      <PhaseMessage
        phase={phase}
        errorKind={errorKind}
        onConfirm={() => void confirm(sessionId)}
        onPurchase={() => void startCheckout()}
        onRetry={() => void confirm(sessionId)}
      />

      <Link href="/plan">プラン画面へ</Link>
    </main>
  );
}

function SuccessRoute() {
  const sessionId = useSearchParams().get("session_id");

  if (!sessionId) {
    return (
      <main>
        <h1>決済の確認</h1>
        <p role="alert">決済の情報を確認できませんでした。</p>
        <Link href="/plan">プラン画面へ</Link>
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