# VNet 統合カットオーバーの実測記録

[vnet-integration-cutover.md](../../operations/vnet-integration-cutover.md)（手順の正本）の実行記録。
設計判断は [ADR-0018](../../adr/0018-postgresql-private-access-and-vnet-integration.md) /
[ADR-0019](../../adr/0019-enable-geo-redundant-backup.md)。時刻はすべて UTC。
ステップごとに記録を積む（本ファイルが cutover 全体の記録置き場。途中で作業が中断しても
次のセッションがここから状態を読めるようにする）。

## ステップ A: persistent 層の apply（2026-08-22 実施。完了）

### 結果サマリ

- **B1ms × private access は作成できた**（ADR-0018 の未確定事項の決着。エラーなしで
  `B_Standard_B1ms` のサーバーが delegated subnet + private DNS zone 構成で作成完了。
  GP への切り分け・firewall 方式への巻き戻しは不要になった）
- apply は **7 added / 0 changed / 3 destroyed** で成功。エラーなし
- 新サーバーは state Ready / `publicNetworkAccess: Disabled` / `geoRedundantBackup: Enabled`

### 前提（apply 前の状態）

- main = `ebf8e40`。リソースプロバイダー登録（§0-1）は実施済み
  （`Microsoft.Network` / `Microsoft.ContainerService` とも Registered）
- ephemeral 層は destroy 済み。Azure 残存は `pgsql-felisaichatbot-dev`（public access のまま稼働）/
  `id-felisaichatbot-dev` / `log-felisaichatbot-dev` の 3 件
- 旧サーバーはテーブル 0 件・バックアップ Full 1 件のみ（旧 `earliestRestoreDate`:
  2026-08-21T05:59:00Z）。データ引き継ぎなしの再作成前提を満たす
- `terraform.tfvars` から削除済み変数 `firewall_allowed_client_ips` の行を除去（§0）

### plan の差分要約（apply 前）

**Plan: 7 to add, 0 to change, 3 to destroy**（期待どおり。期待外の差分なし）

| 種別 | リソース | 備考 |
| --- | --- | --- |
| replace | `azurerm_postgresql_flexible_server.main` | ForceNew: `delegated_subnet_id`（+ `private_dns_zone_id` / `public_network_access_enabled`）と `geo_redundant_backup_enabled: false -> true`（ADR-0019） |
| replace | `azurerm_postgresql_flexible_server_configuration.azure_extensions` | `server_id` 追随の随伴 replace |
| add | VNet / subnet aca / subnet pgsql / private DNS zone / VNet link | ADR-0018 のネットワーク一式 |
| destroy | `azurerm_postgresql_flexible_server_firewall_rule.client["allow-workstation"]` | firewall 方式の撤去 |

Log Analytics workspace は無変更。

### タイムライン（2026-08-22）

| 時刻 (UTC) | 操作 | 結果 / 所要 |
| --- | --- | --- |
| 07:06:54 | `terraform apply`（保存済み plan で実行） | 開始 |
| 07:07 | firewall rule destroy / `azure.extensions` destroy | 16s / 27s |
| 07:08 | 旧サーバー destroy | **1m04s** |
| 07:09 | VNet / subnet aca / subnet pgsql | 9s / 6s / 10s |
| 07:09 | private DNS zone / VNet link | 34s / 34s |
| 07:10〜 | 新サーバー create（B1ms × private access） | **6m28s**（エラーなし） |
| 07:16 | `azure.extensions` create（VECTOR,PGSTATTUPLE） | 12s |
| 07:16 | **Apply complete! 7 added, 0 changed, 3 destroyed** | 全体 約 9.5 分 |

### 設計値と実測の対照（`az postgres flexible-server show`。2026-08-22 実測）

| 項目 | 設計値（計画書 §3-1 / ADR-0018 / ADR-0019） | 実測 | 一致 |
| --- | --- | --- | --- |
| state | Ready | `Ready` | ✅ |
| SKU | `B_Standard_B1ms`（Burstable） | `Standard_B1ms` / tier `Burstable` | ✅ |
| ストレージ | 32 GiB | `storageSizeGb: 32` | ✅ |
| バージョン | 17 | `17` | ✅ |
| `network.delegatedSubnetResourceId` | `snet-felisaichatbot-dev-pgsql` | `.../virtualNetworks/vnet-felisaichatbot-dev/subnets/snet-felisaichatbot-dev-pgsql` | ✅ |
| `network.privateDnsZoneArmResourceId` | `felisaichatbot-dev.private.postgres.database.azure.com` | 同名 zone の ID | ✅ |
| `network.publicNetworkAccess` | **Disabled** | `Disabled` | ✅ |
| `backup.geoRedundantBackup` | **Enabled**（ADR-0019） | `Enabled` | ✅ |
| 保持日数 | 7 | `7` | ✅ |
| `earliestRestoreDate` | （新サーバーで新規に始まる） | `2026-08-22T07:16:21Z` | ✅（バックアップチェーンが再スタート） |
| メンテナンスウィンドウ | カスタム: 水 17:00 UTC | `customWindow: Enabled, dayOfWeek: 3, 17:00` | ✅ |
| HA | 無効（Day 5 に有効化） | `Disabled` | ✅ |

