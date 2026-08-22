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

### apply 後の残ドリフト（**解消済み。対応は下の「ステップ A-2」**）

apply 直後の `terraform plan -detailed-exitcode` は **exit 2（差分あり）**:

- `azurerm_subnet.pgsql` の in-place update 1 件のみ（add / destroy なし）。
  **Azure がサーバー作成時に `Microsoft.Storage` の service endpoint を委任サブネットへ自動付与**し、
  コード（`service_endpoints` 未記載）がそれを外そうとする
- サーバー稼働（バックアップ等のストレージアクセス）への影響が否定できないため、この plan は
  **apply していない**。恒久対応は「ステップ A-2」で実施した（なお、この時点で想定していた
  `service_endpoints = ["Microsoft.Storage"]` という書き方は azurerm 5.1.0 には存在しない。
  実際の記法はステップ A-2 を参照）

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

---

## ステップ A-2: 残ドリフトの解消（2026-08-22 実施。完了。#96）

ステップ A の「apply 後の残ドリフト」1 件をコード側で解消した。**Azure への書き込みは行っていない**
（`terraform apply` / `destroy` を実行せず、az も読み取り系のみ。ephemeral 層にも触れていない）。

### 結果サマリ

- **`terraform plan -detailed-exitcode` が exit 0（`No changes.`）になった**。ドリフト 0 件
- 対応は `azurerm_subnet.pgsql` に `service_endpoint` ブロックを明記しただけで、**Azure 側の実物は
  一切変更していない**（コードを実物に合わせた。実物をコードに合わせたのではない）

### ドリフトの正確な内容（apply 前の plan 実測）

```text
  # azurerm_subnet.pgsql will be updated in-place
  ~ resource "azurerm_subnet" "pgsql" {
      - service_endpoint {
          - service            = "Microsoft.Storage" -> null
        }
    }

Plan: 0 to add, 1 to change, 0 to destroy.
```

| 項目 | 内容 |
| --- | --- |
| リソース | `azurerm_subnet.pgsql`（`snet-felisaichatbot-dev-pgsql`） |
| 属性 | `service_endpoint` ブロックの `service` |
| 変更前（実物） | `"Microsoft.Storage"` |
| 変更後（コードが意図） | `null`（＝ブロックごと削除） |
| 種別 | in-place update（add / destroy なし） |

### 実物の service endpoint の実測（`az network vnet subnet show`。2026-08-22。読み取りのみ）

| サブネット | `serviceEndpoints` | 委任 | ドリフト |
| --- | --- | --- | --- |
| `snet-felisaichatbot-dev-aca` | **`[]`（空）** | `Microsoft.App/environments` | **なし** |
| `snet-felisaichatbot-dev-pgsql` | **`Microsoft.Storage`**（`locations: japaneast, japanwest` / `provisioningState: Succeeded`）の 1 件のみ | `Microsoft.DBforPostgreSQL/flexibleServers` | あり（上記） |

- pgsql 側に付与されているのは **`Microsoft.Storage` の 1 件だけ**で、他の service endpoint はない
- aca 側は空で、plan にも差分は出ていない。**ただしこれは CAE 未作成の状態での実測**であり、
  ephemeral 層 apply 後に同種の自動付与が起きないかはステップ B で plan を取って確認する

### 原因（公式ドキュメントの一次情報で確認）

Azure は**委任サブネットに最初のサーバーをプロビジョンした時点で `Microsoft.Storage` の
service endpoint を自動付与する**。用途は **WAL（Write-Ahead Log）ファイルを Azure Storage
アカウントへアップロードする通信の経路確保**であり、削除は明確に警告されている。

出典: <https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private>

> The Microsoft.Storage service endpoint is automatically configured on the delegated subnet when
> the first server is provisioned in that subnet. This configuration ensures reliable routing of
> traffic to the Azure Storage accounts used for uploading Write-Ahead Log (WAL) files.
> **Removing this endpoint may disrupt connectivity** and can lead to unintended consequences for
> core service operations.

同ページの「Unsupported virtual network scenarios」にも重ねて記載がある（原文に `Micosoft.Storage`
という誤記があるが、文意は同じ）:

> By default, the service adds a Micosoft.Storage service endpoint when the first server is
> provisioned in the delegated subnet, which provides secure and direct connectivity to Azure
> Storage over the Azure backbone network. Removing this endpoint can lead to unintended
> consequences for core service operations.

**この事実はステップ A の時点で本リポジトリのどのドキュメントにも記録されていなかった**
（計画書 §2-1 の No.1〜28 にも ADR-0018 にもなし）。本対応で計画書 §2-1 に **No.29** として
出典付きで追加した。

### なぜ放置できなかったか

