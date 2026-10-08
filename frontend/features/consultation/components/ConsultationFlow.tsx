"use client";

import type { ReactNode } from "react";

import type { GuidedDialogueHistoryItem } from "./GuidedDialogueStep";
import type {
  EmotionCategory,
  EmotionRequest,
  EventSummaryConfirmRequest,
  GuidedDialogueRequest,
  HandlingType,
  StartConsultationRequest,
  UpdateConsultationResultRequest,
} from "../model/contracts";
import type { ConsultationScreen } from "../model/screen";
import {
  isConsultationPending,
  type ConsultationState,
} from "../model/state";
import { ConsultationScreenRouter } from "./ConsultationScreenRouter";
import { ConsultationStartFlow } from "./ConsultationStartFlow";
import { ConsultationUnavailableStep } from "./ConsultationUnavailableStep";
import { EmotionInputFlow } from "./EmotionInputFlow";
import { EventDialogueStep } from "./EventDialogueStep";
import { EventSummaryStep } from "./EventSummaryStep";
import { GuidedDialogueStep } from "./GuidedDialogueStep";
import { HandlingSelectionStep } from "./HandlingSelectionStep";
import { ResultReviewStep } from "./ResultReviewStep";
import { SaveConfirmationStep } from "./SaveConfirmationStep";

export interface ConsultationFlowLimits {
  startDetail: number;
  eventAnswer: number;
  eventSummaryField: number;
  emotionDetail: number;
  guidedAnswer: number;
  resultField: number;
  saveReason: number;
}

export interface ConsultationFlowDraft {
  selectedEmotion: EmotionCategory | null;
  guidedHistory: readonly GuidedDialogueHistoryItem[];
  guidedAnswer: string;
  saveReason: string;
  isReselectingHandling: boolean;
}

export interface ConsultationFlowActions {
  onBackToNotice: () => void;
  onReturnHomeAfterStateLoss: () => void;
  onCancel: () => void;
  onStartConsultation: (request: StartConsultationRequest) => void;
  onEventAnswer: (answer: string) => void;
  onEventCorrect: (correction: string) => void;
  onEventSummaryConfirm: (request: EventSummaryConfirmRequest) => void;
  onEmotionChange: (emotion: EmotionCategory) => void;
  onSubmitEmotion: (request: EmotionRequest) => void;
  onGuidedAnswerChange: (answer: string) => void;
  onSubmitGuidedAnswer: (request: GuidedDialogueRequest) => void;
  onApproveResult: (changes: UpdateConsultationResultRequest) => void;
  onChooseHandling: (handling: HandlingType) => void;
  onSaveReasonChange: (reason: string) => void;
  onReturnToHandlingSelection: () => void;
  onSave: (reason: string | null) => void;
  onFinishWithoutSaving: () => void;
  onFinishSafetyGuidance: () => void;
}

interface ConsultationFlowProps {
  state: ConsultationState;
  draft: ConsultationFlowDraft;
  limits: ConsultationFlowLimits;
  actions: ConsultationFlowActions;
  resultLoadingScreen: ReactNode;
}

export function ConsultationFlow({
  state,
  draft,
  limits,
  actions,
  resultLoadingScreen,
}: ConsultationFlowProps) {
  const isSubmitting = isConsultationPending(state);
  const selectedEmotion = state.emotionCategory ?? draft.selectedEmotion;
  const unavailableScreen = (
    <ConsultationUnavailableStep
      onReturnHome={actions.onReturnHomeAfterStateLoss}
    />
  );

  const handlingSelectionScreen = (
    <HandlingSelectionStep
      selectedHandling={state.handling}
      isSubmitting={isSubmitting}
      onSelect={actions.onChooseHandling}
      onCancel={actions.onCancel}
    />
  );

  const screens = {
    start: (
      <ConsultationStartFlow
        detailMaxLength={limits.startDetail}
        isSubmitting={isSubmitting}
        startErrorCode={state.errorCode}
        onBackToNotice={actions.onBackToNotice}
        onCancel={actions.onCancel}
        onStartConsultation={actions.onStartConsultation}
      />
    ),
    state_unavailable: unavailableScreen,
    event_dialogue:
      state.aiQuestion !== null ? (
        <EventDialogueStep
          aiQuestion={state.aiQuestion}
          aiUnderstanding={state.aiUnderstanding}
          questionCount={state.questionCount ?? 0}
          correctionCount={state.correctionCount ?? 0}
          correctionLimitReached={state.correctionLimitReached ?? false}
          answerMaxLength={limits.eventAnswer}
          isSubmitting={isSubmitting}
          onAnswer={actions.onEventAnswer}
          onCorrect={actions.onEventCorrect}
          onCancel={actions.onCancel}
        />
      ) : (
        unavailableScreen
      ),
    event_summary_ready:
      state.eventDetails !== null ? (
        <EventSummaryStep
          eventDetails={state.eventDetails}
          questionCount={state.questionCount ?? 0}
          canAskMore={state.canAskMore ?? false}
          correctionLimitReached={state.correctionLimitReached ?? false}
          fieldMaxLength={limits.eventSummaryField}
          isSubmitting={isSubmitting}
          onProceed={actions.onEventSummaryConfirm}
          onAskMore={() =>
            actions.onEventSummaryConfirm({ action: "ask_more" })
          }
          onCancel={actions.onCancel}
        />
      ) : (
        unavailableScreen
      ),
    emotion_selection: (
      <EmotionInputFlow
        selectedEmotion={selectedEmotion}
        detailMaxLength={limits.emotionDetail}
        isSubmitting={isSubmitting}
        onEmotionChange={actions.onEmotionChange}
        onCancel={actions.onCancel}
        onSubmit={actions.onSubmitEmotion}
      />
    ),
    guided_dialogue:
      selectedEmotion !== null &&
      state.aiQuestion !== null &&
      state.currentTopic !== null ? (
        <GuidedDialogueStep
          selectedEmotion={selectedEmotion}
          aiResponse={state.aiResponse}
          aiQuestion={state.aiQuestion}
          currentTopic={state.currentTopic}
          history={draft.guidedHistory}
          answer={draft.guidedAnswer}
          answerMaxLength={limits.guidedAnswer}
          isSubmitting={isSubmitting}
          onAnswerChange={actions.onGuidedAnswerChange}
          onSubmit={actions.onSubmitGuidedAnswer}
          onCancel={actions.onCancel}
        />
      ) : (
        unavailableScreen
      ),
    result_loading: resultLoadingScreen,
    result_ready:
      state.result !== null ? (
        <ResultReviewStep
          result={state.result}
          fieldMaxLength={limits.resultField}
          isSubmitting={isSubmitting}
          onApprove={actions.onApproveResult}
          onCancel={actions.onCancel}
        />
      ) : (
        resultLoadingScreen
      ),
    handling_selection: handlingSelectionScreen,
    save_confirmation: draft.isReselectingHandling ? (
      handlingSelectionScreen
    ) : state.handling !== null ? (
      <SaveConfirmationStep
        handling={state.handling}
        reason={draft.saveReason}
        reasonMaxLength={limits.saveReason}
        isSubmitting={isSubmitting}
        onReasonChange={actions.onSaveReasonChange}
        onBack={actions.onReturnToHandlingSelection}
        onSave={actions.onSave}
        onFinishWithoutSaving={actions.onFinishWithoutSaving}
      />
    ) : (
      unavailableScreen
    ),
  } satisfies Record<ConsultationScreen, ReactNode>;

  return (
    <ConsultationScreenRouter
      state={state}
      screens={screens}
      onFinishSafetyGuidance={actions.onFinishSafetyGuidance}
    />
  );
}
