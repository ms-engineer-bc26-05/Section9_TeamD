"use client";

import { useCallback } from "react";
import { useParams, useRouter } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";
import { authenticatedMemoApi } from "@/features/memos/api/authenticatedMemoApi";
import { MemoDetailContainer } from "@/features/memos/components/MemoDetailContainer";

export default function MemoDetailPage() {
  const router = useRouter();
  const params = useParams<{ memoId: string }>();
  const { handleAuthFailure } = useAuth();
  const handleApiError = useCallback(
    (error: unknown) => {
      void handleAuthFailure(error);
    },
    [handleAuthFailure],
  );

  return (
    <MemoDetailContainer
      memoId={params.memoId}
      api={authenticatedMemoApi}
      onBackToList={() => router.push("/memos")}
      onDeleted={() => router.replace("/memos?deleted=1")}
      onApiError={handleApiError}
    />
  );
}
