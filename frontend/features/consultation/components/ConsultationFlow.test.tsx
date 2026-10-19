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
    onReturnHomeFromSafetyGuidance: vi.fn(),
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
  it("整理結果の文字数上限をAPI契約に合わせる", () => {
    const actions = createActions();

    render(
      <ConsultationFlow
        state={{
          ...initialConsultationState,
          consultationId: "c1",
          status: "result_ready",
          result: {
            event_summary: "架空の出来事",
            emotion: "架空の感情",
            true_feeling: "架空の本音",
            background: "",
            wish: "架空の望み",
            approved: false,
          },
        }}
        draft={{
          selectedEmotion: null,
          guidedHistory: [],
          guidedAnswer: "",
          saveReason: "",
          isReselectingHandling: false,
        }}
        limits={{
          startDetail: 2000,
          eventAnswer: 1000,
          eventSummaryField: 500,
          emotionDetail: 300,
          guidedAnswer: 1000,
          resultField: 500,
          resultEmotion: 300,
          saveReason: 500,
        }}
        actions={actions}
        saveState={{ isSubmitting: false, errorCode: null }}
      />,
    );

    expect(screen.getByRole("textbox", { name: "感情" })).toHaveAttribute(
      "maxlength",
      "300",
    );
    expect(screen.getByRole("textbox", { name: "出来事" })).toHaveAttribute(
      "maxlength",
      "500",
    );
  });

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
          resultEmotion: 300,
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

  it("保存APIの404では内容を表示せず状態消失画面へ切り替える", async () => {
    const user = userEvent.setup();
    const actions = createActions();

    render(
      <ConsultationFlow
        state={{
          ...initialConsultationState,
          consultationId: "c1",
          status: "save_confirmation",
          handling: "hold",
        }}
        draft={{
          selectedEmotion: null,
          guidedHistory: [],
          guidedAnswer: "",
          saveReason: "架空の理由",
          isReselectingHandling: false,
        }}
        limits={{
          startDetail: 500,
          eventAnswer: 500,
          eventSummaryField: 500,
          emotionDetail: 500,
          guidedAnswer: 500,
          resultField: 500,
          resultEmotion: 300,
          saveReason: 500,
        }}
        actions={actions}
        saveState={{
          isSubmitting: false,
          errorCode: "CONSULTATION_NOT_FOUND",
        }}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "相談を続けるための情報を確認できませんでした",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("架空の理由")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "ホームへ戻る" }));
    expect(actions.onReturnHomeAfterStateLoss).toHaveBeenCalledOnce();
  });

  it("保存に失敗しても入力した理由を保持し手動で再試行できる", () => {
    const actions = createActions();

    render(
      <ConsultationFlow
        state={{
          ...initialConsultationState,
          consultationId: "c1",
          status: "save_confirmation",
          handling: "hold",
        }}
        draft={{
          selectedEmotion: null,
          guidedHistory: [],
          guidedAnswer: "",
          saveReason: "あとで落ち着いて考えたい",
          isReselectingHandling: false,
        }}
        limits={{
          startDetail: 500,
          eventAnswer: 500,
          eventSummaryField: 500,
          emotionDetail: 500,
          guidedAnswer: 500,
          resultField: 500,
          resultEmotion: 300,
          saveReason: 500,
        }}
        actions={actions}
        saveState={{
          isSubmitting: false,
          errorCode: "NETWORK_ERROR",
        }}
      />,
    );

    expect(screen.getByRole("textbox")).toHaveValue(
      "あとで落ち着いて考えたい",
    );
    expect(
      screen.getByText(
        "通信できませんでした。接続を確認して、もう一度お試しください。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "保存する" }),
    ).toBeEnabled();
  });

  it("扱い方の選び直しでは前回の選択と保存エラーを引き継がない", async () => {
    const user = userEvent.setup();
    const actions = createActions();

    render(
      <ConsultationFlow
        state={{
          ...initialConsultationState,
          consultationId: "c1",
          status: "save_confirmation",
          handling: "hold",
        }}
        draft={{
          selectedEmotion: null,
          guidedHistory: [],
          guidedAnswer: "",
          saveReason: "",
          isReselectingHandling: true,
        }}
        limits={{
          startDetail: 500,
          eventAnswer: 500,
          eventSummaryField: 500,
          emotionDetail: 500,
          guidedAnswer: 500,
          resultField: 500,
          resultEmotion: 300,
          saveReason: 500,
        }}
        actions={actions}
        saveState={{
          isSubmitting: false,
          errorCode: "NETWORK_ERROR",
        }}
      />,
    );

    const previousChoice = screen.getByRole("radio", {
      name: /今は保留する/,
    });
    expect(previousChoice).not.toBeChecked();
    expect(
      screen.queryByText(
        "通信できませんでした。接続を確認して、もう一度お試しください。",
      ),
    ).not.toBeInTheDocument();

    await user.click(previousChoice);
    expect(actions.onChooseHandling).toHaveBeenCalledWith("hold");
  });

  it("安全案内の終了に失敗した場合は再試行とホーム復帰を表示する", async () => {
    const user = userEvent.setup();
    const actions = createActions();

    render(
      <ConsultationFlow
        state={{
          ...initialConsultationState,
          consultationId: "c1",
          status: "safety_guidance",
          errorCode: "NETWORK_ERROR",
          safetyGuidance: {
            risk_detected: true,
            safety_message: "安全のため相談窓口をご案内します。",
            continued_normal_structuring: false,
          },
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
          resultEmotion: 300,
          saveReason: 500,
        }}
        actions={actions}
        saveState={{ isSubmitting: false, errorCode: null }}
      />,
    );

    expect(
      screen.getByText(
        "通信できませんでした。接続を確認して、もう一度お試しください。",
      ),
    ).toHaveAttribute("role", "alert");

    await user.click(screen.getByRole("button", { name: "もう一度終了する" }));
    expect(actions.onFinishSafetyGuidance).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "ホームへ戻る" }));
    expect(actions.onReturnHomeFromSafetyGuidance).toHaveBeenCalledOnce();
  });
});
