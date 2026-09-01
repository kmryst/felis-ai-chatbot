# 気象庁データの seed 投入と実 embedding backfill の実測記録（Issue #196）

- 実施日: 2026-09-01（UTC）〜 2026-09-02（JST）
- 実施 PR: #204（squash `92a0a25`）。手順の正本:
  [seed-and-embedding-backfill.md](../../operations/seed-and-embedding-backfill.md)
- 実施者: Claude Code（apply / Job 実行までの包括許可は 2026-09-01 にユーザーから伝達済み）
- 使用イメージ: `backend-ops:sha-2df47f9`（イメージ変更なし。Job 2 本の新設のみ）

## 1. apply（Job 2 本の新設）

- plan / apply とも `azurerm_container_app_job.seed[0]` / `azurerm_container_app_job.embed_backfill[0]`
  の **2 to add, 0 to change, 0 to destroy**（既存リソース無変更）。
  `Apply complete! Resources: 2 added, 0 changed, 0 destroyed.`
- 実行前の before 実測（ops コンテナ経由 psql）: `documents` **0 行**。シード由来以外の
  既存データは存在せず、diff-sync の削除対象なし（手順書 §0 の停止条件に該当しない）

## 2. 課金の概算見積り（実行前）と実測

- 対象: `documents` 38 行・本文計 5,597 文字（`jma_seed.py` から機械的に集計）
- 見積り: 「日本語 1 文字 ≒ 1〜2 token」の**未検証の前提**で 6,000〜12,000 token
- 実測: **6,224 token**（§5 の表。見積り範囲内で停止条件に該当せず）

## 3. seed 投入 → 実 embedding backfill（実行と before / after）

| 時刻（UTC） | 操作 | execution | 結果 |
| --- | --- | --- | --- |
| 18:21:45〜18:22:14 | seed Job（`python -m app.ingest`） | `caj-felisaichatbot-dev-seed-74w76tc` | Succeeded（29 秒） |
| 18:23:09〜18:23:51 | backfill Job（`python -m app.ingest --embed`） | `caj-felisaichatbot-dev-embed-5ai4s4j` | Succeeded（42 秒） |

行数の実測（ops コンテナ経由 psql。すべて同一コマンドで取得）:

| 時点 | `documents` | `embedding IS NULL` | `object_properties` | `objects` | `sources` |
| --- | --- | --- | --- | --- | --- |
| before（投入前） | 0 | 0 | — | — | — |
| seed 後・backfill 前 | 38 | 38 | 53 | 15 | 13 |
| backfill 後 | **38** | **0** | — | — | — |

seed 後の 4 テーブルの行数は `jma_seed.py` の定義（DOCUMENTS 38 / PROPERTIES 53 /
OBJECTS 15 / SOURCES 13）と完全一致。

## 4. backfill の冪等性（再実行安全）の実測

backfill Job をもう一度実行した（`caj-felisaichatbot-dev-embed-zwy1tj3`。
18:28:03〜18:28:37 UTC）:

- execution は **Succeeded**、行数は **38 / NULL 0 のまま不変**
- 該当時間帯（18:27:30〜18:35 UTC / PT1M）の Azure OpenAI メトリクスは
  `AzureOpenAIRequests` / `TokenTransaction` とも **増分 0**（`embedding IS NULL` の行が
  0 件のため embedding API を一切呼ばない = `backend/app/ingest/embeddings.py` の設計どおり）

## 5. token 消費と課金（実測）

`az monitor metrics list`（PT1M / aggregation Total）の実測。この時間帯の呼び出し源は
本作業のみ（CI からは呼ばない = ADR-0004）。

| 時間帯（UTC） | 内容 | Requests | ProcessedPromptTokens | GeneratedTokens | TokenTransaction |
| --- | --- | --- | --- | --- | --- |
| 18:24 | backfill（38 行の embedding 生成） | 38 | 6,224 | 0 | **6,224** |
| 18:26 | RAG 成立確認 probe（§6。embedding + chat 各 1 回） | 2 | 5,721 | 108 | **5,829** |
| 合計 | | 40 | 11,945 | 108 | **12,053** |

- probe の prompt が大きいのは、`/chat` のコンテキストに `object_properties` 全 53 行
  （約 6KB）を常時併載する設計（ADR-0010）のため
- 単価は本記録では検証しない（未検証の前提）。金額の断定はせず消費 token 数の実測のみを記録する
- Azure Cost Management（`az consumption usage list` 2026-09-01〜09-02）では Azure OpenAI の
  meter 行（`gpt 4.1 mini Inp/Outp glbl - JA East`）は現れているが、金額・数量は照会時点で
  未確定（null）だった。コストデータの反映遅延によるもので、確定値は後日の照会で確認する
  （クレジット残 192.65 USD・spending limit 有効のサブスクリプションであり、1.2 万 token
  規模が残高に対して軽微であることは呼び出し量から明らかだが、金額は断定しない）

## 6. RAG 成立の実測（deployed 環境 end-to-end）

backend serving コンテナ内（注入済み env・実ネットワーク経路）で、
(1) アプリと同じ `Settings.from_env()` → `create_llm_client()` で質問を実 embedding して
`search_similar_documents`（top_k=5）を直接実行し、
(2) `http://localhost:8000/chat` へ同じ質問を実プロンプト POST して SSE を全文取得した
（#195 実測記録 §4-1 と同じ probe 経路。18:26 UTC 台）。

