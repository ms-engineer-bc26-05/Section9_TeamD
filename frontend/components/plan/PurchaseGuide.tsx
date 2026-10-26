import styles from "./plan.module.css";

type Props = {
  starting: boolean; // 購入手続きを開始中(ボタンを押せなくする)
  onPurchase: () => void;
  onConfirm: () => void; // 「決済を確認する」
};

// 無料プランに表示する、有料プランの案内(UI-012 / F-04 #58)
// - 購入を促しすぎない表現にする
// - テストモードであること、決済結果を確認してから反映することを伝える
export function PurchaseGuide({ starting, onPurchase, onConfirm }: Props) {
  return (
    <section className={styles.guide} aria-label="プランの違い">
      <h2 className={styles.sectionTitle}>プランの違いを確認</h2>

      <div className={styles.card}>
        <h3 className={styles.cardTitle}>有料プラン</h3>
        <ul className={styles.checkList}>
          <li>相談できる回数が増えます</li>
          <li>保存できるメモの件数が増えます</li>
        </ul>
        <p className={styles.note}>必要なときだけ、ご検討ください。</p>
        <p className={styles.note}>
          テスト環境のため、実際の請求は発生しません。
        </p>
        <button
          type="button"
          className={styles.primaryButton}
          onClick={onPurchase}
          disabled={starting}
        >
          購入手続きへ進む
        </button>
      </div>

      <p className={styles.infoBox}>
        決済結果を確認してから反映します。確認できない場合は成功として扱いません。
      </p>
      <p className={styles.footnote}>キャンセル時はプランを更新しません。</p>
      <p className={styles.footnote}>
        お支払い後に反映されない場合は、
        <button type="button" className={styles.linkButton} onClick={onConfirm}>
          決済を確認する
        </button>
      </p>
    </section>
  );
}