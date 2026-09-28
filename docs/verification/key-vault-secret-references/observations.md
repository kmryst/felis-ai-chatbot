# Container Apps の secret の Key Vault 参照化（Issue #286）実施記録

- 対象 Issue: #286（設計判断は [ADR-0032](../../adr/0032-key-vault-references-for-container-apps-secrets.md)。事前の実測は [key-vault-and-identity-sandbox/observations.md](../key-vault-and-identity-sandbox/observations.md)）
- 秘密値は書かない。必要な場合は長さか判定結果（PASS / FAIL）で代用する
- subscription ID・テナント ID・principal ID・アカウント名は伏せる
- 本書は PR ごとに追記する。PR 1 は Key Vault 基盤（persistent 層）

## PR 1: Key Vault 基盤（persistent 層）

### 事前確認（2026-09-23。すべて読み取り）

| 確認 | 結果 |
| --- | --- |
| Key Vault 名 `kv-felisaichatbot-dev` の空き（`Microsoft.KeyVault/checkNameAvailability`、api-version `2023-07-01`） | `nameAvailable: true`。soft-delete 中の Key Vault（`az keyvault list-deleted`）は 0 件。既存の Key Vault も 0 件 |
| リソースプロバイダー `Microsoft.KeyVault` | `Registered`（Issue #287 の検証時に登録済み） |
| tfstate の Storage Account の blob サービス設定 | `isVersioningEnabled: true`、blob の soft delete は無効。**過去の state のバージョンには、切り替え前の値（ephemeral 層の Easy Auth クライアントシークレットと chat API キー）が残る**。PR 2 / PR 3 で値を置き換え・失効させて対処する（ADR-0032「影響」） |
| アラートのクエリの実データ検証 | Issue #287 の検証用アプリは felis の Container Apps 環境に相乗りしたため、felis の Log Analytics workspace に実際の同期失敗が残っている。2026-09-22T08:40〜08:50Z を範囲に、log search alert と同じ条件（`ContainerAppSystemLogs_CL \| where Reason_s == "SyncingSecretFromAzureKeyVaultForContainerAppFailed"`）で集計すると `ca-kvsbx-7x8cht` 1 件 / `ca-kvsbx-probe-7x8cht` 1 件。直近 30 日の `SyncingSecret*` は `Succeeded` 19 件 / `Failed` 2 件（いずれも検証用アプリ） |

### plan（2026-09-23。読み取りのみ。apply は未実施）

作業端末のローカル設定を変えないよう、別の `TF_DATA_DIR` で `terraform init`（backend は `backend.tf` のとおり）してから実行した。

| plan | 結果 |
| --- | --- |
| `terraform -chdir=terraform/persistent plan -target=azurerm_key_vault.main -target=azurerm_monitor_diagnostic_setting.key_vault` | `Plan: 2 to add, 0 to change, 0 to destroy.` |
| `terraform -chdir=terraform/persistent plan`（全体） | `Plan: 4 to add, 0 to change, 0 to destroy.`（`azurerm_key_vault.main` / `azurerm_monitor_diagnostic_setting.key_vault` / `azurerm_monitor_scheduled_query_rules_alert_v2.kv_secret_sync_failed` / `azurerm_key_vault_secret.chat_api_key`）。**既存リソース（PostgreSQL・VNet・Log Analytics・Action Group・メトリクスアラート 5 件）の変更は 0 件** |
| plan 出力の `azurerm_key_vault_secret.chat_api_key` | `value_wo = (write-only attribute)`、`value_wo_version = 1`。値は plan に出ない |
| plan 出力の `azurerm_key_vault.main` | `rbac_authorization_enabled = true`、`soft_delete_retention_days = 7`、`purge_protection_enabled = false` |

ephemeral 層は PR 1 で変更しない。

### apply とロール割当（2026-09-23 実施）

ユーザーの確認（plan の結果を提示して承認を得る）を 2 回挟み、Claude Code が実行した。
apply はいずれも `plan -out` で保存した plan ファイルに対して行い、plan ファイルは実施後に削除した（コミットしていない）。
事前に `terraform -chdir=terraform/persistent init -reconfigure` で、ローカルの backend 設定を移行先の Storage Account に合わせた（state の移行は無し）。

