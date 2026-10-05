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
embed backfill Job `caj-felisaichatbot-dev-embed` の template は 2026-10-01 に `az containerapp job show` で読み取りのみ確認した（手動実行はしない。`--embed` は
seed の diff-sync と stale 行の削除を伴うため）: env に `AZURE_OPENAI_API_VERSION=2024-10-21` / `AZURE_OPENAI_CHAT_DEPLOYMENT=chat` / `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=embedding` が入っている。

### lock ファイルの整理と plan 収束（2026-09-28。ユーザーが実施）

apply 後に `terraform -chdir=terraform/ephemeral init` を再実行すると、state に `random_password` が無くなったため
random が不要になり、`.terraform.lock.hcl` から random の項（21 行）が外れた（init の出力に
"Terraform has made some changes to the provider dependency selections"）。続く `plan -detailed-exitcode` は `No changes.`（exit 0）。
lock ファイルの変更はこの PR に含める。

### rollback 1 回（Key Vault 参照 → 直接値 → Key Vault 参照。2026-09-28 実施。すべて az CLI）

rollback 用の値は apply の前（07:37Z）に Key Vault から作業端末の一時ファイル（mode 600、改行なし、64 バイト）へ取り出しておいたものを使い、
Key Vault へは読みに行かない（Key Vault の読み取り障害が切替失敗の原因だった場合でも戻せるようにするため）。
直接値が入っている間は ephemeral 層で Terraform（plan を含む）を実行しない（値方式の secret の値が state に書かれるため）。

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 08:52:07 | 外形監視の停止 `gh variable set PROBE_ENABLED --body false`（restart を可用性 SLI に入れない） | `false` を確認 |
| 08:52:26 → 08:52:56 | `az containerapp secret set ... --secrets "chat-api-key=<値ファイルの内容>" --output none`（serving 08:52:42、frontend 08:52:56） | 両 app の `keyVaultUrl` が空（値方式に戻った）。値は Key Vault と同じなのでアプリの挙動は変わらない |
| 08:52:59 / 08:53:01 | `az containerapp revision restart`（serving `--0000005` / frontend `--0000004`） | `Restart succeeded`。replica は 08:53:00Z / 08:53:02Z に再作成され、08:54:25Z に両方 `Running`。新 revision は作られない |
| 08:53〜08:54 | frontend `/readyz` 10 秒間隔 6 回 | すべて 200（restart 直後の 1 分間でも 503 は観測されなかった。10 秒間隔の 6 回であり秒単位の計測ではない） |
| 08:54 | 値の一致（sha256 先頭 12 桁） | 値ファイル / serving / frontend とも `a934ba6b5413` |
| 10:43:40 | 機能確認（ユーザーのブラウザ） | チャット 1 往復成功。backend の access log は `POST /chat` `200`。08:50〜10:50Z に両 app のログに `401` / `Unauthorized` は 0 件 |
| 10:44:50 | 外形監視の再開 `gh variable set PROBE_ENABLED --body true` | `true` を確認。**欠測期間: 08:52:07Z 〜 10:44:50Z（約 1 時間 53 分）**。rollback の作業自体は 3 分で終わっており、大半はブラウザ確認までの待ち時間 |
| 10:44:51 → 10:45:25 | Key Vault 参照へ戻す `az containerapp secret set ... --secrets "chat-api-key=keyvaultref:https://kv-felisaichatbot-dev.vault.azure.net/secrets/chat-api-key,identityref:<identity の resource ID>" --output none`（serving 10:45:09、frontend 10:45:25） | 両 app の `keyVaultUrl` と `identity` が戻る。`SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` が serving 10:45:03、frontend 10:45:21（設定直後に platform が解決する）。replica は 08:53 のまま（restart は不要） |
| 10:45 | 値の一致（sha256 先頭 12 桁） | 値ファイル / serving / frontend とも `a934ba6b5413` |
| 10:46 | 値ファイルを `shred -u` | 削除済み |

分かったこと:

- Key Vault 参照 → 直接値 → Key Vault 参照の往復は、`az containerapp secret set` 2 回と `revision restart` 1 回で完結し、Terraform を要しない。
  戻す側（Key Vault 参照の設定し直し）は replica の再起動を伴わない
- `az containerapp secret set` の `identityref` に `az identity show --query id` の値をそのまま渡すと、resource ID の `resourcegroups` が小文字で入る
  （Terraform apply 後は `resourceGroups`）。この表記差は次の plan で差分になった（下記「plan 収束」）。
  **以後 az CLI で `identityref:` に渡す ID は、Terraform が書いた表記そのものを持つ
  `az containerapp show -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev --query "properties.configuration.registries[0].identity" -o tsv`
  から取る**（`az identity show --query id` は使わない）

### plan 収束（identity の resource ID の表記差。2026-10-01。Terraform はユーザーが実施）

rollback の往復後に ephemeral 層の `terraform -chdir=terraform/ephemeral plan -detailed-exitcode` を再開したところ exit 2
（`Plan: 0 to add, 2 to change, 0 to destroy.`）。差分は `azurerm_container_app.main` と `azurerm_container_app.front[0]` の
`secret` ブロック（set 型かつ sensitive のため両 app とも「- 2 / + 2」表示）のみ。

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 事前 | `plan -out=tfplan-pr2-identity-case` の `terraform show -json` を name ごとに比較（値は sha256 先頭 12 桁と長さのみ） | 変わるのは両 app の `chat-api-key` の `identity` だけで、`/resourcegroups/` → `/resourceGroups/` の大文字小文字の差のみ。`key_vault_secret_id` は同一、`value` は両側とも空。`database-url` / `microsoft-provider-authentication-secret` は before / after 同一。`template` / `ingress` / `identity` / `registry` に差分なし、`replace_paths` なし、output の変更なし |
| 04:23:3x → 04:24:0x | `apply tfplan-pr2-identity-case`（ユーザー） | `Apply complete! Resources: 0 added, 2 changed, 0 destroyed.` main 18 秒、front 19 秒。plan ファイルは削除 |
| 04:23:50 / 04:24:07 | `ContainerAppSystemLogs_CL` | 両 app で `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded`、`Revision '...' updated. No new revision was provisioned.`、`No revision restart or provisioning was needed.` のみ。`Failed` は 0 件 |
| 04:25 | revision と replica | serving `ca-felisaichatbot-dev--0000005` / frontend `ca-felisaichatbot-dev-front--0000004` のまま（新 revision なし）。replica の `createdTime` は 2026-09-28T08:53:00Z / 08:53:02Z（rollback の restart 時）のまま = replica の再作成もなし |
| 04:25 | 構成（`az containerapp show`） | 両 app の `chat-api-key` の `identity` が `/resourceGroups/` 表記に揃った |
| 04:25 | frontend `/readyz` 3 回 | すべて 200 |
| 事後 | `plan -detailed-exitcode`（ユーザー） | `No changes.`（exit 0） |

分かったこと: secret の `identity` だけが変わる in-place update は、Container Apps 側では新 revision も replica の再起動も伴わない
（platform のログに "No revision restart or provisioning was needed." と出る）。利用者影響なし。

### revision restart による Key Vault 参照の再取得確認（ops app のテスト用 secret。2026-10-01 実施）

