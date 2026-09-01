"use client";

/**
 * チャット UI（SSE consumer。ADR-0027 決定 2 / 3・ADR-0028 の client 側）。
 *
 * - 相対パス /api/chat のみを呼ぶ（BFF 経由。upstream の base URL や API キーを
 *   client は一切持たない。`NEXT_PUBLIC_BACKEND_URL` / `NEXT_PUBLIC_CHAT_API_KEY` は廃止）
 * - 応答は SSE を fetch + response.body.getReader() で読み、受信しながら描画する
 * - `done` を受けるまで応答は確定しない。終端 event なしの終了は失敗として扱う
 * - `error`（class: content_filter）では表示済み partial text を撤回する（撤回契約）
 * - 旧実装の単一全体 timeout（REQUEST_TIMEOUT_MS）は廃止した。ストリーミングでは
 *   正常な長い応答を全体 timeout が切断してしまうため、client 側の打ち切りは
 *   AbortController によるユーザー操作（停止ボタン）とし、時間ベースの閾値
 *   （threshold 1 / 2）は SLO 側の数値決定後に組み込む（ADR-0028「影響」）
 */

import { FormEvent, useRef, useState } from "react";
import { consumeChatSseStream } from "../lib/chat-sse/consumer";

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
  const abortRef = useRef<AbortController | null>(null);

  function upsertAssistantMessage(id: string, content: string) {
    setMessages((prev) => {
      const exists = prev.some((m) => m.id === id);
      if (exists) {
        return prev.map((m) => (m.id === id ? { ...m, content } : m));
      }
      return [...prev, { id, role: "assistant", content }];
    });
  }

  function handleStop() {
    abortRef.current?.abort();
  }

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

    const assistantId = crypto.randomUUID();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });
      if (!res.ok) {
        // ストリーム開始前の失敗は HTTP status で返る（ADR-0028 決定 2）
        throw new Error(`backend が ${res.status} を返しました`);
      }
      if (res.body === null) {
        throw new Error("応答 body がありません");
      }
      const outcome = await consumeChatSseStream(res.body, (cumulativeText) => {
        upsertAssistantMessage(assistantId, cumulativeText);
      });
      // 終端処理の結果（撤回・失敗文言を反映済みの text）で最終表示を確定する。
      // 失敗時の文言は displayText 側が持つため、別途のバナーは出さない
      upsertAssistantMessage(assistantId, outcome.displayText);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // ユーザーによる停止。表示済み partial text はそのまま残す
        setError("応答の受信を停止しました");
      } else {
        const reason =
          err instanceof Error ? err.message : "backend に接続できませんでした";
        setError(`送信に失敗しました: ${reason}`);
      }
    } finally {
      abortRef.current = null;
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
        {sending ? (
          <button type="button" onClick={handleStop}>
            停止
          </button>
        ) : (
          <button type="submit" disabled={input.trim() === ""}>
            送信
          </button>
        )}
      </form>
    </section>
  );
}
