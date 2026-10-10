"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { apiClient, ApiError } from "@/lib/apiClient";
import type { User } from "@/lib/types";

// 相談窓口の案内先は未確定のため仮置き(確定したら差し替える)
const SUPPORT_URL = "#";
// 遷移先(UI-004)は I-04 の範囲。実装されるまでは仮置き
const NEXT_PATH = "/home";

export default function NoticePage() {
  const router = useRouter();
  const { profile, setHasSeenNotice, handleAuthFailure } = useAuth();
  const [showDetail, setShowDetail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isFirstTime = profile ? !profile.has_seen_notice : true;
  const detailVisible = isFirstTime || showDetail;

  const agree = async () => {
    if (submitting) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      // すでに確認済みなら、PATCHは呼ばずに進む
      if (isFirstTime) {
        await apiClient.patch<User>("/users/me", { has_seen_notice: true });
        setHasSeenNotice(true);
      }
      router.push(NEXT_PATH);
    } catch (e) {
      // 退会処理中・セッション切れならログアウト済み(ログイン画面へ戻る)
      if (await handleAuthFailure(e)) return;
      setErrorMessage(
        e instanceof ApiError && e.kind === "network"
          ? "通信できませんでした。接続を確認してもう一度お試しください。"
          : "同意を保存できませんでした。時間をおいてもう一度お試しください。",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main>
      <h1>はじめる前に</h1>

      <ul>
        <li>入力した内容は、外部のAIに送信されます。</li>
        <li>学習には利用されない設定で利用しています。</li>
        <li>提供元で、一定期間保持される可能性があります。</li>
        <li>相談中のやり取りは、このアプリには残しません。</li>
        <li>個人情報は入力しないでください。</li>
        <li>医療・心理相談の代わりにはなりません。</li>
      </ul>

      {detailVisible ? (
        <section aria-label="詳しい注意">
          <h2>詳しい注意</h2>
          <p>
            AIが整理した内容は、あなたが確認して承認したものだけを、
            整理メモとして保存できます。保存するかどうかは、あなたが選べます。
          </p>
          <p>
            つらさが強いときは、無理に続けず、下の相談窓口を利用してください。
          </p>
        </section>
      ) : (
        <button type="button" onClick={() => setShowDetail(true)}>
          詳しい注意を見る
        </button>
      )}

      <p>
        <a href={SUPPORT_URL}>つらさが強いときの相談窓口</a>
      </p>

      {errorMessage && <p role="alert">{errorMessage}</p>}

      <button type="button" onClick={agree} disabled={submitting}>
        {isFirstTime ? "同意して進む" : "確認して進む"}
      </button>
      <Link href="/home">戻る</Link>
    </main>
  );
}