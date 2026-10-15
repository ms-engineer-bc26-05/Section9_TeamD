import styles from "./ConsultationUnavailableStep.module.css";

interface ConsultationUnavailableStepProps {
  onReturnHome: () => void;
}

export function ConsultationUnavailableStep({
  onReturnHome,
}: ConsultationUnavailableStepProps) {
  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="unavailable-title">
        <p className={styles.eyebrow}>相談を続けられません</p>
        <h1 id="unavailable-title" className={styles.title}>
          相談を続けるための情報を確認できませんでした
        </h1>
        <p className={styles.message}>
          安全のため、相談内容や詳しい理由は表示しません。ホームへ戻ってください。
        </p>
        <button className={styles.returnButton} type="button" onClick={onReturnHome}>
          ホームへ戻る
        </button>
      </section>
    </main>
  );
}