| 順 | 時刻 (UTC) | 操作 | 結果 |
| --- | --- | --- | --- |
| 1 | 09:24:15 → 09:27:24 | persistent apply（`-target=azurerm_key_vault.main -target=azurerm_monitor_diagnostic_setting.key_vault`） | `Apply complete! Resources: 2 added, 0 changed, 0 destroyed.` Key Vault の作成 2 分 39 秒、diagnostic setting 18 秒 |
| 2 | 09:27:29 → 09:27:37 | ロール割当 2 件（台帳 §B #15 の「作り直す手順」） | 作成成功。`Key Vault Secrets User`（ServicePrincipal）/ `Key Vault Secrets Officer`（User） |
| 3 | 09:30:30 → 09:30:43 | persistent apply（全体） | `Apply complete! Resources: 2 added, 0 changed, 0 destroyed.` secret 1 秒、log search alert 4 秒。secret の作成は 403 にならなかった |

**手順からの逸脱（ロール反映の待ち時間）**: 手順では割当後に 2 分待つとしていたが、固定の待機の代わりに
「data plane の操作（`az keyvault secret list`）が通るまで 10 秒間隔で試す」待ち方にした。
所有者アカウントの `Key Vault Secrets Officer` は、割当の完了（09:27:37）から約 10 秒後（09:27:47）の最初の試行で通った。
Issue #287 の実測（84 秒以内）より速い。全体の apply（手順 3）は割当から約 3 分後に行った。
identity 側の `Key Vault Secrets User` の反映は、Container Apps から参照する PR 2 で確認する。

### 確認（2026-09-23。読み取りのみ）

| 確認 | 期待 | 結果 |
| --- | --- | --- |
| Key Vault スコープに直接付いたロール割当（台帳 §B #15 の確認コマンド） | 2 件のみ | PASS: `Key Vault Secrets User` / ServicePrincipal、`Key Vault Secrets Officer` / User の 2 件。継承分を含めても Key Vault 系のロールはこの 2 件だけ |
| Key Vault の設定（`az keyvault show`） | RBAC / soft-delete 7 日 / purge protection 無効 | PASS: `enableRbacAuthorization: true`、`enableSoftDelete: true`、`softDeleteRetentionInDays: 7`、`enablePurgeProtection: null` |
| `chat-api-key` の有効状態（`--query "attributes.enabled"`）と長さ（値は出さない） | `true` / 64 | PASS: `true` / 64 |
| persistent 層の state に chat API キーの値が無い（`grep -F -f`。空入力・JSON 不正・grep エラーは FAIL 扱い） | PASS | PASS。`azurerm_key_vault_secret.chat_api_key` の `value` は空、`value_wo` は null、`value_wo_version` は 1 |
| diagnostic setting | `AuditEvent` が Log Analytics へ | PASS: `diag-kv-felisaichatbot-dev` |
| log search alert `alert-kv-secret-sync-failed` | 有効、15 分 / 1 時間、Sev2 | PASS |
| persistent 層の `terraform plan -detailed-exitcode` | exit 0 | PASS: `No changes.`（`ephemeral "random_password"` が plan ごとに値を作っても差分にならない） |
| ephemeral 層の `terraform plan -detailed-exitcode` | exit 0 | exit 2（PR 1 とは無関係の既存の差分。下記「ephemeral 層の plan」） |
| 実行中のアプリへの影響 | 無し | PASS: frontend `/readyz` が HTTP 200。Container App 3 件は `provisioningState: Succeeded` で、最新 revision の作成日時は 2026-09-19〜20 のまま（本作業で revision は作られていない） |

### ephemeral 層の plan（ユーザーが実施）

`terraform -chdir=terraform/ephemeral plan -detailed-exitcode` は **exit 2（`2 to change`）** だった。

- 差分の内容: `azurerm_container_app.main`（backend serving）と `azurerm_container_app_job.embed_backfill` に、環境変数 3 件（`AZURE_OPENAI_API_VERSION=2024-10-21`、`AZURE_OPENAI_CHAT_DEPLOYMENT=chat`、`AZURE_OPENAI_EMBEDDING_DEPLOYMENT=embedding`）を追加する in-place update のみ
- 原因: ローカルの環境変数ファイルでは `TF_VAR_azure_openai_*` を設定しているが、直前の ephemeral apply はそれを設定せずに実行されていた。3 件の値はいずれも `backend/app/config.py` の既定値と同じで、適用しても動作は変わらない
- PR 1 との関係: PR 1 は ephemeral 層を変更していないため、PR 1 が原因の差分ではない。PR 2 の ephemeral apply で同時に取り込まれる（PR 2 の plan で、この 3 件が差分に含まれることを確認する）

