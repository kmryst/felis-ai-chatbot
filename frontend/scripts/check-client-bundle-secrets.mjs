#!/usr/bin/env node
/**
 * client 配布物（.next/static/ 配下）に秘匿対象が含まれないことを検査する
 * （ADR-0027 決定 2 の受け入れ条件。Issue #193）。
 *
 * 検査対象:
 * - 廃止した env 変数名: NEXT_PUBLIC_CHAT_API_KEY / NEXT_PUBLIC_BACKEND_URL
 *   （NEXT_PUBLIC_ 変数はビルド時に client bundle へ埋め込まれるため、
 *   名前が bundle に現れること自体が再導入の兆候）
 * - 実行環境に CHAT_API_KEY が設定されている場合はその値そのもの
 *
 * `next build` の完了後に実行する（CI では build の直後の step）。
 * 見つかった場合は該当ファイルを列挙して exit 1（値そのものは出力しない）。
 */

import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";
import process from "node:process";

const STATIC_DIR = new URL("../.next/static/", import.meta.url).pathname;

if (!existsSync(STATIC_DIR)) {
  console.error(
    `client 配布物が見つかりません: ${STATIC_DIR}\n先に \`npm run build\` を実行してください`,
  );
  process.exit(1);
}

/** @type {{label: string, value: string}[]} */
const forbidden = [
  { label: "NEXT_PUBLIC_CHAT_API_KEY（廃止した変数名）", value: "NEXT_PUBLIC_CHAT_API_KEY" },
  { label: "NEXT_PUBLIC_BACKEND_URL（廃止した変数名）", value: "NEXT_PUBLIC_BACKEND_URL" },
];
if (process.env.CHAT_API_KEY) {
  forbidden.push({ label: "CHAT_API_KEY の値", value: process.env.CHAT_API_KEY });
}

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      yield* walk(path);
    } else {
      yield path;
    }
  }
}

let fileCount = 0;
const hits = [];
for (const path of walk(STATIC_DIR)) {
  fileCount += 1;
  const content = readFileSync(path, "utf-8");
  for (const { label, value } of forbidden) {
    if (content.includes(value)) {
      hits.push({ path, label });
    }
  }
}

if (hits.length > 0) {
  console.error("client 配布物に秘匿対象が含まれています:");
  for (const { path, label } of hits) {
    console.error(`- ${path}: ${label}`);
  }
  process.exit(1);
}

console.log(
  `OK: .next/static/ 配下 ${fileCount} ファイルに秘匿対象（${forbidden.length} 項目）は含まれていません`,
);
