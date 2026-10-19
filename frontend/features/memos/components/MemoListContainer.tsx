"use client";

import type { MemoApi } from "../api/memoApi";
import { useMemoList } from "../hooks/useMemoList";
import { MemoListScreen } from "./MemoListScreen";

interface MemoListContainerProps {
  /** レンダーごとに参照が変わらないMemoApiを渡す。 */
  api: MemoApi;
  notice?: string | null;
  onOpenMemo: (memoId: string) => void;
  onStartConsultation: () => void;
}

export function MemoListContainer({
  api,
  notice = null,
  onOpenMemo,
  onStartConsultation,
}: MemoListContainerProps) {
  const { state, reload, loadMore } = useMemoList(api);

  return (
    <MemoListScreen
      memos={state.memos}
      hasNextPage={state.nextCursor !== null}
      isInitialLoading={state.isInitialLoading}
      isLoadingMore={state.isLoadingMore}
      initialError={state.initialError}
      loadMoreError={state.loadMoreError}
      notice={notice}
      onOpenMemo={onOpenMemo}
      onStartConsultation={onStartConsultation}
      onReload={() => void reload()}
      onLoadMore={() => void loadMore()}
    />
  );
}
