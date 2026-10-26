"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";

import { EMOTION_OPTIONS } from "../model/constants";
import type { EmotionCategory, EmotionRequest } from "../model/contracts";
import styles from "./EmotionDetailStep.module.css";

interface EmotionDetailStepProps {
  selectedEmotion: EmotionCategory;
  detail: string;
  cannotVerbalize: boolean;
  maxLength: number;
  isSubmitting: boolean;
  onDetailChange: (detail: string) => void;
  onCannotVerbalizeChange: (cannotVerbalize: boolean) => void;
  onBack: () => void;
  onCancel: () => void;
  onNext: (request: EmotionRequest) => void;
}

export function EmotionDetailStep({
  selectedEmotion,
  detail,
  cannotVerbalize,
  maxLength,
  isSubmitting,
  onDetailChange,
  onCannotVerbalizeChange,
  onBack,
  onCancel,
  onNext,
}: EmotionDetailStepProps) {
  const [showRequiredError, setShowRequiredError] = useState(false);
  const selectedEmotionLabel =
    EMOTION_OPTIONS.find((option) => option.value === selectedEmotion)?.label ??
    "選択した気持ち";
  const hasDetail = detail.trim().length > 0;
  const canSubmit = cannotVerbalize || hasDetail;

  function handleDetailChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const nextDetail = event.target.value;

    if (nextDetail.trim().length > 0) {
      setShowRequiredError(false);
    }

    onDetailChange(nextDetail);
  }

  function handleCannotVerbalizeChange(event: ChangeEvent<HTMLInputElement>) {
    const isChecked = event.target.checked;

    if (isChecked) {
      setShowRequiredError(false);
    }

    onCannotVerbalizeChange(isChecked);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (!canSubmit) {
      setShowRequiredError(true);
      return;
    }

    setShowRequiredError(false);

    if (cannotVerbalize) {
      onNext({
        category: selectedEmotion,
        cannot_verbalize: true,
      });
      return;
    }

    onNext({
      category: selectedEmotion,
      detail,
    });
  }

  const describedBy = showRequiredError
    ? "emotion-detail-help emotion-detail-count emotion-detail-error"
    : "emotion-detail-help emotion-detail-count";

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="emotion-detail-title">
        <header className={styles.header}>
          <button
            className={styles.headerButton}
            type="button"
            aria-label="感情の選択に戻る"
            disabled={isSubmitting}
            onClick={onBack}
          >
            <span className={styles.backIcon} aria-hidden="true">
              ‹
            </span>
          </button>
          <p className={styles.headerTitle}>気持ちを整理する</p>
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
          <li className={styles.completedStep}>出来事</li>
          <li className={styles.currentStep} aria-current="step">
            感情
          </li>
          <li>本音</li>
          <li>望み</li>
        </ol>

        <div className={styles.emotionSummary}>
          <p className={styles.emotionTag}>{selectedEmotionLabel}</p>
          <button
            className={styles.reselectButton}
            type="button"
            disabled={isSubmitting}
            onClick={onBack}
          >
            選び直す
          </button>
        </div>

        <h1 id="emotion-detail-title" className={styles.title}>
          その気持ちについて、
          <br />
          もう少し教えてください
        </h1>
        <p id="emotion-detail-help" className={styles.helpText}>
          短くても、まとまっていなくても大丈夫です
        </p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.visuallyHidden} htmlFor="consultation-emotion-detail">
            選んだ気持ちについて
          </label>
          <div className={styles.textareaWrapper}>
            <textarea
              id="consultation-emotion-detail"
              className={styles.textarea}
              value={detail}
              maxLength={maxLength}
              placeholder="例：一緒にいるのに、自分だけが置いていかれたように感じました…"
              aria-describedby={describedBy}
              aria-invalid={showRequiredError}
              disabled={isSubmitting || cannotVerbalize}
              onChange={handleDetailChange}
            />
            <output id="emotion-detail-count" className={styles.characterCount}>
              {detail.length} / {maxLength}
            </output>
          </div>

          <label className={styles.cannotVerbalizeOption}>
            <input
              className={styles.checkbox}
              type="checkbox"
              checked={cannotVerbalize}
              disabled={isSubmitting}
              onChange={handleCannotVerbalizeChange}
            />
            <span className={styles.optionCard}>
              <span className={styles.checkMark} aria-hidden="true" />
              <span>うまく言葉にできない</span>
            </span>
          </label>

          {showRequiredError ? (
            <p id="emotion-detail-error" className={styles.errorMessage} role="alert">
              気持ちを入力するか、「うまく言葉にできない」を選んでください。
            </p>
          ) : null}

          <button
            className={styles.primaryButton}
            type="submit"
            disabled={isSubmitting || !canSubmit}
          >
            {isSubmitting ? "送信中…" : "次へ"}
          </button>

          {isSubmitting ? (
            <p className={styles.loadingMessage} role="status">
              気持ちを整理しています。通常より時間がかかることがあります。
              そのままお待ちください。
            </p>
          ) : null}
        </form>

        <p className={styles.supportText}>相談窓口・利用上の注意</p>
      </section>
    </main>
  );
}
