"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { onAuthStateChanged, type User as FirebaseUser } from "firebase/auth";
import { getFirebaseAuth } from "@/lib/firebase";

type AuthState = {
  user: FirebaseUser | null; // Firebase側のログイン状態
  loading: boolean; // 初回の認証状態を確認中か
  error: boolean; // 認証状態の取得に失敗したか(詳細は持たない)
};

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  error: false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    error: false,
  });

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(
      getFirebaseAuth(),
      (user) => setState({ user, loading: false, error: false }),
      () => setState({ user: null, loading: false, error: true }),
    );
    return unsubscribe;
  }, []);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}