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
const REQUEST_TIMEOUT_MS = 15_000;

/**
 * LLM を通していない未加工の原文抜粋と、その出所（ADR-0006）。
 * 出典（URL / タイトル / 取得日 / クレジット）は AI 生成文には付けず、
 * この未加工引用にのみ付ける。RAG 本結線は次フェーズのため現状は常に空。
 */
type Reference = {
  excerpt: string;
  url: string;
  title: string;
  retrieved_at: string;
  credit: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  references?: Reference[];
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (!res.ok) {
        throw new Error(`backend が ${res.status} を返しました`);
      }
      const data: { reply: string; references?: Reference[] } =
        await res.json();
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.reply,
          references: data.references ?? [],
        },
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
            {m.role === "assistant" &&
              m.references &&
              m.references.length > 0 && (
                // 回答本文（AI 生成）と混ざらない折りたたみ枠。
                // 中身は LLM を通していない未加工の原文抜粋であり、
                // 出典表記はこの枠の中にのみ付ける（ADR-0006）
                <details className="chat-references">
                  <summary>参照した資料（未加工の抜粋）</summary>
                  <ul>
                    {m.references.map((ref) => (
                      <li key={`${m.id}-${ref.url}-${ref.excerpt}`}>
                        <blockquote>{ref.excerpt}</blockquote>
                        <p className="chat-reference-meta">
                          <a
                            href={ref.url}
                            target="_blank"
                            rel="noreferrer noopener"
                          >
                            {ref.title}
                          </a>
                          （取得日: {ref.retrieved_at} / {ref.credit}）
                        </p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
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
