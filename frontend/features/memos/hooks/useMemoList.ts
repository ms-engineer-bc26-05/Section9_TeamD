"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { MemoApi } from "../api/memoApi";
import {
  toMemoApiFailure,
  type MemoErrorCode,
} from "../api/memoApiError";
import type { MemoListItem } from "../model/contracts";

export interface MemoListState {
  memos: MemoListItem[];
  nextCursor: string | null;
  isInitialLoading: boolean;
  isLoadingMore: boolean;
  initialError: MemoErrorCode | null;
  loadMoreError: MemoErrorCode | null;
}

const INITIAL_STATE: MemoListState = {
  memos: [],
  nextCursor: null,
  isInitialLoading: true,
  isLoadingMore: false,
  initialError: null,
  loadMoreError: null,
};

export function useMemoList(
  api: MemoApi,
  onApiError?: (error: unknown) => void,
) {
  const [state, setState] = useState<MemoListState>(INITIAL_STATE);
  const initialRequest = useRef<AbortController | null>(null);
  const loadingMore = useRef(false);

  const loadInitial = useCallback(async () => {
    initialRequest.current?.abort();
    const controller = new AbortController();
    initialRequest.current = controller;
    setState({ ...INITIAL_STATE });

    try {
      const response = await api.list(undefined, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setState({
        memos: response.memos,
        nextCursor: response.next_cursor,
        isInitialLoading: false,
        isLoadingMore: false,
        initialError: null,
        loadMoreError: null,
      });
    } catch (error) {
      if (controller.signal.aborted) return;
      onApiError?.(error);
      const failure = toMemoApiFailure(error);
      if (failure.type === "aborted") return;
      setState((current) => ({
        ...current,
        isInitialLoading: false,
        initialError: failure.code,
      }));
    }
  }, [api, onApiError]);

  useEffect(() => {
    void loadInitial();
    return () => initialRequest.current?.abort();
  }, [loadInitial]);

  const loadMore = useCallback(async () => {
    if (loadingMore.current || state.nextCursor === null) return;
    loadingMore.current = true;
    const cursor = state.nextCursor;
    setState((current) => ({
      ...current,
      isLoadingMore: true,
      loadMoreError: null,
    }));

    try {
      const response = await api.list(cursor);
      setState((current) => ({
        ...current,
        memos: [...current.memos, ...response.memos],
        nextCursor: response.next_cursor,
        isLoadingMore: false,
        loadMoreError: null,
      }));
      loadingMore.current = false;
    } catch (error) {
      onApiError?.(error);
      const failure = toMemoApiFailure(error);
      loadingMore.current = false;
      if (failure.type === "aborted") return;
      setState((current) => ({
        ...current,
        isLoadingMore: false,
        loadMoreError: failure.code,
      }));
    }
  }, [api, onApiError, state.nextCursor]);

  return {
    state,
    reload: loadInitial,
    loadMore,
  };
}
