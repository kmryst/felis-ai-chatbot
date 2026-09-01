# Azure OpenAI streaming の raw chunk 到達順序の実測記録（Issue #184）

ADR-0028（[/chat の SSE 化と応答契約の固定](../../adr/0028-chat-sse-response-contract.md)）の
写像表（決定 5）・撤回契約（決定 6）・fixture 系列（決定 9）が置いている
「未検証の前提」を、実 stream の観測で消す・または「観測できなかった」と確定させるための記録。
**時刻はすべて UTC**。raw 証跡は [raw/](./raw/) に置く（大きい採取は抜粋。抜粋方針は各ファイル
先頭の `note` 行に記載）。

最重要の作法として、**観測できなかった系列について「存在しない」とは結論しない**。
「今回の条件では観測できなかった」が結論であり、ADR-0028 の防御的契約（到達順に依存しない
設計）は維持される。また本記録は platform / API の挙動観測であって、**SLI threshold 等の
数値の根拠には使わない**（ADR-0028 決定 11・「影響」の ACA ingress の注意と同じ扱い）。

## 1. 実施条件

| 項目 | 値 | 取得根拠 |
| --- | --- | --- |
| 実施日時 | 2026-09-01T09:17:40Z 〜 09:21:42Z（7 呼び出し） | 各 raw JSONL の `meta.started_utc` |
| endpoint リージョン | Japan East | 全応答の `x-ms-region` ヘッダ |
| デプロイ名 | `chat`（`.env` の `AZURE_OPENAI_CHAT_DEPLOYMENT`） | リクエスト URL |
| モデル | `gpt-4.1-mini-2025-04-14` | 全 chunk の `model` field |
| `system_fingerprint` | `fp_51ebab882d`（全 7 呼び出しで同一） | 全 chunk |
| `service_tier` | `default` | 全 chunk |
| api-version | `2024-10-21`（Issue #184 指定。`.env` の値も同一で差異なし） | リクエスト URL |
| content filter 構成 | 既定（カスタム filter policy 未設定。Default streaming filtering = ADR-0028 決定 7 の採用 mode） | Azure 側設定を変更していないこと |
| 採取方法 | SDK 不使用。Python 標準ライブラリ（`http.client`）で SSE の raw バイト列を recv 単位で読み、行単位で到達時刻（リクエスト送信からの相対 ms）つき JSONL に保存 | `scripts/verification/observe-azure-openai-stream.py` |

補足:

- API キーは `.env` から読み取りのみ。本記録・raw 証跡・スクリプトのどこにも出力していない
- Azure リソースの作成・変更・削除は行っていない（既存デプロイへの API 呼び出しのみ。ADR-0014）
- 応答は非決定的なため、raw 証跡は「この条件でこの系列が実在した」ことの証跡であり、
  再実行で同一系列が得られることは意味しない

## 2. 採取一覧（7 呼び出し）

run1〜run4 が本採取。run1u〜run3u は token 実測（usage）のために同一プロンプトを
`stream_options: {"include_usage": true}` 付きで再実行した別呼び出し（応答本文は毎回異なる）。

| run | プロンプト要旨 | `include_usage` | HTTP | JSON chunk 数 | `finish_reason` | ヘッダ到達 | 総所要 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| run1-normal | 注意報と警報の違いを 2 文で | なし | 200 | 77 | `stop` | 764 ms | 1.73 s |
| run2-filter-candidate | 架空のファンタジー小説の戦闘シーン描写（filter 発火候補） | なし | 200 | 643 | `stop` | 420 ms | 10.1 s |
| run3-long | 四季の気象の特徴を 1500 字程度で | なし | 200 | 1683 | `stop` | 803 ms | 29.9 s |
| run4-usage-optin | 「梅雨」を 1 文で | あり | 200 | 38 | `stop` | 493 ms | 1.09 s |
| run1u | run1 と同一プロンプト | あり | 200 | 88 | `stop` | 418 ms | 2.13 s |
| run2u | run2 と同一プロンプト | あり | 200 | 685 | `stop` | 566 ms | 11.95 s |
| run3u | run3 と同一プロンプト | あり | 200 | 1547 | `stop` | 406 ms | 25.0 s |

