import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { MemoApi } from "../api/memoApi";
import { MemoListContainer } from "./MemoListContainer";

const FIRST_MEMO = {
  memo_id: "memo-1",
  created_at: "2026-10-15T10:00:00Z",
  summary: "架空の出来事について整理したメモ",
  handling: "hold" as const,
};

const SECOND_MEMO = {
  memo_id: "memo-2",
  created_at: "2026-10-14T10:00:00Z",
  summary: "別の架空の出来事について整理したメモ",
  handling: "tell" as const,
};

function createApi(): MemoApi {
  return {
    list: vi.fn(),
    detail: vi.fn(),
    delete: vi.fn(),
  };
}

describe("MemoListContainer", () => {
  it("一覧を表示し、summaryを再加工せず詳細選択へ渡す", async () => {
    const api = createApi();
    vi.mocked(api.list).mockResolvedValue({
      memos: [FIRST_MEMO],
      next_cursor: null,
    });
    const onOpenMemo = vi.fn();

    render(
      <MemoListContainer
        api={api}
        onOpenMemo={onOpenMemo}
        onStartConsultation={vi.fn()}
      />,
    );

    expect(await screen.findByText(FIRST_MEMO.summary)).toBeInTheDocument();
    expect(screen.getByText("今は保留する")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: new RegExp(FIRST_MEMO.summary) }),
    );
    expect(onOpenMemo).toHaveBeenCalledWith("memo-1");
  });

  it("空状態から相談開始へ進める", async () => {
    const api = createApi();
    vi.mocked(api.list).mockResolvedValue({ memos: [], next_cursor: null });
    const onStartConsultation = vi.fn();

    render(
      <MemoListContainer
        api={api}
        onOpenMemo={vi.fn()}
        onStartConsultation={onStartConsultation}
      />,
    );

    expect(
      await screen.findByText("まだ保存したメモはありません。"),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "相談を始める" }));
    expect(onStartConsultation).toHaveBeenCalledOnce();
  });

  it("追加取得に失敗しても表示済み一覧を残し、再試行できる", async () => {
    const api = createApi();
    vi.mocked(api.list)
      .mockResolvedValueOnce({ memos: [FIRST_MEMO], next_cursor: "next value" })
      .mockRejectedValueOnce({ kind: "network" })
      .mockResolvedValueOnce({ memos: [SECOND_MEMO], next_cursor: null });

    render(
      <MemoListContainer
        api={api}
        onOpenMemo={vi.fn()}
        onStartConsultation={vi.fn()}
      />,
    );

    expect(await screen.findByText(FIRST_MEMO.summary)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "もっと見る" }));
    expect(
      await screen.findByText(/追加のメモを読み込めませんでした/),
    ).toBeInTheDocument();
    expect(screen.getByText(FIRST_MEMO.summary)).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "もう一度読み込む" }),
    );
    expect(await screen.findByText(SECOND_MEMO.summary)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "もっと見る" })).not.toBeInTheDocument();
    expect(api.list).toHaveBeenNthCalledWith(2, "next value");
    expect(api.list).toHaveBeenNthCalledWith(3, "next value");
  });

  it("初回取得失敗では再読み込み導線を表示する", async () => {
    const api = createApi();
    vi.mocked(api.list)
      .mockRejectedValueOnce({ kind: "server" })
      .mockResolvedValueOnce({ memos: [FIRST_MEMO], next_cursor: null });

    render(
      <MemoListContainer
        api={api}
        onOpenMemo={vi.fn()}
        onStartConsultation={vi.fn()}
      />,
    );

    expect(
      await screen.findByText(/保存メモを読み込めませんでした/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "再読み込み" }));
    await waitFor(() =>
      expect(screen.getByText(FIRST_MEMO.summary)).toBeInTheDocument(),
    );
  });

  it("追加取得中はもっと見るを無効にして二重取得を防ぐ", async () => {
    const api = createApi();
    let resolveNextPage: ((value: {
      memos: (typeof FIRST_MEMO)[];
      next_cursor: null;
    }) => void) | undefined;
    vi.mocked(api.list)
      .mockResolvedValueOnce({ memos: [FIRST_MEMO], next_cursor: "next" })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveNextPage = resolve;
          }),
      );

    render(
      <MemoListContainer
        api={api}
        onOpenMemo={vi.fn()}
        onStartConsultation={vi.fn()}
      />,
    );

    const button = await screen.findByRole("button", { name: "もっと見る" });
    await userEvent.dblClick(button);
    expect(api.list).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "読み込み中…" })).toBeDisabled();

    resolveNextPage?.({ memos: [], next_cursor: null });
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "読み込み中…" }),
      ).not.toBeInTheDocument(),
    );
  });
});
