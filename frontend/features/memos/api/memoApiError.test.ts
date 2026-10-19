import { describe, expect, it } from "vitest";

import { toMemoApiFailure } from "./memoApiError";

describe("toMemoApiFailure", () => {
  it("404をメモ不存在へ変換する", () => {
    expect(toMemoApiFailure({ kind: "not_found" })).toEqual({
      type: "failed",
      code: "MEMO_NOT_FOUND",
    });
  });

  it("通信失敗と中断を区別する", () => {
    expect(toMemoApiFailure({ kind: "network" })).toEqual({
      type: "failed",
      code: "NETWORK_ERROR",
    });
    expect(toMemoApiFailure({ kind: "aborted" })).toEqual({ type: "aborted" });
  });

  it("error messageや未知のcodeを画面用コードとして採用しない", () => {
    expect(
      toMemoApiFailure({
        kind: "server",
        code: "INTERNAL_DETAIL",
        message: "sensitive",
      }),
    ).toEqual({ type: "failed", code: "SERVER_ERROR" });
  });
});
