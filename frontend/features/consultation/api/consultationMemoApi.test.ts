import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthenticatedApiClient } from "./consultationApi";
import { createConsultationMemoApi } from "./consultationMemoApi";

describe("createConsultationMemoApi", () => {
  const post = vi.fn();
  const client = {
    get: vi.fn(),
    post,
    patch: vi.fn(),
    delete: vi.fn(),
  } as unknown as AuthenticatedApiClient;
  const api = createConsultationMemoApi(client);

  beforeEach(() => {
    post.mockReset().mockResolvedValue({
      memo_id: "memo-1",
      created_at: "2026-10-13T12:00:00Z",
      handling: "hold",
      reason: null,
      event_summary: "架空の出来事",
    });
  });

  it("相談IDをエンコードして理由とAbortSignalを保存APIへ渡す", async () => {
    const signal = new AbortController().signal;

    await api.save("id/with space", { reason: "落ち着いて考えたい" }, { signal });

    expect(post).toHaveBeenCalledWith(
      "/consultations/id%2Fwith%20space/save",
      { reason: "落ち着いて考えたい" },
      { signal },
    );
  });

  it("理由が未入力の場合も本文を省略せずnullで送る", async () => {
    await api.save("c1", { reason: null });

    expect(post).toHaveBeenCalledWith(
      "/consultations/c1/save",
      { reason: null },
      undefined,
    );
  });
});
