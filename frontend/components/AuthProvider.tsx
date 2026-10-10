"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  onAuthStateChanged,
  signOut,
  type User as FirebaseUser,
} from "firebase/auth";
import { getFirebaseAuth } from "@/lib/firebase";
import { apiClient, ApiError } from "@/lib/apiClient";
import type { User } from "@/lib/types";

export type ProfileStatus = "idle" | "syncing" | "ready" | "error";
export type ProfileErrorKind = "network" | "server";
// ログアウトされた理由(ログイン画面で表示する)
export type SignInNotice = "account_deleting" | "session_expired" | null;

type AuthState = {
  user: FirebaseUser | null; // Firebase側のログイン状態
  loading: boolean; // 初回のFirebase認証状態を確認中か
  error: boolean; // 認証状態の取得に失敗したか(詳細は持たない)
  profile: User | null; // 内部ユーザー(POST /users/me の結果)
  profileStatus: ProfileStatus;
  profileErrorKind: ProfileErrorKind | null;
  signInNotice: SignInNotice;
  retryProfile: () => void;
  setHasSeenNotice: (value: boolean) => void; // PATCH成功後に呼ぶ
  // 退会処理中・セッション切れならログアウトして true を返す(それ以外は false)
  handleAuthFailure: (e: unknown) => Promise<boolean>;
};

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  error: false,
  profile: null,
  profileStatus: "idle",
  profileErrorKind: null,
  signInNotice: null,
  retryProfile: () => {},
  setHasSeenNotice: () => {},
  handleAuthFailure: async () => false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<FirebaseUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [profile, setProfile] = useState<User | null>(null);
  const [profileStatus, setProfileStatus] = useState<ProfileStatus>("idle");
  const [profileErrorKind, setProfileErrorKind] =
    useState<ProfileErrorKind | null>(null);
  const [signInNotice, setSignInNotice] = useState<SignInNotice>(null);
  const [retryCount, setRetryCount] = useState(0);

  // 1. Firebaseの認証状態を監視する
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(
      getFirebaseAuth(),
      (firebaseUser) => {
        setUser(firebaseUser);
        setLoading(false);
        setError(false);
      },
      () => {
        setUser(null);
        setLoading(false);
        setError(true);
      },
    );
    return unsubscribe;
  }, []);

  const handleAuthFailure = useCallback(async (e: unknown) => {
    // 退会処理中: 通知を出してログアウトする
    if (
      e instanceof ApiError &&
      e.kind === "forbidden" &&
      e.code === "ACCOUNT_DELETING"
    ) {
      setSignInNotice("account_deleting");
      await signOut(getFirebaseAuth());
      return true;
    }
    // 再試行後も401: ログインし直してもらう
    if (e instanceof ApiError && e.kind === "unauthenticated") {
      setSignInNotice("session_expired");
      await signOut(getFirebaseAuth());
      return true;
    }
    return false;
  }, []);

  // 2. ログイン中のユーザーを、内部ユーザーと紐付ける
  const uid = user?.uid ?? null;
  useEffect(() => {
    if (!uid) {
      setProfile(null);
      setProfileStatus("idle");
      setProfileErrorKind(null);
      return;
    }

    const controller = new AbortController();
    setProfileStatus("syncing");
    setProfileErrorKind(null);

    apiClient
      .post<User>("/users/me", undefined, { signal: controller.signal })
      .then((me) => {
        setProfile(me);
        setProfileStatus("ready");
        setSignInNotice(null);
      })
      .catch(async (e: unknown) => {
        if (e instanceof ApiError && e.kind === "aborted") return;

        if (await handleAuthFailure(e)) return;

        // 通信失敗・サーバー障害(503含む)は、ログアウトせず再試行できる状態にする
        setProfileErrorKind(
          e instanceof ApiError && e.kind === "network" ? "network" : "server",
        );
        setProfileStatus("error");
      });

    return () => controller.abort();
  }, [uid, retryCount, handleAuthFailure]);

  const retryProfile = useCallback(() => setRetryCount((n) => n + 1), []);

  const setHasSeenNotice = useCallback((value: boolean) => {
    setProfile((p) => (p ? { ...p, has_seen_notice: value } : p));
  }, []);


  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        profile,
        profileStatus,
        profileErrorKind,
        signInNotice,
        retryProfile,
        setHasSeenNotice,
        handleAuthFailure,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}