/**
 * SSE wire parser のテスト（ADR-0028 決定 2 / 決定 8 の downstream 方向）。
 * 共有 fixture（docs/contracts/chat-sse/）を単一正本として読む（決定 9）。
 */

import { describe, expect, it } from "vitest";
import { SseStreamParser, SseWireFormatError, WireEvent } from "./parser";
import {
  chunkBytes,
  loadByteSplitPatterns,
  loadSeriesFixtures,
  splitAt,
} from "./fixtures";

const fixtures = loadSeriesFixtures();
const patterns = loadByteSplitPatterns();
const encoder = new TextEncoder();

function parseAll(chunks: Uint8Array[]): {
  events: WireEvent[];
  incomplete: boolean;
} {
  const parser = new SseStreamParser();
  const events: WireEvent[] = [];
  for (const chunk of chunks) {
    events.push(...parser.feed(chunk));
  }
  return { events, incomplete: parser.end().incomplete };
}

/** 全量 feed + end して event 列を返す（契約違反は feed / end のどちらかで throw される）。 */
function parseStrict(text: string): WireEvent[] {
  const parser = new SseStreamParser();
  const events = parser.feed(encoder.encode(text));
  parser.end();
  return events;
}

describe.each(fixtures)("系列 $name", (fixture) => {
  const bytes = encoder.encode(fixture.wire_sse);

  it("無分割で expected_wire_events と同一の event 列を復元する", () => {
    const { events, incomplete } = parseAll([bytes]);
    expect(events).toEqual(fixture.expected_wire_events);
    expect(incomplete).toBe(false);
  });

  describe.each(patterns.chunk_size_patterns)(
    "byte 分断パターン $name（決定 8）",
    (pattern) => {
      it("無分割時と同一の event 列を復元する", () => {
        const { events } = parseAll(chunkBytes(bytes, pattern.chunk_size));
        expect(events).toEqual(fixture.expected_wire_events);
      });
    },
  );
});

describe("single_split_patterns（決定 8。wire_sse 対象分）", () => {
  const wirePatterns = patterns.single_split_patterns.filter(
    (p) => p.target === "wire_sse",
  );

  it("wire_sse 対象のパターンが存在する", () => {
    expect(wirePatterns.length).toBeGreaterThan(0);
  });

  describe.each(wirePatterns)("$name", (pattern) => {
    it("指定 offset で 2 分割しても無分割時と同一の event 列を復元する", () => {
      const fixture = fixtures.find((f) => f.name === pattern.series);
      expect(fixture).toBeDefined();
      const bytes = encoder.encode(fixture!.wire_sse);
      const { events } = parseAll(splitAt(bytes, pattern.split_byte_offset));
      expect(events).toEqual(fixture!.expected_wire_events);
    });
  });
});

describe("wire framing の契約違反", () => {
  it("data が JSON でない event は SseWireFormatError になる", () => {
    expect(() =>
      parseStrict("event: message\ndata: ここは JSON ではない\n\n"),
    ).toThrow(SseWireFormatError);
  });

  it("data が JSON object でない event は SseWireFormatError になる", () => {
    expect(() => parseStrict('event: message\ndata: "文字列"\n\n')).toThrow(
      SseWireFormatError,
    );
  });

  it("event: 行のない data だけの event は SseWireFormatError になる", () => {
    expect(() => parseStrict("data: {}\n\n")).toThrow(SseWireFormatError);
  });

  it("SSE として解釈できない行は SseWireFormatError になる", () => {
    expect(() => parseStrict("なにかの生テキスト\n")).toThrow(SseWireFormatError);
  });

  it("契約違反の行より前に完結した event は失わない", () => {
    const parser = new SseStreamParser();
    const events = parser.feed(
      encoder.encode('event: message\ndata: {"text":"警報の"}\n\n生テキスト行\n'),
    );
    expect(events).toEqual([{ event: "message", data: { text: "警報の" } }]);
    expect(() => parser.end()).toThrow(SseWireFormatError);
  });
});

describe("SSE 仕様上の許容形", () => {
  it("CRLF 行末を LF と同様に扱う", () => {
    const parser = new SseStreamParser();
    const events = parser.feed(
      encoder.encode('event: message\r\ndata: {"text":"雨"}\r\n\r\n'),
    );
    expect(events).toEqual([{ event: "message", data: { text: "雨" } }]);
  });

  it("comment 行（: で始まる行）を無視する", () => {
    const parser = new SseStreamParser();
    const events = parser.feed(
      encoder.encode(": keep-alive\nevent: done\ndata: {}\n\n"),
    );
    expect(events).toEqual([{ event: "done", data: {} }]);
  });

  it("event 途中で stream が終了すると end() が不完全を報告する", () => {
    const parser = new SseStreamParser();
    const events = parser.feed(encoder.encode('event: message\ndata: {"tex'));
    expect(events).toEqual([]);
    expect(parser.end().incomplete).toBe(true);
  });
});
