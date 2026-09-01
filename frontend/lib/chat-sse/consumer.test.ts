/**
 * SSE consumer のテスト（ADR-0028 決定 2 / 4 / 6 / 8 / 9 の client 側）。
 * 共有 fixture（docs/contracts/chat-sse/）を単一正本として読む（決定 9）。
 *
 * 必須条件（決定 9）: 系列 5〜7 は「`done` なし・`error` 終端・class が
 * `content_filter` なら撤回」になること。
 */

import { describe, expect, it } from "vitest";
import {
  CONTENT_FILTER_RETRACTION_TEXT,
  INCOMPLETE_RESPONSE_TEXT,
  consumeChatSseStream,
} from "./consumer";
import {
  chunkBytes,
  consumerExpectation,
  loadByteSplitPatterns,
  loadSeriesFixtures,
  streamOf,
} from "./fixtures";

const fixtures = loadSeriesFixtures();
const patterns = loadByteSplitPatterns();
const encoder = new TextEncoder();

describe.each(fixtures)("系列 $name", (fixture) => {
  const bytes = encoder.encode(fixture.wire_sse);
  const expected = consumerExpectation(fixture);

  it("fixture の期待どおりに終端・撤回する", async () => {
    const rendered: string[] = [];
    const outcome = await consumeChatSseStream(streamOf([bytes]), (text) =>
      rendered.push(text),
    );

    expect(outcome.partialText).toBe(expected.partialText);
    expect(outcome.terminal).toBe(expected.terminal);
    expect(outcome.errorClass).toBe(expected.errorClass);
    expect(outcome.retract).toBe(expected.retract);

    if (expected.terminal === "done") {
      // done を受けて確定した応答はそのまま表示される
      expect(outcome.displayText).toBe(expected.partialText);
    } else if (expected.retract) {
      // 撤回契約: partial text を撤回し固定文言に置換する（決定 6）
      expect(outcome.displayText).toBe(CONTENT_FILTER_RETRACTION_TEXT);
      if (expected.partialText !== "") {
        expect(outcome.displayText).not.toContain(
          expected.partialText.slice(0, 4),
        );
      }
    } else {
      // content_filter 以外の失敗は partial text を保持して文言を付す
      expect(outcome.displayText).toContain(INCOMPLETE_RESPONSE_TEXT);
      if (expected.partialText !== "") {
        expect(outcome.displayText).toContain(expected.partialText);
      }
    }

    // 描画 callback は累積 text で呼ばれ、最後の値は partial text 全体に一致する
    if (expected.partialText !== "") {
      expect(rendered.at(-1)).toBe(expected.partialText);
    } else {
      expect(rendered).toEqual([]);
    }
  });

  describe.each(patterns.chunk_size_patterns)(
    "byte 分断パターン $name（決定 8）",
    (pattern) => {
      it("無分割時と同一の結果になる", async () => {
        const outcome = await consumeChatSseStream(
          streamOf(chunkBytes(bytes, pattern.chunk_size)),
        );
        expect(outcome.partialText).toBe(expected.partialText);
        expect(outcome.terminal).toBe(expected.terminal);
        expect(outcome.errorClass).toBe(expected.errorClass);
        expect(outcome.retract).toBe(expected.retract);
      });
    },
  );
});

describe("決定 9 の必須条件（系列 5〜7）", () => {
  const required = fixtures.filter((f) => [5, 6, 7].includes(f.series ?? -1));

  it("系列 5〜7 の fixture がすべて存在する", () => {
    expect(new Set(required.map((f) => f.series))).toEqual(new Set([5, 6, 7]));
    // 系列 6 は複数形（6a）と実測の単数形（6b。run3-long）の両方を持つ
    expect(required.filter((f) => f.series === 6).length).toBe(2);
  });

  describe.each(required)("系列 $name", (fixture) => {
    it("done なし・error 終端（class: content_filter）・撤回になる", async () => {
      const outcome = await consumeChatSseStream(
        streamOf([encoder.encode(fixture.wire_sse)]),
      );
      expect(fixture.expect_done).toBe(false);
      expect(
        fixture.expected_wire_events.some((e) => e.event === "done"),
      ).toBe(false);
      expect(outcome.terminal).toBe("error");
      expect(outcome.errorClass).toBe("content_filter");
      expect(outcome.retract).toBe(true);
      expect(outcome.displayText).toBe(CONTENT_FILTER_RETRACTION_TEXT);
    });
  });
});

