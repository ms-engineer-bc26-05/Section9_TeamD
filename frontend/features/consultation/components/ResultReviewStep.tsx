"use client";

import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import type {
  ConsultationResult,
  UpdateConsultationResultRequest,
} from "../model/contracts";
import styles from "./ResultReviewStep.module.css";

type ResultField = Exclude<keyof ConsultationResult, "approved">;

const RESULT_FIELDS = [
  "event_summary",
  "emotion",
  "true_feeling",
  "background",
  "wish",
] as const satisfies readonly ResultField[];

const RESULT_FIELD_LABELS: Record<ResultField, string> = {
  event_summary: "出来事",
  emotion: "感情",
  true_feeling: "本音",
  background: "背景",
  wish: "望み",
};

interface ResultReviewStepProps {
  result: ConsultationResult;
  fieldMaxLength: number;
  emotionMaxLength: number;
  isSubmitting: boolean;
  onApprove: (changes: UpdateConsultationResultRequest) => void;
  onCancel: () => void;
}

export function ResultReviewStep({
  result,
  fieldMaxLength,
  emotionMaxLength,
  isSubmitting,
  onApprove,
  onCancel,
}: ResultReviewStepProps) {
  const [draft, setDraft] = useState<ConsultationResult>(result);
  const [emptyFields, setEmptyFields] = useState<ResultField[]>([]);

  useEffect(() => {
    setDraft(result);
    setEmptyFields([]);
  }, [result]);

  function handleFieldChange(
    field: ResultField,
    event: ChangeEvent<HTMLTextAreaElement>,
  ) {
    const value = event.target.value;

    setDraft((current) => ({ ...current, [field]: value }));

    if (field === "background" || value.trim().length > 0) {
      setEmptyFields((current) => current.filter((name) => name !== field));
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    const nextEmptyFields = RESULT_FIELDS.filter(
      (field) => field !== "background" && draft[field].trim().length === 0,
    );

    if (nextEmptyFields.length > 0) {
      setEmptyFields([...nextEmptyFields]);
      return;
    }

    const changes: UpdateConsultationResultRequest = {};

    for (const field of RESULT_FIELDS) {
      if (draft[field] !== result[field]) {
        changes[field] = draft[field];
      }
    }

    setEmptyFields([]);
    onApprove(changes);
  }

  return (
    <main className={styles.page}>
      <section
        className={styles.panel}
        aria-labelledby="result-review-title"
        aria-busy={isSubmitting}
      >
        <header className={styles.header}>
          <span className={styles.headerSpacer} aria-hidden="true" />
          <p className={styles.headerTitle}>整理結果を確認</p>
          <button
            className={styles.cancelButton}
            type="button"
            disabled={isSubmitting}
            onClick={onCancel}
          >
            中断
          </button>
        </header>

        <h1 id="result-review-title" className={styles.visuallyHidden}>
          整理結果を確認・編集する
        </h1>
        <p className={styles.helpText}>違うところは編集できます</p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.resultList}>
            {RESULT_FIELDS.map((field, index) => {
              const maxLength =
                field === "emotion" ? emotionMaxLength : fieldMaxLength;
              const hasError = emptyFields.includes(field);
              const inputId = `consultation-result-${field}`;
              const errorId = `${inputId}-error`;
              const countId = `${inputId}-count`;

              return (
                <div className={styles.fieldGroup} key={field}>
                  <div
                    className={`${styles.resultCard} ${
                      index % 2 === 0 ? styles.warmCard : styles.greenCard
                    }`}
                  >
                    <label className={styles.fieldLabel} htmlFor={inputId}>
                      {RESULT_FIELD_LABELS[field]}
                    </label>
                    <div className={styles.inputArea}>
                      <textarea
                        id={inputId}
                        className={styles.textarea}
                        value={draft[field]}
                        maxLength={maxLength}
                        rows={3}
                        aria-invalid={hasError}
                        aria-describedby={hasError ? `${countId} ${errorId}` : countId}
                        disabled={isSubmitting}
                        onChange={(event) => handleFieldChange(field, event)}
                      />
                      <div className={styles.inputMeta}>
                        <span className={styles.editLabel} aria-hidden="true">
                          編集
                        </span>
                        <output id={countId} className={styles.characterCount}>
                          {draft[field].length} / {maxLength}
                        </output>
                      </div>
                    </div>
                  </div>

                  {hasError ? (
                    <p id={errorId} className={styles.errorMessage} role="alert">
                      {RESULT_FIELD_LABELS[field]}を入力してください。
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <button className={styles.primaryButton} type="submit" disabled={isSubmitting}>
            {isSubmitting ? "承認しています…" : "この内容で合っています"}
          </button>

          <div className={styles.notices}>
            <p>背景が分からない場合は空欄でも進めます</p>
            <p>承認するまで保存されません</p>
            <p className={styles.importantNotice}>
              承認後は、この編集画面には戻れません
            </p>
          </div>

          {isSubmitting ? (
            <p className={styles.loadingMessage} role="status">
              編集内容を確認しています…
            </p>
          ) : null}
        </form>

        <p className={styles.supportText}>相談窓口・利用上の注意</p>
      </section>
    </main>
  );
}
