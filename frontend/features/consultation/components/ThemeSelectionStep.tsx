"use client";

import { THEME_OPTIONS } from "../model/constants";
import type { ThemeCategory } from "../model/contracts";
import styles from "./ThemeSelectionStep.module.css";

interface ThemeSelectionStepProps {
  selectedTheme: ThemeCategory | null;
  onThemeChange: (theme: ThemeCategory) => void;
  onBack: () => void;
  onNext: (theme: ThemeCategory) => void;
}

export function ThemeSelectionStep({
  selectedTheme,
  onThemeChange,
  onBack,
  onNext,
}: ThemeSelectionStepProps) {
  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (selectedTheme === null) {
      return;
    }

    onNext(selectedTheme);
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="theme-selection-title">
        <div className={styles.progressHeader}>
          <button
            className={styles.backButton}
            type="button"
            aria-label="利用前の注意に戻る"
            onClick={onBack}
          >
            <span aria-hidden="true">‹</span>
          </button>
          <span className={styles.progressText}>1 / 4</span>
        </div>
        <div
          className={styles.progressTrack}
          role="progressbar"
          aria-label="相談の進み具合"
          aria-valuemin={0}
          aria-valuemax={4}
          aria-valuenow={1}
          aria-valuetext="4段階中1段階"
        >
          <span className={styles.progressValue} />
        </div>

        <h1 id="theme-selection-title" className={styles.title}>
          今、どんなことが気になっていますか？
        </h1>
        <p id="theme-selection-help" className={styles.helpText}>
          いちばん近いものを1つ選んでください
        </p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <fieldset
            className={styles.fieldset}
            aria-describedby="theme-selection-help"
          >
            <legend className={styles.visuallyHidden}>相談テーマ</legend>

            <div className={styles.options}>
              {THEME_OPTIONS.map((option) => {
                const inputId = `consultation-theme-${option.value}`;

                return (
                  <label
                    key={option.value}
                    className={styles.option}
                    htmlFor={inputId}
                  >
                    <input
                      id={inputId}
                      className={styles.radio}
                      type="radio"
                      name="consultation-theme"
                      value={option.value}
                      checked={selectedTheme === option.value}
                      onChange={() => onThemeChange(option.value)}
                    />
                    <span className={styles.card}>
                      <span className={styles.radioMark} aria-hidden="true" />
                      <span className={styles.cardLabel}>{option.label}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <p className={styles.reassurance}>完全に当てはまらなくても大丈夫です</p>

          <button
            className={styles.primaryButton}
            type="submit"
            disabled={selectedTheme === null}
          >
            次へ
          </button>
        </form>
      </section>
    </main>
  );
}