目的: `az containerapp revision restart` が Key Vault 参照の secret を Key Vault の最新バージョンに取り直すかを本番構成で実測し、
ローテーション失敗時の復旧手順（restart を先にするか、Key Vault 参照の設定し直しを先にするか）を決める。
対象は ops app `ca-felisaichatbot-dev-ops`（利用者トラフィック無し）。テスト用 secret `kv-sync-alert-test` はアラート発火試験でも使う。

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 04:27:29 | Key Vault にテスト用 secret `kv-sync-alert-test` のバージョン 1 を作成（`openssl rand -hex 16`） | 作成 |
| 04:27:48 | ops app に Key Vault 参照で付与（`identityref:` は `registries[0].identity` から取得） | `keyVaultUrl` と `identity`（`/resourceGroups/` 表記）が付く。`SyncingSecret...Succeeded` 04:27:41 / 04:27:42 |
| 04:28:09 | env `KV_SYNC_ALERT_TEST=secretref:kv-sync-alert-test` を追加（`az containerapp update --set-env-vars`） | 新 revision `ca-felisaichatbot-dev-ops--0000002`、replica 04:28:06Z 作成、04:28:35 に `latestReadyRevisionName` が切り替わる。`SyncingSecret...Succeeded` 04:28:06（5 行）/ 04:28:36 |
| 04:28:58 〜 04:29:55 | 基準（sha256 先頭 12 桁。値は出さない） | (a) Key Vault 最新 = (b) platform `secret list --show-values` = (c) コンテナ内 env（`az containerapp exec --command env` の出力をローカルでハッシュ化）= `fbae6e9bd451`。直近の同期 04:28:36 |
| 04:30:12 → 04:30:13 | **バージョン 2 の作成時刻**: Key Vault にバージョン 2 を作成 | `list-versions` 2 件。(a) は `244405669b48` に変わる |
| 04:30:15 → 04:30:16 | **restart の実行時刻**: `az containerapp revision restart --revision ca-felisaichatbot-dev-ops--0000002` | `Restart succeeded`。新 replica 04:30:17Z 作成、04:30:35 に `Running`（旧 replica は 04:30:36 に `NotRunning`） |
| 04:31:14 | **再測定の時刻**: (b) と (c) を取り直す | (b) `fbae6e9bd451`、(c) `fbae6e9bd451`（新 replica `...-5846479f75-j5vzr` 内）。**どちらもバージョン 1 のまま** |
| 04:38:00 | 定期同期の割り込み確認（KQL: ops app の `SyncingSecret*` を 04:28:30Z 以降で検索。04:33:35 のログまで取り込み済み） | バージョン 2 の作成時刻 〜 再測定の時刻の間の `SyncingSecret*` は **0 件**（直近は 04:28:36）。判定は有効 |

判定: **`az containerapp revision restart` は Key Vault の値を取り直さない**。restart 後の replica には、platform が最後に同期した値（バージョン 1）がそのまま入る。
Microsoft Learn manage-secrets の記述（Key Vault 参照は "the app automatically retrieves the latest version within 30 minutes"（30 分以内に自動で最新バージョンを取得する）、
更新した secret の反映は "1. Deploy a new revision. 2. Restart an existing revision."（新 revision のデプロイか既存 revision の再起動））は platform が解決済みの値を
replica に配る話であり、Key Vault への再取得は定期同期（または Key Vault 参照の設定し直し）が担う、という理解と一致する。
ローテーション失敗時の復旧は計画どおり「原因の解消 → Key Vault 参照の設定し直し（`az containerapp secret set ... keyvaultref:...,identityref:...`。設定直後に同期が走る。rollback 節で実測）→ sha256 の一致確認 → 必要なら restart」の順とする。

補足: `az containerapp exec --command 'sh -c "..."'` は接続は成功するが出力が返らなかった（引用符の多重エスケープが原因とみられる）。
`--command env` は出力が返るので、その出力をローカルでパイプしてハッシュ化した（値は画面に出していない）。

### ローテーション試験（ADR-0032 決定 3 を本番構成で確認。2026-10-01 実施。Terraform はユーザーが実施）

同じ Key Vault secret `chat-api-key` を backend serving と frontend が環境変数で参照し、新バージョンの取り込みで両 app が再起動する構成の実測。
Key Vault 参照はバージョン無しなので ephemeral 層の apply は不要で、persistent 層の `chat_api_key_version` を +1 して apply するだけ。

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 04:38:29 | 基準（読み取り） | serving `--0000005`（replica 2026-09-28T08:53:00Z）/ frontend `--0000004`（replica 08:53:02Z）。Key Vault / serving / frontend の sha256 先頭 12 桁は 3 つとも `a934ba6b5413`。`list-versions` 1 件 |
| 04:38 | rollback 用の値（ローテーション前のバージョン）を作業端末の一時ファイル（mode 600、改行なし、64 バイト）へ | 6-9 の PASS まで保持 |
| 04:38:56 | 外形監視の停止 `gh variable set PROBE_ENABLED --body false` | `false` を確認 |
| 04:39:04 | persistent 層 `terraform.tfvars` に `chat_api_key_version = 2` を追記（編集前のコピーを `backup-before-chat-api-key-rotation-<UTC>.tfvars` に残す。いずれも gitignore 済み） | — |
| 04:4x | `terraform -chdir=terraform/persistent plan -detailed-exitcode -out=tfplan-pr2-rotation`（ユーザー） | exit 2、`Plan: 0 to add, 1 to change, 0 to destroy.`。差分は `azurerm_key_vault_secret.chat_api_key` の `value_wo_version: 1 -> 2`（`value_wo = (write-only attribute)`）のみ。他のリソースに差分なし |
| 04:42:59 → 04:43:02 | `apply tfplan-pr2-rotation`（ユーザー。**ローテーション apply の完了時刻 = 04:43:02**） | `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`（3 秒）。plan ファイルは削除 |
| 04:43:17 | 新バージョンの確認 | `list-versions` 2 件: 旧 `19ec93bf...`（2026-09-23 作成、enabled）/ 新 `c2eb05b4...`（04:43:03 作成、enabled）。Key Vault 最新の sha256 先頭 12 桁は `74919a81d6a3`。両 app の platform 側の値はまだ `a934ba6b5413`（旧） |

| 04:43:52 〜 05:06:35 | 取り込みの観測ループ（platform 側 sha256・replica を 35 秒間隔、frontend `/readyz` を 10 秒間隔） | `/readyz` 123 回すべて 200 |
| 04:57:42 | （参考）ops app のテスト用 secret `kv-sync-alert-test` の定期同期 | ops は 04:27:42 の付与から 30 分後に同期し、バージョン 2 を取り込んで `RevisionRestartWithNewSecrets`（replica 再作成）。手順 5 で restart が取り直さなかった値が、定期同期では取り込まれた |
| 05:03:45.87 | **両 app の取り込み（同一秒）**: `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` → `RevisionRestartWithNewSecrets`（serving `--0000005` / frontend `--0000004`。新 revision は作られない） | apply 完了（04:43:02）から **20 分 43 秒**。両 app の定期同期は 04:03:44 / 04:33:44 の 30 分周期で、次の周期 05:03:45 に乗った |
| 05:03:45 | 新 replica 作成（両 app とも `createdTime` 05:03:45Z） | 05:04:01 frontend `ContainerStarted`、05:04:05 serving `ContainerStarted`、05:04:12 両 app の旧 container `ManuallyStopped` |
| 05:04:19 | platform 側の値（sha256 先頭 12 桁） | serving / frontend とも `74919a81d6a3` = Key Vault 最新。6-1 の `a934ba6b5413` から変わった |
| 05:08:18 | 外形監視の再開 `gh variable set PROBE_ENABLED --body true` | `true` を確認。**欠測期間: 04:38:56Z 〜 05:08:18Z（約 29 分）**。再起動は 05:04:12 に終わっており、ブラウザ確認を待たずに戻した |
| 04:43〜05:08 | 両 app のコンソールログの `401` / `Unauthorized` | 0 件（`has "401"` に一致した 2 行はタイムスタンプ `.401` の誤検知） |

