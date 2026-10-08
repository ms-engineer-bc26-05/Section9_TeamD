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
  EmotionRequest,
  EventDialogueRequest,
  EventSummaryConfirmRequest,
  GuidedDialogueRequest,
  HandlingType,
  StartConsultationRequest,
  UpdateConsultationResultRequest,
} from "../model/contracts";
import {
  areResultChangesApplied,
  createPostRecoverySnapshot,
  decideApprovalRecovery,
  decidePostRecovery,
  decideResultUpdateRecovery,
  type PostRecoverySnapshot,
} from "../model/recovery";
import {
  consultationReducer,
  initialConsultationState,
  type ConsultationAction,
  type ConsultationOperation,
} from "../model/state";

interface ActiveRequest {
  controller: AbortController;
}

type ResultUpdateOutcome = "continue_approval" | "completed" | "failed";

export interface ConsultationSessionController {
  state: ReturnType<typeof consultationReducer>;
  startConsultation: (request: StartConsultationRequest) => Promise<boolean>;
  restoreConsultation: (consultationId: string) => Promise<boolean>;
  discardConsultation: () => Promise<boolean>;
  submitEventDialogue: (request: EventDialogueRequest) => Promise<boolean>;
  confirmEventSummary: (
    request: EventSummaryConfirmRequest,
  ) => Promise<boolean>;
  submitEmotion: (request: EmotionRequest) => Promise<boolean>;
  submitGuidedDialogue: (
    request: GuidedDialogueRequest,
  ) => Promise<boolean>;
  updateAndApproveResult: (
    changes: UpdateConsultationResultRequest,
  ) => Promise<boolean>;
  chooseHandling: (handling: HandlingType) => Promise<boolean>;
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

  const runViewOperation = useCallback(
    async (
      operation: ConsultationOperation,
      request: (
        consultationId: string,
        signal: AbortSignal,
      ) => Promise<ConsultationView>,
    ): Promise<boolean> => {
      if (state.consultationId === null) {
        safeDispatch({ type: "session_lost" });
        return false;
      }

      const consultationId = state.consultationId;
      const activeRequest = beginRequest(operation);
      if (activeRequest === null) {
        return false;
      }

      try {
        const view = await request(
          consultationId,
          activeRequest.controller.signal,
        );
        await receiveView(
          view,
          consultationId,
          activeRequest.controller.signal,
        );
        return true;
      } catch (error: unknown) {
        handleFailure(error, true);
        return false;
      } finally {
        finishRequest(activeRequest);
      }
    },
    [
      beginRequest,
      finishRequest,
      handleFailure,
      receiveView,
      safeDispatch,
      state.consultationId,
    ],
  );

  const recoverPostResponse = useCallback(
    async (
      consultationId: string,
      before: PostRecoverySnapshot,
      signal: AbortSignal,
    ): Promise<boolean> => {
      try {
        const current = await api.get(consultationId, { signal });
        const decision = decidePostRecovery(before, current);

        switch (decision) {
          case "advanced":
          case "safety_guidance":
            await receiveView(current, consultationId, signal);
            return true;
          case "retry":
            safeDispatch({ type: "request_failed", code: "NETWORK_ERROR" });
            return false;
          case "state_conflict":
            safeDispatch({
              type: "request_failed",
              code: "CONSULTATION_STATE_CONFLICT",
            });
            return false;
        }
      } catch (error: unknown) {
        handleFailure(error, true);
        return false;
      }
    },
    [api, handleFailure, receiveView, safeDispatch],
  );

  const runRecoverablePost = useCallback(
    async (
      operation: ConsultationOperation,
      request: (
        consultationId: string,
        signal: AbortSignal,
      ) => Promise<ConsultationView>,
    ): Promise<boolean> => {
      if (state.consultationId === null) {
        safeDispatch({ type: "session_lost" });
        return false;
      }

      const consultationId = state.consultationId;
      const before = createPostRecoverySnapshot(state);
      const activeRequest = beginRequest(operation);
      if (activeRequest === null) {
        return false;
      }

      try {
        const view = await request(
          consultationId,
          activeRequest.controller.signal,
        );
        await receiveView(
          view,
          consultationId,
          activeRequest.controller.signal,
        );
        return true;
      } catch (error: unknown) {
        const failure = toConsultationApiFailure(error);

        if (
          before !== null &&
          failure.type === "failed" &&
          failure.code === "NETWORK_ERROR"
        ) {
          return recoverPostResponse(
            consultationId,
            before,
            activeRequest.controller.signal,
          );
        }

        handleFailure(error, true);
        return false;
      } finally {
        finishRequest(activeRequest);
      }
    },
    [
      beginRequest,
      finishRequest,
      handleFailure,
      receiveView,
      recoverPostResponse,
      safeDispatch,
      state,
    ],
  );

  const submitEventDialogue = useCallback(
    (request: EventDialogueRequest) =>
      runViewOperation("event_dialogue", (consultationId, signal) =>
        api.answerEvent(consultationId, request, { signal }),
      ),
    [api, runViewOperation],
  );

  const confirmEventSummary = useCallback(
    (request: EventSummaryConfirmRequest) =>
      runViewOperation("confirm_event_summary", (consultationId, signal) =>
        api.confirmEventSummary(consultationId, request, { signal }),
      ),
    [api, runViewOperation],
  );