### ネットワークの実測（`az network vnet show` / `subnet list`）

| リソース | CIDR | 委任 |
| --- | --- | --- |
| `vnet-felisaichatbot-dev` | `10.10.0.0/24` | — |
| `snet-felisaichatbot-dev-aca` | `10.10.0.0/26` | `Microsoft.App/environments` |
| `snet-felisaichatbot-dev-pgsql` | `10.10.0.64/27` | `Microsoft.DBforPostgreSQL/flexibleServers` |

### FQDN と名前解決の実測（手順書 §1 の記述との差分あり）

- `terraform output server_fqdn` / az の `fullyQualifiedDomainName` はともに
  **`pgsql-felisaichatbot-dev.postgres.database.azure.com`**（再作成前と同じ形式。
  手順書 §1 の「private DNS zone 配下の名前に変わる」という予想と異なった）
- private DNS zone 内の実レコードは **ランダムラベルの A レコード**
  （`bf4b8e9cdc10.felisaichatbot-dev.private.postgres.database.azure.com` → `10.10.0.68`。
  pgsql サブネット内のアドレス）で、サーバー FQDN はここへ委譲されて VNet 内でのみ解決される
- 作業端末からの名前解決は **失敗する**（`getaddrinfo: Name or service not known` を実測）。
  手順書 §1 の「作業端末からこの FQDN へは到達できなくなるのが正常」どおり
- `DATABASE_URL` のホスト部は従来どおり `pgsql-felisaichatbot-dev.postgres.database.azure.com`
  のままでよい（`.env` の `TF_VAR_database_url` は更新済み。値はここに書かない）

### apply 後の残ドリフト（未対応。ステップ B 以降の判断材料）

apply 直後の `terraform plan -detailed-exitcode` は **exit 2（差分あり）**:

- `azurerm_subnet.pgsql` の in-place update 1 件のみ（add / destroy なし）。
  **Azure がサーバー作成時に `Microsoft.Storage` の service endpoint を委任サブネットへ自動付与**し、
  コード（`service_endpoints` 未記載）がそれを外そうとする
- サーバー稼働（バックアップ等のストレージアクセス）への影響が否定できないため、この plan は
  **apply していない**。恒久対応（コードに `service_endpoints = ["Microsoft.Storage"]` を追記して
  ドリフト解消する等）は別途判断する

### リソース一覧（`az resource list -g rg-felisaichatbot-dev-tf`。apply 後）

`pgsql-felisaichatbot-dev` / `id-felisaichatbot-dev` / `log-felisaichatbot-dev` /
`vnet-felisaichatbot-dev` / private DNS zone / VNet link の 6 件（すべて Succeeded）。
ephemeral 層（ACR / CAE / Container Apps）には触れていない。

### クレジット残（計画書 §8 の balanceSummary API。2026-08-22 実測）

- currentBalance **USD 200.00** / estimatedBalance **USD 199.87**
  （前回 2026-08-21 実測の 199.99 から 0.12 USD 減）

### 制約の再確認（geo リストア）

- 再作成直後 1 時間（〜2026-08-22 08:16 UTC 頃）はペアリージョンへのレプリケーション待ちのため
  geo リストア不可（ADR-0019。PITR とは別経路なので Day 4 ドリルには影響しない）

### 次にやること（ステップ B）

手順書 §2 の ephemeral 層 apply（本記録の時点では未着手）:

1. §0-2 の `TF_VAR_*` export（`TF_VAR_database_url` は新ホストで `.env` 更新済み。
   DB 名はサーバー既定の `postgres` を指定した — アプリ用 DB は未作成のため。
   ステップ B 開始時にこの前提を確認すること）
2. ACR-only apply（`-target=azurerm_container_registry.main`）
3. イメージ build / push ×2（serving + ops。タグは §0-2 で確定する SHA）
4. ephemeral full apply（CAE + app + ops app + migration Job）→ `/readyz` 検証
5. その後ステップ C: §3 の ops 結線（migration Job 実行・psql 経路確認）