filter 発火候補（run2 / run2u）のプロンプトは、明らかに架空・無害な文脈の穏当な題材
（フィクションの戦闘描写の依頼）に限定した。filter の回避・迂回（jailbreak）は一切試していない。

## 3. Issue #184 の目的 1〜4 に対する結論

| # | 観測対象 | 結論 |
| --- | --- | --- |
| 1 | 表示済み partial text の後に `finish_reason: "content_filter"` 終端が届く系列の実在 | **観測できなかった**。7 呼び出しすべて `finish_reason: "stop"` で正常終端し、filter 起因の終端は一度も発火しなかった。系列の不在は主張しない（撤回契約は維持） |
| 2 | `content_filter_results` の `error` が届く系列の実在と到達位置 | **`content_filter_results`（複数形）の `error` は観測できなかった**。ただし近縁の未知形状として、**単数形 field `content_filter_result` の `error`**（`code: "content_filter_error"`, `message: "The contents are not filtered"`）が run3 の**全 1683 JSON chunk**（最初の role delta から `finish_reason: "stop"` chunk まで）に付いたまま正常終端する系列を観測した（§5）。写像表が指す field 名と異なるため「目的 2 の系列」とは扱わない |
| 3 | Default mode で `finish_reason` の後・raw `[DONE]` の前に metadata chunk が届く系列の実在 | **自発的な（opt-in なしの）系列は観測できなかった**（run1〜run3 では `finish_reason: "stop"` chunk の直後が `[DONE]`）。一方、`stream_options.include_usage` を opt-in した 4 呼び出しでは、**usage chunk（`choices: []`）が毎回 `finish_reason` の後・`[DONE]` の前に届いた**。「`finish_reason` 後・`[DONE]` 前に chunk が届く」経路は Default mode に実在するため、写像表の「終端判定を `[DONE]` まで遅延」する設計の実データ裏付けになる |
| 4 | 写像表が列挙していない未知の chunk 形状の有無 | **chunk 全体として写像表のどの行にも当てはまらない形状は現れなかった**が、**field レベルの未知が 4 種**現れた（§5 に全文）。(a) 単数形 `content_filter_result` の `error`、(b) 全 chunk の `obfuscation`、(c) usage chunk の `latency_checkpoint` / `routing`、(d) `include_usage` opt-in 時に全 chunk へ付く `usage: null` |

## 4. 写像表（ADR-0028 決定 5）との対応表

写像表の各行について、対応する raw chunk 形状の観測有無。

| 写像表の行（raw stream の chunk） | 観測 | 実測の詳細 |
| --- | --- | --- |
| role のみの delta（content なし） | **厳密な形は観測できなかった** | `content` キー自体を持たない role delta は一度も現れなかった。実際の先頭 delta は常に `delta: {"content": "", "refusal": null, "role": "assistant"}` で、**本行と次行（空 content）の複合形**だった（7/7 回）。どちらの行でも「出力しない」なので写像結果は変わらない |
| content が空文字列または null の delta | **空文字列は観測**（先頭 delta のみ）。null は観測できなかった | 空文字列 content は上記の role delta に同乗する形でのみ出現。応答本文の途中に空 content delta が単独で現れる系列は観測できなかった |
| `choices` が空の chunk（prompt annotation・usage 等のメタ chunk） | **観測** | 2 種類を観測。(1) `prompt_filter_results` chunk: 7 回中 6 回、**stream の先頭**（最初の delta より前）に到達。`id: ""`・`created: 0`・`model: ""`・`object: ""` という空 field 形状（run3 では欠落。§5-1）。(2) usage chunk: `include_usage` opt-in の 4 回すべてで `finish_reason` 後・`[DONE]` 前に到達 |
| content を持たず choice 内に `content_filter_results`（`error` なし）を持つ annotation chunk | **観測できなかった** | content を持たない独立の annotation chunk は一度も現れなかった。`content_filter_results` は**すべての content delta chunk と `finish_reason` chunk に同乗**し、その値はほぼ常に空 object `{}`。run2 / run2u / run4 の一部 chunk でのみ `{"protected_material_code": {"detected": false, "filtered": false}}` が付いた。**公式 sample にあるカテゴリ別（hate / sexual / violence / self_harm）の per-chunk 結果は一度も現れなかった** |
| content が非空の delta | **観測** | 全 7 回。1 呼び出しあたり 34〜1682 個 |
| `finish_reason: "stop"` の chunk | **観測** | 全 7 回。形状は `delta: {}`（空 object）+ `content_filter_results: {}` 同乗。content と同時に届く形は観測せず |
| `finish_reason: "content_filter"` の終端 | **観測できなかった** | filter 発火候補プロンプトでも発火せず。不在は主張しない |
| chunk 内の `content_filter_results` に `error` を検出 | **観測できなかった**（複数形 field には `error` は一度も現れなかった） | 近縁の単数形 `content_filter_result.error` は観測（§5-1）。写像表のこの行は複数形 field を指すため該当なしと判定 |
| raw `[DONE]` | **観測** | 全 7 回、最終行として到達。`data: [DONE]` |
| 上記以外の未知の chunk 形状 | **chunk 単位では観測できなかった**。field 単位の未知は 4 種観測 | §5。写像表は chunk 形状単位の規定のため、既知形状の chunk に未知 field が同乗するケースの扱いは写像表からは一意に決まらない（ADR 追記の論点。本 PR では ADR を変更しない） |

