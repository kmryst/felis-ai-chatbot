import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "felis-ai-chatbot",
  description:
    "pgvector RAG チャットボット。PostgreSQL の Backup / Restore / Maintenance / Monitoring を設計・実装・検証する個人開発",
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
