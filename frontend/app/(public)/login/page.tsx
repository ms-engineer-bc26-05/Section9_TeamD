"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
} from "firebase/auth";
import { getFirebaseAuth } from "@/lib/firebase";
import { toAuthErrorMessage } from "@/lib/authErrors";
import { useAuth } from "@/components/AuthProvider";
import styles from "./login.module.css";

// 相談窓口の案内先は未確定のため仮置き(確定したら差し替える)
const SUPPORT_URL = "#";

export default function LoginPage() {
  const router = useRouter();
  const { signInNotice } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const submit = async (mode: "login" | "signup") => {
    if (submitting) return;
    if (email.trim() === "" || password === "") {
      setErrorMessage("入力されていない項目があります");
      return;
    }
    setSubmitting(true);
    setErrorMessage(null);
    try {
      if (mode === "login") {
        await signInWithEmailAndPassword(getFirebaseAuth(), email.trim(), password);
      } else {
        await createUserWithEmailAndPassword(getFirebaseAuth(), email.trim(), password);
      }
      router.push("/home");
    } catch (error) {
      // 入力は保持し、定型文だけを表示する(エラーの中身は出さない)
      setErrorMessage(toAuthErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit("login");
  };

  return (
    <main className={styles.page}>
      <h1 className={styles.brand}>ぽろり。</h1>
      <h2 className={styles.title}>おかえりなさい</h2>
      <p className={styles.lead}>安心して気持ちを整理する場所</p>

      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <label className={styles.field}>
          メールアドレス
          <input
            className={styles.input}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className={styles.field}>
          パスワード
          <input
            className={styles.input}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {signInNotice === "account_deleting" && (
          <p className={styles.notice} role="alert">
            退会処理中のため利用できません。
          </p>
        )}
        {signInNotice === "session_expired" && (
          <p className={styles.notice} role="alert">
            安全のため、もう一度ログインしてください。
          </p>
        )}
        {errorMessage && (
          <p className={styles.notice} role="alert">
            {errorMessage}
          </p>
        )}

        <button
          className={styles.primaryButton}
          type="submit"
          disabled={submitting}
        >
          ログイン
        </button>
        <button
          className={styles.secondaryButton}
          type="button"
          disabled={submitting}
          onClick={() => void submit("signup")}
        >
          はじめて使う方はこちら
        </button>
      </form>

      <a className={styles.support} href={SUPPORT_URL}>
        つらさが強いときの相談窓口
      </a>
    </main>
  );
}