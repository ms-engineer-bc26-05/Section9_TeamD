import type { ConsultationState } from "./state";

export type ConsultationScreen =
  | "start"
  | "state_unavailable"
  | "usage_limit"
  | "event_dialogue"
  | "event_summary_ready"
  | "emotion_selection"
  | "guided_dialogue"
  | "result_loading"
  | "result_ready"
  | "handling_selection"
  | "save_confirmation";

export function resolveConsultationScreen(
  state: Pick<ConsultationState, "status" | "result" | "errorCode">,
): ConsultationScreen {
  if (state.errorCode === "CONSULTATION_NOT_FOUND") {
    return "state_unavailable";
  }

  if (state.errorCode === "USAGE_LIMIT_EXCEEDED") {
    return "usage_limit";
  }

  if (state.status === null) {
    return "start";
  }

  if (state.status === "result_ready" && state.result === null) {
    return "result_loading";
  }

  if (state.status === "safety_guidance") {
    // 実際の表示はConsultationSafetyBoundaryが安全案内へ置き換える。
    return "start";
  }

  return state.status;
}