## PR 2: chat API キーの Container Apps secret を Key Vault 参照に切り替える

対象: backend serving `ca-felisaichatbot-dev` と frontend `ca-felisaichatbot-dev-front` の secret `chat-api-key`。
Easy Auth の `microsoft-provider-authentication-secret` は PR 3。計画は PR 本文の「ユーザーが実施する手順」。

### 変更内容（ephemeral 層）

- `random_password.chat_api_key`、変数 `chat_api_key_rotation`、output `chat_api_key`、env `CHAT_API_KEY_CONFIG_CHECKSUM`、
  `required_providers.random` を削除。`data "azurerm_key_vault" "main"`（変数 `key_vault_name`）と、
  バージョン無しの secret ID `local.chat_api_key_secret_id` を追加し、両 app の `secret "chat-api-key"` を
  `key_vault_secret_id` + `identity`（`id-felisaichatbot-dev`）に変更
- 同時に取り込む既存の差分（PR 1 の記録参照）: serving と embed Job への `AZURE_OPENAI_API_VERSION` /
  `AZURE_OPENAI_CHAT_DEPLOYMENT` / `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`（値は backend の既定と同じ）

### 事前確認（2026-09-28。すべて読み取り）

| 確認 | 結果 |
| --- | --- |
| 3 つの Container App の secret | serving: `database-url` / `chat-api-key`、frontend: `microsoft-provider-authentication-secret` / `chat-api-key`、ops: `database-url`。いずれも値方式（`keyVaultUrl` 無し） |
| 稼働 revision | `ca-felisaichatbot-dev--0000004` / `ca-felisaichatbot-dev-front--0000003` / `ca-felisaichatbot-dev-ops--0000001`。3 件とも `Running` |
| Key Vault の secret | `chat-api-key` 1 件（enabled、2026-09-23 作成） |
| Key Vault スコープのロール割り当て | `Key Vault Secrets User`（identity）/ `Key Vault Secrets Officer`（所有者）の 2 件のみ |
| `ContainerAppSystemLogs_CL` | 現在の workspace に存在（直近 1 日 14,000 行超）。log search alert の評価対象テーブルは既にある |
| azurerm 5.1.0 の `azurerm_container_app.secret` の schema | set。属性 `name` / `identity` / `key_vault_secret_id` / `value`。Key Vault 参照の secret は state の `value` が空文字になり、plan 差分にならない（2026-09-22 実測） |
| `terraform validate`（ephemeral。別 `TF_DATA_DIR` で `init -backend=false`） | `Success! The configuration is valid.` `.terraform.lock.hcl` から random の項が消える |

### plan（2026-09-28。ユーザーが実施）

`terraform -chdir=terraform/ephemeral init` の後、`plan -detailed-exitcode -out=tfplan-pr2-cutover` は exit 2、
`Plan: 0 to add, 3 to change, 1 to destroy.`、`Changes to Outputs: - chat_api_key`。

| 差分 | 内容 |
| --- | --- |
| `random_password.chat_api_key` | destroy（state からの削除のみ） |
| `azurerm_container_app.main` | in-place。secret `chat-api-key` が `value` → `key_vault_secret_id` + `identity`、env `CHAT_API_KEY_CONFIG_CHECKSUM` 削除、env `AZURE_OPENAI_API_VERSION=2024-10-21` / `AZURE_OPENAI_CHAT_DEPLOYMENT=chat` / `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=embedding` 追加（既存の差分） |
| `azurerm_container_app.front[0]` | in-place。secret `chat-api-key` の同じ変更、env `CHAT_API_KEY_CONFIG_CHECKSUM` 削除 |
| `azurerm_container_app_job.embed_backfill[0]` | in-place。env 3 件追加 |
| その他（`azapi_resource.front_auth`、ops、Job、ingress） | 差分なし |

plan の `secret` ブロックは set 型かつ sensitive のため両 app とも「- 2 / + 2」と表示される。`terraform show -json` の
`resource_changes[].change.before / after` を name ごとに（値は sha256 先頭 12 桁と長さだけに加工して）比較し、
`database-url`（main）と `microsoft-provider-authentication-secret`（front）は before / after で同一（同じハッシュ・同じ長さ・Key Vault 参照なし）、
変わるのは `chat-api-key` だけであることを確認してから apply した。

