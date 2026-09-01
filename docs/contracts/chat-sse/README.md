# /chat SSE 共有 contract fixture

[ADR-0028](../../adr/0028-chat-sse-response-contract.md) 決定 9 の共有 contract fixture。
backend（producer）・frontend（BFF・client parser）・synthetic verifier の 3 者が参照する
**単一正本**であり、3 者の契約解釈の分岐を構造的に防ぐ。CI から実 LLM を呼ばない決定
（ADR-0004）の下で、raw stream 系列の fixture がスタブ側の入力になる。

## error class 識別子（表記の正本）

wire の `error` event の data は `{"class": "<識別子>"}` のみを持つ（詳細メッセージを
含めない。決定 2）。識別子の表記は本 fixture が固定する。

| 識別子 | 対応（`backend/app/llm/errors.py`） | 意味 |
| --- | --- | --- |
| `timeout` | `LLMTimeoutError` | upstream 呼び出しの timeout |
| `rate_limit` | `LLMRateLimitError` | レート制限（HTTP 429 相当） |
| `server_error` | `LLMServerError` | 提供元の一時障害・契約違反の stream（途中切断・未知の chunk 形状等の fail-closed を含む） |
| `bad_request` | `LLMBadRequestError` | リクエスト自体が不正（HTTP 4xx 相当） |
| `content_filter` | `LLMContentFilterError` | content filter 起因の終端（`finish_reason: "content_filter"`、または error field の検出 = 決定 6 の撤回契約の対象） |

## wire event の data schema

- `message`: `{"text": "<非空文字列>"}`（決定 4）
- `notice`: `{"text": "<NO_CONTEXT_NOTICE 全文>"}`（決定 3。正本は
  `backend/app/llm/prompts.py` の `NO_CONTEXT_NOTICE`）
- `done`: 終端メタデータの JSON object（最小は `{}`）。consumer は未知 field を無視する
- `error`: `{"class": "<識別子>"}`

producer の JSON 直列化は決定的（`ensure_ascii=False`・separator は `,` と `:` で空白
なし）とし、`wire_sse` は producer の実出力と byte 単位で一致する canonical wire example を
兼ねる。

## fixture ファイルの schema（`fixtures/*.json`）

| field | 内容 |
| --- | --- |
| `name` / `series` / `title` | 系列の識別。`series` は ADR-0028 決定 9 の系列番号（途中切断系列は `null`） |
| `basis` | `measured`（実測形状に基づく）/ `spec`（仕様ベース）/ `measured+spec`（混在） |
| `basis_note` | 実データの出典（`docs/verification/azure-openai-stream/raw/`）または仕様ベースで置く理由。実測で得られなかった系列はその旨を明記する |
| `raw_sse` | Azure OpenAI raw stream の SSE テキスト全体（upstream parser への入力）。guard 系列は `null` |
| `wire_sse` | 期待される wire 出力の SSE テキスト全体（canonical wire example。downstream parser への入力） |
| `expected_wire_events` | `wire_sse` の parse 結果（`{"event", "data"}` の列） |
| `expect_done` | 有効な終端 `done` で終わるか。**系列 5〜7 と途中切断系列は必ず `false`**（`done` なし・`error` 終端がテストの必須条件。決定 9） |
| `expected_error_class` | `error` 終端の場合の class 識別子。正常終端は `null` |

`fixtures/byte-split-patterns.json` は決定 8 の byte 分断パターン試験データ。分断 offset
（UTF-8 マルチバイト文字の途中・`data:` / `event:` プレフィクスの途中・event 区切りの
空行の直前後）と固定長分割（1 byte / 3 byte）を、upstream（`raw_sse`）・downstream
（`wire_sse`）の両方向に対して定義する。どのパターンで分断しても無分割時と同一の
event 列に復元されることをテストの必須条件とする。

## 参照方法

- backend: `backend/tests/test_sse_contract.py` 等がリポジトリルートからの相対パス
  （`docs/contracts/chat-sse/fixtures/`）で読む
- frontend / synthetic verifier: 同じ JSON を同じ相対パスで読む（`raw_sse` は BFF には
  不要で、`wire_sse` / `expected_wire_events` / `expect_done` / `expected_error_class` を
  consumer parser・撤回処理・verifier の分類のテスト入力に使う）

## 実データとの関係

`measured` の系列は [実測記録](../../verification/azure-openai-stream/observations.md)
（Issue #184）の raw 証跡（`raw/*.jsonl`）の chunk 形状（複合形の先頭 delta・
`obfuscation` / `usage: null` 等の未知 field 同乗・単数形 `content_filter_result.error`
系列・post-`stop` の usage chunk）をそのまま使い、content 本文と chunk 数のみ短縮して
いる。実測で得られなかった系列（`finish_reason: "content_filter"`・複数形
`content_filter_results` の `error`・post-`stop` の error chunk）は防御的契約の検証用
として仕様ベースで置く（不在は主張しない。observations.md §9）。
