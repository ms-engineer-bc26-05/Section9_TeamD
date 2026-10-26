import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  pushMock,
  searchParamsGetMock,
  handleAuthFailureMock,
  containerPropsMock,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  searchParamsGetMock: vi.fn(),
  handleAuthFailureMock: vi.fn(),
  containerPropsMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => ({ get: searchParamsGetMock }),
}));

vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ handleAuthFailure: handleAuthFailureMock }),
}));

vi.mock("@/features/memos/api/authenticatedMemoApi", () => ({
  authenticatedMemoApi: { list: vi.fn(), detail: vi.fn(), delete: vi.fn() },
}));

vi.mock("@/features/memos/components/MemoListContainer", () => ({
  MemoListContainer: (props: {
    notice: string | null;
    onBackHome: () => void;
    onOpenMemo: (memoId: string) => void;
    onStartConsultation: () => void;
    onApiError: (error: unknown) => void;
  }) => {
    containerPropsMock(props);
    return (
      <div>
        <p>{props.notice}</p>
        <button type="button" onClick={props.onBackHome}>
          ホームへ
        </button>
        <button type="button" onClick={() => props.onOpenMemo("memo/id")}>
          詳細へ
        </button>
        <button type="button" onClick={props.onStartConsultation}>
          相談へ
        </button>
        <button
          type="button"
          onClick={() => props.onApiError({ kind: "network" })}
        >
          エラー通知
        </button>
      </div>
    );
  },
}));

import MemoListPage from "./page";

beforeEach(() => {
  pushMock.mockReset();
  searchParamsGetMock.mockReset().mockReturnValue(null);
  handleAuthFailureMock.mockReset().mockResolvedValue(false);
  containerPropsMock.mockReset();
});

describe("MemoListPage", () => {
  it("削除完了通知を表示し、ホーム・詳細・相談開始へ遷移する", async () => {
    searchParamsGetMock.mockReturnValue("1");
    render(<MemoListPage />);

    expect(screen.getByText("メモを削除しました。")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "ホームへ" }));
    await userEvent.click(screen.getByRole("button", { name: "詳細へ" }));
    await userEvent.click(screen.getByRole("button", { name: "相談へ" }));

    expect(pushMock).toHaveBeenNthCalledWith(1, "/home");
    expect(pushMock).toHaveBeenNthCalledWith(2, "/memos/memo%2Fid");
    expect(pushMock).toHaveBeenNthCalledWith(3, "/notice");
  });

  it("APIエラーを共通認証処理へ渡す", async () => {
    render(<MemoListPage />);

    await userEvent.click(screen.getByRole("button", { name: "エラー通知" }));

    expect(handleAuthFailureMock).toHaveBeenCalledWith({ kind: "network" });
  });
});
