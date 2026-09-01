# 気象庁データの seed 投入と実 embedding での backfill（Issue #196）

Azure 上の PostgreSQL へ気象庁シードデータを投入し、実 Azure OpenAI で
`documents.embedding` を backfill して RAG を成立させる手順の正本。実行手段は
Container App Job 2 本（`caj-felisaichatbot-dev-seed` / `caj-felisaichatbot-dev-embed`。
`terraform/ephemeral/main.tf`）で、migrate Job と同型の Manual トリガー。

> 実行前提: apply / Job 実行は CLAUDE.md の禁止事項に従い**ユーザーの明示承認を得てから**
> 実行する。本書は手順の正本であって実行許可ではない。

## 0. 停止条件（包括許可時も有効）

- **永続データの破壊**: seed 投入は diff-sync（シードに現れない行の削除）を含む。実行前に
  §3 の before 実測で既存データを確認し、**シード由来以外のデータが存在して削除対象になる
  場合は実行を止めてユーザーに確認する**（現行の想定は「空 or シード由来のみ」）
- **見積りを大きく超える課金**: backfill の対象は最大 `documents` 全行（§2 の見積り）。
  Azure OpenAI メトリクスの消費 token が見積りを大きく超えて増え続ける場合は、以後の
  実行を止めてユーザーに確認する（未 commit 分は巻き戻り、再実行は `embedding IS NULL`
  の行のみを対象とするため中断は安全）
- **継続的なエラー**: Job execution の失敗が 2 回連続したら再実行せず、原因
  （`az containerapp job execution list` とコンソールログ）を確認して報告する

## 1. 前提

- ops イメージ（`backend-ops:sha-<DEPLOY_SHA>`）がデプロイ済み（Job 2 本は ops イメージを
  使う。runtime ステージ由来の `app/` + `.venv` を含むため `python -m app.ingest` を実行できる）
- `LLM_PROVIDER=azure-openai` 切替済み（[llm-provider-cutover.md](./llm-provider-cutover.md)。
  embed Job は `llm_provider = "azure-openai"` のときにしか作られない = stub のダミーベクトル
  で embedding 列を埋める経路は Terraform 側で塞いである）
- 実行順は **seed → backfill** に固定（ADR-0010。backfill は `embedding IS NULL` の行のみを
  対象とする冪等な実行で、diff-sync により文面改訂も自然に再生成対象になる）

## 2. 課金の概算見積り（実行前に確認）

- 対象: シードの `documents` 38 行・本文計 5,597 文字（`jma_seed.py` から機械的に集計。
  再集計は `python -c` で `len(DOCUMENTS)` / `sum(len(...))` を出す）
- embedding の消費 token は「日本語 1 文字 ≒ 1〜2 token」の**未検証の前提**で概算
  **6,000〜12,000 token** とする（tokenizer の実測はしていない。実測値は Job 実行後に
  Azure OpenAI メトリクス `TokenTransaction` で確認し、実測記録に残す）
- 単価は本書では検証しない（未検証の前提）。参考実測: #195 の疎通確認 70 token は
  クレジット残高（192.65 USD）に対して計測誤差レベルだった。1 万 token 規模でも同じ
  オーダーの軽微さと見込むが、**金額の断定はしない**。実コストは実行後に
  Azure Cost Management で確認する

## 3. 実行手順

```bash
# 0) 変数の読み込み（vnet-integration-cutover.md §0-2 の作法）
set -a; source .env; set +a
export TF_VAR_container_image="felisaichatbotacrdev.azurecr.io/backend:sha-${DEPLOY_SHA:?}"
export TF_VAR_ops_container_image="felisaichatbotacrdev.azurecr.io/backend-ops:sha-${DEPLOY_SHA:?}"
export TF_VAR_frontend_container_image="felisaichatbotacrdev.azurecr.io/frontend:sha-${DEPLOY_SHA:?}"

# 1) plan（期待 diff: Job 2 本の add のみ）→ apply
terraform -chdir=terraform/ephemeral plan
terraform -chdir=terraform/ephemeral apply

# 2) before 実測（ops コンテナ経由。documents 行数と embedding IS NULL 行数）
az containerapp exec -n ca-felisaichatbot-dev-ops -g rg-felisaichatbot-dev-tf \
  --command 'psql "$DATABASE_URL" -c "SELECT count(*) AS documents, count(*) FILTER (WHERE embedding IS NULL) AS embedding_null FROM documents"'

# 3) seed Job 実行 → execution の Succeeded を確認
az containerapp job start -n caj-felisaichatbot-dev-seed -g rg-felisaichatbot-dev-tf
az containerapp job execution list -n caj-felisaichatbot-dev-seed -g rg-felisaichatbot-dev-tf -o table

# 4) 中間実測（documents が入り embedding が全行 NULL であること）→ 手順 2 と同じコマンド

# 5) backfill Job 実行 → execution の Succeeded を確認
az containerapp job start -n caj-felisaichatbot-dev-embed -g rg-felisaichatbot-dev-tf
az containerapp job execution list -n caj-felisaichatbot-dev-embed -g rg-felisaichatbot-dev-tf -o table

# 6) after 実測（embedding_null = 0 であること）→ 手順 2 と同じコマンド
```

RAG 成立の確認（token 課金を伴う。数回に留める）は、backend serving コンテナ内からの
`http://localhost:8000/chat` への実プロンプト POST で行う（#195 実測記録 §4-1 の probe と
同じ経路。質問はシードに実際に含まれる内容を選ぶ）。token 消費は Azure OpenAI メトリクス
（`az monitor metrics list`）で実測する。

## 4. 再実行・失敗時

- seed Job: 冪等（再実行しても行数は増えない）。ただし diff-sync の削除を含むため、
  再実行前にも §0 の確認を行う
- backfill Job: 冪等（`embedding IS NULL` の行のみ対象）。途中失敗は未 commit 分が
  巻き戻り、再実行が残りだけを処理する。§0 の停止条件（連続失敗 2 回）を守る
- Job の実行ログ: Log Analytics（`ContainerAppConsoleLogs_CL`）または
  `az containerapp job execution list` で確認する

## 関連

- ADR-0010（RAG 結線・ガード・ingest → backfill の順序）
- ADR-0004（stub 既定・CI から実 LLM を呼ばない。**Job は CI から実行しない**）
- ADR-0009（Azure OpenAI 必須変数）/ ADR-0018（ops イメージ・migrate Job の作法）
- Issue #196 / 実測記録は `docs/verification/seed-embedding-backfill/` 配下（実行時に追加）
