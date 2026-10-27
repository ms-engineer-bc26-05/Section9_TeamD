import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  pushMock,
  replaceMock,
  handleAuthFailureMock,
  containerPropsMock,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
  handleAuthFailureMock: vi.fn(),
  containerPropsMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  useParams: () => ({ memoId: "memo-1" }),
}));

vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ handleAuthFailure: handleAuthFailureMock }),
}));

vi.mock("@/features/memos/api/authenticatedMemoApi", () => ({
  authenticatedMemoApi: { list: vi.fn(), detail: vi.fn(), delete: vi.fn() },
}));

vi.mock("@/features/memos/components/MemoDetailContainer", () => ({
  MemoDetailContainer: (props: {
    memoId: string;
    onBackToList: () => void;
    onDeleted: (memoId: string) => void;
    onApiError: (error: unknown) => void;
  }) => {
    containerPropsMock(props);
    return (
      <div>
        <p>{props.memoId}</p>
        <button type="button" onClick={props.onBackToList}>
          一覧へ
        </button>
        <button type="button" onClick={() => props.onDeleted(props.memoId)}>
          削除完了
        </button>
        <button
          type="button"
          onClick={() => props.onApiError({ kind: "unauthenticated" })}
        >
          エラー通知
        </button>
      </div>
    );
  },
}));

import MemoDetailPage from "./page";

beforeEach(() => {
  pushMock.mockReset();
  replaceMock.mockReset();
  handleAuthFailureMock.mockReset().mockResolvedValue(false);
  containerPropsMock.mockReset();
});

describe("MemoDetailPage", () => {
  it("URLのIDを詳細へ渡し、一覧遷移と削除完了通知を接続する", async () => {
    render(<MemoDetailPage />);

    expect(screen.getByText("memo-1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "一覧へ" }));
    await userEvent.click(screen.getByRole("button", { name: "削除完了" }));

    expect(pushMock).toHaveBeenCalledWith("/memos");
    expect(replaceMock).toHaveBeenCalledWith("/memos?deleted=1");
  });

  it("APIエラーを共通認証処理へ渡す", async () => {
    render(<MemoDetailPage />);

    await userEvent.click(screen.getByRole("button", { name: "エラー通知" }));

    expect(handleAuthFailureMock).toHaveBeenCalledWith({
      kind: "unauthenticated",
    });
  });
});
