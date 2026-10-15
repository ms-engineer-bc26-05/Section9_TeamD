/**
 * Issue #49で確定した相談APIの公開契約。
 *
 * バックエンド内部のAI分類には依存せず、公開APIが返すstatusなどだけを扱う。
 */

export type ConsultationStatus =
  | "event_dialogue"
  | "event_summary_ready"
  | "emotion_selection"
  | "guided_dialogue"
  | "result_ready"
  | "handling_selection"
  | "save_confirmation"
  | "safety_guidance";

export type ThemeCategory =
  | "communication"
  | "lifestyle"
  | "money"
  | "care"
  | "future"
  | "other";

export type EmotionCategory =
  | "lonely"
  | "sad"
  | "anxious"
  | "angry"
  | "confused"
  | "hurt"
  | "self_blame"
  | "other";

export type GuidedTopic = "true_feeling" | "background" | "wish";

export type HandlingType = "tell" | "hold" | "not_tell";

export interface EventDetails {
  what_happened: string;
  what_bothered_me: string;
}

export interface SafetyGuidance {
  risk_detected: boolean;
  safety_message: string;
  continued_normal_structuring: boolean;
}

export interface ConsultationResult {
  event_summary: string;
  emotion: string;
  true_feeling: string;
  background: string;
  wish: string;
  approved: boolean;
}

export interface ConsultationView {
  consultation_id?: string;
  status: ConsultationStatus;
  question_count?: number;
  can_ask_more?: boolean;
  correction_count?: number;
  correction_limit_reached?: boolean;
  ai_understanding?: string;
  ai_question?: string;
  ai_response?: string;
  current_topic?: GuidedTopic;
  event_details?: EventDetails;
  emotion_category?: EmotionCategory;
  handling?: HandlingType;
  approved?: boolean;
  safety_guidance?: SafetyGuidance;
}

export interface StartConsultationRequest {
  theme: ThemeCategory;
  detail: string;
}

export type EventDialogueRequest =
  | {
      action: "answer";
      answer: string;
      correction_input?: never;
    }
  | {
      action: "correct";
      answer?: never;
      correction_input: string;
    };

export type EventSummaryConfirmRequest =
  | {
      action: "proceed";
      event_details?: EventDetails;
    }
  | {
      action: "ask_more";
      event_details?: never;
    };

export type EmotionRequest =
  | {
      category: EmotionCategory;
      detail: string;
      cannot_verbalize?: false;
    }
  | {
      category: EmotionCategory;
      detail?: never;
      cannot_verbalize: true;
    };

export type GuidedDialogueRequest =
  | {
      answer: string;
      skipped?: false;
    }
  | {
      answer?: never;
      skipped: true;
    };

export type UpdateConsultationResultRequest = Partial<
  Omit<ConsultationResult, "approved">
>;

export interface HandlingRequest {
  handling: HandlingType;
}

export type KnownConsultationErrorCode =
  | "UNAUTHORIZED"
  | "ACCOUNT_DELETING"
  | "AUTH_UNAVAILABLE"
  | "DB_UNAVAILABLE"
  | "USAGE_LIMIT_EXCEEDED"
  | "MEMO_LIMIT_EXCEEDED"
  | "CONSULTATION_NOT_FOUND"
  | "CONSULTATION_BUSY"
  | "CONSULTATION_STATE_CONFLICT"
  | "RESULT_NOT_READY"
  | "VALIDATION_ERROR"
  | "AI_UNAVAILABLE"
  | "AI_OUTPUT_INVALID";

export interface ApiErrorDetail {
  field: string;
  reason: string;
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetail[];
  };
}
