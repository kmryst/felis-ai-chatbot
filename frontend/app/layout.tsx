import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "気象情報チャットボット",
  description:
    "気象庁ホームページの観測データを参照して回答する AI チャットボット（felis-ai-chatbot）",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
