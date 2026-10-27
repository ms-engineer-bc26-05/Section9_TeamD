"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type {
  ConsultationMemoApi,
  SavedConsultationMemo,
} from "../api/consultationMemoApi";
import { toConsultationApiFailure } from "../api/consultationApiError";
import type { ConsultationErrorCode } from "../model/state";

export interface ConsultationMemoSaveRequest {
  consultationId: string;
  reason: string | null;
}

export interface ConsultationMemoSaveState {
  isSubmitting: boolean;
  errorCode: ConsultationErrorCode | null;
}

const INITIAL_STATE: ConsultationMemoSaveState = {
  isSubmitting: false,
  errorCode: null,
};

export function useConsultationMemoSave(
  api: ConsultationMemoApi,
  onApiError?: (error: unknown) => void,
) {
  const [state, setState] = useState<ConsultationMemoSaveState>(INITIAL_STATE);
  const activeControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      activeControllerRef.current?.abort();
      activeControllerRef.current = null;
    };
  }, []);

  const save = useCallback(
    async (
      request: ConsultationMemoSaveRequest,
    ): Promise<SavedConsultationMemo | null> => {
      if (activeControllerRef.current !== null) {
        return null;
      }

      const controller = new AbortController();
      activeControllerRef.current = controller;
      setState({ isSubmitting: true, errorCode: null });

      try {
        return await api.save(
          request.consultationId,
          { reason: request.reason },
          { signal: controller.signal },
        );
      } catch (error: unknown) {
        onApiError?.(error);
        const failure = toConsultationApiFailure(error);

        if (mountedRef.current) {
          setState({
            isSubmitting: false,
            errorCode: failure.type === "failed" ? failure.code : null,
          });
        }
        return null;
      } finally {
        if (activeControllerRef.current === controller) {
          activeControllerRef.current = null;
        }
        if (mountedRef.current) {
          setState((current) => ({ ...current, isSubmitting: false }));
        }
      }
    },
    [api, onApiError],
  );

  const reset = useCallback(() => {
    activeControllerRef.current?.abort();
    activeControllerRef.current = null;
    setState(INITIAL_STATE);
  }, []);

  return { state, save, reset };
}
