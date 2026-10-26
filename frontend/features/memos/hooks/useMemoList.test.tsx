import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MemoApi } from "../api/memoApi";
import { useMemoList } from "./useMemoList";

function createApi(): MemoApi {
  return {
    list: vi.fn(),
    detail: vi.fn(),
    delete: vi.fn(),
  };
}

describe("useMemoList", () => {
  it("onApiErrorの参照が変わっても再取得せず、最新の関数へ通知する", async () => {
    const api = createApi();
    const error = { kind: "network" };
    vi.mocked(api.list)
      .mockResolvedValueOnce({ memos: [], next_cursor: "next" })
      .mockRejectedValueOnce(error);
    const firstHandler = vi.fn();
    const latestHandler = vi.fn();

    const { result, rerender } = renderHook(
      ({ onApiError }) => useMemoList(api, onApiError),
      { initialProps: { onApiError: firstHandler } },
    );

    await waitFor(() =>
      expect(result.current.state.isInitialLoading).toBe(false),
    );
    rerender({ onApiError: latestHandler });

    expect(api.list).toHaveBeenCalledOnce();

    await act(async () => {
      await result.current.loadMore();
    });

    expect(api.list).toHaveBeenCalledTimes(2);
    expect(firstHandler).not.toHaveBeenCalled();
    expect(latestHandler).toHaveBeenCalledOnce();
    expect(latestHandler).toHaveBeenCalledWith(error);
  });

  it("abortedを認証エラー処理へ通知しない", async () => {
    const api = createApi();
    vi.mocked(api.list)
      .mockResolvedValueOnce({ memos: [], next_cursor: "next" })
      .mockRejectedValueOnce({ kind: "aborted" });
    const onApiError = vi.fn();

    const { result } = renderHook(() => useMemoList(api, onApiError));

    await waitFor(() =>
      expect(result.current.state.isInitialLoading).toBe(false),
    );
    await act(async () => {
      await result.current.loadMore();
    });

    expect(onApiError).not.toHaveBeenCalled();
    expect(result.current.state.isLoadingMore).toBe(false);
  });
});
