import type { PlanCode, UsageResponse } from "@/lib/billing";

type Props = {
  plan: PlanCode;
  usage: UsageResponse | null;
};

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

// null の意味は backend の UsageView に合わせる
// - consultation_limit が null: 無制限
// - consultation_count が null: Redisから取得できず、回数が分からない
function consultationText(usage: UsageResponse): string {
  const { consultation_count: count, consultation_limit: limit } = usage;
  if (limit === null) return "相談回数:上限はありません。";
  if (count === null) {
    return `相談回数:現在の回数を確認できません(上限 ${limit}回)。`;
  }
  const remaining = Math.max(limit - count, 0);
  return `相談回数:残り${remaining}回(上限 ${limit}回)`;
}

function memoText(usage: UsageResponse): string {
  return usage.memo_limit === null
    ? `保存したメモ:${usage.memo_count}件`
    : `保存したメモ:${usage.memo_count}件(上限 ${usage.memo_limit}件)`;
}

// 現在の利用状況(UI-002)。表示できるのは、サーバーで確認できたプランだけ
export function UsageSummary({ plan, usage }: Props) {
  const resetDate = formatDate(usage?.consultation_resets_at ?? null);

  return (
    <section aria-label="利用状況">
      <h2>利用状況</h2>
      <p>{`現在のプラン:${plan === "premium" ? "有料プラン" : "無料プラン"}`}</p>

      {usage === null ? (
        <p>利用状況を取得できませんでした。</p>
      ) : (
        <>
          <p>{consultationText(usage)}</p>
          {usage.can_start_consultation ? (
            <>
              <p>相談を始められます。</p>
              {resetDate && (
                <p>{`この期間の回数は、${resetDate}にリセットされます。`}</p>
              )}
            </>
          ) : (
            <p>
              {`この期間の相談回数の上限に達しました。${
                resetDate ? `${resetDate}以降に、また相談できます。` : ""
              }`}
            </p>
          )}
          <p>{memoText(usage)}</p>
        </>
      )}
    </section>
  );
}