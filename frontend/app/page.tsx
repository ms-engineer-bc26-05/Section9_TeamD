"use client";

import { useEffect, useState } from "react";

// ブラウザから直接FastAPIを呼ぶため、PC側の公開URL（localhost）を使う
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Q-01 #46：Actions上で故意に失敗させる確認用（このPRはマージしない）
const broken: number = "x";

type CheckState = "loading" | "ok" | "error";

const CHECKS = [
  { path: "/health", label: "バックエンド（FastAPI）" },
  { path: "/health/db", label: "データベース（PostgreSQL）" },
  { path: "/health/redis", label: "Redis" },
] as const;

const STATE_LABELS: Record<CheckState, string> = {
  loading: "接続中…",
  ok: "成功",
  error: "失敗",
};

export default function Home() {
  const [states, setStates] = useState<Record<string, CheckState>>(
    Object.fromEntries(CHECKS.map((check) => [check.path, "loading"])),
  );

  useEffect(() => {
    CHECKS.forEach(({ path }) => {
      fetch(`${API_URL}${path}`)
        .then((res): CheckState => (res.ok ? "ok" : "error"))
        // エラーの詳細は画面に出さず、成功・失敗だけを表示する
        .catch((): CheckState => "error")
        .then((state) => {
          setStates((prev) => ({ ...prev, [path]: state }));
        });
    });
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>ぽろり。開発環境の疎通確認</h1>
      <p>フロントエンドから、各サービスへ接続できるかを確認します。</p>
      <ul>
        {CHECKS.map(({ path, label }) => (
          <li key={path}>
            {label}：{STATE_LABELS[states[path]]}
          </li>
        ))}
      </ul>
      <p>失敗した場合は、READMEの「うまく動かないとき」を確認してください。</p>
    </main>
  );
}