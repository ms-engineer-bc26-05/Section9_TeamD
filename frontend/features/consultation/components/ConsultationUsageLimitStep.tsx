import styles from "./ConsultationUsageLimitStep.module.css";

interface ConsultationUsageLimitStepProps {
  onOpenPlan: () => void;
  onReturnHome: () => void;
}

export function ConsultationUsageLimitStep({
  onOpenPlan,
  onReturnHome,
}: ConsultationUsageLimitStepProps) {
  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="usage-limit-title">
        <p className={styles.eyebrow}>相談回数について</p>
        <h1 id="usage-limit-title" className={styles.title}>
          現在のプランで利用できる相談回数に達しました
        </h1>
        <p className={styles.message}>
          次に利用できる時期はホームで確認できます。プランについて確認することもできます。
        </p>

        <div className={styles.actions}>
          <button className={styles.primaryButton} type="button" onClick={onOpenPlan}>
            プランを確認する
          </button>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={onReturnHome}
          >
            ホームへ戻る
          </button>
        </div>
      </section>
    </main>
  );
}
