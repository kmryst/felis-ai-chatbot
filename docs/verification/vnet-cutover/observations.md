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

## ステップ B: ephemeral 層の apply（2026-08-22 実施。完了。#100）

手順書 §0-2 / §2 の初回ブートストラップ経路（`DEPLOY_SHA` 未設定から開始）を初めて通した。
ユーザーの実行承認済み。ゲート（G0〜G2）は各段の直後に実施し、**全ゲート合格**。

### 結果サマリ

| 項目 | 実測 |
| --- | --- |
| ACR-only apply（第 1 段） | 12:03:37Z 開始、**31.8 秒**、1 added |
| serving / ops イメージ build | 12:04:29Z〜36Z（キャッシュ多用で 6.2 秒 / 0.7 秒）。SHA=`06ad1f3`（作業ツリー clean 確認済み） |
| push | 12:06:08Z〜13Z（3.0 秒 / 2.3 秒） |
| ephemeral 全体 apply（第 2 段） | 12:07:10Z〜12:11:12Z、**計 4 分 03 秒**。内訳: **CAE（workload profiles + custom VNet）3 分 07 秒** / serving 50 秒 / ops 49 秒 / migration Job 18 秒 |
| 委任サブネット → ACR 到達性（未実測だった前提 1） | **到達できる**。NSG / UDR / NAT Gateway なしのまま、serving / ops とも ACR からの pull で revision が `RunningAtMaxScale` に到達 |
| `/readyz` | **200** `{"status":"ok","db":"ok"}`（12:12:30Z。VNet 内経路での `SELECT 1` 開通） |

### 実施順の正直な記録

ローカルゲート（G0）の指示を受領したのは **ACR-only apply の完了後**。ACR 単体は後段の検証を無効化
しない資源のため取り消さず、**イメージ push（Azure へ内容が渡る最初の 操作）より前に G0 を全件実施**した。
G0c の persistent 基準線 plan も厳密には「ACR-only apply 後」の取得である。

### G0: ローカルゲート（Azure へ push する前）

#### G0a. ops イメージでの実 migration テスト（`%` 入り DSN）

PR #99 の回帰テストは `engine_from_config` をモックしており実 DB 非接続。ここでは
「ローカル DSN に `%` が無かったから踏まなかった」という元不具合の条件を意図的に再現した。

```text
実行: docker network create g0a-net
      docker run -d --name g0a-pg --network g0a-net (pgvector/pgvector:pg17)
      CREATE USER testpct WITH PASSWORD 'p@ss%word' SUPERUSER;   ← URL エンコードで %40 / %25 が DSN に現れる
      docker run --rm --network g0a-net -e DATABASE_URL='postgresql://testpct:p%40ss%25word@g0a-pg:5432/felis' \
        felisaichatbotacrdev.azurecr.io/backend-ops:sha-06ad1f3 alembic upgrade head
出力: Running upgrade  -> 0001 / exit 0
検証: alembic_version = 0001 = `alembic heads`（同イメージで実行）と一致 / public に 5 テーブル
      イメージ内 migrations/env.py に `replace("%", "%%")` が入っていることも grep で確認（1 件）
後始末: コンテナ停止・削除 → ネットワーク削除（依存の逆順）。残存コンテナ 0・ポート保持プロセスなし
合否: **合格**
```

#### G0b. イメージの中身と素性

```text
docker image inspect: 両イメージとも arch=amd64 os=linux
ops イメージ: /usr/bin/psql / /app/.venv/bin/alembic / alembic.ini / migrations/versions/0001_initial_schema.py 実在
serving 単体起動（DB 到達不能な DSN を与えて）: /health=200、/readyz=503、
  WARNING "database readiness check failed" が構造化ログに出る（起動可否と DB 不達の振る舞いを分離して確認）
合否: **合格**
```

#### G0c. plan を読んでから apply

