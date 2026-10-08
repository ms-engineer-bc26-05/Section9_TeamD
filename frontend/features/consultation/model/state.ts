import type {
  ConsultationResult,
  ConsultationStatus,
  ConsultationView,
  EmotionCategory,
  EventDetails,
  GuidedTopic,
  HandlingType,
  KnownConsultationErrorCode,
  SafetyGuidance,
} from "./contracts";

export type ConsultationOperation =
  | "start"
  | "fetch_state"
  | "event_dialogue"
  | "confirm_event_summary"
  | "submit_emotion"
  | "guided_dialogue"
  | "fetch_result"
  | "update_result"
  | "approve_result"
  | "choose_handling"
  | "discard";

export type ConsultationErrorCode =
  | KnownConsultationErrorCode
  | "NETWORK_ERROR"
  | "SERVER_ERROR"
  | "UNKNOWN_ERROR";

export interface ConsultationState {
  consultationId: string | null;
  status: ConsultationStatus | null;
  questionCount: number | null;
  canAskMore: boolean | null;
  correctionCount: number | null;
  correctionLimitReached: boolean | null;
  aiUnderstanding: string | null;
  aiQuestion: string | null;
  aiResponse: string | null;
  emotionCategory: EmotionCategory | null;
  currentTopic: GuidedTopic | null;
  eventDetails: EventDetails | null;
  result: ConsultationResult | null;
  handling: HandlingType | null;
  approved: boolean;
  safetyGuidance: SafetyGuidance | null;
  pendingOperation: ConsultationOperation | null;
  errorCode: ConsultationErrorCode | null;
}

export const initialConsultationState: ConsultationState = {
  consultationId: null,
  status: null,
  questionCount: null,
  canAskMore: null,
  correctionCount: null,
  correctionLimitReached: null,
  aiUnderstanding: null,
  aiQuestion: null,
  aiResponse: null,
  emotionCategory: null,
  currentTopic: null,
  eventDetails: null,
  result: null,
  handling: null,
  approved: false,
  safetyGuidance: null,
  pendingOperation: null,
  errorCode: null,
};

export type ConsultationAction =
  | { type: "request_started"; operation: ConsultationOperation }
  | { type: "view_received"; view: ConsultationView }
  | { type: "result_received"; result: ConsultationResult }
  | { type: "request_failed"; code: ConsultationErrorCode }
  | { type: "request_cancelled" }
  | { type: "session_lost" }
  | { type: "clear_error" }
  | { type: "reset" };

function stateFromView(
  state: ConsultationState,
  view: ConsultationView,
): ConsultationState {
  if (view.status === "safety_guidance") {
    return {
      ...initialConsultationState,
      consultationId: view.consultation_id ?? state.consultationId,
      status: "safety_guidance",
      safetyGuidance: view.safety_guidance ?? null,
    };
  }

  return {
    consultationId: view.consultation_id ?? state.consultationId,
    status: view.status,
    questionCount: view.question_count ?? null,
    canAskMore: view.can_ask_more ?? null,
    correctionCount: view.correction_count ?? null,
    correctionLimitReached: view.correction_limit_reached ?? null,
    aiUnderstanding: view.ai_understanding ?? null,
    aiQuestion: view.ai_question ?? null,
    aiResponse: view.ai_response ?? null,
    emotionCategory: view.emotion_category ?? state.emotionCategory,
    currentTopic: view.current_topic ?? null,
    eventDetails: view.event_details ?? null,
    result: state.result,
    handling: view.handling ?? state.handling,
    approved: view.approved ?? state.approved,
    safetyGuidance: view.safety_guidance ?? null,
    pendingOperation: null,
    errorCode: null,
  };
}

export function consultationReducer(
  state: ConsultationState,
  action: ConsultationAction,
): ConsultationState {
  switch (action.type) {
    case "request_started":
      return {
        ...state,
        pendingOperation: action.operation,
        errorCode: null,
      };

    case "view_received":
      return stateFromView(state, action.view);

    case "result_received":
      return {
        ...state,
        result: action.result,
        approved: action.result.approved,
        pendingOperation: null,
        errorCode: null,
      };

    case "request_failed":
      return {
        ...state,
        pendingOperation: null,
        errorCode: action.code,
      };

    case "request_cancelled":
      return {
        ...state,
        pendingOperation: null,
        errorCode: null,
      };

    case "session_lost":
      return {
        ...initialConsultationState,
        errorCode: "CONSULTATION_NOT_FOUND",
      };

    case "clear_error":
      return {
        ...state,
        errorCode: null,
      };

    case "reset":
      return initialConsultationState;
  }
}

export function isConsultationPending(state: ConsultationState): boolean {
  return state.pendingOperation !== null;
}