rotation 中に frontend と backend の `chat-api-key` が一致しない期間（ADR-0027 で混在窓と呼んでいる期間）: 両 app の同期と replica 作成は同一秒（05:03:45）で、
新 container の起動は frontend 05:04:01 / serving 05:04:05、旧 container の停止は両方 05:04:12。新旧の container が混在していた
**05:04:01 〜 05:04:12 の約 11 秒**が上限（2026-09-22 の sandbox 実測「同じ同期周期で同時再起動」と一致）。実トラフィックは無く、401 の実測は無い。

| 05:11:21 / 05:12:15 | 機能確認（ユーザーのブラウザ。Entra にサインイン → チャット） | PASS: backend の access log は `POST /chat` `200` が 2 件（1,592 ms / 364 ms）、frontend の `/api/chat` も `200`（SSE）。05:04〜05:13Z に両 app のログに `401` / `Unauthorized` は 0 件 |
| 05:13 | rollback 用の値ファイルを `shred -u` | 削除済み（ローテーション前のバージョンは Key Vault に残るが、参照されない） |

| 05:1x | `terraform -chdir=terraform/persistent plan -detailed-exitcode`（ユーザー） | `No changes.`（exit 0）。state の `azurerm_key_vault_secret.chat_api_key` の ID は新バージョン `c2eb05b4...` を指す。tfvars の `chat_api_key_version = 2` と一致 |

分かったこと（ADR-0032 決定 3 の確認）:

- ローテーションは persistent 層の apply 1 回（3 秒）で済み、ephemeral 層の apply は不要。取り込みは Container Apps の 30 分周期の定期同期に乗るため、
  apply 直後ではなく次の同期（今回は 20 分 43 秒後）に起きる。両 app は同じ周期で同一秒に同期・再起動した
- 再起動は replica の再作成で、新 revision は作られない（`RevisionRestartWithNewSecrets`）。`/readyz` は 10 秒間隔の観測で 503 なし
- rotation 中に frontend と backend の `chat-api-key` が一致しない期間は、新旧 container が混在した約 11 秒が上限。切替 apply のとき（約 16 秒）と同程度

### アラート発火試験（ops app のテスト用 secret を Key Vault 側で無効化。2026-10-01 実施）

log search alert `alert-kv-secret-sync-failed`（`ContainerAppSystemLogs_CL | where Reason_s == "SyncingSecretFromAzureKeyVaultForContainerAppFailed" | summarize FailedCount = count() by ContainerAppName_s`、
`FailedCount > 0`、評価 15 分ごと、ウィンドウ 1 時間、Sev2）が実際の同期失敗で発火することの確認。
対象は ops app のテスト用 secret `kv-sync-alert-test`（手順 5 で付与済み。`chat-api-key` と serving / frontend には触らない）。
復旧（再有効化）は発火・メール確認を待たずに行い、失敗ログが評価ウィンドウ 1 時間に残ることで発火と通知を観測する。

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 05:13 | 事前確認（読み取り） | テスト用 secret は 2 バージョンとも enabled。ops app の定期同期は 04:27:42 / 04:57:42 の 30 分周期（次は 05:27:42 の見込み）。Key Vault スコープのロール割り当ては 2 件（`Key Vault Secrets User` / `Key Vault Secrets Officer`）。復旧コマンド（再有効化、ロール割り当ての再作成 = 台帳 §B #15）を準備 |
| 05:14:09 | **無効化の時刻**: `az keyvault secret set-attributes --vault-name kv-felisaichatbot-dev -n kv-sync-alert-test --enabled false` | 無効化（`az keyvault secret show` は disabled の secret に対して失敗するので、`list-versions` の `attributes.enabled` で確認） |

| 05:27:42 | ops app の定期同期（無効化から 13 分 33 秒。04:27:42 起点の 30 分周期どおり） | **`SyncingSecretFromAzureKeyVaultForContainerAppFailed`** 1 件。本文: "Failed to sync secret 'kv-sync-alert-test' from Azure Key Vault '...' for ContainerApp 'ca-felisaichatbot-dev-ops'. The secret is in a disabled state in Azure Key Vault. Please enable the secret in Key Vault to resolve this issue. Retries: 1."（無効化された secret の同期に失敗。Key Vault で有効化すれば解消する）。serving / frontend の `chat-api-key` の同期には影響なし |
| 05:27:57 | 失敗ログの取り込み確認（30 秒間隔のポーリング） | 失敗の 15 秒後には KQL で見えた |
| 05:31:13 | **復旧の完了時刻**: 再有効化 `az keyvault secret set-attributes ... --enabled true` | 2 バージョンとも enabled。ロール剥奪は行っていないので Key Vault スコープのロール割り当ては 2 件のまま（再作成不要） |

ロール一時剥奪（代替案）は不要だった。無効化した secret は最初の定期同期で `Failed` になる（Microsoft Learn の Troubleshoot Key Vault references の
"Secret disabled in Key Vault" のとおり）。

| 05:36:52 | **発火**: `Microsoft.AlertsManagement/alerts` に `alert-kv-secret-sync-failed` が `monitorCondition: Fired`、`alertState: New`、Sev2、対象 `log-felisaichatbot-dev`（60 秒間隔のポーリングで 05:37:24 に確認） | 失敗ログ（05:27:42）から **9 分 10 秒**、無効化から 22 分 43 秒。復旧（05:31:13）の後に発火しており、「復旧を発火確認から切り離す」設計どおり |

| 05:55 | メール受信（ユーザーの Gmail で `azure-noreply` を検索） | **未着**（発火から 18 分）。詳細は下記「メール未着」 |
| 05:57:42 | ops app の次の定期同期（復旧から 26 分 29 秒） | `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded`。失敗は 05:27:42 の 1 件だけで収まった |

#### メール未着（読み取りのみで調査。2026-10-01 05:45〜05:58Z）

| 確認 | 結果 |
| --- | --- |
| ルール `alert-kv-secret-sync-failed` | `enabled: true`、`actions.actionGroups` に `ag-felisaichatbot-dev-email`、`autoMitigate: true`、`muteActionsDuration` なし |
| Action Group `ag-felisaichatbot-dev-email` | `enabled: true`、email receiver `opsmail` は `status: Enabled`、`useCommonAlertSchema: true`、宛先は設定あり。他の receiver なし |
| 発火した alert の `actionStatus` | `isSuppressed: false`（Alert Processing Rule による抑止なし） |
| rate limit | この subscription の過去 30 日の alert は 2 件（本件と 2026-09-19 の `alert-pgsql-cpu-credits-remaining-low`）。メール上限（1 宛先 100 通 / 時）に遠い |
| Activity Log | Action Group の通知送信は Activity Log に残らないため判定材料にならない |
| 受信実績 | 移行前の subscription では 2026-08-27〜09-23 の Fired / Resolved メールが届いている。**移行後の subscription では、09-19 の `alert-pgsql-cpu-credits-remaining-low` の Fired / Resolved も、Action Group 作成時の "You've been added to an Azure Monitor action group" も届いておらず、受信実績は 0 件** |
| `az monitor action-group test-notifications` | 旧 subscription で API が `Conflict` を返して実行できなかった（サブスクリプションの種類による制限。台帳 §B #10）ため実行していない |

