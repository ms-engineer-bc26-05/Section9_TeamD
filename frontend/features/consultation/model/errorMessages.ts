import type { ConsultationErrorCode } from "./state";

const START_BUSY_MESSAGE =
  "前の操作を処理しています。少し待ってから「対話を始める」を押してください。";

export function getStartConsultationErrorMessage(
  errorCode: ConsultationErrorCode | null,
): string | null {
  if (errorCode === "CONSULTATION_BUSY") {
    return START_BUSY_MESSAGE;
  }

  return null;
}