`init` について: `required_providers` から random を外しても、state に `random_password` が残っている間は init が
state 側の要求として random 3.9.1 を取得し、`.terraform.lock.hcl` に random の項が戻る。apply 後の init で外れる（下記）。

### apply と確認（2026-09-28 実施）

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 07:37:58 | 切替前の基準（読み取り） | serving `ca-felisaichatbot-dev--0000004`（replica 2026-09-20T08:46:40Z）/ frontend `ca-felisaichatbot-dev-front--0000003`（replica 2026-09-20T08:46:58Z）。frontend `/readyz` 200。両 app の `chat-api-key` の sha256 先頭 12 桁は `6e0b695a2ecf`（旧 `random_password` の値）、Key Vault の `chat-api-key` は `a934ba6b5413` |
| 07:40:00 → 07:40:39 | `terraform -chdir=terraform/ephemeral apply tfplan-pr2-cutover`（ユーザー） | `Apply complete! Resources: 0 added, 3 changed, 1 destroyed.` `random_password` destroy 0 秒 → main と embed Job が同時に開始、main 18 秒 → front 開始、17 秒 → embed Job 24 秒 |
| 07:40:12 〜 07:40:14 | Key Vault `AuditEvent`（`AzureDiagnostics`） | `SecretGet` `chat-api-key` が identity `id-felisaichatbot-dev` の client ID から `OK` で複数回（取り込み遅延があり、07:41 の時点では 0 行、07:47 の再確認で見えた） |
| 07:40:13 / 07:40:29 | `ContainerAppSystemLogs_CL` | `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` が serving / frontend の順。以後も成功のみ |
| 07:40:14 / 07:40:30 | 新 revision の replica | serving `ca-felisaichatbot-dev--0000005`、frontend `ca-felisaichatbot-dev-front--0000004`。両方 `Running`。**rotation 中に frontend と backend の `chat-api-key` が一致しない期間（ADR-0027 で混在窓と呼んでいる期間）の上限は、両 app の新 replica の作成時刻の差 = 約 16 秒** |
| 07:41:09 | 構成（`az containerapp show`） | PASS: 両 app の `chat-api-key` が `https://kv-felisaichatbot-dev.vault.azure.net/secrets/chat-api-key` + identity `id-felisaichatbot-dev`。`database-url` / `microsoft-provider-authentication-secret` は値方式のまま |
| 07:41〜07:42 | frontend `/readyz` 10 秒間隔 6 回 | PASS: すべて 200 |
| 07:42 | 値の一致（sha256 先頭 12 桁のみ） | PASS: Key Vault / serving / frontend の 3 つとも `a934ba6b5413` |
| 07:45:25 | 機能確認（ユーザーのブラウザ） | PASS: 所有者アカウントで Entra に手動サインイン → チャット画面に戻る → チャット 1 往復成功（応答は最後までストリーミング）。backend の access log は `POST /chat` `200`。07:38〜07:50Z に両 app のコンソールログに `401` / `Unauthorized` は 0 件 |
| 07:47 | state（`state pull` を jq で加工。値は出さない） | PASS: `random_password` 0 件、output `chat_api_key` 無し、両 app の `chat-api-key` は `key_vault_secret_id` あり・`identity` あり・`value` の長さ 0 |

切替 apply による `/readyz` のダウンタイムは観測されなかった（10 秒間隔の 6 回と Container Apps のログのみで、秒単位の計測ではない = ADR-0023）。
`/chat` は切替中の実トラフィックが無く、401 の実測は無い。

### lock ファイルの整理と plan 収束（2026-09-28。ユーザーが実施）

apply 後に `terraform -chdir=terraform/ephemeral init` を再実行すると、state に `random_password` が無くなったため
random が不要になり、`.terraform.lock.hcl` から random の項（21 行）が外れた（init の出力に
"Terraform has made some changes to the provider dependency selections"）。続く `plan -detailed-exitcode` は `No changes.`（exit 0）。
lock ファイルの変更はこの PR に含める。

（以下、rollback・restart の再取得確認・ローテーション・アラート発火試験の結果は実施後に追記する）
