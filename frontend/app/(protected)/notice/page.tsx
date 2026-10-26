"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { apiClient, ApiError } from "@/lib/apiClient";
import type { User } from "@/lib/types";
import styles from "./notice.module.css";

// 相談窓口の案内先(厚生労働省「まもろうよ こころ」。#48で確定)
const SUPPORT_URL = "https://www.mhlw.go.jp/mamorouyokokoro/soudan/";
const NEXT_PATH = "/consultation";

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
    <main className={styles.page}>
      <div className={styles.panel}>
        <header className={styles.header}>
          <Link className={styles.backLink} href="/home" aria-label="ホームへ戻る">
            ‹
          </Link>
          <h1 className={styles.title}>はじめる前に</h1>
          <span className={styles.headerSpacer} aria-hidden="true" />
        </header>

        <section className={styles.noticeCard} aria-label="利用前の注意事項">
          <ul className={styles.noticeList}>
            <li>入力した内容は、外部のAIに送信されます。</li>
            <li>学習には利用されない設定で利用しています。</li>
            <li>提供元で、一定期間保持される可能性があります。</li>
            <li>相談中のやり取りは、このアプリには残しません。</li>
            <li>個人情報は入力しないでください。</li>
            <li>医療・心理相談の代わりにはなりません。</li>
          </ul>

          {detailVisible ? (
            <section className={styles.detail} aria-label="詳しい注意">
              <h2 className={styles.detailTitle}>詳しい注意</h2>
              <p>
                AIが整理した内容は、あなたが確認して承認したものだけを、
                整理メモとして保存できます。保存するかどうかは、あなたが選べます。
              </p>
              <p>
                つらさが強いときは、無理に続けず、下の相談窓口を利用してください。
              </p>
            </section>
          ) : (
            <button
              className={styles.detailButton}
              type="button"
              onClick={() => setShowDetail(true)}
            >
              詳しい注意を見る
            </button>
          )}

          <a
            className={styles.supportLink}
            href={SUPPORT_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            つらさが強いときの相談窓口
          </a>
        </section>

        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}

        <div className={styles.actions}>
          <button
            className={styles.primaryButton}
            type="button"
            onClick={agree}
            disabled={submitting}
          >
            {isFirstTime ? "同意して進む" : "確認して進む"}
          </button>
          <Link className={styles.secondaryButton} href="/home">
            ホームへ戻る
          </Link>
        </div>
      </div>
    </main>
  );
}
