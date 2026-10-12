"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { user, loading, error, profileStatus, profileErrorKind, retryProfile } =
    useAuth();

  useEffect(() => {
    if (!loading && !error && !user) {
      router.replace("/login");
    }
  }, [loading, error, user, router]);

  if (loading) {
    return <p role="status">読み込み中です…</p>;
  }

  if (error) {
    return (
      <p role="alert">
        認証状態を確認できませんでした。時間をおいてもう一度お試しください。
      </p>
    );
  }

  if (!user) {
    return null; // /login への遷移中は何も表示しない
  }

  if (profileStatus === "error") {
    return (
      <div role="alert">
        <p>
          {profileErrorKind === "network"
            ? "通信できませんでした。接続を確認してもう一度お試しください。"
            : "現在サービスを利用できません。時間をおいてもう一度お試しください。"}
        </p>
        <button type="button" onClick={retryProfile}>
          再試行
        </button>
      </div>
    );
  }

  if (profileStatus !== "ready") {
    return <p role="status">読み込み中です…</p>;
  }

  return <>{children}</>;
}