**原因（2026-10-01 確定）: email receiver の宛先確認（OTP による verification）が未完了。** ユーザーの受信箱に 2026-09-19 06:53Z（Activity Log によれば現 subscription の `ag-felisaichatbot-dev-email` は Terraform apply で 06:53:08〜06:53:09Z に作成されており、その直後）、
`azure-noreply@microsoft.com` から "Action required: Verify your email for Azure Monitor action group" が届いていた。本文:
"Someone added your email address as a notification receiver in Azure Monitor - Action group(s). To receive these notifications, please verify your email address.
To verify, click the link below and enter the OTP code displayed. The code expires in 30 minutes."
（誰かがあなたのメールアドレスを Azure Monitor の Action group の通知先に追加した。通知を受け取るにはメールアドレスを確認する必要がある。リンクを開いて表示された OTP を入力する。コードは 30 分で失効する）。
この確認を行っておらず、OTP は失効していた。

Microsoft Learn [Create and manage action groups in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups)（Notification types の Email 行、2026-07-21 版）:
"Email addresses must be verified through a one-time passcode (OTP) within 30 minutes of saving the action group. This verification persists across all past and future action groups within the same tenant.
If the passcode expires, open the action group and select Resend. An unverified receiver can't receive alert or test notifications after enforcement is active."
（メールアドレスは Action Group の保存から 30 分以内に OTP で確認しなければならない。確認は同じディレクトリ（tenant）内の過去・将来のすべての Action Group に引き継がれる。
パスコードが失効したら Action Group を開いて Resend を選ぶ。未確認の受信者は、強制が有効になった後はアラート通知もテスト通知も受け取れない）。
同ページの作成手順の注記: "New email addresses receive a one-time passcode (OTP) validation request. Previously validated email addresses receive a standard notification email."
（新しいメールアドレスには OTP の確認要求が送られ、確認済みのアドレスには通常の通知メールが送られる）。

旧 subscription では 2026-08-27 に同じアドレスで受信できていたが、確認は同じディレクトリ内の Action Group にしか引き継がれないため、09-18 に別のディレクトリに作った Action Group では改めて確認が必要だった。
`az monitor action-group show` の `emailReceivers[].status` は確認の有無に関係なく `Enabled` で、確認状態は Azure CLI / REST（api-version 2023-01-01 / 2024-10-01-preview）には出ない。
Resend も Azure portal の Action Group 画面の操作のみで、CLI / REST には無い。

もう 1 つの食い違い: ユーザーはローカル環境変数ファイルの `TF_VAR_alert_email_address` を別のアドレスに変えていたが、`terraform/persistent/terraform.tfvars`
（gitignore 済み）に移行時（09-19）から `alert_email_address` が書かれており、tfvars は環境変数より優先されるため、環境変数の変更が plan に出ていなかった
（6-11 の `No changes` もこのため）。`variables.tf` の説明文「環境変数で渡す」と実態がずれていた。

対処（2026-10-01。ユーザーは OTP 確認メールが届いていた旧アドレスを使い続けるのではなく、環境変数側の新アドレスへ付け替える方を選んだ）:

| 時刻 (UTC) | 操作 | 結果 |
| --- | --- | --- |
| 06:06:48 | tfvars の直前コピーを `backup-before-alert-email-<UTC>.tfvars` に残し、`alert_email_address` の行を削除（環境変数に任せる） | tfvars は `entra_administrator_*` と `chat_api_key_version` のみ |
| 06:07 | `terraform -chdir=terraform/persistent plan -detailed-exitcode -out=tfplan-alert-email`（ユーザー） | exit 2、`0 to add, 1 to change`。差分は `azurerm_monitor_action_group.email` の `email_receiver.email_address` のみ |
| 06:07:56 → 06:08:00 | `apply tfplan-alert-email`（ユーザー） | `0 added, 1 changed`。plan ファイルは削除 |
| 06:08 | 読み取り確認 `az monitor action-group show` | receiver `opsmail` は `status: Enabled`、アドレスの sha256 先頭 12 桁が `16458216cf25` → `02406007e366` に変わった（ドメインは gmail.com のまま） |
| 06:08 | 新アドレスに "Action required: Verify your email for Azure Monitor action group" が届き、ユーザーが OTP を入力（15:08 JST） | 確認完了（apply から数分以内）。以後このアドレスへ通知が届くはず。最初の配送確認は本ルールの `Resolved` 通知 |
| 06:09 | 新アドレスに Action Group からの通知メール（"You've been added to an Azure Monitor action group" とみられる）が届く（15:09 JST） | **現 subscription の Action Group から配送されたメールの最初の実績**。アラート通知そのものの配送は本ルールの `Resolved` メールで確認する |

`variables.tf` の説明文と台帳 §B #10 に、tfvars に書かないこと・OTP 確認が要ることを追記した（本 PR に含める）。
本 PR の発火試験は「ルールが実際の同期失敗で `Fired` になる」までを PASS とし、メール到達は Action Group の宛先確認（Key Vault 参照とは独立）として記録する。
OTP 確認後の最初の配送確認は、本ルールの `Resolved` 通知（間に合えば）か、次に発火するアラートのメールで行う。

#### 後片付け（2026-10-01。自動解決の観測と並行して実施）

| 時刻 (UTC) | 操作 | 結果 |
| --- | --- | --- |
| 05:59:33 → 05:59:56 | ops app から env を外す `az containerapp update --remove-env-vars KV_SYNC_ALERT_TEST` | 新 revision `ca-felisaichatbot-dev-ops--0000003`（06:00:08 に ready）。env は手順 5 の前の 4 件に戻る |
| 06:00:29 → 06:00:42 | ops app から secret を外す `az containerapp secret remove --secret-names kv-sync-alert-test` | secret は `database-url` のみ。revision は `--0000003` のまま（secret の削除は新 revision を作らない） |
| 06:00:43 → 06:00:49 | Key Vault から削除 `az keyvault secret delete` → soft-delete 状態を確認 → `az keyvault secret purge` | Key Vault の secret は `chat-api-key` のみ。soft-delete 中の secret 0 件 |

env → secret の順を守った（secret を先に消すと env の `secretref` の参照先が無くなり更新が失敗する）。

| 06:0x | `terraform -chdir=terraform/ephemeral plan -detailed-exitcode`（ユーザー） | `No changes.`（exit 0）。ops app の管理外の env / secret は残っていない |

#### 自動解決の見込みの訂正

