import { describe, expect, it } from "vitest";

import {
  areResultChangesApplied,
  decideApprovalRecovery,
  decidePostRecovery,
  decideResultUpdateRecovery,
} from "./recovery";

describe("相談APIのレスポンス未達後の復旧判定", () => {
  it("statusが進んでいればPOST成功済みとして扱う", () => {
    expect(
      decidePostRecovery(
        { status: "emotion_selection", currentTopic: null },
        { status: "guided_dialogue", current_topic: "true_feeling" },
      ),
    ).toBe("advanced");
  });

  it("guided_dialogueのtopicが進んでいればPOSTを再送しない", () => {
    expect(
      decidePostRecovery(
        { status: "guided_dialogue", currentTopic: "true_feeling" },
        { status: "guided_dialogue", current_topic: "background" },
      ),
    ).toBe("advanced");
  });

  it("statusとtopicが変わっていなければ再試行可能と判定する", () => {
    expect(
      decidePostRecovery(
        { status: "guided_dialogue", currentTopic: "background" },
        { status: "guided_dialogue", current_topic: "background" },
      ),
    ).toBe("retry");
  });

  it("安全案内を通常フローへ戻さない", () => {
    expect(
      decidePostRecovery(
        { status: "event_summary_ready", currentTopic: null },
        { status: "safety_guidance" },
      ),
    ).toBe("safety_guidance");
  });

  it("PATCH未達時は編集可能状態だけ結果を再取得する", () => {
    expect(decideResultUpdateRecovery("result_ready")).toBe("fetch_result");
    expect(decideResultUpdateRecovery("handling_selection")).toBe("advanced");
    expect(decideResultUpdateRecovery("save_confirmation")).toBe("advanced");
  });

  it("送信した部分更新が反映済みかだけを比較する", () => {
    const result = {
      event_summary: "架空の出来事",
      emotion: "不安",
      true_feeling: "落ち着きたい",
      background: "",
      wish: "ゆっくり話し合いたい",
      approved: false,
    };

    expect(areResultChangesApplied({ wish: result.wish }, result)).toBe(true);
    expect(areResultChangesApplied({ wish: "別の希望" }, result)).toBe(false);
  });

  it("承認後の状態では承認POSTを再送しない", () => {
    expect(decideApprovalRecovery("handling_selection")).toBe("approved");
    expect(decideApprovalRecovery("save_confirmation")).toBe("approved");
    expect(decideApprovalRecovery("result_ready")).toBe("retry");
  });
});
