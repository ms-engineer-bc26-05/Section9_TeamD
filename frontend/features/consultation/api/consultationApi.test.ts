import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createConsultationApi,
  type AuthenticatedApiClient,
} from "./consultationApi";

const view = {
  consultation_id: "consultation-1",
  status: "event_dialogue" as const,
};

describe("createConsultationApi", () => {
  const get = vi.fn();
  const post = vi.fn();
  const patch = vi.fn();
  const deleteRequest = vi.fn();
  const client = {
    get,
    post,
    patch,
    delete: deleteRequest,
  } as unknown as AuthenticatedApiClient;
  const api = createConsultationApi(client);

  beforeEach(() => {
    get.mockReset().mockResolvedValue(view);
    post.mockReset().mockResolvedValue(view);
    patch.mockReset().mockResolvedValue({
      event_summary: "架空の出来事",
      emotion: "不安",
      true_feeling: "落ち着きたい",
      background: "",
      wish: "話し合いたい",
      approved: false,
    });
    deleteRequest.mockReset().mockResolvedValue(undefined);
  });

  it("相談開始リクエストとAbortSignalを共通クライアントへ渡す", async () => {
    const signal = new AbortController().signal;
    const request = { theme: "communication" as const, detail: "架空の入力" };

    await api.start(request, { signal });

    expect(post).toHaveBeenCalledWith("/consultations", request, { signal });
  });

  it("相談IDをエンコードして取得・破棄する", async () => {
    const signal = new AbortController().signal;

    await api.get("id/with space", { signal });
    await api.discard("id/with space", { signal });

    expect(get).toHaveBeenCalledWith("/consultations/id%2Fwith%20space", {
      signal,
    });
    expect(deleteRequest).toHaveBeenCalledWith(
      "/consultations/id%2Fwith%20space",
      { signal },
    );
  });

  it("各更新操作を確定した相談APIのパスへ送る", async () => {
    const signal = new AbortController().signal;
    const options = { signal };

    await api.answerEvent("c1", { action: "answer", answer: "架空の回答" }, options);
    await api.confirmEventSummary("c1", { action: "proceed" }, options);
    await api.submitEmotion(
      "c1",
      { category: "anxious", detail: "少し不安" },
      options,
    );
    await api.answerGuidedDialogue("c1", { skipped: true }, options);
    await api.approveResult("c1", options);
    await api.chooseHandling("c1", { handling: "hold" }, options);

    expect(post.mock.calls).toEqual([
      [
        "/consultations/c1/event-dialogue",
        { action: "answer", answer: "架空の回答" },
        options,
      ],
      ["/consultations/c1/event-summary/confirm", { action: "proceed" }, options],
      [
        "/consultations/c1/emotion",
        { category: "anxious", detail: "少し不安" },
        options,
      ],
      ["/consultations/c1/guided-dialogue", { skipped: true }, options],
      ["/consultations/c1/result/approve", undefined, options],
      ["/consultations/c1/handling", { handling: "hold" }, options],
    ]);
  });

  it("整理結果の取得と部分更新を確定したパスへ送る", async () => {
    const signal = new AbortController().signal;
    const changes = { wish: "ゆっくり話し合いたい" };

    await api.getResult("c1", { signal });
    await api.updateResult("c1", changes, { signal });

    expect(get).toHaveBeenCalledWith("/consultations/c1/result", { signal });
    expect(patch).toHaveBeenCalledWith(
      "/consultations/c1/result",
      changes,
      { signal },
    );
  });
});
