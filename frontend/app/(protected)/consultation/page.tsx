"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { AuthenticatedConsultationFlow } from "@/features/consultation/components/AuthenticatedConsultationFlow";
import type { ConsultationFlowLimits } from "@/features/consultation/components/ConsultationFlow";
import styles from "./page.module.css";

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
      <main className={styles.completionPage}>
        <section
          className={styles.completionPanel}
          aria-labelledby="save-completed-title"
        >
          <span className={styles.completionIcon} aria-hidden="true">
            ✓
          </span>
          <h1 id="save-completed-title" className={styles.completionTitle}>
            整理メモを保存しました
          </h1>
          <p className={styles.completionMessage}>保存が完了しました。</p>
          <button
            className={styles.returnHomeButton}
            type="button"
            onClick={() => router.replace("/home")}
          >
            ホームへ戻る
          </button>
        </section>
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
