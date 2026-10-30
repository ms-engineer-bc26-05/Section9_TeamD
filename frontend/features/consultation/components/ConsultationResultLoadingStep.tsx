import styles from "./ConsultationResultLoadingStep.module.css";

interface ConsultationResultLoadingStepProps {
  isLoading: boolean;
  hasError: boolean;
  onRetry: () => void;
  onCancel: () => void;
}

export function ConsultationResultLoadingStep({
  isLoading,
  hasError,
  onRetry,
  onCancel,
}: ConsultationResultLoadingStepProps) {
  return (
    <main className={styles.page}>
      <section
        className={styles.panel}
        aria-labelledby="result-loading-title"
        aria-busy={isLoading}
      >
        <p className={styles.eyebrow}>整理結果</p>
        <h1 id="result-loading-title" className={styles.title}>
          {hasError
            ? "整理結果を取得できませんでした"
            : "整理結果を準備しています"}
        </h1>

        {hasError ? (
          <>
            <p className={styles.message}>
              入力内容はそのままです。少し待ってから、もう一度お試しください。
            </p>
            <button
              className={styles.primaryButton}
              type="button"
              disabled={isLoading}
              onClick={onRetry}
            >
              もう一度取得する
            </button>
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isLoading}
              onClick={onCancel}
            >
              相談を終了する
            </button>
          </>
        ) : (
          <p className={styles.loadingMessage} role="status">
            内容をまとめています。もう少しお待ちください…
          </p>
        )}
      </section>
    </main>
  );
}
