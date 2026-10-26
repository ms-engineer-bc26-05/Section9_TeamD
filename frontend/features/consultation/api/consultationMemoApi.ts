import { apiClient } from "@/lib/apiClient";

import type { AuthenticatedApiClient, ApiRequestOptions } from "./consultationApi";
import type { HandlingType } from "../model/contracts";

export interface SaveConsultationMemoRequest {
  reason: string | null;
}

export interface SavedConsultationMemo {
  memo_id: string;
  created_at: string;
  handling: HandlingType;
  reason: string | null;
  event_summary: string;
}

export interface ConsultationMemoApi {
  save(
    consultationId: string,
    request: SaveConsultationMemoRequest,
    options?: ApiRequestOptions,
  ): Promise<SavedConsultationMemo>;
}

export function createConsultationMemoApi(
  client: AuthenticatedApiClient,
): ConsultationMemoApi {
  return {
    save(consultationId, request, options) {
      return client.post<SavedConsultationMemo>(
        `/consultations/${encodeURIComponent(consultationId)}/save`,
        request,
        options,
      );
    },
  };
}

export const authenticatedConsultationMemoApi =
  createConsultationMemoApi(apiClient);
