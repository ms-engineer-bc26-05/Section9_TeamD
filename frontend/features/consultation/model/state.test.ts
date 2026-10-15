import { describe, expect, it } from "vitest";

import {
  consultationReducer,
  initialConsultationState,
  isConsultationPending,
} from "./state";

describe("consultationReducer", () => {
  it("安全案内へ進んだら通常フローの状態を破棄する", () => {
    const previous = {
      ...initialConsultationState,
      consultationId: "c1",
      status: "result_ready" as const,
      result: {
        event_summary: "架空の出来事",
        emotion: "不安",
        true_feeling: "落ち着きたい",
        background: "",
        wish: "話し合いたい",
        approved: false,
      },
      handling: "tell" as const,
      approved: true,
    };

    const next = consultationReducer(previous, {
      type: "view_received",
      view: {
        consultation_id: "c1",
        status: "safety_guidance",
        safety_guidance: {
          risk_detected: true,
          safety_message: "安全を優先してください。",
          continued_normal_structuring: false,
        },
      },
    });

    expect(next.status).toBe("safety_guidance");
    expect(next.result).toBeNull();
    expect(next.handling).toBeNull();
    expect(next.approved).toBe(false);
  });

  it("状態不存在では内容を残さず専用エラーだけを保持する", () => {
    const next = consultationReducer(
      {
        ...initialConsultationState,
        consultationId: "c1",
        status: "guided_dialogue",
        aiQuestion: "架空の質問",
        currentTopic: "background",
      },
      { type: "session_lost" },
    );

    expect(next).toEqual({
      ...initialConsultationState,
      errorCode: "CONSULTATION_NOT_FOUND",
    });
  });

  it("復旧が必要な間は送信操作を保留扱いにする", () => {
    expect(
      isConsultationPending({
        ...initialConsultationState,
        recoveryRequired: true,
      }),
    ).toBe(true);
  });
});
