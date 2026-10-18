import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { postMock, signOutMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  signOutMock: vi.fn(),
}));

let emitUser: (user: { uid: string } | null) => void = () => {};
let handleAuthFailureFromContext: (error: unknown) => Promise<boolean> =
  async () => false;

vi.mock("firebase/auth", () => ({
  onAuthStateChanged: (
    _auth: unknown,
    next: (user: { uid: string } | null) => void,
  ) => {
    emitUser = next;
    return () => {};
  },
  signOut: signOutMock,
}));

vi.mock("@/lib/firebase", () => ({ getFirebaseAuth: () => ({}) }));

vi.mock("@/lib/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/apiClient")>();
  return { ...actual, apiClient: { post: postMock } };
});

import { AuthProvider, useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/apiClient";

function Probe() {
  const {
    profile,
    profileStatus,
    profileErrorKind,
    signInNotice,
    handleAuthFailure,
  } = useAuth();
  handleAuthFailureFromContext = handleAuthFailure;
  return (
    <div>
      <p data-testid="status">{profileStatus}</p>
      <p data-testid="error">{profileErrorKind ?? ""}</p>
      <p data-testid="notice">{signInNotice ?? ""}</p>
      <p data-testid="seen">{profile ? String(profile.has_seen_notice) : ""}</p>
    </div>
  );
}

function renderAndLogin() {
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  act(() => emitUser({ uid: "u1" }));
}

beforeEach(() => {
  postMock.mockReset();
  signOutMock.mockReset().mockResolvedValue(undefined);
  handleAuthFailureFromContext = async () => false;
});

describe("AuthProvider", () => {
  it("ログイン後に POST /users/me を呼び、内部ユーザーを保持する", async () => {
    postMock.mockResolvedValue({ user_id: "uuid-1", has_seen_notice: false });

    renderAndLogin();

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("ready"),
    );
    expect(screen.getByTestId("seen")).toHaveTextContent("false");
    expect(postMock).toHaveBeenCalledWith(
      "/users/me",
      undefined,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(signOutMock).not.toHaveBeenCalled();
  });

  it("403 ACCOUNT_DELETING は通知を出してログアウトする", async () => {
    postMock.mockRejectedValue(
      new ApiError("forbidden", { status: 403, code: "ACCOUNT_DELETING" }),
    );

    renderAndLogin();

    await waitFor(() => expect(signOutMock).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("notice")).toHaveTextContent("account_deleting");
  });

  it("再試行後も401なら、通知を出してログアウトする", async () => {
    postMock.mockRejectedValue(new ApiError("unauthenticated", { status: 401 }));

    renderAndLogin();

    await waitFor(() => expect(signOutMock).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("notice")).toHaveTextContent("session_expired");
  });

  it("503(server)ではログアウトせず、再試行できる状態にする", async () => {
    postMock.mockRejectedValue(
      new ApiError("server", { status: 503, code: "AUTH_UNAVAILABLE" }),
    );

    renderAndLogin();

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("error"),
    );
    expect(screen.getByTestId("error")).toHaveTextContent("server");
    expect(signOutMock).not.toHaveBeenCalled();
  });

  it("通信失敗でもログアウトしない", async () => {
    postMock.mockRejectedValue(new ApiError("network"));

    renderAndLogin();

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("error"),
    );
    expect(screen.getByTestId("error")).toHaveTextContent("network");
    expect(signOutMock).not.toHaveBeenCalled();
  });

  it.each([
    [
      "保存件数上限の403",
      new ApiError("forbidden", {
        status: 403,
        code: "MEMO_LIMIT_EXCEEDED",
      }),
    ],
    ["通信失敗", new ApiError("network")],
    ["意図的なキャンセル", new ApiError("aborted")],
  ])("%sは認証失敗として扱わずログアウトしない", async (_name, error) => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    let handled = true;
    await act(async () => {
      handled = await handleAuthFailureFromContext(error);
    });

    expect(handled).toBe(false);
    expect(signOutMock).not.toHaveBeenCalled();
  });
});