## 5. 写像表にない観測（全文記録）

### 5-1. 単数形 `content_filter_result` の `error`（run3。正常終端 stream に同乗）

run3-long では、**最初の role delta から `finish_reason: "stop"` chunk まで、全 1683 個の
JSON chunk の `choices[0]` に**次の field が付いていた（[raw/run3-long-excerpt.jsonl](./raw/run3-long-excerpt.jsonl)）。

```json
"content_filter_result": {"error": {"code": "content_filter_error", "message": "The contents are not filtered"}}
```

chunk 全文の例（先頭 delta。1 行を整形せずそのまま）:

```text
data: {"choices":[{"content_filter_result":{"error":{"code":"content_filter_error","message":"The contents are not filtered"}},"content_filter_results":{},"delta":{"content":"","refusal":null,"role":"assistant"},"finish_reason":null,"index":0,"logprobs":null}],"created":1788254279,"id":"chatcmpl-EJEutqAFspAZFB7NOhd08tRyVah11","model":"gpt-4.1-mini-2025-04-14","obfuscation":"U99lN","object":"chat.completion.chunk","service_tier":"default","system_fingerprint":"fp_51ebab882d"}
```

観測事実:

- **複数形** `content_filter_results` は同じ chunk 内で空 object `{}` のまま
- この run では stream 先頭の `prompt_filter_results` chunk も**欠落**していた
  （他 6 回はすべて存在）。message の字義（"The contents are not filtered"）と整合的で、
  このリクエストでは content filtering の evaluation が完了していないと解される
- stream は `finish_reason: "stop"` → `[DONE]` で**正常終端**した
- 同一プロンプトの再実行（run3u）では再現せず、リクエスト単位で間欠的に起こる事象である

ADR-0028 決定 6 が引用する公式意味論（「content filtering が evaluation を完了することを
妨げた error の詳細」）に該当するのはこの事象と解されるが、**公式 REST 仕様や写像表が指す
field 名（複数形 `content_filter_results`）と実際に届いた field 名（単数形
`content_filter_result`）が食い違っている**。現行の写像表を字義どおり実装すると:

- 複数形の `error` 検出行は発火しない（複数形は空 `{}` のため）
- 「未知の chunk 形状 → server error 系で終端」行に該当するかは、chunk 全体としては既知形状
  （content delta / finish chunk）に未知 field が同乗した形のため一意に決まらない

fail-closed の趣旨（filter の判定が得られなかった応答を完了扱いにしない）に照らすと、この系列
こそ撤回契約の対象とすべき実データであり、**写像表・fixture 系列 6 の追記改訂の入力になる**
（ADR-0028「影響」の予定どおり別作業。本 PR では ADR を変更しない）。

### 5-2. `obfuscation` field（全 chunk）

