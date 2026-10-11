import { beforeEach, describe, expect, it, vi } from "vitest";

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));

vi.mock("@/lib/firebase", () => ({
  getFirebaseAuth: () => ({ currentUser: { getIdToken } }),
}));

import { apiClient, ApiError } from "@/lib/apiClient";

const fetchMock = vi.fn();

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

async function catchError(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (e) {
    return e;
  }
  throw new Error("エラーになるはずでした");
}

beforeEach(() => {
  getIdToken.mockReset().mockResolvedValue("dummy-token");
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("apiClient", () => {
  it("Authorizationヘッダを付けて /api/v1 配下を呼ぶ", async () => {
    fetchMock.mockResolvedValueOnce(json({ user_id: "u1", has_seen_notice: false }));

    const me = await apiClient.post<{ user_id: string }>("/users/me");

    expect(me.user_id).toBe("u1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/users/me");
    expect(init.headers.Authorization).toBe("Bearer dummy-token");
  });

  it("401は強制更新して1回だけ再試行する", async () => {
    fetchMock
      .mockResolvedValueOnce(json({}, 401))
      .mockResolvedValueOnce(json({ ok: true }));

    await apiClient.get("/users/me");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getIdToken).toHaveBeenNthCalledWith(1, false);
    expect(getIdToken).toHaveBeenNthCalledWith(2, true);
  });

  it("再試行後も401なら、繰り返さず unauthenticated を投げる", async () => {
    fetchMock.mockResolvedValue(json({}, 401));

    const error = await catchError(apiClient.get("/users/me"));

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe("unauthenticated");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("503は再試行せず、kind=server と code を返す", async () => {
    fetchMock.mockResolvedValue(
      json({ error: { code: "AUTH_UNAVAILABLE", message: "x" } }, 503),
    );

    const error = (await catchError(apiClient.get("/users/me"))) as ApiError;

    expect(error.kind).toBe("server");
    expect(error.code).toBe("AUTH_UNAVAILABLE");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getIdToken).toHaveBeenCalledTimes(1);
  });

  it("403は forbidden と code を保持する(一律に退会扱いしない)", async () => {
    fetchMock.mockResolvedValue(
      json({ error: { code: "ACCOUNT_DELETING", message: "x" } }, 403),
    );

    const error = (await catchError(apiClient.post("/users/me"))) as ApiError;

    expect(error.kind).toBe("forbidden");
    expect(error.code).toBe("ACCOUNT_DELETING");
  });

  it("旧形式の本文は読まず、固定メッセージにする", async () => {
    fetchMock.mockResolvedValue(json({ detail: "secret-detail" }, 500));

    const error = (await catchError(apiClient.get("/x"))) as ApiError;

    expect(error.kind).toBe("server");
    expect(error.code).toBeUndefined();
    expect(error.message).not.toContain("secret-detail");
  });

  it("通信失敗は network、AbortSignalによる中断は aborted", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("failed"));
    expect(((await catchError(apiClient.get("/x"))) as ApiError).kind).toBe("network");

    fetchMock.mockRejectedValueOnce(new DOMException("aborted", "AbortError"));
    expect(((await catchError(apiClient.get("/x"))) as ApiError).kind).toBe("aborted");
  });

    it("初回のトークン取得で通信失敗なら、network を投げ、fetch は呼ばない", async () => {
    getIdToken.mockRejectedValue({ code: "auth/network-request-failed" });

    const error = await catchError(apiClient.get("/users/me"));

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe("network");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("401後の強制更新で通信失敗なら、unauthenticated ではなく network を投げる", async () => {
    getIdToken
      .mockResolvedValueOnce("dummy-token")
      .mockRejectedValueOnce({ code: "auth/network-request-failed" });
    fetchMock.mockResolvedValueOnce(json({}, 401));

    const error = await catchError(apiClient.get("/users/me"));

    expect((error as ApiError).kind).toBe("network");
    expect(getIdToken).toHaveBeenNthCalledWith(2, true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("トークン取得が通信失敗以外で失敗したら、unauthenticated を投げる", async () => {
    getIdToken.mockRejectedValue({ code: "auth/user-token-expired" });

    const error = await catchError(apiClient.get("/users/me"));

    expect((error as ApiError).kind).toBe("unauthenticated");
  });
});