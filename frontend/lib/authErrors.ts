import { FirebaseError } from "firebase/app";

export function toAuthErrorMessage(error: unknown): string {
  const code = error instanceof FirebaseError ? error.code : "";

  switch (code) {
    case "auth/invalid-email":
      return "メールアドレスの形式を確認してください";
    case "auth/invalid-credential":
    case "auth/user-not-found":
    case "auth/wrong-password":
      return "メールアドレスまたはパスワードを確認してください";
    case "auth/network-request-failed":
      return "通信できませんでした。接続を確認してもう一度お試しください";
    default:
      return "現在ログインできません。時間をおいてもう一度お試しください";
  }
}