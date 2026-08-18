import Chat from "./chat";

export default function Home() {
  return (
    <main className="page">
      <h1>felis-ai-chatbot</h1>
      <p className="subtitle">
        pgvector RAG チャットボット（Day 1: LLM はスタブ。RAG 接続は Day 2）
      </p>
      <Chat />
      {/* ツール全体としての AI 生成表示・免責（常設）。NASA AI 条項が明示的に
          許可しているのは「ツールが NASA 素材を含む」という事実の開示であり、
          回答ごとの出典帰属ではない（ADR-0006） */}
      <footer className="disclosure">
        <p>
          本ツールは NASA の公開情報を素材として利用しています。回答は AI
          が生成したものであり、NASA
          による審査・許可・公認を受けたものではありません。NASA
          の見解ではありません。
        </p>
      </footer>
    </main>
  );
}
