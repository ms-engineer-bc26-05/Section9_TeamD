import type { PlanErrorKind, PlanPhase } from "@/lib/usePlanStatus";

type Props = {
  phase: PlanPhase;
  errorKind: PlanErrorKind | null;
  onConfirm: () => void; // 「決済を確認する」
  onPurchase: () => void; // 購入手続き(期限切れ・準備中のやり直し)
  onRetry: () => void; // 直前に失敗した操作の再試行
};

// エラーの固定文言。内部コード・サーバーの文言は表示しない
const ERROR_MESSAGES: Record<PlanErrorKind, string> = {
  network: "通信できませんでした。接続を確認してもう一度お試しください。",
  server: "サーバーで問題が発生しました。時間をおいてもう一度お試しください。",
  validation:
    "購入手続きを開始できませんでした。時間をおいてもう一度お試しください。",
  plan_unavailable: "このプランは現在購入できません。",
};

// 決済の確認・購入手続きの途中状態を、利用者向けの文言で表示する(F-04 / #58)
// - APIの状態名・エラーコード・Stripe内部の状態は表示しない
// - pending は再確認だけを案内する(再購入は促さない)
export function PhaseMessage({
  phase,
  errorKind,
  onConfirm,
  onPurchase,
  onRetry,
}: Props) {
  switch (phase) {
    case "starting":
      return <p role="status">決済画面へ移動しています。</p>;

    case "confirming":
      return <p role="status">決済状態を確認しています。</p>;

    case "pending":
      return (
        <section aria-label="決済の確認">
          <p role="status">
            決済状態をまだ確認できません。少し時間をおいて、もう一度ご確認ください。
          </p>
          <button type="button" onClick={onConfirm}>
            決済を確認する
          </button>
        </section>
      );

    case "expired":
      return (
        <section aria-label="決済の確認">
          <p role="status">
            決済手続きは完了していません。購入を希望する場合は、もう一度お手続きください。
          </p>
          <button type="button" onClick={onPurchase}>
            購入手続きへ進む
          </button>
        </section>
      );

    case "in_progress":
      return (
        <section aria-label="決済の準備">
          <p role="status">
            決済画面を準備しています。少し待ってから、もう一度お試しください。
          </p>
          <button type="button" onClick={onPurchase}>
            もう一度試す
          </button>
        </section>
      );

    case "not_found":
      return <p role="alert">確認できる決済がありません。</p>;

    case "error": {
      const kind = errorKind ?? "server";
      return (
        <section aria-label="エラー">
          <p role="alert">{ERROR_MESSAGES[kind]}</p>
          {/* 購入できないプランは、再試行しても変わらないので、ボタンを出さない */}
          {kind !== "plan_unavailable" && (
            <button type="button" onClick={onRetry}>
              再試行する
            </button>
          )}
        </section>
      );
    }

    default:
      return null;
  }
}