計画では「最後の `Failed` から約 1 時間〜1 時間 15 分で `Resolved`」としていたが、06:52Z を過ぎても `Fired` のままだった。
Microsoft Learn [Overview of Azure Monitor alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)（Stateful alerts、2026-07-08 版）の表:
"Log search alerts — The alert condition isn't met for a specific time range. The time range differs based on the frequency of the alert: 1 minute: The alert condition isn't met for 10 minutes.
5 to 15 minutes: The alert condition isn't met for three frequency periods. 15 minutes to 11 hours: The alert condition isn't met for two frequency periods."
（log search alert は、条件が満たされない状態が一定時間続いたときに解決される。評価頻度 1 分なら 10 分、5〜15 分なら 3 周期、15 分〜11 時間なら 2 周期）。
本ルールは評価 15 分・ウィンドウ 1 時間なので、`Failed`（05:27:42）がウィンドウから外れて初めて条件不成立になる評価（06:36:52 頃）の後、さらに 2〜3 周期（30〜45 分）必要で、
**`Resolved` の見込みは 07:07〜07:22Z**（最後の `Failed` から約 1 時間 40 分〜1 時間 55 分 = ウィンドウ 1 時間 + 評価位相 + 2〜3 周期）。

| 時刻 (UTC) | 事象 | 結果 |
| --- | --- | --- |
| 07:07:51 | **自動解決**: `monitorCondition: Resolved`（`monitorConditionResolvedDateTime` 07:07:51.87Z。60 秒間隔のポーリングで 07:08:52 に確認） | 最後の `Failed`（05:27:42）から **1 時間 40 分 9 秒**、`Fired`（05:36:52）から 1 時間 31 分。訂正後の見込み（07:07〜07:22Z）の範囲内。評価位相 05:36:52 + 15 分 × n の 07:06:52 の評価で条件不成立 2 周期目となり解決 |
| 〜07:45 | Resolved 通知メール（新アドレス） | **未着**。受信箱の最後のメールは 06:08Z の "You've been added to an Azure Monitor action group" |

Resolved メールが届かなかった理由: Microsoft Learn [alerts-overview](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview) は
"Fired alert instances in Azure Monitor are read-only and cannot be edited. Configuration changes apply only to future alerts."
（発火済みの alert インスタンスは読み取り専用で編集できない。設定変更は以後の alert にだけ適用される）としており、
05:36:52 に発火した alert は受信者が OTP 未確認だった時点の構成で処理される。06:08 のアドレス付け替えと OTP 確認は以後の alert にしか効かないため、
この alert では Fired / Resolved いずれの通知も到達を実証できない。そこで発火試験を同じ手順でもう 1 回行う（下記）。

#### 発火試験 2 回目（受信者の OTP 確認後。アラート通知メールの到達確認）

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 07:50:17 | テスト用 secret `kv-sync-alert-test` を再作成（1 回目は purge 済み） | 作成 |
| 07:50:37 | ops app に Key Vault 参照で付与（`identityref:` は `registries[0].identity`） | 付与 |
| 07:50:50 | env `KV_SYNC_ALERT_TEST=secretref:kv-sync-alert-test` を追加 | 新 revision `ca-felisaichatbot-dev-ops--0000004`（07:51:10 に ready） |
| 07:51:21 | **無効化の時刻**: `--enabled false` | 無効化 |

| 07:57:42 | ops app の定期同期 | **`SyncingSecretFromAzureKeyVaultForContainerAppFailed`**（Retries: 1）。**同期の周期は 1 回目の付与（04:27:42）起点の :27:42 / :57:42 のままで、secret の外し・付け直しや revision の更新では位相が変わらなかった**（07:50 の付与直後に即時同期は走るが、定期同期の位相は変わらない）。「07:50:37 起点で 08:20:37 頃」という見込みは誤り |
| 08:06:49 | **発火**: `alert-kv-secret-sync-failed` の新しい alert インスタンスが `Fired`（`startDateTime` 08:06:49.89Z） | 失敗ログから 9 分 7 秒（1 回目は 9 分 10 秒）。受信者の OTP 確認（06:08）より後に発火した alert なので、通知メールはこの alert で初めて実証できる |
| 08:27:42 | ops app の定期同期（再有効化前） | `...Failed`（Retries: 2）。監視スクリプトが `Failed` の検知に失敗しており（KQL 結果の判定ミス）、再有効化が遅れた。影響は ops app のテスト用 secret のみ |
| 08:30:01 | **復旧の完了時刻**: 再有効化 `--enabled true`（手動） | `enabled: true` |

| 09:02:06 → 09:02:58 | 後片付け: env を外す（新 revision `ca-felisaichatbot-dev-ops--0000005`、09:02:41 ready）→ secret を外す | ops app は `database-url` のみ、env は手順 5 の前の 4 件 |
| 09:02:59 → 09:03:01 | Key Vault から削除 → purge | Key Vault の secret は `chat-api-key` のみ、soft-delete 中 0 件 |

| 09:0x | `terraform -chdir=terraform/ephemeral plan -detailed-exitcode`（ユーザー） | `No changes.`（exit 0） |
| 〜09:3x | Fired 通知メール（新アドレス。08:06:49 の発火分） | **未着**（ユーザーの受信箱の確認。`azure-noreply` の検索） |
| 10:07:52 | 自動解決: 2 件目の alert が `Resolved`（最後の `Failed` 08:27:42 から 1 時間 40 分 10 秒。1 回目と同じ） | alert の history（`Microsoft.AlertsManagement/alerts/{id}/history`）には 08:06:50.82 と 10:07:52.82 に `ActionsTriggered` "Action group ag-felisaichatbot-dev-email executed (Configured on alert rule)"（Action Group `ag-felisaichatbot-dev-email` を実行した）が記録されている = **Azure Monitor 側は Fired / Resolved の両方で Action Group を実行済み** |

Fired メールが届かない件の読み取り確認（2026-10-01 09:3x〜10:1x）: alert インスタンス `3401ddee-...` の `actionStatus.isSuppressed: false`、`monitorService: Log Alerts V2`、
dimension `ContainerAppName_s = ca-felisaichatbot-dev-ops`、`metricValue 1`。ルールの `actions.actionGroups` は `.../Microsoft.Insights/actionGroups/ag-felisaichatbot-dev-email`、
Action Group の `id` は `.../microsoft.insights/actionGroups/...`（provider 名の大文字小文字が違うだけ。ARM の resource ID は大文字小文字を区別しない）。
receiver `opsmail` は `status: Enabled`、アドレスの sha256 先頭 12 桁 `02406007e366`（OTP 確認済みのアドレス）。rate limit（1 宛先 100 通 / 時）に遠い。
Action Group の実行は history に残るが、メールの配送結果（受理 / 拒否 / 遅延）は API に出ない。

2026-10-02 02:52Z（11:52 JST）、ユーザーが Azure portal の Action Group `ag-felisaichatbot-dev-email` の「通知」欄を確認: receiver `opsmail`（電子メール、新アドレス）の
「メール アドレスの確認」は **「確認済み」**。**OTP 未確認が原因という線は消えた**（確認状態はポータルにだけ表示され、CLI / REST には出ない）。
ポータルには Action Group の「テスト」ボタンがある（旧 subscription では API が `Conflict` を返して実行できなかった。現 subscription での可否は未確認）。

