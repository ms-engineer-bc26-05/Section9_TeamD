import type { ConsultationErrorCode } from "./state";

const START_BUSY_MESSAGE =
  "相談の開始処理中です。少し待ってから、もう一度お試しください。";

export function getConsultationErrorMessage(
  errorCode: ConsultationErrorCode | null,
): string | null {
  switch (errorCode) {
    case null:
    case "CONSULTATION_NOT_FOUND":
      return null;

    case "CONSULTATION_BUSY":
      return "前の操作を処理しています。少し待ってから、もう一度お試しください。";

    case "CONSULTATION_STATE_CONFLICT":
      return "現在の相談の状態では、この操作を続けられません。画面の状態を確認して、もう一度お試しください。";

    case "RESULT_NOT_READY":
      return "整理結果を準備しています。少し待ってから、もう一度お試しください。";

    case "VALIDATION_ERROR":
      return "入力内容を確認してください。";

    case "AI_UNAVAILABLE":
    case "AI_OUTPUT_INVALID":
      return "回答を作成できませんでした。入力内容はそのままです。もう一度お試しください。";

    case "UNAUTHORIZED":
      return "ログイン状態を確認できませんでした。ホームに戻って、もう一度ログインしてください。";

    case "NETWORK_ERROR":
      return "通信できませんでした。接続を確認して、もう一度お試しください。";

    case "SERVER_ERROR":
    case "UNKNOWN_ERROR":
      return "処理を完了できませんでした。時間をおいて、もう一度お試しください。";
  }
}

export function getStartConsultationErrorMessage(
  errorCode: ConsultationErrorCode | null,
): string | null {
  if (errorCode === "CONSULTATION_BUSY") {
    return START_BUSY_MESSAGE;
  }

  return getConsultationErrorMessage(errorCode);
}