```text
terraform -chdir=terraform/persistent plan -detailed-exitcode → exit 0（12:05:46Z。作業基準線）
ephemeral 全体 plan（apply 直前に取得・熟読）: 4 to add（CAE / serving / ops / Job）、
  イメージ参照は push 済み sha-06ad1f3、revision_suffix = (known after apply)、
  ops に DSN_REVISION_MARKER env あり。serving 側の env 2 ブロックは
  dynamic ブロックの for_each が sensitive 変数（database_url）由来のため plan 上
  「(sensitive value)」とマスクされる（ブロック数 2 で存在は確認。機能影響なし）
合否: **合格**
```

### G1: push 直後（12:06 実測）

```text
az acr repository show-tags: backend / backend-ops とも sha-06ad1f3 実在
ダイジェスト一致: backend  sha256:20e70f8b7f8e…（ローカル RepoDigest = ACR digest）
                 backend-ops sha256:1503b275cb4c…（同上）
合否: **合格**
push 後に .env へ DEPLOY_SHA=06ad1f3 を書き戻し、§0-2 の 2)〜4) を再実行（手順書どおり）
```

### G2: ephemeral apply 直後

```text
terraform -chdir=terraform/ephemeral plan -detailed-exitcode → exit 0（12:11:35Z）
revision 実測: serving ca-felisaichatbot-dev--axeh5j3 / ops ca-felisaichatbot-dev-ops--snnzgc3、
  いずれも runningState=RunningAtMaxScale・runningStateDetails=null・replicas=1
  （suffix 未指定時の自動生成名と、区切り文字が実測で `--` であることを確認。
   公式 revisions ドキュメントの例は `<APP名>-<suffix>` の一重ハイフンで、実挙動と食い違う）
/readyz: HTTP/2 200 {"status":"ok","db":"ok"}（12:12:30Z）。
  terraform output container_app_fqdn（= latest_revision_fqdn。revision 固有名入り）と
  アプリ安定 FQDN（az containerapp show の ingress.fqdn）の両方で 200（→ Issue #101）
ネガティブテスト（private access の実証）: 作業端末から DB FQDN へ
  getent hosts → 解決失敗（Name or service not known）。**DNS 解決の段階で失敗**するため
  TCP 接続の試行自体が不成立（到達性は DNS で遮断されていることを区別して記録）
一過性事象: ops の revision list が 1 回だけ ARM InternalServerError
  （correlation ID fa67178b-…）。10 秒後のリトライで成功。以後再発なし
合否: **合格**
```

## ステップ C: ops 結線と revision 名衝突実測（2026-08-22 実施。完了。#100）

### §3-1 マイグレーション Job（G3）

```text
az containerapp job start（12:13:12Z）→ execution caj-felisaichatbot-dev-migrate-og8aw5j
  12:13:15Z 開始 → 12:13:59Z のポーリングで Succeeded（所要 44 秒以内）
G3（Succeeded を鵜呑みにしない検証。ops コンテナから exec で実測）:
  SELECT 1 → 1
  SELECT version_num FROM alembic_version → 0001（= alembic heads と一致）
  \dt → 5 テーブル（alembic_version / documents / object_properties / objects / sources、owner felisadmin）
  ローカル G0a と同一のテーブル構成であることを確認
合否: **合格**
```

### §3-2 psql 経路と exec の実挙動（G4）

- **min_replicas を上げずに exec に成功した**。ephemeral apply 直後の初期プロビジョニングの
  レプリカ（12:10:44Z 作成）が Running のまま残っており、その状態では
  `az containerapp exec` が直接つながる。手順書 §3-2 の「まず min-replicas を 1 に上げる」は
  この経路では不要だった。**「レプリカ 0 の状態で exec できるか」は今回も踏んでおらず未実測のまま**
- `az containerapp exec --command` の実挙動（手順書に反映済み）:
  - コマンド文字列はコンテナ内シェルを介さず実行され、**`$DATABASE_URL` 等の環境変数は展開されない**
    （psql がローカルソケットに向かう誤動作を実測）
  - `sh -c "…"` の入れ子引用は az 側の分割で**壊れる**（Syntax error を実測）
  - 動いた方式: `--command bash` で対話セッションを張り、**標準入力からコマンドを流し込む**
    （接続確立まで約 10 秒待ってから入力。`script -qec` で pty を割り当て）
