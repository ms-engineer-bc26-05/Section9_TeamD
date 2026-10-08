"use client";

import { useEffect, useState, type ChangeEvent } from "react";

import { HANDLING_OPTIONS } from "../model/constants";
import type { HandlingType } from "../model/contracts";
import styles from "./HandlingSelectionStep.module.css";

const HANDLING_DESCRIPTIONS: Record<HandlingType, string> = {
  tell: "相手に自分の気持ちを伝えたい",
  hold: "今すぐ決めず、いったん置いておきたい",
  not_tell: "伝えないことを自分で選びたい",
};

interface HandlingSelectionStepProps {
  selectedHandling: HandlingType | null;
  isSubmitting: boolean;
  onSelect: (handling: HandlingType) => void;
  onCancel: () => void;
}

export function HandlingSelectionStep({
  selectedHandling,
  isSubmitting,
  onSelect,
  onCancel,
}: HandlingSelectionStepProps) {
  const [selection, setSelection] = useState<HandlingType | null>(selectedHandling);

  useEffect(() => {
    setSelection(selectedHandling);
  }, [selectedHandling]);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    if (isSubmitting) {
      return;
    }

    const nextHandling = event.target.value as HandlingType;

    setSelection(nextHandling);
    onSelect(nextHandling);
  }

  return (
    <main className={styles.page}>
      <section
        className={styles.panel}
        aria-labelledby="handling-selection-title"
        aria-busy={isSubmitting}
      >
        <header className={styles.header}>
          <span className={styles.headerSpacer} aria-hidden="true" />
          <span aria-hidden="true" />
          <button
            className={styles.cancelButton}
            type="button"
            disabled={isSubmitting}
            onClick={onCancel}
          >
            中断
          </button>
        </header>

        <h1 id="handling-selection-title" className={styles.title}>
          この気持ちを、
          <br />
          今どう扱いたいですか？
        </h1>
        <p className={styles.helpText}>今の時点での気持ちで大丈夫です</p>

        <fieldset className={styles.options} disabled={isSubmitting}>
          <legend className={styles.visuallyHidden}>気持ちの扱い方を選ぶ</legend>
          {HANDLING_OPTIONS.map((option, index) => (
            <label
              className={`${styles.optionLabel} ${
                selection === option.value ? styles.selectedOption : ""
              }`}
              key={option.value}
            >
              <input
                className={styles.radio}
                type="radio"
                name="consultation-handling"
                value={option.value}
                checked={selection === option.value}
                onChange={handleChange}
              />
              <span
                className={`${styles.optionIcon} ${
                  index === 0
                    ? styles.warmIcon
                    : index === 1
                      ? styles.neutralIcon
                      : styles.greenIcon
                }`}
                aria-hidden="true"
              >
                {index === 0 ? "↗" : index === 1 ? "…" : "✓"}
              </span>
              <span className={styles.optionText}>
                <span className={styles.optionTitle}>{option.label}</span>
                <span className={styles.optionDescription}>
                  {HANDLING_DESCRIPTIONS[option.value]}
                </span>
              </span>
            </label>
          ))}
        </fieldset>

        {isSubmitting ? (
          <p className={styles.loadingMessage} role="status">
            選択を反映しています…
          </p>
        ) : null}

        <div className={styles.notices}>
          <p>どの選択も間違いではありません</p>
          <p>後から気持ちが変わっても大丈夫です</p>
        </div>

        <p className={styles.supportText}>相談窓口・利用上の注意</p>
      </section>
    </main>
  );
}
