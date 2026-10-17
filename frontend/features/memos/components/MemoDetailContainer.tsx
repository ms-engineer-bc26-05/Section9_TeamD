"use client";

import type { MemoApi } from "../api/memoApi";
import { useMemoDetail } from "../hooks/useMemoDetail";
import { MemoDetailScreen } from "./MemoDetailScreen";

interface MemoDetailContainerProps {
  memoId: string;
  /** レンダーごとに参照が変わらないMemoApiを渡す。 */
  api: MemoApi;
  onBackToList: () => void;
  onDeleted: (memoId: string) => void;
}

export function MemoDetailContainer({
  memoId,
  api,
  onBackToList,
  onDeleted,
}: MemoDetailContainerProps) {
  const detail = useMemoDetail({ memoId, api, onDeleted });

  return (
    <MemoDetailScreen
      loadState={detail.loadState}
      deleteState={detail.deleteState}
      onBackToList={onBackToList}
      onReload={() => void detail.reload()}
      onRequestDelete={detail.requestDelete}
      onCancelDelete={detail.cancelDelete}
      onConfirmDelete={() => void detail.confirmDelete()}
    />
  );
}