質問（シードに実在する内容）: **「台風の定義は？」**

検索結果（0 件でないこと）: **5 件**

| 順位 | 類似度 | チャンク冒頭 |
| --- | --- | --- |
| top1 | 0.5710 | 台風に関する情報の中では台風の大きさと強さを組み合わせて… |
| top2 | 0.5537 | 気象庁は台風のおおよその勢力を示す目安として… |
| top3 | 0.5535 | 台風は、通常東風が吹いている低緯度では西に移動し… |
| top4 | 0.5261 | 気象庁では、皆様に風の強さの程度を容易にご理解いただくために… |
| top5 | 0.4995 | 熱帯の海上で発生する低気圧を「熱帯低気圧」と呼びますが… |

`/chat` の応答は guard の `notice` ではなく **`message` event の stream（1 文字〜数文字の
delta が多数）→ `done`** で終端した（ADR-0028 の wire contract の正常系列。#195 時点で
未確認だった「実 LLM の `message` stream の end-to-end」がこれで確認できた）。応答全文:

> 台風とは、熱帯の海上で発生する低気圧のうち、北西太平洋または南シナ海にあり、その低気圧
> 域内の最大風速（10分間平均）が約17メートル毎秒（風力8、34ノット）以上のものを指します。
> 簡単に言うと、一定以上の強い風が吹いている熱帯の低気圧が台風と呼ばれます。

応答が検索結果を根拠にしていることの判別: 数値・条件（17 m/s・10分間平均・風力8・
34 ノット・北西太平洋・南シナ海）が top5 チャンク（`jma_seed.py` の台風の定義の文面）と
一致する。RAG 未結線時の実測（ADR-0010 の背景: 事前知識で誤った 41.0℃ を答えた）と
対照的に、コンテキスト由来の内容のみで構成されている。

## 7. 類似度閾値（ADR-0010）の再測定の要否

「台風の定義は？」の top1 類似度は deployed 環境の実測で 0.5710。ADR-0010 の閾値決定時の
ローカル実測（同一シード・同一 embedding モデル）では同じ質問で top1 0.5711 であり、
分布はほぼ一致する（差 0.0001）。シードのデータ規模・文面・embedding モデルは閾値決定時から
変わっていないため、**再測定は不要**と記録する（データ追加時に再測定する運用は
production-readiness.md §7 のとおり）。値の変更はしない（Issue #196 の対象外）。

## 8. 系列全体の完了判定（deployed 環境で 6 点が同時成立していることの確認）

作業系列「frontend デプロイ〜SSE 化〜Azure OpenAI 実接続」の最終確認（Issue #196 受け入れ
条件）。確認はすべて 2026-09-01 18:21〜18:40 UTC 台の同一構成
（`ca-felisaichatbot-dev--0000006` / `ca-felisaichatbot-dev-front--0000001`）に対して行った。

| # | 判定項目 | 状態 | 何を見て確認したか |
| --- | --- | --- | --- |
| 1 | frontend が Azure 上で公開されている | 成立 | `ca-felisaichatbot-dev-front`（`...japaneast.azurecontainerapps.io`）へ本日 HTTPS 到達。`/readyz` 200（frontend → internal backend → DB の経路生存） |
| 2 | Easy Auth で認証される | 成立 | 未認証の `GET /` が本日 401（Easy Auth が全経路で有効）。非管理者テストユーザーの成功試験と `AADSTS50105` の否定側証跡は #194 の実測記録（frontend-easy-auth-cutover 配下）で確認済み |
| 3 | SSE でストリーミング応答が返る | 成立 | §6: `/chat` が `message`（多数 delta の逐次到達）→ `done` の SSE で応答（ADR-0028 正常系列）。実 LLM 応答の end-to-end は本記録で初確認 |
| 4 | 応答が stub ではなく実 Azure OpenAI 由来 | 成立 | §5: 該当時刻の Azure OpenAI メトリクス増分（stub は外部呼び出しゼロ）+ §6 の応答が stub の決定的接頭辞 `[stub]` でない生成文 |
| 5 | RAG が成立している | 成立 | §3: `documents` 38 行・`embedding IS NULL` 0 行。§6: 検索 5 件（0 件でない）・応答が検索結果の数値・条件と一致 |
| 6 | `CHAT_API_KEY` がクライアントバンドルに露出していない | 成立 | deployed frontend コンテナ内 grep を本日再実測: `.next/static` 配下に `NEXT_PUBLIC_CHAT_API_KEY` の出現 0 件・実 key 値の出現 0 件（#193 の CI 自動検査・#194 の初回実測と同結果） |

系列全体のゴール（ユーザー定義:「AI chatbot が動く。ちゃんと RAG と DB を参照して LLM で
返事を返す」)は、上記 6 点の同時成立をもって達成を確認した。

## 関連

- Issue #196 / PR #204（Job 2 本の Terraform 化）
- ADR-0010（RAG 結線・ガード・閾値の根拠）/ ADR-0028（SSE wire contract）
- #195 実測記録: [llm-provider-cutover/observations.md](../llm-provider-cutover/observations.md)