残る可能性: Action Group のメール送信から受信箱までの区間（送信元 3 アドレスのいずれかが Gmail 側で拒否されている、など）。ユーザーの Gmail 検索は迷惑メール・プロモーション・
すべてのメールを含めても 2 回目の Fired メールを見つけられなかった（2026-10-01）。公式ドキュメント上は "Emails are sent from the following email addresses:"（通知メールは次のアドレスから送られる）として
`azure-noreply@microsoft.com` / `azureemail-noreply@microsoft.com` / `alerts-noreply@mail.windowsazure.com` の 3 つを挙げている。
2026-10-02 02:54Z（11:54 JST）、ユーザーが Azure portal の Action Group の「テスト」を実行（通知の種類 = 電子メール、通知名 = `opsmail`）: **失敗**。
表示は「このテストの完了で問題が発生しました。数分後にもう一度お試しください。」、状態は「不明」。旧 subscription では同じ機能の API
`actionGroups/createNotifications` が `Conflict` を返して実行できなかった（サブスクリプションの種類による制限。台帳 §B #10）。
Activity Log（subscription スコープ）に 02:54:30Z と 02:57:41Z の 2 回、`Microsoft.Insights/actiongroups/createNotifications/action` が
`status: Failed` / `subStatus: Conflict` で記録されており、**旧 subscription と同じ原因（テスト通知は本サブスクリプションでは実行できない）と確定**。
ポータルの「テスト」も内部で同じ API を呼ぶ。
テスト通知の失敗は Action Group の実通知の可否とは別で、Fired メールが届かない原因の説明にはならない。

#### 発火試験の判定（2026-10-02 確定）

| 区分 | 内容 |
| --- | --- |
| **PASS** | ルールが実際の同期失敗で `Fired`（2 回、失敗ログから約 9 分）、公式の解決条件どおり自動 `Resolved`（2 回、最後の失敗から約 1 時間 40 分）、Azure Monitor による Action Group の実行（alert の history に `ActionsTriggered` 4 件）、ルール・Action Group・receiver（OTP 確認済み）の設定 |
| **未確認** | アラートのメール（Fired / Resolved）が受信箱に届くこと。2 回の発火・4 回の Action Group 実行で 0 通。テスト通知は API が `Conflict` を返して実行できない（サブスクリプションの種類による制限）ため、ポータルの「テスト」でも切り分けできない |
| **別 Issue** | 「Action Group `ag-felisaichatbot-dev-email` からアラートのメールが届かない」。PR 2 のマージ後、PR 3（Easy Auth secret の Key Vault 参照化）より前に着手する |

Codex による読み取りのみの調査（2026-10-02）の要点: 原因は不明。候補は (1) Azure 側のメール配送障害 (2) Gmail 側の拒否（bounce は送信側にしか見えない）
(3) OTP の確認状態の反映の不整合（ポータルは「確認済み」だが、送信経路の判定が追随していない可能性）。通常の通知の配送結果を見る公開 API は無い
（`notificationStatus` はテスト通知専用）。推奨される次の一手は、検証用のルールを 1 本作り、通常のメール receiver・Email Azure Resource Manager role（OTP 確認が不要）・
Azure mobile app の push の 3 経路を同時に比べる試験。これを別 Issue の最初の作業にする。

分かったこと（発火試験全体）:

- 無効化した Key Vault secret は次の定期同期で `Failed` になり、log search alert は失敗ログから約 9 分で `Fired`、条件不成立が続くと公式の解決条件（15 分評価では 2 周期）どおり約 1 時間 40 分で `Resolved` になる。
  復旧（再有効化）は発火を待たずに行ってよく、発火・解決の観測には影響しない
- 定期同期の位相は app ごとに固定され（ops は :27:42 / :57:42、serving / frontend は :03:4x / :33:4x）、secret の付け直しや revision の更新では変わらない。
  試験の時刻計画はこの位相から立てる
- Action Group の email receiver は OTP 確認が済むまで通知を受け取れず、確認前に発火した alert は確認後も通知されない（設定変更は以後の alert にだけ適用）。
  受信者を変えたら、必ずその後に発火する alert で到達を確認する

## PR 3: Easy Auth のクライアントシークレットを Key Vault 参照に切り替える（2026-10-03 実施）

対象: frontend `ca-felisaichatbot-dev-front` の secret `microsoft-provider-authentication-secret`（authConfigs の `clientSecretSettingName` が参照）。
値方式（`value = var.easy_auth_client_secret`。tfvars と state に平文）から、Key Vault `kv-felisaichatbot-dev` の secret `easy-auth-client-secret` への
バージョン無しの Key Vault 参照（`key_vault_secret_id` + `identity`）に切り替えた。これで ADR-0031 が「state に残る」とした秘密値 2 つが両方 state から消えた。

ユーザー判断（計画時）: PR 2 のマージ後に着手 / クライアントシークレットは**新しく発行**し、発行コマンドの出力を `az keyvault secret set` へ直接パイプして人も Claude Code も値を見ない
（既存値を tfvars から移すと値をもう一度扱うことになり、過去の state バージョンの値も有効なまま残る）/ rollback の演習と本番でのローテーション追従試験は省略
（Key Vault 参照 → 直接値 → Key Vault 参照の往復は PR 2 で、Easy Auth sidecar のローテーション追従は Issue #287 の検証環境で実測済み。本 PR の切替自体が
「app に存在しなかった新しい値が Key Vault 参照経由で sidecar に届く」実測になる）/ Key Vault の secret 名は `easy-auth-client-secret`。

### 変更内容（ephemeral 層）

- 変数 `easy_auth_client_secret` を削除。`local.easy_auth_client_secret_id` と `data "azurerm_key_vault_secrets" "main"`（secret の名前一覧だけを読む。値は読まない）を追加。
  frontend の `secret "microsoft-provider-authentication-secret"` を `key_vault_secret_id` + `identity`（`id-felisaichatbot-dev`）に変更。
  frontend の precondition を `var.easy_auth_client_id != "" && contains(data.azurerm_key_vault_secrets.main.names, "easy-auth-client-secret")` に置き換え（ADR-0027 決定 6 の fail-closed を維持）
- `terraform fmt -check` / `validate`（別 `TF_DATA_DIR`、`init -backend=false`）PASS

### 事前確認（2026-10-03。すべて読み取り）

| 確認 | 結果 |
| --- | --- |
| main | `c86c972`（PR 2 = #298 マージ済み、#299 の Action Group 作り直しも反映済み） |
| frontend の secret | `microsoft-provider-authentication-secret` は値方式（`keyVaultUrl` 無し）、`chat-api-key` は Key Vault 参照。revision `ca-felisaichatbot-dev-front--0000004`、replica 2026-10-01T05:03:45Z 作成 |
| ops app | secret は `database-url` のみ（PR 2 の発火試験のテスト用 secret は残っていない） |
| Key Vault | secret は `chat-api-key` のみ。soft-delete 中 0 件。Key Vault スコープのロール割当は `Key Vault Secrets User` / `Key Vault Secrets Officer` の 2 件 |
| Entra の資格情報 | `easyauth` 1 本（2026-09-19 発行 / 2027-09-19 失効） |
| `az containerapp secret set` の制約 | `--help` に "'key' cannot be longer than 20 characters"（key は 20 文字まで）。`microsoft-provider-authentication-secret` は 40 文字なので、この secret を CLI で直接値に戻すことはできない（rollback は ARM への PATCH = entra-easy-auth-setup.md §8） |
| Easy Auth sidecar のコンテナ名 | `ContainerAppConsoleLogs_CL` の `ContainerName_s` は `front` と `http-auth`（検証環境と同じ） |
| `PROBE_ENABLED` | `true` |

### 新しいクライアントシークレットの発行と Key Vault への投入（2026-10-03。ユーザーが実施）

