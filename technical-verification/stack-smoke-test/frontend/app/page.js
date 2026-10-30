"use client";

import { useEffect, useState } from "react";

// ブラウザから直接FastAPIを叩くため、公開ポート(localhost)を指すNEXT_PUBLIC_変数を使う
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [result, setResult] = useState({ state: "loading" });

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => res.json())
      .then((data) => setResult({ state: "done", data }))
      .catch((err) => setResult({ state: "error", error: String(err) }));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>stack-smoke-test</h1>
      <p>FastAPIのヘルスチェック結果:</p>
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </main>
  );
}
