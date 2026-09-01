# LLM provider stub → azure-openai 切替の実測記録（Issue #195）

- 実施日: 2026-09-01（UTC）〜 2026-09-02（JST）
- 実施 PR: #202（squash `6d2d30b`）。手順の正本:
  [llm-provider-cutover.md](../../operations/llm-provider-cutover.md)
- 実施者: Claude Code（apply までの包括許可は 2026-09-01 にユーザーから伝達済み）
- デプロイイメージ: `DEPLOY_SHA=2df47f9`（イメージ変更なし。env / secret 注入のみ）

## 1. 切替前の状態（実測）

- backend serving `ca-felisaichatbot-dev` の env は `DATABASE_URL` / `DSN_CONFIG_CHECKSUM` /
  `CHAT_API_KEY` / `CHAT_DISABLED` / `CHAT_API_KEY_CONFIG_CHECKSUM` の 5 件のみ。
  `LLM_PROVIDER` 未設定 = `backend/app/config.py` の既定 `"stub"` で稼働
- `terraform/` / `.github/` に `LLM_PROVIDER` / `AZURE_OPENAI_*` の設定 0 件（grep 実測）
- documents テーブルは空（seed 未投入 = 後続 Issue #196 の範囲）

## 2. plan で検出した事故未遂（backend_ingress_external の指定漏れ）

1 回目の `terraform plan` に、意図しない差分 2 件が混入した:

- `azurerm_container_app.main` の ingress が `external_enabled = false -> true` /
  `allow_insecure_connections = true -> false`（**internal ingress が external に戻る**）
- `azurerm_container_app.front[0]` の `BACKEND_ORIGIN` が `http://...internal...` →
  `https://...` に変わる

原因は `TF_VAR_backend_ingress_external` が `.env` に永続化されておらず、変数既定値
`true`（cutover 前の値）が効いたこと。#201 の cutover apply ではシェル export で渡して
いたため、セッションが変わると消える。**apply せず停止し、`.env` に
`TF_VAR_backend_ingress_external=false` を追記して plan を取り直した。** 2 回目の plan は
`azurerm_container_app.main` の in-place 更新 1 件のみ（期待どおりの secret 1 件 +
env 7 件の追加。add 0 / destroy 0）となったことを確認して apply した。

教訓: cutover スイッチ型の変数は apply した瞬間に `.env` へ書き戻す（`DEPLOY_SHA` と
同じ扱い）。シェル export だけだと次のセッションの plan が黙って巻き戻しを提案する。

## 3. apply と反映確認

- `terraform apply`: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`
  （17:49 UTC）
- 新 revision `ca-felisaichatbot-dev--0000006` が作成され traffic 100%・
  `RunningAtMaxScale / Healthy` へ遷移（`az containerapp revision list` 実測）。
  **Healthy になったこと自体が「`LLM_PROVIDER=azure-openai` で必須変数が揃い、起動時
  `MissingEnvError` にならなかった」ことの確認になる**（config.py は欠落時に起動で fail する）
- env 名の一覧（値は確認しない）: 既存 5 件 + `LLM_PROVIDER` / `AZURE_OPENAI_ENDPOINT` /
  `AZURE_OPENAI_API_KEY`（secretRef）/ `AZURE_OPENAI_API_VERSION` /
  `AZURE_OPENAI_CHAT_DEPLOYMENT` / `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` /
  `AZURE_OPENAI_CONFIG_CHECKSUM`（`aoai-c5026809`）の計 12 件
- frontend 経由 `/readyz` → 200（frontend → internal backend → DB の経路生存。17:50 UTC）

## 4. 実 Azure OpenAI が呼ばれていることの確認

DB が空のため `/chat` は RAG ガード（ADR-0010）の固定文言（`notice`）で終端し、chat
completion までは到達しない。そこで手順書 §3 のとおり 2 通りで確認した。

### 4-1. `/chat` 実プロンプト → embedding が実 provider に到達（メトリクスで判別）

backend serving コンテナ内から `http://localhost:8000/chat` へ実プロンプト
（`X-API-Key` はコンテナ env から参照。値は出力していない）を 1 回送信（17:50:48 UTC 完了）:

```text
STATUS 200
event: notice
data: {"text":"参照資料に記載がないため、お答えできません。…"}
event: done
data: {}
```

