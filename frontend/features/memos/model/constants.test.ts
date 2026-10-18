import { describe, expect, it } from "vitest";

import { formatMemoCreatedAt } from "./constants";

describe("formatMemoCreatedAt", () => {
  it("UTCの日時を日本時間で表示する", () => {
    expect(formatMemoCreatedAt("2026-10-15T10:00:00Z")).toBe(
      "2026年10月15日 19:00",
    );
  });

  it("不正な日時では固定文言を返す", () => {
    expect(formatMemoCreatedAt("invalid-date")).toBe("日時を表示できません");
  });
});
