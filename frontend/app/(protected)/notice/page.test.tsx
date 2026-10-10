import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { pushMock, patchMock, setHasSeenNoticeMock, handleAuthFailureMock, useAuthMock } = vi.hoisted(
  () => ({
    pushMock: vi.fn(),
    patchMock: vi.fn(),
    setHasSeenNoticeMock: vi.fn(),
    handleAuthFailureMock: vi.fn(),
    useAuthMock: vi.fn(),
  }),
);

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));
vi.mock("@/components/AuthProvider", () => ({ useAuth: useAuthMock }));
vi.mock("@/lib/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/apiClient")>();
  return { ...actual, apiClient: { patch: patchMock } };
});

import NoticePage from "./page";
import { ApiError } from "@/lib/apiClient";

function setProfile(hasSeenNotice: boolean) {
  useAuthMock.mockReturnValue({
    profile: { user_id: "uuid-1", has_seen_notice: hasSeenNotice },
    setHasSeenNotice: setHasSeenNoticeMock,
    handleAuthFailure: handleAuthFailureMock,
  });
}

beforeEach(() => {
  pushMock.mockReset();
  patchMock.mockReset().mockResolvedValue({});
  setHasSeenNoticeMock.mockReset();
  handleAuthFailureMock.mockReset().mockResolvedValue(false);
});

describe("NoticePage", () => {
  it("初回は詳しい注意を表示し、同意でPATCHして進む", async () => {
    setProfile(false);
    render(<NoticePage />);

    expect(screen.getByText("詳しい注意")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "同意して進む" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(patchMock).toHaveBeenCalledWith("/users/me", { has_seen_notice: true });
    expect(setHasSeenNoticeMock).toHaveBeenCalledWith(true);
  });

  it("2回目以降は短い表示で、詳しい注意と相談窓口の導線を残し、PATCHは呼ばない", async () => {
    setProfile(true);
    render(<NoticePage />);

    expect(screen.queryByText("詳しい注意")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "詳しい注意を見る" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "つらさが強いときの相談窓口" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "確認して進む" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(patchMock).not.toHaveBeenCalled();
  });

  it("保存に失敗したら、エラーを表示して進まない", async () => {
    setProfile(false);
    patchMock.mockRejectedValue(new ApiError("server", { status: 503 }));
    render(<NoticePage />);

    await userEvent.click(screen.getByRole("button", { name: "同意して進む" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("401(再試行後)ならログアウト処理に任せ、エラー表示も遷移もしない", async () => {
    setProfile(false);
    const error = new ApiError("unauthenticated", { status: 401 });
    patchMock.mockRejectedValue(error);
    handleAuthFailureMock.mockResolvedValue(true);
    render(<NoticePage />);

    await userEvent.click(screen.getByRole("button", { name: "同意して進む" }));

    await waitFor(() =>
      expect(handleAuthFailureMock).toHaveBeenCalledWith(error),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(setHasSeenNoticeMock).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("403 ACCOUNT_DELETINGでも、ログアウト処理に任せ、エラー表示も遷移もしない", async () => {
    setProfile(false);
    const error = new ApiError("forbidden", {
      status: 403,
      code: "ACCOUNT_DELETING",
    });
    patchMock.mockRejectedValue(error);
    handleAuthFailureMock.mockResolvedValue(true);
    render(<NoticePage />);

    await userEvent.click(screen.getByRole("button", { name: "同意して進む" }));

    await waitFor(() =>
      expect(handleAuthFailureMock).toHaveBeenCalledWith(error),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(setHasSeenNoticeMock).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });
});