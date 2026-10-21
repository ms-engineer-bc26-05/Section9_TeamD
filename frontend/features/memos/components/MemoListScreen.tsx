import type { MemoErrorCode } from "../api/memoApiError";
import {
  formatMemoCreatedAt,
  MEMO_HANDLING_LABELS,
} from "../model/constants";
import type { MemoListItem } from "../model/contracts";
import styles from "./MemoListScreen.module.css";

export interface MemoListScreenProps {
  memos: MemoListItem[];
  hasNextPage: boolean;
  isInitialLoading: boolean;
  isLoadingMore: boolean;
  initialError: MemoErrorCode | null;
  loadMoreError: MemoErrorCode | null;
  notice?: string | null;
  onBackHome: () => void;
  onOpenMemo: (memoId: string) => void;
  onStartConsultation: () => void;
  onReload: () => void;
  onLoadMore: () => void;
}

function listErrorMessage(error: MemoErrorCode): string {
  if (error === "UNAUTHORIZED") return "ログインしてください。";
  if (error === "NETWORK_ERROR") {
    return "通信できませんでした。接続を確認してもう一度お試しください。";
  }
  return "保存メモを読み込めませんでした。時間をおいてもう一度お試しください。";
}

export function MemoListScreen({
  memos,
  hasNextPage,
  isInitialLoading,
  isLoadingMore,
  initialError,
  loadMoreError,
  notice = null,
  onBackHome,
  onOpenMemo,
  onStartConsultation,
  onReload,
  onLoadMore,
}: MemoListScreenProps) {
  return (
    <main className={styles.page}>
      <div className={styles.content}>
        <header className={styles.header}>
          <button
            type="button"
            className={styles.backButton}
            aria-label="ホームへ戻る"
            onClick={onBackHome}
          >
            <span aria-hidden="true">‹</span>
          </button>
          <h1 className={styles.heading}>保存メモ</h1>
          <span className={styles.headerSpacer} aria-hidden="true" />
        </header>

        {notice !== null ? (
          <p className={styles.successNotice} role="status">
            {notice}
          </p>
        ) : null}

        {isInitialLoading ? <p role="status">読み込み中です…</p> : null}

        {!isInitialLoading && initialError !== null ? (
          <section className={styles.statePanel} role="alert">
            <p>{listErrorMessage(initialError)}</p>
            <button type="button" className={styles.primaryButton} onClick={onReload}>
              再読み込み
            </button>
          </section>
        ) : null}

        {!isInitialLoading && initialError === null && memos.length === 0 ? (
          <section className={styles.statePanel}>
            <p>まだ保存したメモはありません。</p>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={onStartConsultation}
            >
              相談を始める
            </button>
          </section>
        ) : null}

        {memos.length > 0 ? (
          <ul className={styles.list} aria-label="保存メモ一覧">
            {memos.map((memo) => (
              <li key={memo.memo_id}>
                <button
                  type="button"
                  className={styles.card}
                  onClick={() => onOpenMemo(memo.memo_id)}
                >
                  <time dateTime={memo.created_at} className={styles.date}>
                    {formatMemoCreatedAt(memo.created_at)}
                  </time>
                  <span className={styles.summary}>{memo.summary}</span>
                  <span className={styles.handling}>
                    {MEMO_HANDLING_LABELS[memo.handling]}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        {loadMoreError !== null ? (
          <p className={styles.loadMoreError} role="alert">
            追加のメモを読み込めませんでした。もう一度お試しください。
          </p>
        ) : null}

        {hasNextPage ? (
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={isLoadingMore}
            onClick={onLoadMore}
          >
            {isLoadingMore
              ? "読み込み中…"
              : loadMoreError === null
                ? "もっと見る"
                : "もう一度読み込む"}
          </button>
        ) : null}
      </div>
    </main>
  );
}