- G4: scale 設定は serving / ops とも minReplicas=null（=0）/ maxReplicas=1 を `az containerapp show` で
  確認（今回 min-replicas は一度も変更していない）。serving は夜間放置前に **ScaledToZero を実測**
  （その状態で /readyz を叩くと cold start 後に 200）
- 合否: **合格**

### §3-3 の実測結果は次節の記入欄に記載（実施済み）

### G6: 終了時の全体確認（12:25:51Z）

```text
az resource list -g rg-felisaichatbot-dev-tf: 11 リソース（persistent 6 + ACR / CAE /
  serving / ops / Job の 5）。意図しないリソースなし
serving 無傷確認: revision は axeh5j3 の 1 本のみ（§3-3 の probe は ops のみ）。/readyz 200
クレジット残（balanceSummary API）: current 200.00 / estimated 199.83 USD
  作業開始時点（12:02:57Z）の実測も current 200.00 / estimated 199.83 USD で**差分なし**。
  課金データは反映ラグがあるため「本日の作業分が 0 USD」を意味しない（未反映。
  翌日以降の終業チェックで消費を確認する）。参考: coordinator 把握の開始残高 199.87 USD とは
  0.04 USD の差があるが、いずれも estimated（推定値）であり、実測時刻の違いによるもの
```

## revision 名衝突の意図的実測（**2026-08-22 実施。完了**。手順: [vnet-integration-cutover.md](../../operations/vnet-integration-cutover.md) §3-3。#98 / #100）

ADR-0018 追記 #98 の未実測項目「過去に使った revision suffix の再指定を ARM API がエラーにするのか
黙認するのか」を、ステップ C（§3-2 の psql 疎通成功直後）に ops Container App で意図的に衝突させて
実測した。ユーザーの実行承認済み。**結論: ARM に PATCH は受理（HTTP 202）された後、
サーバー側の revision provisioning が「revision with suffix probe1 already exists」で明示的に失敗する
（判定表 1 行目 = エラーが返る）。既存 revision には一切影響しない。**

### タイムライン（実施時に記入）

| 時刻 (UTC) | ステップ | コマンド exit code | メモ |
| --- | --- | --- | --- |
| 12:17:29 | 0) 基準の revision list | 0 | active は `…ops--snnzgc3`（RunningAtMaxScale・replicas 1）のみ |
| 12:17:29〜38 | 1) suffix probe1 + env=1 | 0 | `…ops--probe1` 作成（created 12:17:38Z）。suffix と実名の区切りは **`--`**（公式例の一重 `-` と食い違い） |
| 12:17:5x | 1-b) 既存 env 生存確認（ガード） | 0 | 下表。**3 env とも残存 = 合格** |
| 12:18:08〜16 | 2) suffix probe2 + env=2 | 0 | `…ops--probe2` 作成。probe1 は 12:18:51 Deprovisioning → 12:19:13 以降**既定の revision list から消える**（`--all` を付けると Active=False / Stopped で保持されていることを確認。手順書側に `--all` を追記済み） |
| 12:23:07〜15 | 3) suffix probe1 再指定 + env=3（本番） | **1** | 下表 |

### 1-b) ガードの結果（実施時に記入。ここが NG なら 2) 3) は未実施のまま後始末へ）

| 項目 | 記録 |
| --- | --- |
| probe1 revision の env 一覧（`revision show` の実出力。secret 値は含めない） | `[{name: DATABASE_URL, secretRef: database-url}, {name: DSN_REVISION_MARKER, value: dsn-6bf2e8ac}, {name: REVISION_COLLISION_PROBE, value: "1"}]`（クエリパス `properties.template.containers[0].env` は手順書の想定どおりで修正不要。secretRef は参照名のみで値は出力されない形式であることを確認） |
| `DATABASE_URL`（secretRef = database-url）が残っているか | **残っている** |
| `DSN_REVISION_MARKER` が残っているか | **残っている**（値 dsn-6bf2e8ac も不変） |
| ヘルプ記述（"Existing environment variables are not modified."）と実挙動の一致 / 食い違い | **一致**（追加 1 件のみで既存 2 件は無変更） |

