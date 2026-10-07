"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { user, loading, error } = useAuth();

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

  return <>{children}</>;
}