"use client";

import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <h1>ホーム</h1>
      <p>モヤモヤを、ゆっくり整理してみませんか。</p>
      <Link href="/notice">相談を始める</Link>
    </main>
  );
}