`/chat` は SSE（`notice` → `done`）で応答し、ガード判定より前の `embed()` が実 provider へ
飛ぶ。Azure OpenAI アカウント `felisaichatbot-openai-dev` のメトリクス
（`az monitor metrics list` / PT1M / Total）で該当時刻のリクエストを実測した（§5 の表）。
**stub provider は外部呼び出しを一切行わないため、このメトリクス増分が「deployed 環境の
`/chat` から実 Azure OpenAI が呼ばれた」ことの決定的な判別になる。**

### 4-2. chat completion のストリーミング実測（stub の決定的応答との差異）

backend serving コンテナ内（注入済み env・実ネットワーク経路）で、アプリと同じ
`Settings.from_env()` → `create_llm_client()` を組み立てて `chat_stream()` を 1 回実行
（17:55 UTC 台）:

```text
PROVIDER azure-openai
DELTAS 4
TEXT 稼働確認OK
EMBED_DIM 1536 HEAD [0.0175, -0.004, -0.0388]
```

判別根拠:

- stub の chat 応答は決定的な接頭辞 `[stub] これはスタブ応答です。…`
  （`backend/app/llm/client.py`）で始まる。実測の応答は接頭辞なしの自然文で、指示
  （「稼働確認OK とだけ短く」）に従った生成文だった
- content delta が 4 回に分かれて逐次到達した（= raw stream の chunk 分割を
  `SSEStreamParser` → `raw_stream_to_deltas` が処理するストリーミング経路が実データで動作）
- embedding は 1536 次元（ADR-0003 のとおり）

なお、`/chat` の `message` event stream として実 LLM 応答が返る end-to-end の確認は、
seed 投入・embedding backfill（#196）後でないと構造的に到達しない（RAG ガードが LLM を
呼ばない設計 = ADR-0010 はコードで担保されており、これは本切替の失敗ではない）。

## 5. token 消費と課金（実測）

`az monitor metrics list`（PT1M / aggregation Total / 17:40〜18:05 UTC）の実測。
切替前のこの時間帯に他の呼び出し源はない（stub 稼働 + CI からは呼ばない = ADR-0004）ため、
以下はすべて §4 の疎通確認 3 呼び出し（`/chat` の embedding 1 回 + 直接実行の chat 1 回・
embedding 1 回）に対応する。

| メトリクス | 17:51 | 17:52 | 合計 |
| --- | --- | --- | --- |
| AzureOpenAIRequests | 2 | 1 | 3 |
| ProcessedPromptTokens | 36 | 28 | 64 |
| GeneratedTokens | 0 | 6 | 6 |
| TokenTransaction | 36 | 34 | 70 |

単価は本記録では検証していない（未検証の前提）。金額の断定はせず、消費 token 数の実測
（計 70 token）のみを記録する。クレジット残高（切替前実測 192.65 USD・日次約 17 円）に
対して軽微であることは呼び出し回数から明らか。

## 6. rollback 経路の確認

rollback は「`TF_VAR_llm_provider` を空にして apply」（手順書 §4）。本記録の実測で
その前提 2 点が成立していることを確認した:

- `LLM_PROVIDER` env は revision-scope（今回の追加自体が新 revision `--0000006` を作った
  実測）であり、除去の apply も必ず新 revision を作る
- `Settings.from_env()` は `LLM_PROVIDER` 不在なら既定 `"stub"` に戻り、`AZURE_OPENAI_*`
  が残っていても読まない（`backend/tests/test_app.py` の分岐テストで担保）

rollback の実 apply は実施していない（切替直後に stub へ戻す動機がなく、往復の
revision 作成はコストのみ。手順の実行可能性は上記 2 点と手順書の plan 差分確認で担保）。

## 7. 後続（#196 seed + backfill）への引き継ぎ

- `/chat` の end-to-end（実 LLM の `message` stream）は seed + 実 embedding backfill 後に
  初めて確認できる。確認時は本記録 §4-1 の probe（コンテナ内 localhost POST）がそのまま使える
- ops container / backfill Job には `AZURE_OPENAI_*` を注入していない（本 Issue の対象は
  backend serving のみ）。実 embedding での backfill には ops 側への注入が必要になる
- `TF_VAR_backend_ingress_external=false` は `.env` に永続化済み（§2）。以後の plan で
  ingress 巻き戻し差分は出ない
