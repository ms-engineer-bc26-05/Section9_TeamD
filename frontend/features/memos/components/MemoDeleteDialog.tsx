"use client";

import { useEffect, useRef, type SyntheticEvent } from "react";

import type { MemoDeleteState } from "../hooks/useMemoDetail";
import styles from "./MemoDetailScreen.module.css";

interface MemoDeleteDialogProps {
  state: Exclude<MemoDeleteState, { status: "idle" }>;
  onCancel: () => void;
  onConfirm: () => void;
}

export function MemoDeleteDialog({
  state,
  onCancel,
  onConfirm,
}: MemoDeleteDialogProps) {
  const isDeleting = state.status === "deleting";
  const isNotFound =
    state.status === "error" && state.error === "MEMO_NOT_FOUND";
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    cancelButtonRef.current?.focus();

    return () => {
      if (typeof dialog.close === "function" && dialog.open) dialog.close();
    };
  }, []);

  function handleCancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault();
    if (!isDeleting) onCancel();
  }

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby="memo-delete-title"
      onCancel={handleCancel}
    >
      <h2 id="memo-delete-title">このメモを削除しますか？</h2>
      <p>削除後は元に戻せません。</p>

      {state.status === "unknown" ? (
        <p className={styles.error} role="alert">
          削除結果を確認できませんでした。もう一度お試しください。
        </p>
      ) : null}

      {state.status === "error" ? (
        <p className={styles.error} role="alert">
          {state.error === "MEMO_NOT_FOUND"
            ? "このメモは表示できません。"
            : "メモを削除できませんでした。時間をおいてもう一度お試しください。"}
        </p>
      ) : null}

      <div className={styles.dialogActions}>
        <button
          ref={cancelButtonRef}
          type="button"
          className={styles.secondaryButton}
          disabled={isDeleting}
          onClick={onCancel}
        >
          {isNotFound ? "一覧へ戻る" : "キャンセル"}
        </button>
        <button
          type="button"
          className={styles.dangerButton}
          disabled={
            isDeleting || isNotFound
          }
          onClick={onConfirm}
        >
          {isDeleting
            ? "削除中…"
            : state.status === "unknown"
              ? "もう一度削除"
              : "削除する"}
        </button>
      </div>
    </dialog>
  );
}
