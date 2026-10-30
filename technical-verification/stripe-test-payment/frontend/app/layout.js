export const metadata = {
  title: "stack-smoke-test",
  description: "候補技術のスモークテスト用の最小フロントエンド",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
