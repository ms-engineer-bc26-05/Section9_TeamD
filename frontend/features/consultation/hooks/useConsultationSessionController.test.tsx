import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/apiClient";

import type { ConsultationApi } from "../api/consultationApi";
import type { ConsultationView } from "../model/contracts";
import { useConsultationSessionController } from "./useConsultationSessionController";

function createApi(): ConsultationApi {
  return {
    start: vi.fn(),
    get: vi.fn(),
    discard: vi.fn(),
    answerEvent: vi.fn(),
    confirmEventSummary: vi.fn(),
    submitEmotion: vi.fn(),
    answerGuidedDialogue: vi.fn(),
    getResult: vi.fn(),
    updateResult: vi.fn(),
    approveResult: vi.fn(),
    chooseHandling: vi.fn(),
  };
}

const startRequest = {
  theme: "communication" as const,
  detail: "架空の入力",
};

describe("useConsultationSessionController", () => {
  it("認証エラーを共通認証処理へ通知する", async () => {
    const api = createApi();
    const error = new ApiError("unauthenticated", { status: 401 });
    const onApiError = vi.fn();
    vi.mocked(api.start).mockRejectedValue(error);
    const { result } = renderHook(() =>
      useConsultationSessionController(api, onApiError),
    );

    await act(async () => {
      await result.current.startConsultation(startRequest);
    });

    expect(onApiError).toHaveBeenCalledOnce();
    expect(onApiError).toHaveBeenCalledWith(error);
    expect(result.current.state.errorCode).toBe("UNAUTHORIZED");
  });

  it("開始処理中に相談が失われた404では内容を破棄して状態消失へ切り替える", async () => {
    const api = createApi();
    vi.mocked(api.start).mockRejectedValue(
      new ApiError("not_found", { code: "CONSULTATION_NOT_FOUND" }),
    );
    const { result } = renderHook(() => useConsultationSessionController(api));

    let started = true;
    await act(async () => {
      started = await result.current.startConsultation(startRequest);
    });

    expect(started).toBe(false);
    expect(result.current.state).toMatchObject({
      consultationId: null,
      status: null,
      errorCode: "CONSULTATION_NOT_FOUND",
      pendingOperation: null,
    });
  });

  it("処理中に同じ操作を重ねてもAPIを二重送信しない", async () => {
    const api = createApi();
    let resolveStart: ((view: ConsultationView & { consultation_id: string }) => void) | null =
      null;
    vi.mocked(api.start).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveStart = resolve;
        }),
    );
    const { result } = renderHook(() => useConsultationSessionController(api));

    let firstRequest: Promise<boolean> | null = null;
    let secondRequest: Promise<boolean> | null = null;
    act(() => {
      firstRequest = result.current.startConsultation(startRequest);
      secondRequest = result.current.startConsultation(startRequest);
    });

    await expect(secondRequest).resolves.toBe(false);
    expect(api.start).toHaveBeenCalledOnce();

    await act(async () => {
      resolveStart?.({
        consultation_id: "c1",
        status: "emotion_selection",
      });
      await firstRequest;
    });
  });

  it("感情POSTのレスポンス未達時は再送せずGETで進行状態を確認する", async () => {
    const api = createApi();
    vi.mocked(api.start).mockResolvedValue({
      consultation_id: "c1",
      status: "emotion_selection",
    });
    vi.mocked(api.submitEmotion).mockRejectedValue(new ApiError("network"));
    vi.mocked(api.get).mockResolvedValue({
      consultation_id: "c1",
      status: "guided_dialogue",
      current_topic: "true_feeling",
      ai_question: "架空の質問",
    });
    const { result } = renderHook(() => useConsultationSessionController(api));

    await act(async () => {
      await result.current.startConsultation(startRequest);
    });

    let submitted = false;
    await act(async () => {
      submitted = await result.current.submitEmotion({
        category: "anxious",
        detail: "少し不安",
      });
    });

    expect(submitted).toBe(true);
    expect(api.submitEmotion).toHaveBeenCalledOnce();
    expect(api.get).toHaveBeenCalledOnce();
    expect(result.current.state.status).toBe("guided_dialogue");
    expect(result.current.state.currentTopic).toBe("true_feeling");
  });

  it("処理中のGETはバックエンドのAI再試行を含む60秒まで待つ", async () => {
    vi.useFakeTimers();

    try {
      const api = createApi();
      vi.mocked(api.start).mockResolvedValue({
        consultation_id: "c1",
        status: "emotion_selection",
      });
      vi.mocked(api.get).mockRejectedValue(
        new ApiError("conflict", { code: "CONSULTATION_BUSY" }),
      );
      const { result } = renderHook(() => useConsultationSessionController(api));

      await act(async () => {
        await result.current.startConsultation(startRequest);
      });

      let settled = false;
      let checking: Promise<boolean> | null = null;
      act(() => {
        checking = result.current.checkCurrentState();
        void checking.then(() => {
          settled = true;
        });
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(36_000);
      });
      expect(settled).toBe(false);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(24_000);
      });
      await expect(checking).resolves.toBe(false);
      expect(result.current.state.errorCode).toBe("CONSULTATION_BUSY");
    } finally {
      vi.useRealTimers();
    }
  });

  it("扱い方APIがstatusだけを返しても送信済みの選択を保存確認へ引き継ぐ", async () => {
    const api = createApi();
    vi.mocked(api.start).mockResolvedValue({
      consultation_id: "c1",
      status: "handling_selection",
    });
    vi.mocked(api.chooseHandling).mockResolvedValue({
      status: "save_confirmation",
    });
    const { result } = renderHook(() => useConsultationSessionController(api));

    await act(async () => {
      await result.current.startConsultation(startRequest);
    });

    let selected = false;
    await act(async () => {
      selected = await result.current.chooseHandling("hold");
    });

    expect(selected).toBe(true);
    expect(api.chooseHandling).toHaveBeenCalledWith(
      "c1",
      { handling: "hold" },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(result.current.state.status).toBe("save_confirmation");
    expect(result.current.state.handling).toBe("hold");
  });

  it("保存しない場合は相談を破棄して画面状態を初期化する", async () => {
    const api = createApi();
    vi.mocked(api.start).mockResolvedValue({
      consultation_id: "c1",
      status: "save_confirmation",
      handling: "hold",
    });
    vi.mocked(api.discard).mockResolvedValue(undefined);
    const { result } = renderHook(() => useConsultationSessionController(api));

    await act(async () => {
      await result.current.startConsultation(startRequest);
    });

    let discarded = false;
    await act(async () => {
      discarded = await result.current.discardConsultation();
    });

    expect(discarded).toBe(true);
    expect(api.discard).toHaveBeenCalledWith(
      "c1",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(result.current.state).toMatchObject({
      consultationId: null,
      status: null,
      pendingOperation: null,
      errorCode: null,
    });
  });

  it("破棄時の404は既に一時状態がないため終了成功として扱う", async () => {
    const api = createApi();
    vi.mocked(api.start).mockResolvedValue({
      consultation_id: "c1",
      status: "safety_guidance",
      safety_guidance: {
        risk_detected: true,
        safety_message: "固定の安全案内",
        continued_normal_structuring: false,
      },
    });
    vi.mocked(api.discard).mockRejectedValue(
      new ApiError("not_found", { code: "CONSULTATION_NOT_FOUND" }),
    );
    const { result } = renderHook(() => useConsultationSessionController(api));

    await act(async () => {
      await result.current.startConsultation(startRequest);
    });

    let discarded = false;
    await act(async () => {
      discarded = await result.current.discardConsultation();
    });

    expect(discarded).toBe(true);
    expect(result.current.state.consultationId).toBeNull();
    expect(result.current.state.status).toBeNull();
    expect(result.current.state.errorCode).toBeNull();
  });

  it("422では画面状態を更新せずGETによる復旧も行わない", async () => {
    const api = createApi();
    vi.mocked(api.start).mockResolvedValue({
      consultation_id: "c1",
      status: "emotion_selection",
      question_count: 2,
    });
    vi.mocked(api.submitEmotion).mockRejectedValue(
      new ApiError("validation", { code: "VALIDATION_ERROR" }),
    );
    const { result } = renderHook(() => useConsultationSessionController(api));

    await act(async () => {
      await result.current.startConsultation(startRequest);
    });

    await act(async () => {
      await result.current.submitEmotion({
        category: "anxious",
        detail: "少し不安",
      });
    });

    expect(api.get).not.toHaveBeenCalled();
    expect(result.current.state.status).toBe("emotion_selection");
    expect(result.current.state.questionCount).toBe(2);
    expect(result.current.state.errorCode).toBe("VALIDATION_ERROR");
  });
});
