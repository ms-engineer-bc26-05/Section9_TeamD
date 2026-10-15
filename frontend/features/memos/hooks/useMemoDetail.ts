"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { MemoApi } from "../api/memoApi";
import {
  toMemoApiFailure,
  type MemoErrorCode,
} from "../api/memoApiError";
import type { MemoDetail } from "../model/contracts";

export type MemoDetailLoadState =
  | { status: "loading"; memo: null; error: null }
  | { status: "ready"; memo: MemoDetail; error: null }
  | { status: "error"; memo: null; error: MemoErrorCode };

export type MemoDeleteState =
  | { status: "idle"; error: null }
  | { status: "confirming"; error: null }
  | { status: "deleting"; error: null }
  | { status: "unknown"; error: "NETWORK_ERROR" }
  | { status: "error"; error: MemoErrorCode };

interface UseMemoDetailOptions {
  memoId: string;
  api: MemoApi;
  onDeleted: (memoId: string) => void;
}

export function useMemoDetail({ memoId, api, onDeleted }: UseMemoDetailOptions) {
  const [loadState, setLoadState] = useState<MemoDetailLoadState>({
    status: "loading",
    memo: null,
    error: null,
  });
  const [deleteState, setDeleteState] = useState<MemoDeleteState>({
    status: "idle",
    error: null,
  });
  const loadRequest = useRef<AbortController | null>(null);
  const deleteOutcomeUnknown = useRef(false);

  const load = useCallback(async () => {
    loadRequest.current?.abort();
    const controller = new AbortController();
    loadRequest.current = controller;
    setLoadState({ status: "loading", memo: null, error: null });

    try {
      const memo = await api.detail(memoId, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setLoadState({ status: "ready", memo, error: null });
    } catch (error) {
      if (controller.signal.aborted) return;
      const failure = toMemoApiFailure(error);
      if (failure.type === "aborted") return;
      setLoadState({ status: "error", memo: null, error: failure.code });
    }
  }, [api, memoId]);

  useEffect(() => {
    deleteOutcomeUnknown.current = false;
    setDeleteState({ status: "idle", error: null });
    void load();
    return () => loadRequest.current?.abort();
  }, [load]);

  const requestDelete = useCallback(() => {
    setDeleteState({ status: "confirming", error: null });
  }, []);

  const cancelDelete = useCallback(() => {
    setDeleteState({ status: "idle", error: null });
  }, []);

  const confirmDelete = useCallback(async () => {
    setDeleteState({ status: "deleting", error: null });
    try {
      await api.delete(memoId);
      deleteOutcomeUnknown.current = false;
      onDeleted(memoId);
    } catch (error) {
      const failure = toMemoApiFailure(error);
      if (failure.type === "aborted") {
        setDeleteState({ status: "idle", error: null });
        return;
      }
      if (
        failure.code === "MEMO_NOT_FOUND" &&
        deleteOutcomeUnknown.current
      ) {
        deleteOutcomeUnknown.current = false;
        onDeleted(memoId);
        return;
      }
      if (failure.code === "NETWORK_ERROR") {
        deleteOutcomeUnknown.current = true;
        setDeleteState({ status: "unknown", error: "NETWORK_ERROR" });
        return;
      }
      setDeleteState({ status: "error", error: failure.code });
    }
  }, [api, memoId, onDeleted]);

  return {
    loadState,
    deleteState,
    reload: load,
    requestDelete,
    cancelDelete,
    confirmDelete,
  };
}
