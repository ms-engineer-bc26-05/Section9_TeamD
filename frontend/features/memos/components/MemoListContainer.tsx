"use client";

import type { MemoApi } from "../api/memoApi";
import { useMemoList } from "../hooks/useMemoList";
import { MemoListScreen } from "./MemoListScreen";

interface MemoListContainerProps {
  /** レンダーごとに参照が変わらないMemoApiを渡す。 */
  api: MemoApi;
  notice?: string | null;
  onBackHome: () => void;
  onOpenMemo: (memoId: string) => void;
  onStartConsultation: () => void;
  onApiError?: (error: unknown) => void;
}

export function MemoListContainer({
  api,
  notice = null,
  onBackHome,
  onOpenMemo,
  onStartConsultation,
  onApiError,
}: MemoListContainerProps) {
  const { state, reload, loadMore } = useMemoList(api, onApiError);

  return (
    <MemoListScreen
      memos={state.memos}
      hasNextPage={state.nextCursor !== null}
      isInitialLoading={state.isInitialLoading}
      isLoadingMore={state.isLoadingMore}
      initialError={state.initialError}
      loadMoreError={state.loadMoreError}
      notice={notice}
      onBackHome={onBackHome}
      onOpenMemo={onOpenMemo}
      onStartConsultation={onStartConsultation}
      onReload={() => void reload()}
      onLoadMore={() => void loadMore()}
    />
  );
}
