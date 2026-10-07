"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import { toAuthErrorMessage } from "@/lib/authErrors";

// 相談窓口の案内先は未確定のため仮置き(確定したら差し替える)
const SUPPORT_URL = "#";

export default function LoginPage() {
  const router = useRouter();
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
        await signInWithEmailAndPassword(auth, email.trim(), password);
      } else {
        await createUserWithEmailAndPassword(auth, email.trim(), password);
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
    <main>
      <h1>ぽろり。</h1>
      <p>モヤモヤをやさしく整理するアプリです。</p>

      <form onSubmit={onSubmit} noValidate>
        <label>
          メールアドレス
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          パスワード
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {errorMessage && <p role="alert">{errorMessage}</p>}

        <button type="submit" disabled={submitting}>
          ログイン
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => void submit("signup")}
        >
          新規登録
        </button>
      </form>

      <a href={SUPPORT_URL}>つらさが強いときの相談窓口</a>
    </main>
  );
}