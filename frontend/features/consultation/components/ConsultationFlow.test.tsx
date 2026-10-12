import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { initialConsultationState } from "../model/state";
import { ConsultationFlow, type ConsultationFlowActions } from "./ConsultationFlow";

function createActions(): ConsultationFlowActions {
  return {
    onBackToNotice: vi.fn(),
    onReturnHomeAfterStateLoss: vi.fn(),
    onReturnHomeAfterUsageLimit: vi.fn(),
    onOpenPlan: vi.fn(),
    onCancel: vi.fn(),
    onStartConsultation: vi.fn(),
    onEventAnswer: vi.fn(),
    onEventCorrect: vi.fn(),
    onEventSummaryConfirm: vi.fn(),
    onEmotionChange: vi.fn(),
    onSubmitEmotion: vi.fn(),
    onGuidedAnswerChange: vi.fn(),
    onSubmitGuidedAnswer: vi.fn(),
    onApproveResult: vi.fn(),
    onRetryResult: vi.fn(),
    onCheckCurrentState: vi.fn(),
    onChooseHandling: vi.fn(),
    onSaveReasonChange: vi.fn(),
    onReturnToHandlingSelection: vi.fn(),
    onSave: vi.fn(),
    onFinishWithoutSaving: vi.fn(),
    onFinishSafetyGuidance: vi.fn(),
  };
}

describe("ConsultationFlow", () => {
  it("復旧が必要なときは再確認とホーム復帰の両方を表示する", async () => {
    const user = userEvent.setup();
    const actions = createActions();

    render(
      <ConsultationFlow
        state={{
          ...initialConsultationState,
          recoveryRequired: true,
          errorCode: "NETWORK_ERROR",
        }}
        draft={{
          selectedEmotion: null,
          guidedHistory: [],
          guidedAnswer: "",
          saveReason: "",
          isReselectingHandling: false,
        }}
        limits={{
          startDetail: 500,
          eventAnswer: 500,
          eventSummaryField: 500,
          emotionDetail: 500,
          guidedAnswer: 500,
          resultField: 500,
          saveReason: 500,
        }}
        actions={actions}
        saveState={{ isSubmitting: false, errorCode: null }}
      />,
    );

    expect(
      screen.getByRole("button", { name: "現在の状態を確認する" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "ホームへ戻る" }));

    expect(actions.onReturnHomeAfterStateLoss).toHaveBeenCalledOnce();
  });
});
