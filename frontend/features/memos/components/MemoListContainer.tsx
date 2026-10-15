"use client";

import type { MemoApi } from "../api/memoApi";
import { useMemoList } from "../hooks/useMemoList";
import { MemoListScreen } from "./MemoListScreen";

interface MemoListContainerProps {
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
      {...state}
      hasNextPage={state.nextCursor !== null}
      notice={notice}
      onOpenMemo={onOpenMemo}
      onStartConsultation={onStartConsultation}
      onReload={() => void reload()}
      onLoadMore={() => void loadMore()}
    />
  );
}