全 7 呼び出しの全 JSON chunk（`prompt_filter_results` chunk を除く）の top-level に、ランダムな
短い文字列の `obfuscation` field が付いていた。例: `"obfuscation":"l2O60"`（値は chunk ごとに
異なる長さ・内容）。写像表・ADR-0028 に記載はない。consumer が未知 field を無視する前方互換
（決定 2）で吸収される種類のもの。

### 5-3. usage chunk の `latency_checkpoint` / `routing`（`include_usage` opt-in 時）

usage chunk の全文（run4。1 行をそのまま）:

```text
data: {"choices":[],"created":1788254314,"id":"chatcmpl-EJEvSY5drsqKTmbzILnMWMhU3tP2C","latency_checkpoint":{"engine_tbt_ms":16,"engine_ttft_ms":49,"engine_ttlt_ms":607,"pre_inference_ms":107,"service_tbt_ms":16,"service_ttft_ms":397,"service_ttlt_ms":953,"user_visible_ttft_ms":291},"model":"gpt-4.1-mini-2025-04-14","obfuscation":"","object":"chat.completion.chunk","routing":{"serving_pipereplica":"d20260821091301-e6adfbb2-default-r1-dp0-default"},"service_tier":"default","system_fingerprint":"fp_51ebab882d","usage":{"completion_tokens":34,"completion_tokens_details":{"accepted_prediction_tokens":0,"audio_tokens":0,"reasoning_tokens":0,"rejected_prediction_tokens":0},"prompt_tokens":22,"prompt_tokens_details":{"audio_tokens":0,"cached_tokens":0},"total_tokens":56}}
```

`latency_checkpoint` / `routing` は公式 REST 仕様に見当たらない undocumented field。
また `include_usage` を opt-in すると、途中の全 chunk にも `usage: null` が付く。

### 5-4. SSE framing の観測

- event はすべて `data:` 行のみで構成され、`event:` 行・`id:` 行・comment 行は一度も
  現れなかった
- 行区切りは LF（`\n`）のみで CR は含まれない。event 区切りは空行
- TCP レベルでは 1 recv に複数 event が同居し、event が recv 境界で分断されることもある
  （raw JSONL の `recv` レコード参照）。ADR-0028 決定 8 の byte 分断耐性の前提と整合

## 6. fixture 系列（ADR-0028 決定 9 の系列 3〜7）への実データ裏付け

| 系列 | 実データ裏付け | 出典 |
| --- | --- | --- |
| 3. role-only delta 混在 | **あり（形状の補正つき）**。実データの先頭 delta は role のみではなく `{"content": "", "refusal": null, "role": "assistant"}` の複合形。fixture はこの実測形状を使える | [raw/run1-normal.jsonl](./raw/run1-normal.jsonl) |
| 4. 空・null content 混在 | **空文字列はあり**（先頭 delta に同乗する形のみ）。null content・本文途中の空 content は実データが無く、fixture では引き続き仕様上の想定として置く | 同上 |
| 5. `content_filter` 終端 | **なし**（観測できなかった）。fixture は防御的契約の検証用として仕様ベースのまま維持 | — |
| 6. partial → `content_filter_results` の `error` | **複数形はなし**。近縁の実データとして run3 の単数形 `content_filter_result.error` 系列（正常終端に同乗）が存在し、系列 6 の追記改訂（単数形の扱い）の入力になる | [raw/run3-long-excerpt.jsonl](./raw/run3-long-excerpt.jsonl) |
| 7. post-`stop` の `error` → `[DONE]` | **`error` 部分はなし**。ただし「`finish_reason` 後・`[DONE]` 前に chunk が届く」構造自体は usage chunk で実在を確認（opt-in 時）。終端判定を `[DONE]` まで遅延する設計の裏付けになる | [raw/run4-usage-optin.jsonl](./raw/run4-usage-optin.jsonl) |

このほか系列 1（正常）は run1 / run4 の raw 全量が、`prompt_filter_results` chunk・
`protected_material_code` の同乗形は run1 / run2 抜粋がそのまま fixture の素材に使える。

## 7. token 消費と料金の実測

usage の実測値（`include_usage` opt-in の 4 呼び出し。証跡は raw の usage chunk）:

