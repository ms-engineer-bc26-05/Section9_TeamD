"use client";

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type SyntheticEvent,
} from "react";

import { HANDLING_OPTIONS } from "../model/constants";
import type { HandlingType } from "../model/contracts";
import styles from "./SaveConfirmationStep.module.css";

interface SaveConfirmationStepProps {
  handling: HandlingType;
  reason: string;
  reasonMaxLength: number;
  isSubmitting: boolean;
  onReasonChange: (reason: string) => void;
  onBack: () => void;
  onSave: (reason: string | null) => void;
  onFinishWithoutSaving: () => void;
}

export function SaveConfirmationStep({
  handling,
  reason,
  reasonMaxLength,
  isSubmitting,
  onReasonChange,
  onBack,
  onSave,
  onFinishWithoutSaving,
}: SaveConfirmationStepProps) {
  const [showFinishConfirmation, setShowFinishConfirmation] = useState(false);
  const finishTriggerButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const dialogBackButtonRef = useRef<HTMLButtonElement>(null);
  const handlingLabel =
    HANDLING_OPTIONS.find((option) => option.value === handling)?.label ??
    "選択した扱い方";

  useEffect(() => {
    if (!showFinishConfirmation) {
      return;
    }

    const dialog = dialogRef.current;
    if (dialog !== null && !dialog.open) {
      dialog.showModal();
    }
    dialogBackButtonRef.current?.focus();

    return () => {
      if (dialog?.open) {
        dialog.close();
      }
    };
  }, [showFinishConfirmation]);

  function handleReasonChange(event: ChangeEvent<HTMLTextAreaElement>) {
    onReasonChange(event.target.value);
  }

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    const normalizedReason = reason.trim();
    onSave(normalizedReason.length > 0 ? reason : null);
  }

  function handleOpenFinishConfirmation() {
    if (!isSubmitting) {
      setShowFinishConfirmation(true);
    }
  }

  function handleCloseFinishConfirmation() {
    if (!isSubmitting) {
      dialogRef.current?.close();
      setShowFinishConfirmation(false);
      finishTriggerButtonRef.current?.focus();
    }
  }

  function handleDialogCancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault();
    handleCloseFinishConfirmation();
  }

  function handleFinishWithoutSaving() {
    if (isSubmitting) {
      return;
    }

    dialogRef.current?.close();
    setShowFinishConfirmation(false);
    onFinishWithoutSaving();
  }

  return (
    <main className={styles.page}>
      <section
        className={styles.panel}
        aria-labelledby="save-confirmation-title"
        aria-busy={isSubmitting}
      >
        <header className={styles.header}>
          <button
            className={styles.backButton}
            type="button"
            aria-label="扱い方の選択に戻る"
            disabled={isSubmitting}
            onClick={onBack}
          >
            <span aria-hidden="true">‹</span>
          </button>
          <h1 id="save-confirmation-title" className={styles.headerTitle}>
            判断を記録する
          </h1>
          <span className={styles.headerSpacer} aria-hidden="true" />
        </header>

        <p className={styles.sectionLabel}>今の選択</p>
        <div className={styles.handlingCard}>
          <p>{handlingLabel}</p>
        </div>

        <form className={styles.form} onSubmit={handleSave}>
          <div className={styles.reasonSection}>
            <label className={styles.reasonLabel} htmlFor="consultation-save-reason">
              そう決めた理由も残しますか？
            </label>
            <p id="consultation-save-reason-help" className={styles.helpText}>
              書かなくても次へ進めます（任意）
            </p>
            <div className={styles.textareaWrapper}>
              <textarea
                id="consultation-save-reason"
                className={styles.textarea}
                value={reason}
                maxLength={reasonMaxLength}
                placeholder="例：今は気持ちが強いので、少し落ち着いてから考えたい"
                aria-describedby="consultation-save-reason-help consultation-save-reason-count"
                disabled={isSubmitting}
                onChange={handleReasonChange}
              />
              <output
                id="consultation-save-reason-count"
                className={styles.characterCount}
              >
                {reason.length} / {reasonMaxLength}
              </output>
            </div>
          </div>

          <div className={styles.savedContentNotice}>
            <p className={styles.noticeTitle}>保存されるもの</p>
            <p>承認した整理結果・選択・入力した理由</p>
            <p>相談中の会話全文は保存しません</p>
          </div>

          <button className={styles.primaryButton} type="submit" disabled={isSubmitting}>
            {isSubmitting ? "処理中…" : "保存する"}
          </button>
          <button
            ref={finishTriggerButtonRef}
            className={styles.secondaryButton}
            type="button"
            disabled={isSubmitting}
            onClick={handleOpenFinishConfirmation}
          >
            保存せず終了
          </button>

          {isSubmitting ? (
            <p className={styles.loadingMessage} role="status">
              選択した処理を進めています…
            </p>
          ) : null}
        </form>

        <p className={styles.supportText}>相談窓口・利用上の注意</p>
      </section>

      {showFinishConfirmation ? (
        <dialog
          ref={dialogRef}
          className={styles.dialog}
          aria-labelledby="finish-without-saving-title"
          aria-describedby="finish-without-saving-description"
          onCancel={handleDialogCancel}
        >
          <h2 id="finish-without-saving-title" className={styles.dialogTitle}>
            保存せずに終了しますか？
          </h2>
          <p id="finish-without-saving-description" className={styles.dialogText}>
            承認した整理結果や入力した理由は、整理メモとして保存されません。
          </p>
          <div className={styles.dialogActions}>
            <button
              ref={dialogBackButtonRef}
              className={styles.dialogSecondaryButton}
              type="button"
              disabled={isSubmitting}
              onClick={handleCloseFinishConfirmation}
            >
              戻る
            </button>
            <button
              className={styles.dialogPrimaryButton}
              type="button"
              disabled={isSubmitting}
              onClick={handleFinishWithoutSaving}
            >
              保存せず終了
            </button>
          </div>
        </dialog>
      ) : null}
    </main>
  );
}
