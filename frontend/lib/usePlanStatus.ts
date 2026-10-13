"use client";

/**
 * 利用状況・プラン・一回払いの画面状態を管理するhook(F-04 / #58)
 *
 * - plan は GET /payments/me の結果だけを入れる。confirm が paid を返し、
 *   プランを再取得するまで premium にならない(支払い確認前に有料表示へ切り替えない)
 * - confirmSessionId を渡すと、最初のプラン取得の代わりに confirm を実行する(成功URL用)
 * - 退会処理中(403 ACCOUNT_DELETING)・セッション切れ(401)は AuthProvider に任せる
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/apiClient";
import {
  confirmPayment,
  createCheckoutSession,
  fetchCurrentPlan,
  fetchUsage,
  type PlanCode,
  type UsageResponse,
} from "@/lib/billing";

export type PlanPhase =
  | "loading" // 初回のプラン・利用状況を取得中
  | "idle" // 通常表示(plan と usage を表示できる)
  | "starting" // 購入手続きを開始中(Checkoutへ移動する直前まで)
  | "confirming" // 決済を確認中(「決済状態を確認しています」)
  | "pending" // まだ支払いを確認できない → 再確認の導線(再購入は促さない)
  | "expired" // 期限切れ → 再購入の導線
  | "not_found" // 確認できる決済がない(固定文言を出してプランは再取得済み)
  | "in_progress" // 決済画面を準備中 → 少し待って手動で再試行
  | "error"; // 通信失敗・サーバー障害(errorKind で区別。再試行できる)

export type PlanErrorKind = "network" | "server";

export type PlanState = {
  plan: PlanCode | null; // サーバーで確認できたプラン。取得前は null
  usage: UsageResponse | null;
  phase: PlanPhase;
  errorKind: PlanErrorKind | null;
  startCheckout: () => Promise<void>; // 購入ボタン
  confirm: (sessionId?: string) => Promise<void>; // 省略時は「決済を確認する」ボタン
  reload: () => Promise<void>; // 再取得・再試行
};

export function usePlanStatus(options?: {
  confirmSessionId?: string;
}): PlanState {
  const confirmSessionId = options?.confirmSessionId;
  const { profileStatus, handleAuthFailure } = useAuth();

  const [plan, setPlan] = useState<PlanCode | null>(null);
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [phase, setPhase] = useState<PlanPhase>("loading");
  const [errorKind, setErrorKind] = useState<PlanErrorKind | null>(null);

  // アンマウント後にstateを更新しない
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // 購入ボタンの二重実行を防ぐ
  const startingRef = useRef(false);

  const handleError = useCallback(
    async (e: unknown) => {
      if (e instanceof ApiError && e.kind === "aborted") return;
      // 退会処理中・セッション切れはログアウトされる
      if (await handleAuthFailure(e)) return;
      if (!aliveRef.current) return;
      setErrorKind(
        e instanceof ApiError && e.kind === "network" ? "network" : "server",
      );
      setPhase("error");
    },
    [handleAuthFailure],
  );

  // プランと利用状況を取得し、成功したら nextPhase に切り替える
  const loadPlan = useCallback(
    async (nextPhase: PlanPhase = "idle") => {
      try {
        const [planRes, usageRes] = await Promise.all([
          fetchCurrentPlan(),
          fetchUsage(),
        ]);
        if (!aliveRef.current) return;
        setPlan(planRes.plan_code);
        setUsage(usageRes);
        setErrorKind(null);
        setPhase(nextPhase);
      } catch (e) {
        await handleError(e);
      }
    },
    [handleError],
  );

  const confirm = useCallback(
    async (sessionId?: string) => {
      setPhase("confirming");
      try {
        const result = await confirmPayment(sessionId);
        switch (result.status) {
          case "paid":
            // プランを再取得できてから有料表示にする
            await loadPlan();
            return;
          case "pending":
            if (aliveRef.current) setPhase("pending");
            return;
          case "expired":
            if (aliveRef.current) setPhase("expired");
            return;
          case "not_found":
            await loadPlan("not_found");
            return;
        }
      } catch (e) {
        await handleError(e);
      }
    },
    [loadPlan, handleError],
  );

  const startCheckout = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setPhase("starting");
    try {
      const result = await createCheckoutSession("premium");
      switch (result.type) {
        case "redirect":
          // Checkoutへ移動する(移動するまで "starting" のまま)
          window.location.assign(result.checkoutUrl);
          return;
        case "already_paid":
          await loadPlan();
          return;
        case "in_progress":
          if (aliveRef.current) setPhase("in_progress");
          return;
        case "confirmation_required":
          // エラーにせず決済確認へ進む(session_idは省略し、サーバーが本人の未確認の決済を探す)
          await confirm();
          return;
      }
    } catch (e) {
      await handleError(e);
    } finally {
      startingRef.current = false;
    }
  }, [loadPlan, confirm, handleError]);

  const reload = useCallback(async () => {
    setPhase("loading");
    await loadPlan();
  }, [loadPlan]);

  // 内部ユーザーと紐付いてから取得する(AuthProviderのprofileStatusが ready になるまで待つ)
  const ready = profileStatus === "ready";
  useEffect(() => {
    if (!ready) return;
    if (confirmSessionId) {
      void confirm(confirmSessionId);
    } else {
      void loadPlan();
    }
  }, [ready, confirmSessionId, confirm, loadPlan]);

  return { plan, usage, phase, errorKind, startCheckout, confirm, reload };
}