- 主成果物は PostgreSQL の **Backup / PITR / Maintenance** であり、WAL アーカイブ経路はその土台である
- 残った plan は「その経路を外す」内容だった。**内容を確認せずに apply した人（エージェント含む）が
  実際に経路を壊せる状態**が残っていた
- 直後に Day 4 の PITR ドリルが控えており、ドリル中の不用意な apply は実験そのものを破壊する

### 対応

`terraform/persistent/main.tf` の `azurerm_subnet.pgsql` に、実物と同じ値を明記した。

```hcl
  service_endpoint {
    service = "Microsoft.Storage"
  }
```

**azurerm 5.1.0 のスキーマ確認**（`terraform providers schema -json` の `azurerm_subnet`。2026-08-22 実測）:

| 確認したこと | 結果 |
| --- | --- |
| `service_endpoints`（文字列リストの属性） | **存在しない**。ステップ A の記録で想定していた `service_endpoints = ["Microsoft.Storage"]` はこのバージョンでは書けない |
| 正しい記法 | 繰り返し可能な**ブロック** `service_endpoint`（`nesting_mode: list`、`max_items` なし） |
| ブロックの属性 | `service`（string・**必須**）/ `network_identifier`（string・任意） |
| `locations` | プロバイダーのスキーマに**存在しない**（Azure は `japaneast` / `japanwest` を返すが Terraform 側では表現しないため記述しない） |

削除防止のため、コードのコメントに「WAL アーカイブ経路であること」「Azure が自動付与すること」
「外すと壊れること」「消すと plan が再び exit 2 に戻ること」と出典 URL を残した。

### 検証（すべて実測。2026-08-22）

| 検証 | 結果 |
| --- | --- |
| `terraform -chdir=terraform/persistent plan -detailed-exitcode` | **exit 0** / `No changes. Your infrastructure matches the configuration.` |
| `terraform fmt -check -recursive terraform/` | pass |
| persistent 層 `init -backend=false` + `validate` | pass |
| ephemeral 層 `init -backend=false` + `validate` | pass |
| `terraform apply` / `destroy` | **未実行**（plan がゼロになったため apply の必要がない） |
| Azure への書き込み | **なし**（az は `show` のみ） |

### 併せて更新したドキュメント

- 計画書 §2-1 に **No.29**（Microsoft.Storage service endpoint の自動付与と削除の危険）を追加
- 計画書 Day 4（§4-1）/ Day 5（§5-1 の前段）に「**apply の前に `plan -detailed-exitcode` が
  exit 0 であることを確認する**」というゲートを追加。ドリル最中の不用意な apply を防ぐため
- ADR-0018 に追記（新規 ADR は起こさない。判断根拠は当該追記に記載）

## revision 名衝突の意図的実測（**未実施**。手順: [vnet-integration-cutover.md](../../operations/vnet-integration-cutover.md) §3-3。#98）

ADR-0018 追記 #98 の未実測項目「過去に使った revision suffix の再指定を ARM API がエラーにするのか
黙認するのか」を、ステップ C（§3-2 の psql 疎通成功直後）に ops Container App で意図的に衝突させて
実測する。**以下はすべて記入欄であり、値が入っていない間は未実施**。実施はユーザーの明示承認後。

### タイムライン（実施時に記入）

| 時刻 (UTC) | ステップ | コマンド exit code | メモ |
| --- | --- | --- | --- |
| | 0) 基準の revision list | | |
| | 1) suffix probe1 + env=1 | | |
| | 2) suffix probe2 + env=2 | | |
| | 3) suffix probe1 再指定 + env=3（本番） | | |

### 3) の結果（実施時に記入。§3-3 の「記録すべきこと」参照）

| 項目 | 記録 |
| --- | --- |
| exit code | |
| エラー全文（メッセージ・ARM エラーコード） | |
| CLI 側バリデーションで ARM 到達前に弾かれたか（`--debug` の PUT/PATCH と HTTP status） | |
| 成功時: probe1 の `REVISION_COLLISION_PROBE` の値（3 = 新内容 / 1 = 旧内容の再利用） | |
| 成功時: probe1 の `createdTime`（1) の時刻のままか 3) の時刻か） | |
| 各ステップの revision list（active / inactive / Replicas 列） | |

### 判定（実施時に記入）

- 観測された挙動が §3-3 判定表のどの行に当たるか:
- Day 4 への含意（旧方式ならどう壊れていたか）:
- ADR-0018 追記 #98 の「未実測」記述の更新要否:

### 後始末とゲート（実施時に記入）

| 検証 | 結果 |
| --- | --- |
| probe 差分に対する `terraform plan -detailed-exitcode`（apply 前。exit 2 想定） | |
| `terraform apply` 後の `plan -detailed-exitcode`（**exit 0 必須ゲート**） | |
| psql 疎通の再確認（§3-2 と同じ手順） | |
