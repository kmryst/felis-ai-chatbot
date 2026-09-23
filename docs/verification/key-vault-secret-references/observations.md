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

### apply とロール割当（ユーザーが実施。未実施）

以下は PR 1 のマージ前にユーザーが実施し、結果を本節に追記する。

| 順 | 操作 | 期待 | 結果 |
| --- | --- | --- | --- |
| 1 | persistent apply（`-target=azurerm_key_vault.main -target=azurerm_monitor_diagnostic_setting.key_vault`） | 2 added | 未実施 |
| 2 | ロール割当 2 件（台帳 §B #15 の「作り直す手順」） | 作成成功。2 分待つ | 未実施 |
| 3 | persistent apply（全体） | 2 added（secret / log search alert） | 未実施 |
| 4 | 台帳 §B #15 の確認コマンド | Key Vault スコープに 2 件のみ | 未実施 |
| 5 | `az keyvault secret show -n chat-api-key` の長さ（値は出さない） | 64 | 未実施 |
| 6 | persistent 層の state に chat API キーの値が無いこと（`grep -F -f` で判定） | PASS | 未実施 |
| 7 | 両層の `terraform plan -detailed-exitcode` | 両層とも exit 0 | 未実施 |
| 8 | 実行中のアプリへの影響が無いこと（frontend `/readyz`、各 Container App の `latestRevisionName`） | 200 / 変化なし | 未実施 |
