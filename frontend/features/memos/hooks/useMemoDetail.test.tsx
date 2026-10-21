import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MemoApi } from "../api/memoApi";
import { useMemoDetail } from "./useMemoDetail";

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

describe("useMemoDetail", () => {
  it("onApiErrorの参照が変わっても再取得せず、最新の関数へ通知する", async () => {
    const error = { kind: "network" };
    const api: MemoApi = {
      list: vi.fn(),
      detail: vi.fn().mockResolvedValue(DETAIL),
      delete: vi.fn().mockRejectedValue(error),
    };
    const onDeleted = vi.fn();
    const firstHandler = vi.fn();
    const latestHandler = vi.fn();
    const { result, rerender } = renderHook(
      ({ onApiError }) =>
        useMemoDetail({
          memoId: "memo-1",
          api,
          onDeleted,
          onApiError,
        }),
      { initialProps: { onApiError: firstHandler } },
    );

    await waitFor(() => expect(result.current.loadState.status).toBe("ready"));
    rerender({ onApiError: latestHandler });

    expect(api.detail).toHaveBeenCalledOnce();

    await act(async () => {
      await result.current.confirmDelete();
    });

    expect(api.detail).toHaveBeenCalledOnce();
    expect(firstHandler).not.toHaveBeenCalled();
    expect(latestHandler).toHaveBeenCalledOnce();
    expect(latestHandler).toHaveBeenCalledWith(error);
  });

  it("abortedを認証エラー処理へ通知しない", async () => {
    const api: MemoApi = {
      list: vi.fn(),
      detail: vi.fn().mockResolvedValue(DETAIL),
      delete: vi.fn().mockRejectedValue({ kind: "aborted" }),
    };
    const onApiError = vi.fn();
    const { result } = renderHook(() =>
      useMemoDetail({
        memoId: "memo-1",
        api,
        onDeleted: vi.fn(),
        onApiError,
      }),
    );

    await waitFor(() => expect(result.current.loadState.status).toBe("ready"));
    await act(async () => {
      await result.current.confirmDelete();
    });

    expect(onApiError).not.toHaveBeenCalled();
    expect(result.current.deleteState).toEqual({ status: "idle", error: null });
  });

  it("状態更新前に削除確認が重なってもAPIを一度だけ呼ぶ", async () => {
    let resolveDelete: (() => void) | undefined;
    const api: MemoApi = {
      list: vi.fn(),
      detail: vi.fn().mockResolvedValue(DETAIL),
      delete: vi.fn(
        () =>
          new Promise<void>((resolve) => {
            resolveDelete = resolve;
          }),
      ),
    };
    const onDeleted = vi.fn();
    const { result } = renderHook(() =>
      useMemoDetail({ memoId: "memo-1", api, onDeleted }),
    );

    await waitFor(() => expect(result.current.loadState.status).toBe("ready"));

    act(() => {
      void result.current.confirmDelete();
      void result.current.confirmDelete();
    });

    expect(api.delete).toHaveBeenCalledOnce();

    resolveDelete?.();
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("memo-1"));
  });
});
