import Chat from "./chat";

export default function Home() {
  return (
    <main className="page">
      <h1>気象情報チャットボット</h1>
      <Chat />
      {/* 出典表示（気象庁の出典記載例に準拠）・加工表記・AI 生成表示・
          予報/警報を提供しない旨の常設フッター（ADR-0008）。
          文言の削除・簡略化は ADR-0008 の再検討を要する */}
      <footer className="disclosure">
        <p>
          出典：気象庁ホームページ（
          <a
            href="https://github.com/kmryst/felis-ai-chatbot/blob/main/docs/data-sources.md"
            target="_blank"
            rel="noreferrer noopener"
          >
            利用ページの一覧
          </a>
          ）
        </p>
        <p>
          本サービスは気象庁ホームページの情報を felis-ai-chatbot
          が加工して作成したものであり、気象庁が作成・提供するものではありません。回答は
          AI が生成したものであり、独自の予報・警報の提供は行いません。
        </p>
      </footer>
    </main>
  );
}
