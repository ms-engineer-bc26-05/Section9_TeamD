"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";

import { THEME_OPTIONS } from "../model/constants";
import type { ThemeCategory } from "../model/contracts";
import styles from "./DetailInputStep.module.css";

interface DetailInputStepProps {
  selectedTheme: ThemeCategory;
  detail: string;
  maxLength: number;
  isSubmitting: boolean;
  startErrorMessage: string | null;
  onDetailChange: (detail: string) => void;
  onBack: () => void;
  onCancel: () => void;
  onStart: (detail: string) => void;
}

export function DetailInputStep({
  selectedTheme,
  detail,
  maxLength,
  isSubmitting,
  startErrorMessage,
  onDetailChange,
  onBack,
  onCancel,
  onStart,
}: DetailInputStepProps) {
  const [showRequiredError, setShowRequiredError] = useState(false);
  const selectedThemeLabel =
    THEME_OPTIONS.find((option) => option.value === selectedTheme)?.label ??
    "選択したテーマ";

  function handleDetailChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const nextDetail = event.target.value;

    if (nextDetail.trim().length > 0) {
      setShowRequiredError(false);
    }

    onDetailChange(nextDetail);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (detail.trim().length === 0) {
      setShowRequiredError(true);
      return;
    }

    setShowRequiredError(false);
    onStart(detail);
  }

  const describedBy = [
    "detail-input-help",
    "detail-input-privacy",
    "detail-input-count",
    showRequiredError ? "detail-input-error" : null,
    startErrorMessage ? "consultation-start-error" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="detail-input-title">
        <div className={styles.progressHeader}>
          <button
            className={styles.headerButton}
            type="button"
            aria-label="テーマ選択に戻る"
            disabled={isSubmitting}
            onClick={onBack}
          >
            <span className={styles.backIcon} aria-hidden="true">
              ‹
            </span>
          </button>
          <span className={styles.progressText}>2 / 4</span>
          <button
            className={styles.cancelButton}
            type="button"
            disabled={isSubmitting}
            onClick={onCancel}
          >
            中断
          </button>
        </div>
        <div
          className={styles.progressTrack}
          role="progressbar"
          aria-label="相談の進み具合"
          aria-valuemin={0}
          aria-valuemax={4}
          aria-valuenow={2}
          aria-valuetext="4段階中2段階"
        >
          <span className={styles.progressValue} />
        </div>

        <p className={styles.themeTag}>{selectedThemeLabel}</p>

        <h1 id="detail-input-title" className={styles.title}>
          どんなことが気になっていますか？
        </h1>
        <p id="detail-input-help" className={styles.helpText}>
          まとまっていなくても大丈夫です
        </p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.visuallyHidden} htmlFor="consultation-detail">
            気になっていること
          </label>
          <div className={styles.textareaWrapper}>
            <textarea
              id="consultation-detail"
              className={styles.textarea}
              value={detail}
              maxLength={maxLength}
              placeholder="例：話をしているときにスマホを見ていて、聞いてもらえていない気がしました…"
              aria-describedby={describedBy}
              aria-invalid={showRequiredError}
              disabled={isSubmitting}
              onChange={handleDetailChange}
            />
            <output id="detail-input-count" className={styles.characterCount}>
              {detail.length} / {maxLength}
            </output>
          </div>

          {showRequiredError ? (
            <p id="detail-input-error" className={styles.errorMessage} role="alert">
              気になっていることを入力してください。
            </p>
          ) : null}

          {startErrorMessage ? (
            <p
              id="consultation-start-error"
              className={styles.requestErrorMessage}
              role="alert"
            >
              {startErrorMessage}
            </p>
          ) : null}

          <aside
            id="detail-input-privacy"
            className={styles.privacyNotice}
            aria-labelledby="privacy-notice-title"
          >
            <h2 id="privacy-notice-title" className={styles.privacyTitle}>
              書かないでほしい情報
            </h2>
            <p className={styles.privacyText}>
              実名・住所・電話番号・メールアドレスなど
            </p>
          </aside>

          <button className={styles.primaryButton} type="submit" disabled={isSubmitting}>
            {isSubmitting ? "送信中…" : "対話を始める"}
          </button>

          {isSubmitting ? (
            <p className={styles.loadingMessage} role="status">
              AIが内容を整理しています。通常より時間がかかることがあります。
              そのままお待ちください。
            </p>
          ) : null}
        </form>
      </section>
    </main>
  );
}
