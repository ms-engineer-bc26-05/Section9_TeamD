// frontend/app/success/page.js
"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function SuccessContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const [result, setResult] = useState({ state: "loading" });

  useEffect(() => {
    if (!sessionId) {
      setResult({ state: "error", error: "session_idがありません" });
      return;
    }
    fetch(`${API_URL}/api/confirm-payment?session_id=${sessionId}`)
      .then(async (res) => {
        const data = await res.json();
        
        if (!res.ok) {
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        return data;
      })
      .then((data) => setResult({ state: "done", data }))
      .catch((err) => setResult({ state: "error", error: String(err.message || err) }));
  }, [sessionId]);

  return <pre>{JSON.stringify(result, null, 2)}</pre>;
}

export default function Success() {
  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>決済結果</h1>
      <Suspense fallback={<pre>読み込み中...</pre>}>
        <SuccessContent />
      </Suspense>
    </main>
  );
}