| run | prompt_tokens | completion_tokens | total_tokens |
| --- | --- | --- | --- |
| run4-usage-optin | 22 | 34 | 56 |
| run1u | 32 | 87 | 119 |
| run2u | 74 | 736 | 810 |
| run3u | 57 | 1583 | 1640 |
| 実測合計 | 185 | 2440 | 2625 |

- run1〜run3（opt-in なし）は stream に usage が届かないため実測できなかった。同一プロンプトの
  再実行（run1u〜run3u）と content chunk 数から、**未実測 3 呼び出しの合計はおおむね
  prompt 163 / completion 2400 token 程度と推定**される（推定であり実測ではない）
- 7 呼び出し合計はおおむね 5,200 token 程度（実測 2,625 + 推定 約 2,560）
- 料金: **単価は未検証の前提**（ADR-0028 と同じ扱い。deployment type・リージョンで変わり、
  本記録では出典を確定しない）。参考として gpt-4.1-mini の一般的な従量単価を
  input $0.40 / 1M・output $1.60 / 1M と仮置きすると、7 呼び出し合計で **1 セント未満
  （約 0.9 セント、1〜2 円）のオーダー**。確定額は Azure Cost Management 側の請求実績で
  別途確認できる（本記録では断定しない）

## 8. 到達タイミングの観測（参考。閾値の根拠にしない）

- content delta は token ごとの逐次到達ではなく、**数百 token 規模のバーストでまとまって
  到達**した。run1 では応答全文 74 chunk が 1,679〜1,685 ms の間に一括到達。run2 / run3 では
  約 2 秒間隔のバーストが続いた（最大 recv 間隔: run2 で 2.1 s、run3u で 5.0 s）。Default
  streaming filtering が buffer 単位で検査してから返す挙動（ADR-0028 決定 6 の引用）と整合する
- ヘッダ到達（TTFB）は 406〜803 ms、最長の呼び出し（run3）でも総所要 29.9 s
- これらは platform の挙動観測であり、**SLI threshold・timeout 値の根拠には使わない**
  （数値決定は SLO 側の手順で行う）

## 9. 成果物の限界

- **不在の主張はしない**: `finish_reason: "content_filter"` 終端・複数形
  `content_filter_results` の `error`・opt-in なしの post-`finish_reason` metadata chunk は
  「今回の 7 呼び出し（Japan East / gpt-4.1-mini / api-version 2024-10-21 / 既定 filter 構成）
  では観測できなかった」が結論であり、存在しないことの証明ではない。写像表・撤回契約の
  防御的設計は維持される
- filter 発火はプロンプト依存で保証できず、穏当な題材の範囲では発火させられなかった。
  filter を回避・迂回する試み（jailbreak）は行っていない
- 応答は非決定的で、単数形 `content_filter_result.error` の系列（run3）は再実行では再現しない
  間欠事象である。raw 証跡が実在の証明であり、再現手順は実在の再確認手段にはならない
- 観測は単一時点・単一リージョン・単一モデルのもの。API の内部実装（`obfuscation` /
  `latency_checkpoint` / `routing` 等の undocumented field を含む）は予告なく変わり得る

## 10. 再現手順

```bash
# リポジトリルート（.env のあるディレクトリ）で
python3 scripts/verification/observe-azure-openai-stream.py <出力ディレクトリ>
```

`.env` に `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_CHAT_DEPLOYMENT` が
必要。スクリプトは使い捨ての観測用で、アプリケーションからは import されず CI からも
呼ばれない（ADR-0004: CI から実 LLM を呼ばない）。

## 関連

- Issue: #184（Refs #107, #113）
- [ADR-0028](../../adr/0028-chat-sse-response-contract.md) — 写像表（決定 5）・撤回契約
  （決定 6）・fixture 系列（決定 9）。本記録が「未検証の前提」の実測入力
- [ADR-0004](../../adr/0004-stub-llm-and-no-llm-in-ci.md) — CI から実 LLM を呼ばない
- [ADR-0014](../../adr/0014-keep-azure-openai-out-of-terraform.md) — Azure OpenAI は
  Terraform 管理外。本観測は既存デプロイへの読み取り呼び出しのみ
