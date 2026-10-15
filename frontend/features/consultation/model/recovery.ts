import type {
  ConsultationResult,
  ConsultationStatus,
  ConsultationView,
  GuidedTopic,
  UpdateConsultationResultRequest,
} from "./contracts";
import type { ConsultationState } from "./state";

const STATUS_ORDER: Record<Exclude<ConsultationStatus, "safety_guidance">, number> = {
  event_dialogue: 0,
  event_summary_ready: 1,
  emotion_selection: 2,
  guided_dialogue: 3,
  result_ready: 4,
  handling_selection: 5,
  save_confirmation: 6,
};

const TOPIC_ORDER: Record<GuidedTopic, number> = {
  true_feeling: 0,
  background: 1,
  wish: 2,
};

const RESULT_FIELDS = [
  "event_summary",
  "emotion",
  "true_feeling",
  "background",
  "wish",
] as const satisfies readonly (keyof UpdateConsultationResultRequest)[];

export interface PostRecoverySnapshot {
  status: ConsultationStatus;
  currentTopic: GuidedTopic | null;
}

export type PostRecoveryDecision =
  | "advanced"
  | "retry"
  | "safety_guidance"
  | "state_conflict";

export function createPostRecoverySnapshot(
  state: Pick<ConsultationState, "status" | "currentTopic">,
): PostRecoverySnapshot | null {
  if (state.status === null) {
    return null;
  }

  return {
    status: state.status,
    currentTopic: state.currentTopic,
  };
}

/**
 * UI-006D・UI-006EのPOSTレスポンスが届かなかったとき、GETで再取得した公開状態だけを比較する。
 * AIの質問文や回答内容から成功・失敗を推測しない。
 */
export function decidePostRecovery(
  before: PostRecoverySnapshot,
  current: Pick<ConsultationView, "status" | "current_topic">,
): PostRecoveryDecision {
  if (current.status === "safety_guidance") {
    return "safety_guidance";
  }

  if (before.status === "safety_guidance") {
    return "state_conflict";
  }

  if (STATUS_ORDER[current.status] > STATUS_ORDER[before.status]) {
    return "advanced";
  }

  if (
    before.status === "guided_dialogue" &&
    current.status === "guided_dialogue" &&
    before.currentTopic !== null &&
    current.current_topic !== undefined &&
    TOPIC_ORDER[current.current_topic] > TOPIC_ORDER[before.currentTopic]
  ) {
    return "advanced";
  }

  const currentTopic = current.current_topic ?? null;
  if (
    current.status === before.status &&
    currentTopic === before.currentTopic
  ) {
    return "retry";
  }

  return "state_conflict";
}

export type ResultUpdateRecoveryDecision =
  | "fetch_result"
  | "advanced"
  | "safety_guidance"
  | "state_conflict";

/** PATCH結果が届かなかったとき、結果を再取得する前に現在の公開状態を判定する。 */
export function decideResultUpdateRecovery(
  status: ConsultationStatus,
): ResultUpdateRecoveryDecision {
  switch (status) {
    case "result_ready":
      return "fetch_result";
    case "handling_selection":
    case "save_confirmation":
      return "advanced";
    case "safety_guidance":
      return "safety_guidance";
    default:
      return "state_conflict";
  }
}

/** 再取得した結果に、送信した部分更新がすべて反映されているかを確認する。 */
export function areResultChangesApplied(
  changes: UpdateConsultationResultRequest,
  current: ConsultationResult,
): boolean {
  return RESULT_FIELDS.every((field) => {
    const submittedValue = changes[field];
    return submittedValue === undefined || current[field] === submittedValue;
  });
}

export type ApprovalRecoveryDecision =
  | "approved"
  | "retry"
  | "safety_guidance"
  | "state_conflict";

/** 承認POSTのレスポンスが届かなかったとき、承認を再送する前に現在状態を判定する。 */
export function decideApprovalRecovery(
  status: ConsultationStatus,
): ApprovalRecoveryDecision {
  switch (status) {
    case "handling_selection":
    case "save_confirmation":
      return "approved";
    case "result_ready":
      return "retry";
    case "safety_guidance":
      return "safety_guidance";
    default:
      return "state_conflict";
  }
}
