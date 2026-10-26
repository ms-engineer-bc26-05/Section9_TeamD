import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/apiClient";

import { toConsultationApiFailure } from "./consultationApiError";

describe("toConsultationApiFailure", () => {
  it("共通ApiErrorの固定codeを相談画面へ引き継ぐ", () => {
    const failure = toConsultationApiFailure(
      new ApiError("conflict", { code: "CONSULTATION_BUSY" }),
    );

    expect(failure).toEqual({
      type: "failed",
      code: "CONSULTATION_BUSY",
    });
  });

  it.each([
    ["unauthenticated", "UNAUTHORIZED"],
    ["not_found", "CONSULTATION_NOT_FOUND"],
    ["conflict", "CONSULTATION_STATE_CONFLICT"],
    ["validation", "VALIDATION_ERROR"],
    ["ai_failed", "AI_UNAVAILABLE"],
    ["network", "NETWORK_ERROR"],
    ["server", "SERVER_ERROR"],
  ] as const)("codeがない%sを%sへ安全に変換する", (kind, expectedCode) => {
    expect(toConsultationApiFailure(new ApiError(kind))).toEqual({
      type: "failed",
      code: expectedCode,
    });
  });

  it("意図的なキャンセルを通信失敗と区別する", () => {
    expect(toConsultationApiFailure(new ApiError("aborted"))).toEqual({
      type: "aborted",
    });
  });

  it("未知のエラー本文を参照せずUNKNOWN_ERRORへ変換する", () => {
    expect(toConsultationApiFailure(new Error("表示してはいけない内容"))).toEqual({
      type: "failed",
      code: "UNKNOWN_ERROR",
    });
  });
});
