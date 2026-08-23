"use client";

/**
 * 最小のチャット UI。
 *
 * - backend の POST /chat を呼ぶ（既定 http://localhost:8000。
 *   NEXT_PUBLIC_BACKEND_URL で上書き）
 * - fetch には明示的な timeout を設定する（timeout なしの通信を作らない）
 * - backend 停止・エラー時はメッセージを表示する（無限待ち・白画面にしない）
 */

import { FormEvent, useRef, useState } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
// /chat の API キー（Issue #113 の 3。backend の CHAT_API_KEY と同じ値を渡す）。
// NEXT_PUBLIC_* はビルド成果物（ブラウザに配られる JS）に埋め込まれるため、
// この渡し方はローカル開発専用。公開デプロイでキーを秘匿する仕組みではない
// （公開面の認証設計は Issue #113 の 4 = レート制限等と合わせてユーザー判断待ち）
const CHAT_API_KEY = process.env.NEXT_PUBLIC_CHAT_API_KEY;
const REQUEST_TIMEOUT_MS = 15_000;

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || sending) return;

    setError(null);
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content: message },
    ]);
    setInput("");

    try {
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // キー未設定ならヘッダ自体を送らない（backend 側は 401 を返す）
          ...(CHAT_API_KEY ? { "X-API-Key": CHAT_API_KEY } : {}),
        },
        body: JSON.stringify({ message }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (!res.ok) {
        throw new Error(`backend が ${res.status} を返しました`);
      }
      const data: { reply: string } = await res.json();
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: data.reply },
      ]);
    } catch (err) {
      const reason =
        err instanceof DOMException && err.name === "TimeoutError"
          ? `${REQUEST_TIMEOUT_MS / 1000} 秒以内に応答がありませんでした`
          : "backend に接続できませんでした";
      setError(`送信に失敗しました: ${reason}`);
    } finally {
      setSending(false);
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
    }
  }

  return (
    <section className="chat">
      <div className="chat-messages" ref={listRef} aria-live="polite">
        {messages.length === 0 && (
          <p className="chat-empty">メッセージを入力して送信してください</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-message chat-message-${m.role}`}>
            <span className="chat-role">
              {m.role === "user" ? "あなた" : "bot"}
            </span>
            <p>{m.content}</p>
          </div>
        ))}
      </div>
      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}
      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="メッセージを入力"
          aria-label="メッセージ"
          disabled={sending}
        />
        <button type="submit" disabled={sending || input.trim() === ""}>
          {sending ? "送信中..." : "送信"}
        </button>
      </form>
    </section>
  );
}
