import type {
  ConsultationResult,
  ConsultationView,
  EmotionRequest,
  EventDialogueRequest,
  EventSummaryConfirmRequest,
  GuidedDialogueRequest,
  HandlingRequest,
  StartConsultationRequest,
  UpdateConsultationResultRequest,
} from "../model/contracts";

export interface ApiRequestOptions {
  signal?: AbortSignal;
}

/**
 * Issue #48で確定した共通apiClientのうち、相談機能が利用する部分だけを表す。
 * IDトークンの取得・付与・更新は、実装側の共通apiClientが担当する。
 */
export interface AuthenticatedApiClient {
  get<T>(path: string, options?: ApiRequestOptions): Promise<T>;
  post<T>(
    path: string,
    body?: unknown,
    options?: ApiRequestOptions,
  ): Promise<T>;
  patch<T>(
    path: string,
    body?: unknown,
    options?: ApiRequestOptions,
  ): Promise<T>;
  delete(path: string, options?: ApiRequestOptions): Promise<void>;
}

export type StartedConsultationView = ConsultationView & {
  consultation_id: string;
};

export interface ConsultationApi {
  start(
    request: StartConsultationRequest,
    options?: ApiRequestOptions,
  ): Promise<StartedConsultationView>;
  get(
    consultationId: string,
    options?: ApiRequestOptions,
  ): Promise<ConsultationView>;
  discard(
    consultationId: string,
    options?: ApiRequestOptions,
  ): Promise<void>;
  answerEvent(
    consultationId: string,
    request: EventDialogueRequest,
    options?: ApiRequestOptions,
  ): Promise<ConsultationView>;
  confirmEventSummary(
    consultationId: string,
    request: EventSummaryConfirmRequest,
    options?: ApiRequestOptions,
  ): Promise<ConsultationView>;
  submitEmotion(
    consultationId: string,
    request: EmotionRequest,
    options?: ApiRequestOptions,
  ): Promise<ConsultationView>;
  answerGuidedDialogue(
    consultationId: string,
    request: GuidedDialogueRequest,
    options?: ApiRequestOptions,
  ): Promise<ConsultationView>;
  getResult(
    consultationId: string,
    options?: ApiRequestOptions,
  ): Promise<ConsultationResult>;
  updateResult(
    consultationId: string,
    request: UpdateConsultationResultRequest,
    options?: ApiRequestOptions,
  ): Promise<ConsultationResult>;
  approveResult(
    consultationId: string,
    options?: ApiRequestOptions,
  ): Promise<ConsultationView>;
  chooseHandling(
    consultationId: string,
    request: HandlingRequest,
    options?: ApiRequestOptions,
  ): Promise<ConsultationView>;
}

function consultationPath(consultationId: string): string {
  return `/consultations/${encodeURIComponent(consultationId)}`;
}

export function createConsultationApi(
  apiClient: AuthenticatedApiClient,
): ConsultationApi {
  return {
    start(request, options) {
      return apiClient.post<StartedConsultationView>(
        "/consultations",
        request,
        options,
      );
    },

    get(consultationId, options) {
      return apiClient.get<ConsultationView>(
        consultationPath(consultationId),
        options,
      );
    },

    discard(consultationId, options) {
      return apiClient.delete(consultationPath(consultationId), options);
    },

    answerEvent(consultationId, request, options) {
      return apiClient.post<ConsultationView>(
        `${consultationPath(consultationId)}/event-dialogue`,
        request,
        options,
      );
    },

    confirmEventSummary(consultationId, request, options) {
      return apiClient.post<ConsultationView>(
        `${consultationPath(consultationId)}/event-summary/confirm`,
        request,
        options,
      );
    },

    submitEmotion(consultationId, request, options) {
      return apiClient.post<ConsultationView>(
        `${consultationPath(consultationId)}/emotion`,
        request,
        options,
      );
    },

    answerGuidedDialogue(consultationId, request, options) {
      return apiClient.post<ConsultationView>(
        `${consultationPath(consultationId)}/guided-dialogue`,
        request,
        options,
      );
    },

    getResult(consultationId, options) {
      return apiClient.get<ConsultationResult>(
        `${consultationPath(consultationId)}/result`,
        options,
      );
    },

    updateResult(consultationId, request, options) {
      return apiClient.patch<ConsultationResult>(
        `${consultationPath(consultationId)}/result`,
        request,
        options,
      );
    },

    approveResult(consultationId, options) {
      return apiClient.post<ConsultationView>(
        `${consultationPath(consultationId)}/result/approve`,
        undefined,
        options,
      );
    },

    chooseHandling(consultationId, request, options) {
      return apiClient.post<ConsultationView>(
        `${consultationPath(consultationId)}/handling`,
        request,
        options,
      );
    },
  };
}
