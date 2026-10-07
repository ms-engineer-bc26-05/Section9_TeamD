"use client";

import type { FormEvent } from "react";

import { EMOTION_OPTIONS } from "../model/constants";
import type { EmotionCategory } from "../model/contracts";
import styles from "./EmotionSelectionStep.module.css";

interface EmotionSelectionStepProps {
  selectedEmotion: EmotionCategory | null;
  onEmotionChange: (emotion: EmotionCategory) => void;
  onNext: (emotion: EmotionCategory) => void;
  onBack: () => void;
  onCancel: () => void;
}

export function EmotionSelectionStep({
  selectedEmotion,
  onEmotionChange,
  onNext,
  onBack,
  onCancel,
}: EmotionSelectionStepProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (selectedEmotion === null) {
      return;
    }

    onNext(selectedEmotion);
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="emotion-selection-title">
        <header className={styles.header}>
          <button
            className={styles.headerButton}
            type="button"
            aria-label="出来事の確認に戻る"
            onClick={onBack}
          >
            <span className={styles.backIcon} aria-hidden="true">
              ‹
            </span>
          </button>
          <p className={styles.headerTitle}>気持ちを整理する</p>
          <button className={styles.cancelButton} type="button" onClick={onCancel}>
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

        <h1 id="emotion-selection-title" className={styles.title}>
          そのとき、どんな気持ちに
          <br />
          近かったですか？
        </h1>
        <p id="emotion-selection-help" className={styles.helpText}>
          いちばん近いものを1つ選んでください
        </p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <fieldset
            className={styles.fieldset}
            aria-describedby="emotion-selection-help emotion-selection-reassurance"
          >
            <legend className={styles.visuallyHidden}>近い感情</legend>

            <div className={styles.options}>
              {EMOTION_OPTIONS.map((option) => {
                const inputId = `consultation-emotion-${option.value}`;

                return (
                  <label key={option.value} className={styles.option} htmlFor={inputId}>
                    <input
                      id={inputId}
                      className={styles.radio}
                      type="radio"
                      name="consultation-emotion"
                      value={option.value}
                      checked={selectedEmotion === option.value}
                      onChange={() => onEmotionChange(option.value)}
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

          <p id="emotion-selection-reassurance" className={styles.reassurance}>
            完全に一致しなくても大丈夫です
          </p>

          <button
            className={styles.primaryButton}
            type="submit"
            disabled={selectedEmotion === null}
          >
            次へ
          </button>
        </form>

        <p className={styles.supportText}>相談窓口・利用上の注意</p>
      </section>
    </main>
  );
}
