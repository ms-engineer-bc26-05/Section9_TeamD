import type { MemoErrorCode } from "../api/memoApiError";
import type {
  MemoDeleteState,
  MemoDetailLoadState,
} from "../hooks/useMemoDetail";
import {
  formatMemoCreatedAt,
  MEMO_HANDLING_LABELS,
} from "../model/constants";
import { MemoDeleteDialog } from "./MemoDeleteDialog";
import styles from "./MemoDetailScreen.module.css";

interface MemoDetailScreenProps {
  loadState: MemoDetailLoadState;
  deleteState: MemoDeleteState;
  onBackToList: () => void;
  onReload: () => void;
  onRequestDelete: () => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}

function detailErrorMessage(error: MemoErrorCode): string {
  if (error === "MEMO_NOT_FOUND") return "このメモは表示できません。";
  if (error === "UNAUTHORIZED") return "ログインしてください。";
  if (error === "NETWORK_ERROR") {
    return "通信できませんでした。接続を確認してもう一度お試しください。";
  }
  return "保存メモを読み込めませんでした。時間をおいてもう一度お試しください。";
}

export function MemoDetailScreen({
  loadState,
  deleteState,
  onBackToList,
  onReload,
  onRequestDelete,
  onCancelDelete,
  onConfirmDelete,
}: MemoDetailScreenProps) {
  return (
    <main className={styles.page}>
      <div className={styles.content}>
        <button type="button" className={styles.backButton} onClick={onBackToList}>
          保存メモ一覧へ戻る
        </button>
        <h1 className={styles.heading}>保存メモ詳細</h1>

        {loadState.status === "loading" ? (
          <p role="status">読み込み中です…</p>
        ) : null}

        {loadState.status === "error" ? (
          <section className={styles.statePanel} role="alert">
            <p>{detailErrorMessage(loadState.error)}</p>
            {loadState.error !== "MEMO_NOT_FOUND" ? (
              <button type="button" className={styles.primaryButton} onClick={onReload}>
                再読み込み
              </button>
            ) : null}
          </section>
        ) : null}

        {loadState.status === "ready" ? (
          <article className={styles.memo}>
            <time dateTime={loadState.memo.created_at} className={styles.date}>
              {formatMemoCreatedAt(loadState.memo.created_at)}
            </time>
            <DetailItem label="出来事" value={loadState.memo.event_summary} />
            <DetailItem label="感情" value={loadState.memo.emotion} />
            <DetailItem label="本音" value={loadState.memo.true_feeling} />
            <DetailItem
              label="背景"
              value={loadState.memo.background || "未記入"}
              muted={loadState.memo.background === ""}
            />
            <DetailItem label="望み" value={loadState.memo.wish} />
            <DetailItem
              label="扱い方"
              value={MEMO_HANDLING_LABELS[loadState.memo.handling]}
            />
            <DetailItem
              label="理由"
              value={loadState.memo.reason || "未記入"}
              muted={loadState.memo.reason === null || loadState.memo.reason === ""}
            />
            <button
              type="button"
              className={styles.deleteButton}
              onClick={onRequestDelete}
            >
              このメモを削除
            </button>
          </article>
        ) : null}

        {deleteState.status !== "idle" ? (
          <MemoDeleteDialog
            state={deleteState}
            onCancel={
              deleteState.status === "error" &&
              deleteState.error === "MEMO_NOT_FOUND"
                ? onBackToList
                : onCancelDelete
            }
            onConfirm={onConfirmDelete}
          />
        ) : null}
      </div>
    </main>
  );
}

function DetailItem({
  label,
  value,
  muted = false,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <section className={styles.detailItem}>
      <h2>{label}</h2>
      <p className={muted ? styles.muted : undefined}>{value}</p>
    </section>
  );
}
