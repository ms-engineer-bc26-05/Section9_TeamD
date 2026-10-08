"use client";

import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
} from "react";

import type { ConsultationApi } from "../api/consultationApi";
import { toConsultationApiFailure } from "../api/consultationApiError";
import type {
  ConsultationView,
  StartConsultationRequest,
} from "../model/contracts";
import {
  consultationReducer,
  initialConsultationState,
  type ConsultationAction,
  type ConsultationOperation,
} from "../model/state";

interface ActiveRequest {
  controller: AbortController;
}

export interface ConsultationSessionController {
  state: ReturnType<typeof consultationReducer>;
  startConsultation: (request: StartConsultationRequest) => Promise<boolean>;
  restoreConsultation: (consultationId: string) => Promise<boolean>;
  discardConsultation: () => Promise<boolean>;
  cancelPendingRequest: () => void;
  clearError: () => void;
  reset: () => void;
}

/**
 * 相談の開始・復帰・破棄と、1リクエストずつ実行する境界を管理する。
 * 相談内容はReactのメモリ内だけで扱い、ブラウザストレージやログへ出力しない。
 */
export function useConsultationSessionController(
  api: ConsultationApi,
): ConsultationSessionController {
  const [state, dispatch] = useReducer(
    consultationReducer,
    initialConsultationState,
  );
  const activeRequestRef = useRef<ActiveRequest | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      activeRequestRef.current?.controller.abort();
      activeRequestRef.current = null;
    };
  }, []);

  const safeDispatch = useCallback((action: ConsultationAction) => {
    if (mountedRef.current) {
      dispatch(action);
    }
  }, []);

  const beginRequest = useCallback(
    (operation: ConsultationOperation): ActiveRequest | null => {
      if (activeRequestRef.current !== null) {
        return null;
      }

      const activeRequest = {
        controller: new AbortController(),
      };

      activeRequestRef.current = activeRequest;
      safeDispatch({ type: "request_started", operation });
      return activeRequest;
    },
    [safeDispatch],
  );

  const finishRequest = useCallback((activeRequest: ActiveRequest) => {
    if (activeRequestRef.current === activeRequest) {
      activeRequestRef.current = null;
    }
  }, []);

  const receiveView = useCallback(
    async (
      view: ConsultationView,
      consultationId: string,
      signal: AbortSignal,
    ) => {
      safeDispatch({ type: "view_received", view });

      if (view.status === "result_ready") {
        safeDispatch({ type: "request_started", operation: "fetch_result" });
        const result = await api.getResult(consultationId, { signal });
        safeDispatch({ type: "result_received", result });
      }
    },
    [api, safeDispatch],
  );

  const handleFailure = useCallback(
    (error: unknown, treatNotFoundAsStateLoss: boolean) => {
      const failure = toConsultationApiFailure(error);

      if (failure.type === "aborted") {
        safeDispatch({ type: "request_cancelled" });
        return;
      }

      if (
        treatNotFoundAsStateLoss &&
        failure.code === "CONSULTATION_NOT_FOUND"
      ) {
        safeDispatch({ type: "session_lost" });
        return;
      }

      safeDispatch({ type: "request_failed", code: failure.code });
    },
    [safeDispatch],
  );

  const startConsultation = useCallback(
    async (request: StartConsultationRequest): Promise<boolean> => {
      const activeRequest = beginRequest("start");
      if (activeRequest === null) {
        return false;
      }

      try {
        const view = await api.start(request, {
          signal: activeRequest.controller.signal,
        });
        await receiveView(
          view,
          view.consultation_id,
          activeRequest.controller.signal,
        );
        return true;
      } catch (error: unknown) {
        handleFailure(error, false);
        return false;
      } finally {
        finishRequest(activeRequest);
      }
    },
    [api, beginRequest, finishRequest, handleFailure, receiveView],
  );

  const restoreConsultation = useCallback(
    async (consultationId: string): Promise<boolean> => {
      if (consultationId.length === 0) {
        safeDispatch({ type: "session_lost" });
        return false;
      }

      const activeRequest = beginRequest("fetch_state");
      if (activeRequest === null) {
        return false;
      }

      try {
        const view = await api.get(consultationId, {
          signal: activeRequest.controller.signal,
        });
        await receiveView(view, consultationId, activeRequest.controller.signal);
        return true;
      } catch (error: unknown) {
        handleFailure(error, true);
        return false;
      } finally {
        finishRequest(activeRequest);
      }
    },
    [api, beginRequest, finishRequest, handleFailure, receiveView, safeDispatch],
  );

  const discardConsultation = useCallback(async (): Promise<boolean> => {
    if (state.consultationId === null) {
      safeDispatch({ type: "reset" });
      return true;
    }

    const activeRequest = beginRequest("discard");
    if (activeRequest === null) {
      return false;
    }

    try {
      await api.discard(state.consultationId, {
        signal: activeRequest.controller.signal,
      });
      safeDispatch({ type: "reset" });
      return true;
    } catch (error: unknown) {
      const failure = toConsultationApiFailure(error);

      if (
        failure.type === "failed" &&
        failure.code === "CONSULTATION_NOT_FOUND"
      ) {
        safeDispatch({ type: "reset" });
        return true;
      }

      handleFailure(error, false);
      return false;
    } finally {
      finishRequest(activeRequest);
    }
  }, [
    api,
    beginRequest,
    finishRequest,
    handleFailure,
    safeDispatch,
    state.consultationId,
  ]);

  const cancelPendingRequest = useCallback(() => {
    activeRequestRef.current?.controller.abort();
  }, []);

  const clearError = useCallback(() => {
    safeDispatch({ type: "clear_error" });
  }, [safeDispatch]);

  const reset = useCallback(() => {
    activeRequestRef.current?.controller.abort();
    safeDispatch({ type: "reset" });
  }, [safeDispatch]);

  return {
    state,
    startConsultation,
    restoreConsultation,
    discardConsultation,
    cancelPendingRequest,
    clearError,
    reset,
  };
}
