"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { AuthenticatedConsultationFlow } from "@/features/consultation/components/AuthenticatedConsultationFlow";
import type { ConsultationFlowLimits } from "@/features/consultation/components/ConsultationFlow";

const LIMITS: ConsultationFlowLimits = {
  startDetail: 2000,
  eventAnswer: 1000,
  eventSummaryField: 500,
  emotionDetail: 300,
  guidedAnswer: 1000,
  resultField: 500,
  resultEmotion: 300,
  saveReason: 500,
};

export default function ConsultationPage() {
  const router = useRouter();
  const [saveCompleted, setSaveCompleted] = useState(false);

  if (saveCompleted) {
    return (
      <main>
        <h1>整理メモを保存しました</h1>
        <p>保存が完了しました。</p>
        <button type="button" onClick={() => router.replace("/home")}>
          ホームへ戻る
        </button>
      </main>
    );
  }

  return (
    <AuthenticatedConsultationFlow
      limits={LIMITS}
      onBackToNotice={() => router.push("/notice")}
      onReturnHome={() => router.replace("/home")}
      onOpenPlan={() => router.replace("/home")}
      onSaveCompleted={() => setSaveCompleted(true)}
    />
  );
}
