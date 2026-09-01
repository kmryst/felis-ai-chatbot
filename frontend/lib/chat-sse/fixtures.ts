/**
 * 共有 contract fixture（docs/contracts/chat-sse/。ADR-0028 決定 9 の単一正本）の
 * 読み込みと byte 分断パターンの適用。テスト専用（app のコードからは import しない）。
 *
 * schema は docs/contracts/chat-sse/README.md（fixture ファイルの schema）に従う。
 * frontend（consumer）側は wire_sse / expected_wire_events / expect_done /
 * expected_error_class を使う（raw_sse は backend の upstream parser 用）。
 */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const FIXTURES_DIR = fileURLToPath(
  new URL("../../../docs/contracts/chat-sse/fixtures/", import.meta.url),
);

export type WireEventFixture = {
  event: string;
  data: Record<string, unknown>;
};

export type SeriesFixture = {
  name: string;
  series: number | null;
  title: string;
  basis: string;
  basis_note: string;
  description: string;
  raw_sse: string | null;
  wire_sse: string;
  expected_wire_events: WireEventFixture[];
  expect_done: boolean;
  expected_error_class: string | null;
};

export type SingleSplitPattern = {
  name: string;
  series: string;
  target: "raw_sse" | "wire_sse";
  split_byte_offset: number;
};

export type ChunkSizePattern = {
  name: string;
  chunk_size: number;
};

export type ByteSplitPatterns = {
  single_split_patterns: SingleSplitPattern[];
  chunk_size_patterns: ChunkSizePattern[];
};

export function loadSeriesFixtures(): SeriesFixture[] {
  return readdirSync(FIXTURES_DIR)
    .filter((f) => f.startsWith("series-") && f.endsWith(".json"))
    .sort()
    .map(
      (f) =>
        JSON.parse(readFileSync(join(FIXTURES_DIR, f), "utf-8")) as SeriesFixture,
    );
}

export function loadByteSplitPatterns(): ByteSplitPatterns {
  return JSON.parse(
    readFileSync(join(FIXTURES_DIR, "byte-split-patterns.json"), "utf-8"),
  ) as ByteSplitPatterns;
}

/** fixture から consumer の期待値を導出する。 */
export function consumerExpectation(fixture: SeriesFixture): {
  partialText: string;
  terminal: "done" | "error";
  errorClass: string | null;
  retract: boolean;
} {
  const partialText = fixture.expected_wire_events
    .filter((e) => e.event === "message" || e.event === "notice")
    .map((e) => e.data["text"] as string)
    .join("");
  return {
    partialText,
    terminal: fixture.expect_done ? "done" : "error",
    errorClass: fixture.expected_error_class,
    retract: fixture.expected_error_class === "content_filter",
  };
}

/** stream 全体を固定長の byte 断片に刻む（chunk_size_patterns）。 */
export function chunkBytes(bytes: Uint8Array, size: number): Uint8Array[] {
  const chunks: Uint8Array[] = [];
  for (let i = 0; i < bytes.length; i += size) {
    chunks.push(bytes.slice(i, i + size));
  }
  return chunks;
}

/** offset の位置で stream を 2 断片に分割する（single_split_patterns）。 */
export function splitAt(bytes: Uint8Array, offset: number): Uint8Array[] {
  return [bytes.slice(0, offset), bytes.slice(offset)].filter(
    (c) => c.length > 0,
  );
}

/** chunk 列から ReadableStream を作る（consumer テスト用）。 */
export function streamOf(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(chunks[i++]);
      } else {
        controller.close();
      }
    },
  });
}