```bash
az ad app credential reset --id "$APP_ID" --append --display-name "easyauth-202610" --years 1 --query password -o tsv \
  | tr -d '\n' | az keyvault secret set --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret --file /dev/stdin --output none
```

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 06:21:24 → 06:21:25 | 上記のパイプ（`umask 077`） | 終了コード 0。az CLI の警告 "The output includes credentials that you must protect" は出るが、値はパイプに流れるだけで画面には出ない。`--file /dev/stdin` はそのまま通った |
| 06:21:3x | 確認（読み取り。値は出さない） | Entra の資格情報 2 本（新 `easyauth-202610` 06:21:25Z 〜 2027-10-03、旧 `easyauth`）。Key Vault `easy-auth-client-secret` は `enabled: true`、06:21:26Z 作成、バージョン 1 件。値は長さ 40（検証環境の実測と同じ）、改行 0、空白 0。sha256 先頭 12 桁 `4887212dea68` |

この時点ではどの app もこの secret を参照しておらず、frontend は旧値で稼働。

### plan と apply（2026-10-03。Terraform はユーザーが実施）

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 06:2x | `terraform -chdir=terraform/ephemeral init` → `plan -detailed-exitcode -out=tfplan-pr3-cutover` | exit 2、`Plan: 0 to add, 1 to change, 0 to destroy.`。差分は `azurerm_container_app.front[0]` の `secret` ブロックのみ（set 型 + sensitive のため「- 2 / + 2」表示）。`azapi_resource.front_auth[0]` / `main` / Job / ops に差分なし。警告は tfvars に残る `easy_auth_client_secret` の "Value for undeclared variable" 1 件 |
| 事前 | plan の `show -json` を name ごとに比較（値は sha256 先頭 12 桁と長さのみ） | 変わるのは `microsoft-provider-authentication-secret` のみ: before = 値方式（長さ 40、sha256 先頭 `e04bb91eba1a` = 稼働中の platform 側の値と一致）→ after = `keyVaultUrl .../secrets/easy-auth-client-secret` + identity（`/resourceGroups/` 表記）、`value` 無し。`chat-api-key` は before / after 同一。template 同一 |
| 06:28:53 | 外形監視の停止 `gh variable set PROBE_ENABLED --body false` | `false` |
| 06:30:20 → 06:30:48 | `apply tfplan-pr3-cutover`（`azurerm_container_app.front[0]` 17 秒）→ plan ファイル削除 | `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` |
| 06:30:31 〜 06:30:33 | Key Vault `AuditEvent`（`AzureDiagnostics`） | `SecretGet` `easy-auth-client-secret` が identity `id-felisaichatbot-dev` の client ID から `Success` 5 件 |
| 06:30:33 / 06:30:34 | `ContainerAppSystemLogs_CL` | `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` 2 行、`Revision '...--0000004' updated. No new revision was provisioned.`、`No revision restart or provisioning was needed.`。`Failed` 0 件 |
| 06:30:32 → 06:30:57 | replica | **再作成された**: 新 replica `...-6799d9bb89-652sb` 06:30:32Z 作成（`AssigningReplica` 06:30:33、image pull 06:30:47、`ContainerStarted` 06:30:48）、旧 replica（10-01 作成）の container は 06:30:57 に `ManuallyStopped`。revision は `--0000004` のまま。platform のログは "No revision restart or provisioning was needed." だが、secret の値が変わったため replica は差し替わっている（PR 2 の 4-12 = identity の表記だけの変更では replica は変わらなかった）。`RevisionRestartWithNewSecrets` の行は出ない（ローテーション時とは別の経路） |
| 06:31 | 構成（`az containerapp show`） | PASS: `microsoft-provider-authentication-secret` = `keyVaultUrl` + identity（`/resourceGroups/` 表記）、`value` 無し。`chat-api-key` 不変。authConfigs の `clientSecretSettingName` 不変 |
| 06:31 | frontend `/readyz` 5 秒間隔 6 回 | すべて 200（新 replica の `ContainerStarted` 06:30:48 以降。再起動中の低下は秒粒度では測っていない = ADR-0023） |
| 06:31 | 値の一致（sha256 先頭 12 桁） | platform 側の `microsoft-provider-authentication-secret` = `4887212dea68` = Key Vault の新値（旧 `e04bb91eba1a` から変わった）。`chat-api-key` は `74919a81d6a3` で不変 |
| 06:32:56 / 06:33:18 / 06:34:10 | **サインイン確認（ユーザーのブラウザ。シークレットウィンドウ = 既存の cookie 無し）** | sidecar `http-auth` のログ: `/.auth/login/aad/callback` POST → token POST `Completed with 200` → `LoginComplete`（ClientId = Easy Auth の app registration）が 3 回。`AADSTS7000215` 0 件。**app のどこにも無かった新しい値が Key Vault 参照経由で sidecar に届き、認可コードの交換に使われた** |
| 06:34:24 / 06:34:25 | チャット 1 往復（ユーザーのブラウザ） | backend `POST /chat` 200（1,151 ms）、frontend `POST /api/chat` 200（SSE、3,503 ms）。401 / Unauthorized 0 件。chat API キーの経路は壊れていない |
| 06:35:30 | 外形監視の再開 `PROBE_ENABLED=true` | **欠測期間: 06:28:53Z 〜 06:35:30Z（約 6 分 37 秒）** |
| 06:3x | `terraform -chdir=terraform/persistent plan -detailed-exitcode`（ユーザー） | `No changes.`（exit 0）。PR 3 は persistent 層を変更しない |

### 旧資格情報の削除（切替の確定。2026-10-03）

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 06:35:31 | `az ad app credential delete --id "$APP_ID" --key-id <旧 easyauth の keyId>` | 削除。`credential list` は `easyauth-202610` 1 本のみ。**過去の tfstate バージョンに残る旧値はこの時点で無効になった** |
| 06:38:45 | **削除後のサインイン確認（ユーザーのブラウザ。新しいシークレットウィンドウ）** | sidecar: token POST `Completed with 200`、`LoginComplete`。`AADSTS7000215` 0 件 |
| 06:38:59 / 06:39:05 | チャット 1 往復 | backend `POST /chat` 200、frontend `POST /api/chat` 200 |

### tfvars からの除去と plan 収束（2026-10-03。ユーザーが実施）

| 時刻 (UTC) | 操作 / 確認 | 結果 |
| --- | --- | --- |
| 06:40:19 | `terraform/ephemeral/terraform.tfvars` のバックアップ（`umask 077`、gitignore 済み）を取り、`easy_auth_client_secret` の行を削除 | tfvars に `easy_auth_client_secret` 0 行、`easy_auth_client_id` 1 行。環境変数 `TF_VAR_easy_auth_client_secret` は無い |
| 06:4x | `terraform -chdir=terraform/ephemeral plan -detailed-exitcode` | `No changes.`（exit 0）。undeclared variable の警告も消えた |
| 06:4x | バックアップを `shred -u`（中身は読まない） | 残り 0 件。値は旧資格情報のもので 06:35:31 以降は使えないが、ローカルにも残さない |

### 分かったこと（PR 3）

- 値方式 → Key Vault 参照の切替 apply は、secret の**値が変わる**ため replica が差し替わる（`AssigningReplica` → 新 replica → 旧 container `ManuallyStopped`。約 25 秒）。
  platform のログは "No revision restart or provisioning was needed." で、ローテーション時の `RevisionRestartWithNewSecrets` も出ない。identity の表記だけが変わる in-place update（PR 2）では replica は変わらなかった。
  **secret の値が変わる apply は、ログの文言に関わらず再起動を伴う前提で外形監視を止める**
