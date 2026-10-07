"use client";

import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import styles from "./EventDialogueStep.module.css";

type InputMode = "answer" | "correction";

interface EventDialogueStepProps {
  aiQuestion: string;
  aiUnderstanding: string | null;
  questionCount: number;
  correctionCount: number;
  correctionLimitReached: boolean;
  answerMaxLength: number;
  isSubmitting: boolean;
  onAnswer: (answer: string) => void;
  onCorrect: (correction: string) => void;
  onBack: () => void;
  onCancel: () => void;
}

export function EventDialogueStep({
  aiQuestion,
  aiUnderstanding,
  questionCount,
  correctionCount,
  correctionLimitReached,
  answerMaxLength,
  isSubmitting,
  onAnswer,
  onCorrect,
  onBack,
  onCancel,
}: EventDialogueStepProps) {
  const [inputMode, setInputMode] = useState<InputMode>("answer");
  const [input, setInput] = useState("");
  const [showRequiredError, setShowRequiredError] = useState(false);
  const displayedQuestionNumber = Math.min(questionCount + 1, 3);

  useEffect(() => {
    setInputMode("answer");
    setInput("");
    setShowRequiredError(false);
  }, [aiQuestion, aiUnderstanding, questionCount, correctionCount]);

  function handleInputChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const nextInput = event.target.value;

    if (nextInput.trim().length > 0) {
      setShowRequiredError(false);
    }

    setInput(nextInput);
  }

  function selectAnswerMode() {
    setInputMode("answer");
    setInput("");
    setShowRequiredError(false);
  }

  function selectCorrectionMode() {
    setInputMode("correction");
    setInput("");
    setShowRequiredError(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (input.trim().length === 0) {
      setShowRequiredError(true);
      return;
    }

    setShowRequiredError(false);

    if (inputMode === "correction") {
      onCorrect(input);
      return;
    }

    onAnswer(input);
  }

  const inputLabel = inputMode === "correction" ? "訂正" : "回答";
  const inputPlaceholder =
    inputMode === "correction"
      ? "違うところや補足したいことを入力"
      : "覚えていることを入力";

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="event-dialogue-title">
        <header className={styles.header}>
          <button
            className={styles.headerButton}
            type="button"
            aria-label="前の画面に戻る"
            disabled={isSubmitting}
            onClick={onBack}
          >
            <span className={styles.backIcon} aria-hidden="true">
              ‹
            </span>
          </button>
          <h1 id="event-dialogue-title" className={styles.headerTitle}>
            気持ちを整理する
          </h1>
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

        <p className={styles.questionCount}>
          出来事の確認 {displayedQuestionNumber} / 3
        </p>

        {aiUnderstanding ? (
          <>
            <div className={styles.aiBubble}>
              <p>{aiUnderstanding}</p>
              <p className={styles.confirmationQuestion}>この理解で合っていますか？</p>
            </div>

            <div className={styles.confirmationActions}>
              <button
                className={inputMode === "answer" ? styles.selectedChoice : styles.choice}
                type="button"
                disabled={isSubmitting}
                aria-pressed={inputMode === "answer"}
                onClick={selectAnswerMode}
              >
                はい、合っています
              </button>
              {!correctionLimitReached ? (
                <button
                  className={
                    inputMode === "correction" ? styles.selectedChoice : styles.choice
                  }
                  type="button"
                  disabled={isSubmitting}
                  aria-pressed={inputMode === "correction"}
                  onClick={selectCorrectionMode}
                >
                  少し違います
                </button>
              ) : null}
            </div>

            <p className={styles.correctionStatus}>
              訂正後はAIの理解をもう一度確認します
              {correctionCount > 0 ? `（訂正 ${correctionCount} / 2）` : ""}
            </p>
          </>
        ) : null}

        {inputMode === "answer" ? (
          <div className={styles.aiBubble}>
            <p>{aiQuestion}</p>
            <p className={styles.bubbleHelp}>覚えている範囲で大丈夫です</p>
            <p className={styles.bubbleHelp}>追加質問は最大3問までです</p>
          </div>
        ) : (
          <p className={styles.correctionPrompt}>
            違うところや補足したいことを教えてください
          </p>
        )}

        <p className={styles.limitNotice}>
          2回の訂正後も違う場合は、次の画面で要約を直接編集できます
        </p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.inputLabel} htmlFor="event-dialogue-input">
            {inputLabel}
          </label>
          <div className={styles.inputWrapper}>
            <textarea
              id="event-dialogue-input"
              className={styles.input}
              value={input}
              maxLength={answerMaxLength}
              rows={1}
              placeholder={inputPlaceholder}
              aria-invalid={showRequiredError}
              aria-describedby={showRequiredError ? "event-dialogue-error" : undefined}
              disabled={isSubmitting}
              onChange={handleInputChange}
            />
            <button
              className={styles.sendButton}
              type="submit"
              aria-label={`${inputLabel}を送る`}
              disabled={isSubmitting}
            >
              <span aria-hidden="true">→</span>
            </button>
          </div>

          {showRequiredError ? (
            <p id="event-dialogue-error" className={styles.errorMessage} role="alert">
              {inputLabel}を入力してください。
            </p>
          ) : null}

          {isSubmitting ? (
            <p className={styles.loadingMessage} role="status">
              AIが内容を整理しています…
            </p>
          ) : null}
        </form>

        <p className={styles.supportText}>相談窓口・利用上の注意</p>
      </section>
    </main>
  );
}
