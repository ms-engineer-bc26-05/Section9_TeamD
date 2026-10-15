import { describe, expect, it, vi } from "vitest";

import { createMemoApi, type MemoAuthenticatedApiClient } from "./memoApi";

function createClient(): MemoAuthenticatedApiClient {
  return {
    get: vi.fn(),
    delete: vi.fn(),
  };
}

describe("createMemoApi", () => {
  it("初回一覧はcursorなしで取得する", async () => {
    const client = createClient();
    vi.mocked(client.get).mockResolvedValue({ memos: [], next_cursor: null });

    await createMemoApi(client).list();

    expect(client.get).toHaveBeenCalledWith("/memos", undefined);
  });

  it("不透明なcursorを解析せずURLエンコードして渡す", async () => {
    const client = createClient();
    vi.mocked(client.get).mockResolvedValue({ memos: [], next_cursor: null });

    await createMemoApi(client).list("created at+/id=");

    expect(client.get).toHaveBeenCalledWith(
      "/memos?cursor=created%20at%2B%2Fid%3D",
      undefined,
    );
  });

  it("詳細取得と削除でmemo IDをURLエンコードする", async () => {
    const client = createClient();
    vi.mocked(client.get).mockResolvedValue({});
    vi.mocked(client.delete).mockResolvedValue();
    const api = createMemoApi(client);

    await api.detail("memo/id");
    await api.delete("memo/id");

    expect(client.get).toHaveBeenCalledWith("/memos/memo%2Fid", undefined);
    expect(client.delete).toHaveBeenCalledWith("/memos/memo%2Fid", undefined);
  });
});
