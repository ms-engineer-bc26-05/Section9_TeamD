"use client";

import { useCallback } from "react";

import { authenticatedConsultationApi } from "../api/authenticatedConsultationApi";
import {
  authenticatedConsultationMemoApi,
  type SavedConsultationMemo,
} from "../api/consultationMemoApi";
import { useConsultationMemoSave } from "../hooks/useConsultationMemoSave";
import {
  ConsultationFlowContainer,
  type ConsultationSaveRequest,
} from "./ConsultationFlowContainer";
import type { ConsultationFlowLimits } from "./ConsultationFlow";

interface AuthenticatedConsultationFlowProps {
  limits: ConsultationFlowLimits;
  onBackToNotice: () => void;
  onReturnHome: () => void;
  onOpenPlan: () => void;
  onSaveCompleted: (memo: SavedConsultationMemo) => void;
}

/**
 * Issue #48の認証済みクライアントと相談・保存フローを接続する。
 * 画面ルートの遷移先はIssue #53からコールバックで受け取る。
 */
export function AuthenticatedConsultationFlow({
  limits,
  onBackToNotice,
  onReturnHome,
  onOpenPlan,
  onSaveCompleted,
}: AuthenticatedConsultationFlowProps) {
  const {
    state: memoSaveState,
    save: saveMemo,
    reset: resetMemoSave,
  } = useConsultationMemoSave(authenticatedConsultationMemoApi);

  const handleSaveRequested = useCallback(
    async (request: ConsultationSaveRequest) => {
      const savedMemo = await saveMemo(request);
      if (savedMemo !== null) {
        onSaveCompleted(savedMemo);
      }
    },
    [onSaveCompleted, saveMemo],
  );

  const handleReturnHome = useCallback(() => {
    resetMemoSave();
    onReturnHome();
  }, [onReturnHome, resetMemoSave]);

  const handleBackToNotice = useCallback(() => {
    resetMemoSave();
    onBackToNotice();
  }, [onBackToNotice, resetMemoSave]);

  return (
    <ConsultationFlowContainer
      api={authenticatedConsultationApi}
      limits={limits}
      saveState={memoSaveState}
      onBackToNotice={handleBackToNotice}
      onReturnHome={handleReturnHome}
      onOpenPlan={onOpenPlan}
      onSaveRequested={(request) => void handleSaveRequested(request)}
      onResetSaveState={resetMemoSave}
    />
  );
}
