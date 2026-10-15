import type { MemoHandling } from "./contracts";

export const MEMO_HANDLING_LABELS: Record<MemoHandling, string> = {
  tell: "伝える",
  hold: "今は保留する",
  not_tell: "伝えない",
};

const MEMO_DATE_FORMATTER = new Intl.DateTimeFormat("ja-JP", {
  timeZone: "Asia/Tokyo",
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatMemoCreatedAt(createdAt: string): string {
  const date = new Date(createdAt);
  return Number.isNaN(date.getTime())
    ? "日時を表示できません"
    : MEMO_DATE_FORMATTER.format(date);
}
