/**
 * /chat SSE wire format の incremental parser（ADR-0028 決定 2 / 決定 8 の downstream 方向）。
 *
 * - 任意の byte 境界で分断された stream から、無分割時と同一の event 列を復元する
 *   （UTF-8 マルチバイト文字の途中・`data:` プレフィクスの途中・空行の直前後を含む）
 * - `TextDecoder` の streaming mode がマルチバイト分断を、行 buffer が行分断を吸収する
 * - wire framing は `event:` 行 + `data:` 行 + 空行（LF）。`data` は必ず JSON object
 *   （ADR-0028 決定 2）。CRLF は SSE 仕様（WHATWG "the event stream format"）どおり
 *   行末の CR を除去して許容する
 */

export type WireEvent = {
  event: string;
  data: Record<string, unknown>;
};

/** wire framing / JSON として解釈できない入力（契約違反）。 */
export class SseWireFormatError extends Error {}

export class SseStreamParser {
  private decoder = new TextDecoder("utf-8");
  private buffer = "";
  private eventType: string | null = null;
  private dataLines: string[] = [];
  private fatal: SseWireFormatError | null = null;

  /**
   * 受信 chunk を与え、この chunk で完結した event 列を返す。
   * event 途中の分断は内部 buffer に保持し、次回の feed で継続する。
   * 契約違反を検出した場合、その行より前に完結した event 列を返してから、
   * 次回の feed / end で SseWireFormatError を投げる（先行 event を失わない）。
   */
  feed(chunk: Uint8Array): WireEvent[] {
    if (this.fatal !== null) {
      throw this.fatal;
    }
    // stream: true でマルチバイト文字の途中の分断を保留する
    this.buffer += this.decoder.decode(chunk, { stream: true });
    return this.drainCompleteLines();
  }

  /**
   * stream 終了時に呼ぶ。契約違反を検出済みなら SseWireFormatError を投げる。
   * buffer に不完全な event が残っていれば incomplete: true を返す
   * （終端 event の有無の判定は呼び出し側 = consumer の責務）。
   */
  end(): { incomplete: boolean } {
    if (this.fatal !== null) {
      throw this.fatal;
    }
    this.buffer += this.decoder.decode();
    const incomplete =
      this.buffer.length > 0 ||
      this.eventType !== null ||
      this.dataLines.length > 0;
    return { incomplete };
  }

  private drainCompleteLines(): WireEvent[] {
    const events: WireEvent[] = [];
    let index: number;
    while ((index = this.buffer.indexOf("\n")) !== -1) {
      let line = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 1);
      if (line.endsWith("\r")) {
        line = line.slice(0, -1);
      }
      let event: WireEvent | null;
      try {
        event = this.processLine(line);
      } catch (error) {
        if (error instanceof SseWireFormatError) {
          // 先に完結した event を呼び出し側へ渡すため、ここでは投げない
          this.fatal = error;
          return events;
        }
        throw error;
      }
      if (event !== null) {
        events.push(event);
      }
    }
    return events;
  }

  private processLine(line: string): WireEvent | null {
    if (line === "") {
      // 空行 = event の dispatch（SSE 仕様）
      return this.dispatch();
    }
    if (line.startsWith("event:")) {
      this.eventType = line.slice("event:".length).trimStart();
      return null;
    }
    if (line.startsWith("data:")) {
      this.dataLines.push(line.slice("data:".length).trimStart());
      return null;
    }
    if (line.startsWith(":")) {
      // comment 行（SSE 仕様）。契約上は使わないが無害なので無視する
      return null;
    }
    throw new SseWireFormatError(
      `SSE として解釈できない行を受信しました（契約違反）`,
    );
  }

  private dispatch(): WireEvent | null {
    if (this.eventType === null && this.dataLines.length === 0) {
      // 連続する空行は event を構成しない
      return null;
    }
    const eventType = this.eventType;
    // SSE 仕様どおり data 行は \n で連結する（契約上は 1 event 1 行）
    const dataText = this.dataLines.join("\n");
    this.eventType = null;
    this.dataLines = [];
    if (eventType === null || dataText === "") {
      throw new SseWireFormatError(
        "event: 行と data: 行が揃っていない event を受信しました（契約違反）",
      );
    }
    let data: unknown;
    try {
      data = JSON.parse(dataText);
    } catch {
      throw new SseWireFormatError(
        "data が JSON として解釈できません（契約違反）",
      );
    }
    if (typeof data !== "object" || data === null || Array.isArray(data)) {
      throw new SseWireFormatError(
        "data が JSON object ではありません（契約違反）",
      );
    }
    return { event: eventType, data: data as Record<string, unknown> };
  }
}
