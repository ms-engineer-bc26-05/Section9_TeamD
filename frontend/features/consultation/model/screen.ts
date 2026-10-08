import type { ConsultationState } from "./state";

export type ConsultationScreen =
  | "start"
  | "event_dialogue"
  | "event_summary_ready"
  | "emotion_selection"
  | "guided_dialogue"
  | "result_loading"
  | "result_ready"
  | "handling_selection"
  | "save_confirmation";

export function resolveConsultationScreen(
  state: Pick<ConsultationState, "status" | "result">,
): ConsultationScreen {
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
