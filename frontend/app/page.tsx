import Chat from "./chat";

export default function Home() {
  return (
    <main className="page">
      <h1>felis-ai-chatbot</h1>
      <p className="subtitle">
        pgvector RAG チャットボット（Day 1: LLM はスタブ。RAG 接続は Day 2）
      </p>
      <Chat />
    </main>
  );
}
