"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";

import { EMOTION_OPTIONS, GUIDED_TOPIC_LABELS } from "../model/constants";
import type {
  EmotionCategory,
  GuidedDialogueRequest,
  GuidedTopic,
} from "../model/contracts";
import styles from "./GuidedDialogueStep.module.css";

const GUIDED_TOPICS: readonly GuidedTopic[] = [
  "true_feeling",
  "background",
  "wish",
];

export interface GuidedDialogueHistoryItem {
  topic: GuidedTopic;
  answer: string;
  skipped?: boolean;
}

interface GuidedDialogueStepProps {
  selectedEmotion: EmotionCategory;
  aiResponse: string | null;
  aiQuestion: string;
  currentTopic: GuidedTopic;
  history: readonly GuidedDialogueHistoryItem[];
  answer: string;
  answerMaxLength: number;
  isSubmitting: boolean;
  onAnswerChange: (answer: string) => void;
  onSubmit: (request: GuidedDialogueRequest) => void;
  onCancel: () => void;
}

export function GuidedDialogueStep({
  selectedEmotion,
  aiResponse,
  aiQuestion,
  currentTopic,
  history,
  answer,
  answerMaxLength,
  isSubmitting,
  onAnswerChange,
  onSubmit,
  onCancel,
}: GuidedDialogueStepProps) {
  const [showRequiredError, setShowRequiredError] = useState(false);
  const selectedEmotionLabel =
    EMOTION_OPTIONS.find((option) => option.value === selectedEmotion)?.label ??
    "選択した気持ち";
  const currentTopicIndex = GUIDED_TOPICS.indexOf(currentTopic);
  const hasAnswer = answer.trim().length > 0;
  const canSkip = currentTopic === "background";

  function handleAnswerChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const nextAnswer = event.target.value;

    if (nextAnswer.trim().length > 0) {
      setShowRequiredError(false);
    }

    onAnswerChange(nextAnswer);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (!hasAnswer) {
      setShowRequiredError(true);
      return;
    }

    setShowRequiredError(false);
    onSubmit({ answer });
  }

  function handleSkip() {
    if (isSubmitting || !canSkip) {
      return;
    }

    setShowRequiredError(false);
    onSubmit({ skipped: true });
  }

  const describedBy = showRequiredError
    ? "guided-dialogue-help guided-dialogue-count guided-dialogue-error"
    : "guided-dialogue-help guided-dialogue-count";

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="guided-dialogue-title">
        <header className={styles.header}>
          <span className={styles.headerSpacer} aria-hidden="true" />
          <h1 id="guided-dialogue-title" className={styles.headerTitle}>
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
          <li className={styles.completedStep}>出来事</li>
          <li className={styles.completedStep}>感情</li>
          {GUIDED_TOPICS.map((topic, index) => {
            const className =
              index < currentTopicIndex
                ? styles.completedStep
                : index === currentTopicIndex
                  ? styles.currentStep
                  : undefined;

            return (
              <li
                key={topic}
                className={className}
                aria-current={index === currentTopicIndex ? "step" : undefined}
              >
                {GUIDED_TOPIC_LABELS[topic]}
              </li>
            );
          })}
        </ol>

        <p className={styles.emotionTag}>選んだ気持ち：{selectedEmotionLabel}</p>

        <div className={styles.dialogue}>
          {aiResponse ? (
            <div className={styles.aiBubble}>
              <p>{aiResponse}</p>
            </div>
          ) : null}

          {history.map((item, index) => (
            <div className={styles.historyGroup} key={`${item.topic}-${index}`}>
              <p className={styles.historyTopic}>{GUIDED_TOPIC_LABELS[item.topic]}</p>
              <div className={styles.userBubble}>
                <p>{item.skipped ? "まだ分からない" : item.answer}</p>
              </div>
            </div>
          ))}

          <div className={styles.aiBubble} aria-live="polite">
            <p className={styles.topicLabel}>
              今は「{GUIDED_TOPIC_LABELS[currentTopic]}」を整理しています
            </p>
            <p className={styles.aiQuestion}>{aiQuestion}</p>
            {currentTopic === "background" ? (
              <p className={styles.questionHint}>
                相手の意図ではなく、あなた自身のことを思いつく範囲で大丈夫です
              </p>
            ) : null}
          </div>
        </div>

        {canSkip ? (
          <button
            className={styles.skipButton}
            type="button"
            disabled={isSubmitting}
            onClick={handleSkip}
          >
            まだ分からない
          </button>
        ) : null}

        <form className={styles.answerForm} onSubmit={handleSubmit}>
          <label className={styles.answerLabel} htmlFor="guided-dialogue-answer">
            あなたの言葉で答えてください
          </label>
          <div className={styles.answerWrapper}>
            <textarea
              id="guided-dialogue-answer"
              className={styles.answerInput}
              value={answer}
              maxLength={answerMaxLength}
              rows={2}
              placeholder="短くても大丈夫です"
              aria-describedby={describedBy}
              aria-invalid={showRequiredError}
              disabled={isSubmitting}
              onChange={handleAnswerChange}
            />
            <button
              className={styles.sendButton}
              type="submit"
              aria-label={`${GUIDED_TOPIC_LABELS[currentTopic]}の回答を送る`}
              disabled={isSubmitting || !hasAnswer}
            >
              <span aria-hidden="true">→</span>
            </button>
          </div>
          <div className={styles.answerMeta}>
            <p id="guided-dialogue-help" className={styles.answerHelp}>
              {canSkip ? "回答するか、「まだ分からない」を選べます" : "短い回答でも大丈夫です"}
            </p>
            <output id="guided-dialogue-count" className={styles.characterCount}>
              {answer.length} / {answerMaxLength}
            </output>
          </div>

          {showRequiredError ? (
            <p id="guided-dialogue-error" className={styles.errorMessage} role="alert">
              回答を入力してください。
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