### 3) の結果（実施時に記入。§3-3 の「記録すべきこと」参照）

| 項目 | 記録 |
| --- | --- |
| exit code | **1**（12:23:07Z 発行 → 12:23:15Z 失敗） |
| エラー全文（メッセージ・ARM エラーコード） | `ERROR: Failed to provision revision for container app 'ca-felisaichatbot-dev-ops'. Error details: The following field(s) are either invalid or missing. Field 'template.revisionsuffix' is invalid with details: 'Invalid value: "probe1": revision with suffix probe1 already exists.';..`　`--debug` の応答 JSON 内のエラーコードは `ContainerAppOperationError` |
| CLI 側バリデーションで ARM 到達前に弾かれたか（`--debug` の PUT/PATCH と HTTP status） | **弾かれていない**。`--debug` で PATCH `…/containerApps/ca-felisaichatbot-dev-ops?api-version=2025-07-01` が発行され **HTTP 202 で受理**された後、非同期の provisioning 操作がサーバー側で失敗（= ARM/RP 側の拒否。CLI バリデーションではない） |
| 成功時: probe1 の `REVISION_COLLISION_PROBE` の値（3 = 新内容 / 1 = 旧内容の再利用） | （失敗のため該当なし）失敗後の probe1 は **値 1・createdTime 12:17:38Z のまま無変更** = 衝突エラーは既存 revision に影響しない |
| 成功時: probe1 の `createdTime`（1) の時刻のままか 3) の時刻か） | 同上（12:17:38Z のまま） |
| 各ステップの revision list（active / inactive / Replicas 列） | 0): snnzgc3 のみ Active。1) 後: snnzgc3 + probe1 Active（遷移中）。2) 後: probe1/snnzgc3 → Deprovisioning → `--all` でのみ Active=False/Stopped として見える。3) 後: 構成不変（probe2 Active のまま）。**既定の `revision list` は inactive を表示しない**（`--all` が必要） |

### 判定（実施時に記入）

- 観測された挙動が §3-3 判定表のどの行に当たるか: **1 行目（エラーが返る）**
- Day 4 への含意（旧方式ならどう壊れていたか）: 旧方式（`revision_suffix` = DSN ハッシュ固定）のままなら、Day 4 §4-5 の戻し apply は過去 suffix の再指定になり、**この `ContainerAppOperationError` でブロックされていた**（切り戻し不能）。「黙認されて計測が偽になる」経路（判定表 2 行目）は実挙動としては発生しないことも同時に確定した
- ADR-0018 追記 #98 の「未実測」記述の更新要否: **要**（実測済みに更新した。ADR-0018 追記 #100 参照）

### 後始末とゲート（実施時に記入）

| 検証 | 結果 |
| --- | --- |
| probe 差分に対する `terraform plan -detailed-exitcode`（apply 前。exit 2 想定） | **exit 2**。差分は ops の in-place update 1 件（`REVISION_COLLISION_PROBE` env の削除のみ）。**provider の refresh は env 差分を拾う**（手順書の未実測注記を実測で解消。`--remove-env-vars` の代替経路は不要だった）。なお config が suffix 未指定のため、probe2 という suffix の残存自体は **drift として検出されない**ことも観測 |
| `terraform apply` 後の `plan -detailed-exitcode`（**exit 0 必須ゲート**） | apply は in-place 18 秒で完了し、Azure が自動生成名 `…ops--0000001` の新 revision を作成（自動 suffix の実形式）。plan → **exit 0**（12:25:07Z）。**合格** |
| psql 疎通の再確認（§3-2 と同じ手順） | 新 revision `…ops--0000001` のレプリカへ exec し `SELECT 1` → **1**。**合格** |
