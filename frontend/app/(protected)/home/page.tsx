"use client";

import Link from "next/link";
import styles from "./home.module.css";

export default function HomePage() {
  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <p className={styles.brand}>ぽろり。</p>
        <section className={styles.hero} aria-labelledby="home-title">
          <h1 id="home-title" className={styles.title}>
            ホーム
          </h1>
          <p className={styles.lead}>モヤモヤを、ゆっくり整理してみませんか。</p>
          <Link className={styles.startButton} href="/notice">
            相談を始める
          </Link>
          <Link className={styles.memoButton} href="/memos">
            保存メモを見る
          </Link>
          <p className={styles.reassurance}>
            うまく言葉にできなくても大丈夫です
          </p>
        </section>
      </div>
    </main>
  );
}