describe("終端 event なしのストリーム終了（決定 2。失敗として扱う）", () => {
  it("wire が途中で切断されると失敗になり、partial text は保持する", async () => {
    // fixture（系列 1）の wire_sse から終端 event を欠落させ、
    // さらに末尾の event を data 行の途中で切断する
    const fixture = fixtures.find((f) => f.series === 1)!;
    const events = fixture.expected_wire_events;
    const contentEvents = events.filter((e) => e.event === "message");
    const full = fixture.wire_sse;
    // 最後の message event の途中（data 行の中）までで切る
    const lastMessageStart = full.lastIndexOf("event: message");
    const truncated = full.slice(0, lastMessageStart + "event: message\ndata: {\"tex".length);
    const outcome = await consumeChatSseStream(
      streamOf([encoder.encode(truncated)]),
    );
    expect(outcome.terminal).toBe("failed");
    // 完結した message までの partial text は保持される（撤回しない）
    const keptText = contentEvents
      .slice(0, -1)
      .map((e) => e.data["text"] as string)
      .join("");
    expect(outcome.partialText).toBe(keptText);
    expect(outcome.retract).toBe(false);
    expect(outcome.displayText).toContain(INCOMPLETE_RESPONSE_TEXT);
    expect(outcome.displayText).toContain(keptText);
  });

  it("event 境界ちょうどで終端 event なしに終了しても失敗になる", async () => {
    const wire = 'event: message\ndata: {"text":"警報の"}\n\n';
    const outcome = await consumeChatSseStream(streamOf([encoder.encode(wire)]));
    expect(outcome.terminal).toBe("failed");
    expect(outcome.partialText).toBe("警報の");
  });
});

describe("契約違反の扱い（fail-closed）", () => {
  it("空文字列 text の message は content event として数えない（決定 4）", async () => {
    const wire =
      'event: message\ndata: {"text":""}\n\n' +
      'event: message\ndata: {"text":"本文"}\n\nevent: done\ndata: {}\n\n';
    const rendered: string[] = [];
    const outcome = await consumeChatSseStream(
      streamOf([encoder.encode(wire)]),
      (text) => rendered.push(text),
    );
    expect(outcome.terminal).toBe("done");
    expect(outcome.partialText).toBe("本文");
    // 空 message では描画 callback を呼ばない
    expect(rendered).toEqual(["本文"]);
  });

  it("契約に無い event 種別は失敗として扱う", async () => {
    const wire = "event: retract\ndata: {}\n\n";
    const outcome = await consumeChatSseStream(streamOf([encoder.encode(wire)]));
    expect(outcome.terminal).toBe("failed");
  });

  it("text が文字列でない message は失敗として扱う", async () => {
    const wire = 'event: message\ndata: {"text":123}\n\n';
    const outcome = await consumeChatSseStream(streamOf([encoder.encode(wire)]));
    expect(outcome.terminal).toBe("failed");
  });

  it("wire framing の違反は失敗として扱い、partial text を保持する", async () => {
    const wire = 'event: message\ndata: {"text":"警報の"}\n\n' + "生テキスト行\n";
    const outcome = await consumeChatSseStream(streamOf([encoder.encode(wire)]));
    expect(outcome.terminal).toBe("failed");
    expect(outcome.partialText).toBe("警報の");
    expect(outcome.displayText).toContain(INCOMPLETE_RESPONSE_TEXT);
  });

  it("done の data の未知 field は無視する（前方互換）", async () => {
    const wire =
      'event: message\ndata: {"text":"本文"}\n\n' +
      'event: done\ndata: {"usage":{"total_tokens":10},"future_field":true}\n\n';
    const outcome = await consumeChatSseStream(streamOf([encoder.encode(wire)]));
    expect(outcome.terminal).toBe("done");
    expect(outcome.displayText).toBe("本文");
  });

  it("終端 event の後の入力は読まずに打ち切る", async () => {
    const wire =
      "event: done\ndata: {}\n\n" + 'event: message\ndata: {"text":"余分"}\n\n';
    const outcome = await consumeChatSseStream(streamOf([encoder.encode(wire)]));
    expect(outcome.terminal).toBe("done");
    expect(outcome.partialText).toBe("");
  });
});
