"use client";

import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import type {
  EventDetails,
  EventSummaryConfirmRequest,
} from "../model/contracts";
import styles from "./EventSummaryStep.module.css";

type EventDetailField = keyof EventDetails;

interface EventSummaryStepProps {
  eventDetails: EventDetails;
  questionCount: number;
  canAskMore: boolean;
  correctionLimitReached: boolean;
  fieldMaxLength: number;
  isSubmitting: boolean;
  onProceed: (request: EventSummaryConfirmRequest) => void;
  onAskMore: () => void;
  onCancel: () => void;
}

export function EventSummaryStep({
  eventDetails,
  questionCount,
  canAskMore,
  correctionLimitReached,
  fieldMaxLength,
  isSubmitting,
  onProceed,
  onAskMore,
  onCancel,
}: EventSummaryStepProps) {
  const [draft, setDraft] = useState<EventDetails>(eventDetails);
  const [emptyFields, setEmptyFields] = useState<EventDetailField[]>([]);
  const remainingQuestions = Math.max(0, 3 - questionCount);

  useEffect(() => {
    setDraft(eventDetails);
    setEmptyFields([]);
  }, [eventDetails]);

  function handleFieldChange(
    field: EventDetailField,
    event: ChangeEvent<HTMLTextAreaElement>,
  ) {
    const value = event.target.value;

    setDraft((current) => ({ ...current, [field]: value }));

    if (value.trim().length > 0) {
      setEmptyFields((current) => current.filter((name) => name !== field));
    }
  }

  function handleProceed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    const nextEmptyFields = (
      ["what_happened", "what_bothered_me"] as EventDetailField[]
    ).filter((field) => draft[field].trim().length === 0);

    if (nextEmptyFields.length > 0) {
      setEmptyFields(nextEmptyFields);
      return;
    }

    setEmptyFields([]);

    const wasEdited =
      draft.what_happened !== eventDetails.what_happened ||
      draft.what_bothered_me !== eventDetails.what_bothered_me;

    onProceed(
      wasEdited
        ? { action: "proceed", event_details: draft }
        : { action: "proceed" },
    );
  }

  function handleAskMore() {
    if (isSubmitting || !canAskMore) {
      return;
    }

    onAskMore();
  }

  const happenedHasError = emptyFields.includes("what_happened");
  const botheredHasError = emptyFields.includes("what_bothered_me");

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="event-summary-title">
        <header className={styles.header}>
          <span className={styles.headerSpacer} aria-hidden="true" />
          <p className={styles.headerTitle}>出来事を確認する</p>
          <button
            className={styles.cancelButton}
            type="button"
            disabled={isSubmitting}
            onClick={onCancel}
          >
            中断
          </button>
        </header>

        <ol className={styles.steps} aria-label="相談の進み具合">
          <li className={styles.currentStep} aria-current="step">
            出来事
          </li>
          <li>感情</li>
          <li>本音</li>
          <li>望み</li>
        </ol>

        <h1 id="event-summary-title" className={styles.title}>
          ここまでの出来事を
          <br />
          このように整理しました
        </h1>
        <p className={styles.helpText}>違うところや足りないところは編集できます</p>

        <form className={styles.form} onSubmit={handleProceed}>
          <div className={styles.summaryCard}>
            <label className={styles.summaryLabel} htmlFor="what-happened">
              何が
              <br />
              あったか
            </label>
            <div className={styles.summaryInputArea}>
              <textarea
                id="what-happened"
                className={styles.summaryInput}
                value={draft.what_happened}
                maxLength={fieldMaxLength}
                aria-invalid={happenedHasError}
                aria-describedby={
                  happenedHasError ? "what-happened-error" : undefined
                }
                disabled={isSubmitting}
                onChange={(event) => handleFieldChange("what_happened", event)}
              />
              <span className={styles.editLabel} aria-hidden="true">
                編集
              </span>
            </div>
          </div>
          {happenedHasError ? (
            <p id="what-happened-error" className={styles.errorMessage} role="alert">
              何があったかを入力してください。
            </p>
          ) : null}

          <div className={`${styles.summaryCard} ${styles.botheredCard}`}>
            <label className={styles.summaryLabel} htmlFor="what-bothered-me">
              何が
              <br />
              気になったか
            </label>
            <div className={styles.summaryInputArea}>
              <textarea
                id="what-bothered-me"
                className={styles.summaryInput}
                value={draft.what_bothered_me}
                maxLength={fieldMaxLength}
                aria-invalid={botheredHasError}
                aria-describedby={
                  botheredHasError ? "what-bothered-me-error" : undefined
                }
                disabled={isSubmitting}
                onChange={(event) => handleFieldChange("what_bothered_me", event)}
              />
              <span className={styles.editLabel} aria-hidden="true">
                編集
              </span>
            </div>
          </div>
          {botheredHasError ? (
            <p id="what-bothered-me-error" className={styles.errorMessage} role="alert">
              何が気になったかを入力してください。
            </p>
          ) : null}

          {!canAskMore ? (
            <p className={styles.directEditNotice}>
              追加の質問には進まず、必要な修正はこの画面で直接編集できます。
              {correctionLimitReached ? " 訂正回数の上限に達しています。" : ""}
            </p>
          ) : null}

          <p id="event-summary-transition-notice" className={styles.transitionNotice}>
            次へ進むと、この画面には戻れません。整理結果は最後の確認画面でも編集できます。
          </p>

          <button
            className={styles.primaryButton}
            type="submit"
            aria-describedby="event-summary-transition-notice"
            disabled={isSubmitting}
          >
            {isSubmitting ? "処理中…" : "この内容で次へ"}
          </button>

          {canAskMore ? (
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isSubmitting}
              onClick={handleAskMore}
            >
              もう少し整理したい（あと{remainingQuestions}問）
            </button>
          ) : null}

          {isSubmitting ? (
            <p className={styles.loadingMessage} role="status">
              内容を確認しています。通常より時間がかかることがあります。
              そのままお待ちください。
            </p>
          ) : null}
        </form>

        <p className={styles.supportText}>相談窓口・利用上の注意</p>
      </section>
    </main>
  );
}
