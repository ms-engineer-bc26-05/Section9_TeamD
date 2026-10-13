import type { PlanCode, UsageResponse } from "@/lib/billing";

type Props = {
  plan: PlanCode;
  usage: UsageResponse | null;
};

function formatResetDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

// 現在の利用状況(UI-002)。表示できるのは、サーバーで確認できたプランだけ
// TODO: 残り回数。GET /usage の最終的なレスポンス項目(API設計書6.7)が分かったら追加する
export function UsageSummary({ plan, usage }: Props) {
  const resetDate = formatResetDate(usage?.consultation_resets_at ?? null);

  return (
    <section aria-label="利用状況">
      <h2>利用状況</h2>
      <p>現在のプラン:{plan === "premium" ? "有料プラン" : "無料プラン"}</p>

      {usage === null ? (
        <p>利用状況を取得できませんでした。</p>
      ) : usage.can_start_consultation ? (
        <p>相談を始められます。</p>
      ) : (
        <p>
          この期間の相談回数の上限に達しました。
          {resetDate ? `${resetDate}以降に、また利用できます。` : ""}
        </p>
      )}
    </section>
  );
}