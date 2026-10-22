import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { MemoApi } from "../api/memoApi";
import { MemoDetailContainer } from "./MemoDetailContainer";

const DETAIL = {
  memo_id: "memo-1",
  created_at: "2026-10-15T10:00:00Z",
  event_summary: "架空の出来事",
  emotion: "寂しい",
  true_feeling: "大切にしたい",
  background: "",
  wish: "落ち着いて話したい",
  handling: "hold" as const,
  reason: null,
};

function createApi(): MemoApi {
  return {
    list: vi.fn(),
    detail: vi.fn().mockResolvedValue(DETAIL),
    delete: vi.fn(),
  };
}

describe("MemoDetailContainer", () => {
  it("詳細の全項目と空項目の未記入表示を行う", async () => {
    const api = createApi();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    expect(await screen.findByText("架空の出来事")).toBeInTheDocument();
    expect(screen.getByText("寂しい")).toBeInTheDocument();
    expect(screen.getByText("大切にしたい")).toBeInTheDocument();
    expect(screen.getByText("落ち着いて話したい")).toBeInTheDocument();
    expect(screen.getByText("今は保留する")).toBeInTheDocument();
    expect(screen.getAllByText("未記入")).toHaveLength(2);
  });

  it("確認をキャンセルした場合は削除しない", async () => {
    const api = createApi();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    await screen.findByText("架空の出来事");
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("204相当の削除成功を呼び出し元へ通知する", async () => {
    const api = createApi();
    vi.mocked(api.delete).mockResolvedValue();
    const onDeleted = vi.fn();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={onDeleted}
      />,
    );

    await screen.findByText("架空の出来事");
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    await userEvent.click(screen.getByRole("button", { name: "削除する" }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("memo-1"));
  });

  it("削除処理中の連続操作ではAPIを一度だけ呼ぶ", async () => {
    const api = createApi();
    let resolveDelete: (() => void) | undefined;
    vi.mocked(api.delete).mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveDelete = resolve;
        }),
    );
    const onDeleted = vi.fn();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={onDeleted}
      />,
    );

    await screen.findByText("架空の出来事");
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    await userEvent.dblClick(screen.getByRole("button", { name: "削除する" }));

    expect(api.delete).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "削除中…" })).toBeDisabled();

    resolveDelete?.();
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("memo-1"));
  });

  it("通信失敗後の再試行404だけを削除済みとして扱う", async () => {
    const api = createApi();
    vi.mocked(api.delete)
      .mockRejectedValueOnce({ kind: "network" })
      .mockRejectedValueOnce({ kind: "not_found", code: "MEMO_NOT_FOUND" });
    const onDeleted = vi.fn();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={onDeleted}
      />,
    );

    await screen.findByText("架空の出来事");
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    await userEvent.click(screen.getByRole("button", { name: "削除する" }));
    expect(
      await screen.findByText(/削除結果を確認できませんでした/),
    ).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "もう一度削除" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("memo-1"));
  });

  it("削除結果不明後にキャンセルした場合は次の操作を再試行扱いにしない", async () => {
    const api = createApi();
    vi.mocked(api.delete)
      .mockRejectedValueOnce({ kind: "network" })
      .mockRejectedValueOnce({ kind: "not_found", code: "MEMO_NOT_FOUND" });
    const onDeleted = vi.fn();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={onDeleted}
      />,
    );

    await screen.findByText("架空の出来事");
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    await userEvent.click(screen.getByRole("button", { name: "削除する" }));
    expect(
      await screen.findByText(/削除結果を確認できませんでした/),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    await userEvent.click(screen.getByRole("button", { name: "削除する" }));

    expect(await screen.findByText("このメモは表示できません。")).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("最初の削除操作の404は削除成功とみなさない", async () => {
    const api = createApi();
    vi.mocked(api.delete).mockRejectedValue({
      kind: "not_found",
      code: "MEMO_NOT_FOUND",
    });
    const onDeleted = vi.fn();
    const onBackToList = vi.fn();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={onBackToList}
        onDeleted={onDeleted}
      />,
    );

    await screen.findByText("架空の出来事");
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    await userEvent.click(screen.getByRole("button", { name: "削除する" }));

    expect(await screen.findByText("このメモは表示できません。")).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "一覧へ戻る" }));
    expect(onBackToList).toHaveBeenCalledOnce();
  });

  it("詳細404は理由を区別せず一覧へ戻る導線を残す", async () => {
    const api = createApi();
    vi.mocked(api.detail).mockRejectedValue({
      kind: "not_found",
      code: "MEMO_NOT_FOUND",
    });
    const onBackToList = vi.fn();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={onBackToList}
        onDeleted={vi.fn()}
      />,
    );

    expect(await screen.findByText("このメモは表示できません。")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "保存メモ一覧へ戻る" }),
    );
    expect(onBackToList).toHaveBeenCalledOnce();
  });

  it("APIエラーを共通認証処理へ通知する", async () => {
    const api = createApi();
    const error = { kind: "forbidden", code: "ACCOUNT_DELETING" };
    const onApiError = vi.fn();
    vi.mocked(api.detail).mockRejectedValue(error);

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={vi.fn()}
        onApiError={onApiError}
      />,
    );

    await screen.findByText(/保存メモを読み込めませんでした/);
    expect(onApiError).toHaveBeenCalledOnce();
    expect(onApiError).toHaveBeenCalledWith(error);
  });

  it("削除500では詳細を残して再試行できる", async () => {
    const api = createApi();
    vi.mocked(api.delete)
      .mockRejectedValueOnce({ kind: "server" })
      .mockResolvedValueOnce();
    const onDeleted = vi.fn();

    render(
      <MemoDetailContainer
        memoId="memo-1"
        api={api}
        onBackToList={vi.fn()}
        onDeleted={onDeleted}
      />,
    );

    await screen.findByText("架空の出来事");
    await userEvent.click(screen.getByRole("button", { name: "このメモを削除" }));
    await userEvent.click(screen.getByRole("button", { name: "削除する" }));
    expect(
      await screen.findByText(/メモを削除できませんでした/),
    ).toBeInTheDocument();
    expect(screen.getByText("架空の出来事")).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "削除する" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("memo-1"));
  });
});
