"use client";

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";
import { authenticatedMemoApi } from "@/features/memos/api/authenticatedMemoApi";
import { MemoListContainer } from "@/features/memos/components/MemoListContainer";

const DELETE_COMPLETED_NOTICE = "メモを削除しました。";

function MemoListRoute() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { handleAuthFailure } = useAuth();
  const handleApiError = useCallback(
    (error: unknown) => {
      void handleAuthFailure(error);
    },
    [handleAuthFailure],
  );

  return (
    <MemoListContainer
      api={authenticatedMemoApi}
      notice={
        searchParams.get("deleted") === "1" ? DELETE_COMPLETED_NOTICE : null
      }
      onBackHome={() => router.push("/home")}
      onOpenMemo={(memoId) =>
        router.push(`/memos/${encodeURIComponent(memoId)}`)
      }
      onStartConsultation={() => router.push("/notice")}
      onApiError={handleApiError}
    />
  );
}

export default function MemoListPage() {
  return (
    <Suspense fallback={<p role="status">読み込み中です…</p>}>
      <MemoListRoute />
    </Suspense>
  );
}