- Easy Auth の client secret の正しい確認は「既存のセッション cookie が無い状態で `/.auth/login/aad/callback` を通し、sidecar の token POST が 200」で、
  サインイン済みのタブを再読み込みしても client secret は使われない。`/.auth/me` は使えない（Container Apps では 404。Issue #287 の実測）
- `az ad app credential reset ... -o tsv | tr -d '\n' | az keyvault secret set --file /dev/stdin` のパイプで、値を画面・ファイル・履歴・Terraform に通さずに投入できる（長さ 40、改行無しで保存された）
- `az containerapp secret set` の key は 20 文字まで（`--help` の記載）。Easy Auth の既定名 `microsoft-provider-authentication-secret`（40 文字）はこの CLI で直接値に戻せず、
  戻し方は ARM への PATCH になる（手順書 §8。未検証）
- 切替 apply の `/readyz` 欠測は約 6 分 37 秒（作業自体は apply 28 秒 + 確認）。ADR-0031 が「state に残る」とした秘密値 2 つは 2026-10-03 をもって両方 state から消え、
  過去の state バージョンの値は chat API キーのローテーション（10-01）と Easy Auth の旧資格情報の削除（10-03）で無効になった

## 最新 state の再照合（2026-10-04。すべて読み取り）

目的: PR 3 の切替（10-03）後、両方の層の最新 raw state に、対象の秘密値 2 つ（chat API キー、Easy Auth のクライアントシークレット）の現在値が保存されていないことを確かめる。
PR 3 では state の照合をしていなかった（PR 1 の確認と PR 2 の 2026-09-28 07:47 の確認は chat API キーのみ）。過去の state バージョン（blob のバージョン履歴）は対象外で、読みに行っていない。

実施は Claude Code。`terraform state pull` と `terraform workspace show` / `list`、`az keyvault secret show` だけを使い、state・Azure リソース・Key Vault・Entra の資格情報は変更していない。
state と秘密値は Python のプロセス内（メモリ上）だけで扱い、画面・ファイルには出していない。出力は一致の有無（true / false）、属性名、型、長さ、null かどうかだけ。

### 対象の特定

| 確認 | 結果 |
| --- | --- |
| working directory | `terraform/persistent`（Key Vault 側。`azurerm_key_vault_secret.chat_api_key`）と `terraform/ephemeral`（アプリ側。Container Apps と `azapi_resource.front_auth`） |
| backend | どちらも azurerm backend、Storage Account `felisaichatbottfstate02` / container `tfstate`。key は `persistent/terraform.tfstate` と `ephemeral/terraform.tfstate`。`.terraform/terraform.tfstate` の backend 設定も同じ |
| workspace | どちらも `terraform workspace list` は `default` のみ（現在も `default`） |
| state 上の名前 | Key Vault `kv-felisaichatbot-dev`、Container App `ca-felisaichatbot-dev` / `ca-felisaichatbot-dev-front` / `ca-felisaichatbot-dev-ops`、resource group `rg-felisaichatbot-dev-tf` |
| state の基本情報 | persistent: serial 16、resources 21。ephemeral: serial 16、resources 17。どちらも `terraform_version` 1.14.8 |
| 比較に使った現在値 | `chat-api-key`: 長さ 64、enabled、バージョン `c2eb05b4...`（10-01 のローテーションで作成）。`easy-auth-client-secret`: 長さ 40、enabled、バージョン `ae8d1b65...`（10-03 06:21:26Z 作成） |

### 現在値との照合（値は表示しない）

両方の層の raw state 全体で、現在値が次のどの形でも見つからないことを確かめた。

- そのままの形
- JSON エスケープした形
- base64 化した形（属性の文字列値の中を検索）
- 各 instance の `private`（provider の private data）を base64 デコードした中身

| 秘密値 | persistent の state | ephemeral の state |
| --- | --- | --- |
| chat API キー（`chat-api-key` の現在値） | PASS: 一致なし | PASS: 一致なし |
| Easy Auth のクライアントシークレット（`easy-auth-client-secret` の現在値） | PASS: 一致なし | PASS: 一致なし |

### 対象 resource の state 構造

| 確認 | 結果 |
| --- | --- |
| `azurerm_key_vault_secret.chat_api_key` | PASS: `value` は長さ 0、`value_wo` は null、`value_wo_version` は number。`sensitive_attributes` は `value` |
| `random_password` / `random_string` の resource | PASS: 両方の state で 0 件（ephemeral resource は state に入らない） |
| `data.azurerm_key_vault_secret`（値を読む data source） | PASS: 両方の state で 0 件。ephemeral 層にあるのは名前一覧だけを読む `data.azurerm_key_vault_secrets.main` |
| `azurerm_container_app.front` の secret | PASS: `chat-api-key` は `value` が null、`microsoft-provider-authentication-secret` は `value` が長さ 0。どちらも `key_vault_secret_id`（バージョン無し）と `identity` あり。env `CHAT_API_KEY` は `secret_name` 参照 |
| `azurerm_container_app.main` の secret | PASS: `chat-api-key` は `value` が長さ 0、`key_vault_secret_id`（バージョン無し）と `identity` あり。env `CHAT_API_KEY` は `secret_name` 参照 |
| `azapi_resource.front_auth`（authConfigs） | PASS: `body` にあるのは `clientSecretSettingName`（secret の名前）だけで、クライアントシークレットの値の属性は無い。`output` は `id` / `type` / `globalValidation.excludedPaths` のみ、`sensitive_body` は null |

### 判定

**PASS（対象は chat API キーと Easy Auth のクライアントシークレットの 2 つだけ）**: この 2 つの現在値は、両方の層の最新 raw state に保存されていない。
対象 resource の state 構造でも、この 2 つの値を持つ属性（`value` / `value_wo`、Container Apps の secret の `value`）は空か null だった。

この PASS は「felis-ai-chatbot のすべての秘密値が state から消えた」という意味ではない。対象外の秘密値は次の節のとおり state に残っている。

### 検証対象外で確認した事項

最新 raw state を確認する過程で、今回の対象 2 つ以外に、秘密値になりうる属性に値が入っていることを確認した（値は表示していない。記録は属性名と長さだけ）。
これらは Issue #286 の移行対象でも、上の PASS 判定の対象でもない。今回の検証では state から除去する対応はしておらず、Terraform・Azure 側とも変更していない。将来の確認・改善の候補として記録する。

| state に値が残っているもの | 層 | 状態 |
| --- | --- | --- |
| `azurerm_log_analytics_workspace.main` の `primary_shared_key` / `secondary_shared_key` | persistent（resource）と ephemeral（data source） | 文字列（長さ 88） |
| secret `database-url`（serving `ca-felisaichatbot-dev`、ops `ca-felisaichatbot-dev-ops`、Container Apps Job 4 件） | ephemeral | 値方式の文字列（長さ 120）。Key Vault 参照ではない |

### 残った未検証事項

- 過去の state バージョンの内容は対象外（切替前の値が残っていることは PR 1 の事前確認のとおり。値は 10-01 のローテーションと 10-03 の旧資格情報の削除で無効化済み）
- 照合に使ったのは Key Vault の現在値だけで、`chat-api-key` の旧バージョン（`19ec93bf...`）などの過去の値との照合はしていない（構造の確認で、対象 resource の値の属性が空か null であることは確かめた）
