"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import type { ConsultationApi } from "../api/consultationApi";
import { useConsultationSessionController } from "../hooks/useConsultationSessionController";
import type { GuidedDialogueHistoryItem } from "./GuidedDialogueStep";
import type {
  EmotionCategory,
  GuidedDialogueRequest,
  HandlingType,
} from "../model/contracts";
import {
  ConsultationFlow,
  type ConsultationFlowLimits,
  type ConsultationSaveState,
} from "./ConsultationFlow";

export interface ConsultationSaveRequest {
  consultationId: string;
  reason: string | null;
}

const IDLE_SAVE_STATE: ConsultationSaveState = {
  isSubmitting: false,
  errorCode: null,
};

const NOOP = () => {};

interface ConsultationFlowContainerProps {
  api: ConsultationApi;
  limits: ConsultationFlowLimits;
  saveState?: ConsultationSaveState;
  onBackToNotice: () => void;
  onReturnHome: () => void;
  onOpenPlan: () => void;
  onSaveRequested: (request: ConsultationSaveRequest) => void;
  onResetSaveState?: () => void;
  onApiError?: (error: unknown) => void;
}

/**
 * API由来の相談状態と、永続化しない画面内入力をConsultationFlowへ接続する。
 * 認証処理と整理メモ保存は、それぞれIssue #48・#52の境界から受け取る。
 */
export function ConsultationFlowContainer({
  api,
  limits,
  saveState = IDLE_SAVE_STATE,
  onBackToNotice,
  onReturnHome,
  onOpenPlan,
  onSaveRequested,
  onResetSaveState = NOOP,
  onApiError,
}: ConsultationFlowContainerProps) {
  const controller = useConsultationSessionController(api, onApiError);
  const [selectedEmotion, setSelectedEmotion] =
    useState<EmotionCategory | null>(null);
  const [guidedHistory, setGuidedHistory] = useState<
    readonly GuidedDialogueHistoryItem[]
  >([]);
  const [guidedAnswer, setGuidedAnswer] = useState("");
  const [saveReason, setSaveReason] = useState("");
  const [isReselectingHandling, setIsReselectingHandling] = useState(false);

  const resetDrafts = useCallback(() => {
    setSelectedEmotion(null);
    setGuidedHistory([]);
    setGuidedAnswer("");
    setSaveReason("");
    setIsReselectingHandling(false);
  }, []);

  useEffect(() => {
    const shouldDiscardDialogueDrafts =
      controller.state.status === "result_ready" ||
      controller.state.status === "handling_selection" ||
      controller.state.status === "save_confirmation" ||
      controller.state.status === "safety_guidance" ||
      controller.state.errorCode === "CONSULTATION_NOT_FOUND";

    if (shouldDiscardDialogueDrafts) {
      setGuidedHistory([]);
      setGuidedAnswer("");
    }

    if (
      controller.state.status === "safety_guidance" ||
      controller.state.errorCode === "CONSULTATION_NOT_FOUND"
    ) {
      setSelectedEmotion(null);
      setSaveReason("");
      setIsReselectingHandling(false);
    }
  }, [controller.state.errorCode, controller.state.status]);

  async function discardAndReturnHome() {
    const discarded = await controller.discardConsultation();

    if (discarded) {
      resetDrafts();
      onReturnHome();
    }
  }

  function handleBackToNotice() {
    controller.reset();
    resetDrafts();
    onBackToNotice();
  }

  function handleReturnHome() {
    controller.reset();
    resetDrafts();
    onReturnHome();
  }

  async function handleGuidedSubmit(request: GuidedDialogueRequest) {
    const topic = controller.state.currentTopic;
    if (topic === null) {
      return;
    }

    const submitted = await controller.submitGuidedDialogue(request);
    if (!submitted) {
      return;
    }

    setGuidedHistory((current) => [
      ...current,
      request.skipped === true
        ? { topic, answer: "", skipped: true }
        : { topic, answer: request.answer },
    ]);
    setGuidedAnswer("");
  }

  async function handleChooseHandling(handling: HandlingType) {
    const selected = await controller.chooseHandling(handling);

    if (selected) {
      setIsReselectingHandling(false);
    }
  }

  function handleSave(reason: string | null) {
    if (controller.state.consultationId === null) {
      handleReturnHome();
      return;
    }

    onSaveRequested({
      consultationId: controller.state.consultationId,
      reason,
    });
  }

  function handleReturnToHandlingSelection() {
    onResetSaveState();
    setIsReselectingHandling(true);
  }

  return (
    <ConsultationFlow
      state={controller.state}
      draft={{
        selectedEmotion,
        guidedHistory,
        guidedAnswer,
        saveReason,
        isReselectingHandling,
      }}
      limits={limits}
      saveState={saveState}
      actions={{
        onBackToNotice: handleBackToNotice,
        onReturnHomeAfterStateLoss: handleReturnHome,
        onReturnHomeAfterUsageLimit: handleReturnHome,
        onReturnHomeFromSafetyGuidance: handleReturnHome,
        onOpenPlan,
        onCancel: () => void discardAndReturnHome(),
        onStartConsultation: (request) =>
          void controller.startConsultation(request),
        onEventAnswer: (answer) =>
          void controller.submitEventDialogue({ action: "answer", answer }),
        onEventCorrect: (correction) =>
          void controller.submitEventDialogue({
            action: "correct",
            correction_input: correction,
          }),
        onEventSummaryConfirm: (request) =>
          void controller.confirmEventSummary(request),
        onEmotionChange: setSelectedEmotion,
        onSubmitEmotion: (request) => void controller.submitEmotion(request),
        onGuidedAnswerChange: setGuidedAnswer,
        onSubmitGuidedAnswer: (request) => void handleGuidedSubmit(request),
        onApproveResult: (changes) =>
          void controller.updateAndApproveResult(changes),
        onRetryResult: () => void controller.fetchResult(),
        onCheckCurrentState: () => void controller.checkCurrentState(),
        onChooseHandling: (handling) => void handleChooseHandling(handling),
        onSaveReasonChange: setSaveReason,
        onReturnToHandlingSelection: handleReturnToHandlingSelection,
        onSave: handleSave,
        onFinishWithoutSaving: () => void discardAndReturnHome(),
        onFinishSafetyGuidance: () => void discardAndReturnHome(),
      }}
    />
  );
}