  const submitEmotion = useCallback(
    (request: EmotionRequest) =>
      runRecoverablePost("submit_emotion", (consultationId, signal) =>
        api.submitEmotion(consultationId, request, { signal }),
      ),
    [api, runRecoverablePost],
  );

  const submitGuidedDialogue = useCallback(
    (request: GuidedDialogueRequest) =>
      runRecoverablePost("guided_dialogue", (consultationId, signal) =>
        api.answerGuidedDialogue(consultationId, request, { signal }),
      ),
    [api, runRecoverablePost],
  );

  const recoverResultUpdate = useCallback(
    async (
      consultationId: string,
      changes: UpdateConsultationResultRequest,
      signal: AbortSignal,
    ): Promise<ResultUpdateOutcome> => {
      try {
        const currentView = await api.get(consultationId, { signal });
        const decision = decideResultUpdateRecovery(currentView.status);

        switch (decision) {
          case "fetch_result": {
            safeDispatch({ type: "view_received", view: currentView });
            safeDispatch({ type: "request_started", operation: "fetch_result" });
            const currentResult = await api.getResult(consultationId, { signal });
            safeDispatch({ type: "result_received", result: currentResult });

            if (areResultChangesApplied(changes, currentResult)) {
              return "continue_approval";
            }

            safeDispatch({ type: "request_failed", code: "NETWORK_ERROR" });
            return "failed";
          }
          case "advanced":
          case "safety_guidance":
            await receiveView(currentView, consultationId, signal);
            return "completed";
          case "state_conflict":
            safeDispatch({
              type: "request_failed",
              code: "CONSULTATION_STATE_CONFLICT",
            });
            return "failed";
        }
      } catch (error: unknown) {
        handleFailure(error, true);
        return "failed";
      }
    },
    [api, handleFailure, receiveView, safeDispatch],
  );

  const updateResultBeforeApproval = useCallback(
    async (
      consultationId: string,
      changes: UpdateConsultationResultRequest,
      signal: AbortSignal,
    ): Promise<ResultUpdateOutcome> => {
      try {
        const result = await api.updateResult(consultationId, changes, {
          signal,
        });
        safeDispatch({ type: "result_received", result });
        return "continue_approval";
      } catch (error: unknown) {
        const failure = toConsultationApiFailure(error);

        if (
          failure.type === "failed" &&
          failure.code === "NETWORK_ERROR"
        ) {
          return recoverResultUpdate(consultationId, changes, signal);
        }

        handleFailure(error, true);
        return "failed";
      }
    },
    [api, handleFailure, recoverResultUpdate, safeDispatch],
  );

  const recoverApproval = useCallback(
    async (
      consultationId: string,
      signal: AbortSignal,
    ): Promise<boolean> => {
      try {
        const currentView = await api.get(consultationId, { signal });
        const decision = decideApprovalRecovery(currentView.status);

        switch (decision) {
          case "approved":
          case "safety_guidance":
            await receiveView(currentView, consultationId, signal);
            return true;
          case "retry":
            safeDispatch({ type: "request_failed", code: "NETWORK_ERROR" });
            return false;
          case "state_conflict":
            safeDispatch({
              type: "request_failed",
              code: "CONSULTATION_STATE_CONFLICT",
            });
            return false;
        }
      } catch (error: unknown) {
        handleFailure(error, true);
        return false;
      }
    },
    [api, handleFailure, receiveView, safeDispatch],
  );

  const updateAndApproveResult = useCallback(
    async (changes: UpdateConsultationResultRequest): Promise<boolean> => {
      if (state.consultationId === null) {
        safeDispatch({ type: "session_lost" });
        return false;
      }

      const consultationId = state.consultationId;
      const hasChanges = Object.keys(changes).length > 0;
      const activeRequest = beginRequest(
        hasChanges ? "update_result" : "approve_result",
      );
      if (activeRequest === null) {
        return false;
      }

      try {
        if (hasChanges) {
          const updateOutcome = await updateResultBeforeApproval(
            consultationId,
            changes,
            activeRequest.controller.signal,
          );

          if (updateOutcome === "completed") {
            return true;
          }

          if (updateOutcome === "failed") {
            return false;
          }
        }

        safeDispatch({ type: "request_started", operation: "approve_result" });

        try {
          const view = await api.approveResult(consultationId, {
            signal: activeRequest.controller.signal,
          });
          await receiveView(
            view,
            consultationId,
            activeRequest.controller.signal,
          );
          return true;
        } catch (error: unknown) {
          const failure = toConsultationApiFailure(error);

          if (
            failure.type === "failed" &&
            failure.code === "NETWORK_ERROR"
          ) {
            return recoverApproval(
              consultationId,
              activeRequest.controller.signal,
            );
          }

          handleFailure(error, true);
          return false;
        }
      } finally {
        finishRequest(activeRequest);
      }
    },
    [
      api,
      beginRequest,
      finishRequest,
      handleFailure,
      receiveView,
      recoverApproval,
      safeDispatch,
      state.consultationId,
      updateResultBeforeApproval,
    ],
  );

  const chooseHandling = useCallback(
    (handling: HandlingType) =>
      runViewOperation("choose_handling", (consultationId, signal) =>
        api.chooseHandling(consultationId, { handling }, { signal }),
      ),
    [api, runViewOperation],
  );

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
    submitEventDialogue,
    confirmEventSummary,
    submitEmotion,
    submitGuidedDialogue,
    updateAndApproveResult,
    chooseHandling,
    cancelPendingRequest,
    clearError,
    reset,
  };
}
