/**
 * /chat SSE の consumer（ADR-0028 の client 側契約）。
 *
 * - content event（message / notice）の text を累積し、描画用 callback に渡す
 * - 終端 event（done / error）を受けるまで応答は確定しない。終端 event なしの
 *   stream 終了は契約違反 = 失敗として扱う（決定 2）
 * - `error` の class が `content_filter` の場合は表示済み partial text を撤回し、
 *   固定文言に置換する（決定 6 の撤回契約）。他の class では partial text を保持する
 * - 空文字列の text を持つ message は契約違反であり、content event として数えず
 *   描画もしない（決定 4）
 */

import { SseStreamParser, SseWireFormatError, WireEvent } from "./parser";

/** 撤回時の固定文言（ADR-0028 決定 6 が固定する文言）。 */
export const CONTENT_FILTER_RETRACTION_TEXT =
  "応答が content filter を通過したことを確認できなかったため、表示を取り消しました";

/** content_filter 以外の失敗時に partial text へ付す文言。 */
export const INCOMPLETE_RESPONSE_TEXT = "応答は完了しませんでした";

export type ChatStreamOutcome = {
  /** 終端処理前までに受信した content event の text の連結。 */
  partialText: string;
  /**
   * - "done": 有効な終端 event を受信して応答が確定した
   * - "error": `error` event で終端した（errorClass を持つ）
   * - "failed": 終端 event なしの stream 終了・wire 契約違反（失敗として扱う）
   */
  terminal: "done" | "error" | "failed";
  errorClass: string | null;
  /** 撤回契約の発動有無（errorClass === "content_filter" のときのみ true）。 */
  retract: boolean;
  /** 画面に最終表示すべき text（撤回・失敗文言を反映済み）。 */
  displayText: string;
};

const CONTENT_EVENTS = new Set(["message", "notice"]);

function finalize(
  partialText: string,
  terminal: ChatStreamOutcome["terminal"],
  errorClass: string | null,
): ChatStreamOutcome {
  const retract = errorClass === "content_filter";
  let displayText: string;
  if (terminal === "done") {
    displayText = partialText;
  } else if (retract) {
    // 撤回契約: partial text を画面から撤回し固定文言に置換する
    displayText = CONTENT_FILTER_RETRACTION_TEXT;
  } else {
    // partial text は保持し、完了しなかったことを付す
    displayText =
      partialText === ""
        ? INCOMPLETE_RESPONSE_TEXT
        : `${partialText}\n${INCOMPLETE_RESPONSE_TEXT}`;
  }
  return { partialText, terminal, errorClass, retract, displayText };
}

/**
 * SSE byte stream を読み切り、契約に従った最終結果を返す。
 *
 * @param stream fetch response の body（`text/event-stream`）
 * @param onText content event を受けるたびに累積 text で呼ばれる（描画用）
 */
export async function consumeChatSseStream(
  stream: ReadableStream<Uint8Array>,
  onText?: (cumulativeText: string) => void,
): Promise<ChatStreamOutcome> {
  const parser = new SseStreamParser();
  const reader = stream.getReader();
  let partialText = "";

  const handleEvent = (event: WireEvent): ChatStreamOutcome | null => {
    if (CONTENT_EVENTS.has(event.event)) {
      const text = event.data["text"];
      if (typeof text !== "string") {
        // data 形状の契約違反
        return finalize(partialText, "failed", null);
      }
      if (text === "") {
        // 空 message は content event として数えない（決定 4）
        return null;
      }
      partialText += text;
      onText?.(partialText);
      return null;
    }
    if (event.event === "done") {
      return finalize(partialText, "done", null);
    }
    if (event.event === "error") {
      const errorClass = event.data["class"];
      // class が取れない error は class 不明の失敗として扱う（撤回はしない）
      return finalize(
        partialText,
        "error",
        typeof errorClass === "string" ? errorClass : null,
      );
    }
    // 契約に無い event 種別は契約違反 = 失敗として扱う（fail-closed）
    return finalize(partialText, "failed", null);
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      let events: WireEvent[];
      try {
        events = parser.feed(value);
      } catch (error) {
        if (error instanceof SseWireFormatError) {
          await reader.cancel().catch(() => {});
          return finalize(partialText, "failed", null);
        }
        throw error;
      }
      for (const event of events) {
        const outcome = handleEvent(event);
        if (outcome !== null) {
          // 終端 event は最後にのみ現れる契約のため、以降は読まない
          // （契約違反による失敗確定時も同様に打ち切る）
          await reader.cancel().catch(() => {});
          return outcome;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  // 終端 event なしの stream 終了 = 契約違反（決定 2）。不完全な末尾 event は破棄する
  try {
    parser.end();
  } catch (error) {
    if (!(error instanceof SseWireFormatError)) {
      throw error;
    }
  }
  return finalize(partialText, "failed", null);
}
