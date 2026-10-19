import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/apiClient";

import type {
  ConsultationMemoApi,
  SavedConsultationMemo,
} from "../api/consultationMemoApi";
import { useConsultationMemoSave } from "./useConsultationMemoSave";

const savedMemo: SavedConsultationMemo = {
  memo_id: "memo-1",
  created_at: "2026-10-13T12:00:00Z",
  handling: "hold",
  reason: null,
  event_summary: "架空の出来事",
};

function createApi(): ConsultationMemoApi {
  return { save: vi.fn() };
}

describe("useConsultationMemoSave", () => {
  it("認証エラーを共通認証処理へ通知し、保存成功にしない", async () => {
    const api = createApi();
    const error = new ApiError("forbidden", {
      status: 403,
      code: "ACCOUNT_DELETING",
    });
    const onApiError = vi.fn();
    vi.mocked(api.save).mockRejectedValue(error);
    const { result } = renderHook(() =>
      useConsultationMemoSave(api, onApiError),
    );

    let response: SavedConsultationMemo | null = savedMemo;
    await act(async () => {
      response = await result.current.save({
        consultationId: "c1",
        reason: null,
      });
    });

    expect(response).toBeNull();
    expect(onApiError).toHaveBeenCalledOnce();
    expect(onApiError).toHaveBeenCalledWith(error);
  });

  it("保存成功時に保存済みメモを返す", async () => {
    const api = createApi();
    vi.mocked(api.save).mockResolvedValue(savedMemo);
    const { result } = renderHook(() => useConsultationMemoSave(api));

    let response: SavedConsultationMemo | null = null;
    await act(async () => {
      response = await result.current.save({
        consultationId: "c1",
        reason: null,
      });
    });

    expect(response).toEqual(savedMemo);
    expect(api.save).toHaveBeenCalledOnce();
    expect(result.current.state).toEqual({
      isSubmitting: false,
      errorCode: null,
    });
  });

  it("保存処理中の再送を拒否する", async () => {
    const api = createApi();
    let resolveSave: ((memo: SavedConsultationMemo) => void) | null = null;
    vi.mocked(api.save).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSave = resolve;
        }),
    );
    const { result } = renderHook(() => useConsultationMemoSave(api));

    let firstRequest: Promise<SavedConsultationMemo | null> | null = null;
    let secondRequest: Promise<SavedConsultationMemo | null> | null = null;
    act(() => {
      firstRequest = result.current.save({ consultationId: "c1", reason: null });
      secondRequest = result.current.save({ consultationId: "c1", reason: null });
    });

    await expect(secondRequest).resolves.toBeNull();
    expect(api.save).toHaveBeenCalledOnce();

    await act(async () => {
      resolveSave?.(savedMemo);
      await firstRequest;
    });
  });

  it.each([
    ["network", undefined, "NETWORK_ERROR"],
    ["forbidden", "MEMO_LIMIT_EXCEEDED", "MEMO_LIMIT_EXCEEDED"],
    ["not_found", "CONSULTATION_NOT_FOUND", "CONSULTATION_NOT_FOUND"],
    ["server", "INTERNAL_SERVER_ERROR", "SERVER_ERROR"],
  ] as const)(
    "%sエラーを安全な画面用コードへ変換する",
    async (kind, code, expectedCode) => {
      const api = createApi();
      vi.mocked(api.save).mockRejectedValue(new ApiError(kind, { code }));
      const { result } = renderHook(() => useConsultationMemoSave(api));

      await act(async () => {
        await result.current.save({ consultationId: "c1", reason: null });
      });

      expect(result.current.state).toEqual({
        isSubmitting: false,
        errorCode: expectedCode,
      });
    },
  );
});
