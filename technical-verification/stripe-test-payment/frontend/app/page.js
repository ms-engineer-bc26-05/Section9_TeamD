"use client";

import { useEffect, useState } from "react";

// ブラウザから直接FastAPIを叩くため、公開ポート(localhost)を指すNEXT_PUBLIC_変数を使う
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [result, setResult] = useState({ state: "loading" });
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => res.json())
      .then((data) => setResult({ state: "done", data }))
      .catch((err) => setResult({ state: "error", error: String(err) }));
  }, []);

  const handleCheckout = async () => {
    setCheckoutLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/create-checkout-session`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        setCheckoutLoading(false);
      }
    } catch (err) {
      console.error(err);
      setCheckoutLoading(false);
    }
  };

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>stack-smoke-test</h1>
      <p>FastAPIのヘルスチェック結果:</p>
      <pre>{JSON.stringify(result, null, 2)}</pre>

      <hr style={{ margin: "2rem 0" }} />

      <p>Stripeテスト決済:</p>
      <button onClick={handleCheckout} disabled={checkoutLoading}>
        {checkoutLoading ? "処理中..." : "テスト決済へ進む"}
      </button>
    </main>
  );
}
