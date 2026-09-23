# 設計値の正本は docs/operations/day3-5-execution-plan.md §3-1（PostgreSQL）と ADR-0016（Log Analytics）。
# 保持期間 7 日の判断は docs/adr/0011、geo 冗長バックアップ有効の判断は docs/adr/0019
# （ADR-0011 の geo 冗長部分のみを supersede）、ネットワーク境界（VNet 統合 / private access）は
# docs/adr/0018 に記録。

data "azurerm_resource_group" "dev" {
  name = var.resource_group_name
}

# Microsoft Entra 認証（authentication.tenant_id / Entra 管理者）に実行主体のテナント ID が要る
# （値はコードに書かない。ephemeral 層の Easy Auth と同じ取り方）
data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# ネットワーク（VNet / 委任サブネット / private DNS zone。ADR-0018）
# ---------------------------------------------------------------------------

# VNet・委任サブネット・private DNS zone は persistent 層に置く（ADR-0018）。
# CAE（ephemeral 層）は destroy / 再作成されるが、PostgreSQL の委任サブネットはサーバーが
# 生きている限り手放せず、ネットワークの寿命は PostgreSQL（persistent）に一致するため。
# ephemeral 層は snet-aca を data source で参照する（terraform_remote_state は使わない。ADR-0015 の 7）。
resource "azurerm_virtual_network" "main" {
  name                = "vnet-felisaichatbot-dev"
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location

  # /24 で足りる: 使うのは snet-aca /26（10.10.0.0〜.63）+ snet-pgsql /27（10.10.0.64〜.95）の
  # 計 96 アドレスのみで、残り 160 アドレスが将来の余白として残る。
  # 他 VNet とのピアリング予定はなく、/24 より広い空間を予約する理由がない
  address_space = ["10.10.0.0/24"]
}

# Container Apps Environment（workload profiles 環境）用サブネット。
# 最小 /27・`Microsoft.App/environments` への委任が必須で、インフラ用に 12 IP が予約される
# （出典: https://learn.microsoft.com/en-us/azure/container-apps/networking ）。
# CAE のネットワーク種別・サブネットサイズは作成後に変更できない（同出典）ため、最小要件の /27
# （32 − Azure 予約 5 − インフラ予約 12 = 実質 15）ではなく /26（実質 47）で確保する。
# Azure 予約 5 IP の出典: https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-faq
# （サブネットごとに先頭 4 + 末尾 1 を予約）。プライベート IP アドレス自体に課金はなく、
# 広げるコストはゼロ。判断の記録は ADR-0018 の追記（2026-08-22）。
resource "azurerm_subnet" "aca" {
  name                 = "snet-felisaichatbot-dev-aca"
  resource_group_name  = data.azurerm_resource_group.dev.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.0.0/26"]

  # service endpoint は付けない。Azure が自動付与するのは PostgreSQL の委任サブネット側だけで
  # （下の snet-pgsql のコメント参照）、こちらは `serviceEndpoints` が `[]` であることを実測済み
  # （`az network vnet subnet show`。2026-08-22。plan にも差分なし）。
  # ただしこれは **CAE 未作成の状態での実測**である。ephemeral 層の apply で CAE を作った後に
  # 同じ形のドリフト（Azure 側の自動付与）が現れないかは、ステップ B で plan を取って確認する
  # （docs/verification/vnet-cutover/observations.md）。
  delegation {
    name = "aca-environments"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# PostgreSQL Flexible Server（private access）用の委任サブネット。最小 /28
# （出典: https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private ）。
# 最小の /28（16 − Azure 予約 5 = 実質 11）ではなく /27（実質 27）で確保する。このサブネットには
# 本体に加えて Day 4 の PITR 復元先サーバー・Day 5 の HA standby が入り、かつ委任サブネットは
# サーバーが生きている限りサイズ変更できない（作り直しは persistent 層＝サーバー再作成を意味する）。
# 判断の記録は ADR-0018 の追記（2026-08-22）。
resource "azurerm_subnet" "pgsql" {
  name                 = "snet-felisaichatbot-dev-pgsql"
  resource_group_name  = data.azurerm_resource_group.dev.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.0.64/27"]

  delegation {
    name = "pgsql-flexible-servers"

    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }

  # 【消さないこと】この service endpoint は WAL アーカイブの経路であり、外すとバックアップが壊れる。
  #
  # Azure は委任サブネットに最初のサーバーをプロビジョンした時点で Microsoft.Storage の
  # service endpoint を**自動で付与する**。用途は WAL（Write-Ahead Log）ファイルを
  # Azure Storage アカウントへアップロードする通信の経路確保である（出典:
  # https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private ）。
  #
  #   "The Microsoft.Storage service endpoint is automatically configured on the delegated
  #    subnet when the first server is provisioned in that subnet. This configuration ensures
  #    reliable routing of traffic to the Azure Storage accounts used for uploading
  #    Write-Ahead Log (WAL) files. Removing this endpoint may disrupt connectivity and can
  #    lead to unintended consequences for core service operations."
  #
  # ここに明記していないと、Terraform は「コードにない = 消すべきもの」と解釈し、
  # 毎回この endpoint を削除する in-place update を plan に出し続ける（ステップ A の apply 直後に
  # 実測。docs/verification/vnet-cutover/observations.md）。本プロジェクトの主成果物は
  # PostgreSQL の Backup / PITR であり、その経路を Terraform が自動で剥がす状態を残さない。
  #
  # したがってこの記述は「不要な冗長」ではなく、**Azure 側の不変条件をコードに固定して
  # 意図しない削除を防ぐためのもの**である。ドリフトが消えたからといって削除しないこと
  # （消すと plan が再び exit 2 に戻り、apply すれば実際に endpoint が外れる）。
  #
  # azurerm 5.1.0 では `service_endpoints`（文字列リスト）という属性は存在せず、
  # 繰り返し可能な `service_endpoint` ブロック（`service` 必須 / `network_identifier` 任意）
  # で表現する（`terraform providers schema -json` で確認。2026-08-22）。
  # Azure が返す `locations`（japaneast / japanwest）はプロバイダーのスキーマに存在せず、記述しない。
  service_endpoint {
    service = "Microsoft.Storage"
  }
}

# private access の名前解決用 private DNS zone。名前は `[name].postgres.database.azure.com`
# 形式が必須で、サーバー名と同名にはできない（出典: 上記 concepts-networking-private）。
# CAF の略語表では DNS zone の「略語」は DNS ドメイン名そのもの（ADR-0013 の規則表を参照）。
resource "azurerm_private_dns_zone" "pgsql" {
  name                = "felisaichatbot-dev.private.postgres.database.azure.com"
  resource_group_name = data.azurerm_resource_group.dev.name
}

# zone を VNet に解決可能にする link。PostgreSQL の作成は「zone が対象 VNet にリンク済み」で
# あることが前提（上記 concepts-networking-private）。サーバーは zone の id しか参照しないため
# link への暗黙依存が作れず、サーバー側に明示 depends_on を張る（下記）。
resource "azurerm_private_dns_zone_virtual_network_link" "pgsql" {
  name                = "vnet-felisaichatbot-dev-link"
  private_dns_zone_id = azurerm_private_dns_zone.pgsql.id
  virtual_network_id  = azurerm_virtual_network.main.id
}

# ---------------------------------------------------------------------------
# PostgreSQL Flexible Server
# ---------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server" "main" {
  name                = var.server_name
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location

  # ローカル（docker-compose の pgvector/pgvector:pg17）と揃える。
  # japaneast での 17 提供は `az postgres flexible-server list-skus -l japaneast` で確認済み（2026-08-20）。
  version = "17"

  # Day 3〜4 は最小構成。Day 5 に GP へスケールして HA を有効化する（§3-1 / §5-1）。
  sku_name   = "B_Standard_B1ms"
  storage_mb = 32768

  # パスワード認証の管理者（ADR-0031）。通常運用では 3 つとも既定（null / null / 0）で、
  # 何も送らない。
  # - 既存サーバー: administrator_login は Optional + Computed のため null でも state の値
  #   （felisadmin。ForceNew）が保たれ差分は出ない。旧 felisadmin ロールは DB 内に残り、managed identity の
  #   ロールがその権限を継承している
  # - 新規作成（Entra 認証のみ）: azurerm 5.1.0 の Create は password_auth_enabled = false のとき
  #   administrator_login / administrator_password / administrator_password_wo の指定をエラーにするため、
  #   null のままにする。新規 DB には felisadmin が存在しないので、DB ロールの初期化は
  #   docs/operations/entra-auth-cutover.md §3「新規作成時」の手順（identity のロールを管理者として作る）
  # - rollback（パスワード認証の一時的な再有効化）は Terraform ではなく az CLI で行う
  #   （`az postgres flexible-server update --password-auth Enabled --admin-password …`。ARM 1 回で
  #   認証の有効化と新パスワードの設定を同時に行う）。azurerm 5.1.0 の Update はパスワード認証を
  #   有効にする apply で login と password 引数の両方を要求し、write-only の password 引数を
  #   sensitive / ephemeral 変数で常設すると plan に空の in-place update が出続けるため（実測。
  #   docs/verification/entra-auth/observations.md §10）、構成にはパスワード関連の引数を置かない。
  #   手順と収束（修復後の apply が Disabled へ戻す）は entra-auth-cutover.md §6
  administrator_login = var.administrator_login

  # 認証方式（Issue #275。ADR-0031）。Microsoft Entra 認証を有効化し、アプリ・Job・ops は
  # user-assigned managed identity のアクセストークンで接続する。
  # - 有効化すると `PGAadAuth` 拡張が有効になりサーバーが再起動する（公式ドキュメント。
  #   出典: https://learn.microsoft.com/en-us/azure/postgresql/security/how-to-configure-sign-in-azure-ad-authentication ）。
  #   所要時間の実測は docs/verification/entra-auth/observations.md
  # - password_auth_enabled = false: managed identity 経路（backend / Job / ops）の疎通を実測で
  #   確認した後に閉じた（併存期間の手順と実測は docs/verification/entra-auth/observations.md）。
  #   緊急時の戻し方は az CLI（上の administrator_login のコメントと entra-auth-cutover.md §6）。
  #   この構成が正であり、修復後の通常 apply が Disabled へ戻す（収束）。修復まで apply しないこと
  # - azurerm 5.1.0 でこのブロックは ForceNew ではない（ForceNew は administrator_login のみ。
  #   `terraform providers schema -json` で確認。2026-09-19）。plan に replacement が出たら apply しない
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  # 保持 7 日（既定のまま）: 検証期間 3 日 < 復旧ウィンドウ 7 日（ADR-0011）
  backup_retention_days = 7
  # geo 冗長バックアップは作成時にしか設定できず、作成後は変更できない（"You can configure
  # geo-redundant storage for backup only during server creation. After a server is provisioned,
  # you can't change the backup storage redundancy option." 出典:
  # https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore ）。
  # azurerm 5.1.0 でも ForceNew 属性（変更 = サーバー再作成。ADR-0019 に確認記録）。
  # 当初は無効（ADR-0011）だったが、12 か月無料枠（バックアップ 32 GB）の判明と
  # 実測 Backup Storage Used 約 2.7 MiB により有効化の実コストがゼロになったため、
  # cutover（ADR-0018）の再作成タイミングで有効化した（ADR-0019）。
  # geo リストアは PITR 不可・RPO 最大 1 時間で、Day 4 の PITR ドリルとは別物（同 ADR）。
  geo_redundant_backup_enabled = true

  # private access（VNet 統合）。ネットワーク方式は作成時にしか決められず、
  # public からの変更はサーバーの再作成（ForceNew）になる（ADR-0018）。
  # 委任サブネット + private DNS zone は上のネットワーク節。firewall rule は廃止
  # （private access では VNet 内からのみ到達可能で、IP 単位の許可リスト自体が存在しない）。
  delegated_subnet_id           = azurerm_subnet.pgsql.id
  private_dns_zone_id           = azurerm_private_dns_zone.pgsql.id
  public_network_access_enabled = false

  # カスタムメンテナンスウィンドウ: 水曜 17:00 UTC 開始（木曜 02:00 JST。検証作業と重ならない深夜帯）
  maintenance_window {
    day_of_week  = 3
    start_hour   = 17
    start_minute = 0
  }

  # HA は Day 5 に有効化（Burstable は HA 非対応）。high_availability ブロックはここでは書かない。

  lifecycle {
    # zone は未指定（Azure の自動割当に任せる）。Day 5 のフェイルオーバーで primary zone が
    # 入れ替わっても Terraform が元の zone へ戻そうとしないよう ignore する（provider docs 推奨）。
    #
    # high_availability も ignore する（Issue #155）。HA failover ドリルでは
    # tier 昇格（B1ms → GP）→ zone-redundant HA 有効化 → planned / forced failover →
    # HA 無効化 → Burstable 復帰 を **すべて az CLI で操作する**。az CLI を使うのは
    # forced failover が Terraform では表現できないため（azurerm 5.1.0 の
    # internal/services/postgres/postgresql_flexible_server_resource.go に "Forced" の
    # 文字列が 1 件も存在せず、扱えるのは PlannedFailover のみ。2026-08-28 確認）。
    #
    # ignore しないと、ドリル中（実環境 HA 有効 / コードに high_availability ブロック無し）に
    # terraform apply すると **HA が無効化される**。同ファイルでの機序:
    #   - high_availability は Optional のみで Computed が無い（L282-301）
    #   - Read が remote の HA を state に書く（L839。flatten は Disabled のときだけ
    #     空リストを返す L1370-1386）→「config に無い + state にある」= 削除差分
    #   - apply で expandFlexibleServerHighAvailabilityForPatch([]) が Mode: Disabled を
    #     PATCH する（L1047、L1345-1351）
    #   - provider のガード（L947-）はすり抜ける。「zone と
    #     high_availability.0.standby_availability_zone の交換以外を弾く」条件は、
    #     上の ignore_changes = [zone] により d.HasChange("zone") が false になり入らない
    # 「ドリル中は apply しない」という運用ルールだけでは provider が止めてくれないため、
    # コード側でガードを持つ。
    #
    # provider の公式 docs も zone と high_availability[0].standby_availability_zone の
    # 両方の ignore を推奨している（azurerm v5.1.0 website docs。2026-08-28 に開いて確認:
    # https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.1.0/website/docs/r/postgresql_flexible_server.html.markdown ）。
    # high_availability ブロックごと ignore すれば、ネストされた standby_availability_zone も
    # 同時にカバーされる。
    #
    # 【この ignore のリスク】HA の drift が plan に一切現れなくなる。誰かが az CLI で HA を
    # 消しても、Azure 側の障害で HA が落ちても plan は無言になる。**HA の状態監視は
    # Terraform 以外の手段で持つ必要がある**（az postgres flexible-server show
    # --query highAvailability の定期確認等）。
    #
    # 【sku_name は絶対に ignore しない】tier の差分は「今 GP に上がっている」ことを plan が
    # 教える唯一の計器であり、ドリル後に B1ms へ戻し忘れた場合の検知手段（課金に直結）。
    # ドリル中に plan が exit 2 になるのは正しい挙動。
    #
    # 【判断保留】ドリル後にこの ignore を外すかどうかは未決。外さないなら
    # 「HA は恒久的に az CLI 管理」という設計判断になり、ADR に記録が必要。
    ignore_changes = [
      zone,
      high_availability,
    ]
  }

  # VNet link が完成する前にサーバー作成を始めると名前解決の結線ができず失敗し得るため、
  # 依存を明示する（link はサーバーから属性参照されず、暗黙依存が発生しない）
  depends_on = [azurerm_private_dns_zone_virtual_network_link.pgsql]
}

# Microsoft Entra 管理者（Issue #275。ADR-0031）。プロジェクト所有者のアカウントを管理者にする。
# 管理者は `pgaadauth_create_principal()` で managed identity のロールを作る主体で、azurerm では
# サーバー本体とは独立したリソース（authentication ブロックと同時に apply できる）。
# object ID / principal name はコードに書かず変数で渡す（個人のアカウント名をコミット対象に
# 載せない。alert_email_address と同じ扱い）。tenant_id は実行主体の Entra テナント。
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "owner" {
  server_name         = azurerm_postgresql_flexible_server.main.name
  resource_group_name = data.azurerm_resource_group.dev.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = var.entra_administrator_object_id
  principal_name      = var.entra_administrator_principal_name
  principal_type      = "User"
}

# CREATE EXTENSION は azure.extensions への allowlist 追加が前提（§2-1 No.27）。
# vector は Alembic 0001_initial_schema の CREATE EXTENSION IF NOT EXISTS vector が必要とし、
# pgstattuple は Day 4 の bloat 実測で使う。
resource "azurerm_postgresql_flexible_server_configuration" "azure_extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR,PGSTATTUPLE"
}

# ---------------------------------------------------------------------------
# Log Analytics Workspace（Container Apps Environment のログ出力先）
# ---------------------------------------------------------------------------

# ephemeral 層ではなくこの層に置く（ADR-0016。bootstrap.md の層分割の説明と一致させる）。
# ephemeral 層は destroy / 再作成されるため、workspace を同居させると監視ログが destroy のたびに消える。
# Day 5 の Monitoring は「閾値は Day 3〜4 の実測レンジを見て決める」（計画書 §7）ため、
# 数日分のログの蓄積が前提になる。ephemeral 層の Container Apps Environment からは
# data "azurerm_log_analytics_workspace" で参照する（terraform_remote_state は使わない。
# persistent の state には sensitive 値が入るため読み取り面を増やさない。ADR-0015 の 7）。
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-felisaichatbot-dev"
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location

  # PAYG（PerGB2018）。取込 3.34 USD/GB（japaneast、Retail Prices API 実測 2026-08-21）。
  sku = "PerGB2018"

  # 保持は最小の 30 日。Analytics テーブルの interactive retention は 31 日まで
  # 取込料金に含まれ、保持コストは発生しない（出典:
  # https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure ）。
  retention_in_days = 30

  # 取込暴走時のコスト上限ガード（変数コメント参照）
  daily_quota_gb = var.log_analytics_daily_quota_gb
}

# ---------------------------------------------------------------------------
# Azure Monitor（Action Group / メトリクスアラート。Issue #151 で az CLI 作成分を import）
# ---------------------------------------------------------------------------

# 監視リソースは persistent 層に置く。scope（監視対象）が PostgreSQL Flexible Server
# （この層のリソース）であり、寿命をそれに一致させるため。ephemeral 層は destroy /
# 再作成される層なので、そこに置くとアラートも一緒に消える（Log Analytics workspace を
# この層に置いたのと同じ理由。ADR-0016）。
# 6 件とも 2026-08-27 に az CLI で作成したものを **削除せず terraform import で取り込んだ**
# （Issue #151）。2026-08-27T05:17:38Z の実発火試験の証跡（台帳 §B #11）が既存の
# リソース ID に紐づいており、作り直すと ID が変わって証跡の対象が消えるため。
# 閾値・severity・条件の設計値と根拠の正本は docs/operations/azure-resource-inventory.md §B #10 / #11。
# ここのコメントは配置と import の判断のみを持ち、値の根拠は台帳に寄せる。

# メール通知の Action Group。#11 のアラート 5 件すべてがこの 1 件を宛先にしている。
# 受信者アドレスはコードに書かず TF_VAR_alert_email_address（.env）で渡す。
resource "azurerm_monitor_action_group" "email" {
  name                = "ag-felisaichatbot-dev-email"
  resource_group_name = data.azurerm_resource_group.dev.name
  short_name          = "felisdev"

  email_receiver {
    name                    = "opsmail"
    email_address           = var.alert_email_address
    use_common_alert_schema = true
  }
}

# 死活監視（最重要）: is_db_alive が 1 を下回ったら Sev0。
resource "azurerm_monitor_metric_alert" "pgsql_is_db_alive" {
  name                = "alert-pgsql-is-db-alive"
  resource_group_name = data.azurerm_resource_group.dev.name
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  description         = "PostgreSQL server not responding (is_db_alive < 1)"
  severity            = 0
  window_size         = "PT5M"
  frequency           = "PT1M"
  auto_mitigate       = true

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "is_db_alive"
    aggregation      = "Minimum"
    operator         = "LessThan"
    threshold        = 1
  }

  action {
    action_group_id = azurerm_monitor_action_group.email.id
  }
}

# ストレージ監視の主計器（早期警告）: 空き 10 GiB 未満で Sev2（台帳 §B #11）。
resource "azurerm_monitor_metric_alert" "pgsql_storage_free_low" {
  name                = "alert-pgsql-storage-free-low"
  resource_group_name = data.azurerm_resource_group.dev.name
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  description         = "storage_free < 10 GiB (10737418240 bytes). Sev2 ticket-level. Azure switches the server to read-only when available capacity < 5 GiB; this fires with 5 GiB of headroom left. Threshold is a design value derived from the 5 GiB read-only condition (no primary source for 10 GiB) and is provisional until consumption rate is measured under load."
  severity            = 2
  window_size         = "PT15M"
  frequency           = "PT5M"
  auto_mitigate       = true

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "storage_free"
    aggregation      = "Minimum"
    operator         = "LessThan"
    threshold        = 10737418240 # 10 GiB
  }

  action {
    action_group_id = azurerm_monitor_action_group.email.id
  }
}

# ストレージ監視の主計器（危機）: 空き 6 GiB 未満で Sev1。read-only 転落（空き 5 GiB）の
# 1 GiB 手前のため、Sev2 より速い周期（PT5M / PT1M）で見る（台帳 §B #11）。
resource "azurerm_monitor_metric_alert" "pgsql_storage_free_critical" {
  name                = "alert-pgsql-storage-free-critical"
  resource_group_name = data.azurerm_resource_group.dev.name
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  description         = "storage_free < 6 GiB (6442450944 bytes). Sev1 page-level: only 1 GiB above the 5 GiB read-only threshold. Faster cadence (PT5M/PT1M) than the Sev2 rule because the remaining headroom is small. Threshold is a design value derived from the 5 GiB read-only condition (no primary source for 6 GiB) and is provisional until consumption rate is measured under load."
  severity            = 1
  window_size         = "PT5M"
  frequency           = "PT1M"
  auto_mitigate       = true

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "storage_free"
    aggregation      = "Minimum"
    operator         = "LessThan"
    threshold        = 6442450944 # 6 GiB
  }

  action {
    action_group_id = azurerm_monitor_action_group.email.id
  }
}

# B1ms のバーストクレジット枯渇の早期警告: 30 を下回ったら Sev2（定常時実測 max 313。台帳 §B #11）。
resource "azurerm_monitor_metric_alert" "pgsql_cpu_credits_remaining_low" {
  name                = "alert-pgsql-cpu-credits-remaining-low"
  resource_group_name = data.azurerm_resource_group.dev.name
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  description         = "B1ms burst credits nearly exhausted (<30 of observed steady-state max 313)"
  severity            = 2
  window_size         = "PT15M"
  frequency           = "PT5M"
  auto_mitigate       = true

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "cpu_credits_remaining"
    aggregation      = "Minimum"
    operator         = "LessThan"
    threshold        = 30
  }

  action {
    action_group_id = azurerm_monitor_action_group.email.id
  }
}

# 補助計器（Sev3 へ格下げ済み・削除しない）: 2026-08-27T05:17:38Z の実発火試験の証跡が
# このルールに紐づいている（格下げの経緯は description と台帳 §B #11）。
resource "azurerm_monitor_metric_alert" "pgsql_storage_percent_80" {
  name                = "alert-pgsql-storage-percent-80"
  resource_group_name = data.azurerm_resource_group.dev.name
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  description         = "DEMOTED to Sev3 (report-level) on 2026-08-27. Superseded as the primary storage gauge by alert-pgsql-storage-free-low / -critical, which measure the absolute quantity the read-only condition is actually defined on (available capacity < 5 GiB). Note the percent denominator is the usable ~31.20 GiB (used 4.10 + free 27.10), not the provisioned 32 GiB, so 5 GiB free = 83.97% and the 95% condition is unreachable in this configuration. Kept, not deleted: the 2026-08-27T05:17:38Z real-fire evidence is attached to this rule."
  severity            = 3
  window_size         = "PT15M"
  frequency           = "PT5M"
  auto_mitigate       = true

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "storage_percent"
    aggregation      = "Average"
    operator         = "GreaterThanOrEqual"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.email.id
  }
}

# ---------------------------------------------------------------------------
# Azure Key Vault（Container Apps の secret の Key Vault 参照化。Issue #286 / ADR-0032）
# ---------------------------------------------------------------------------

# Easy Auth のクライアントシークレットと chat API キーの置き場（ADR-0032）。
# ephemeral 層ではなくこの層に置く: soft-delete は既定で有効かつ無効化できず、soft-delete 中は
# 同名で再作成できない（出典: https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview ）。
# destroy / 再作成を前提にする ephemeral 層（ADR-0015）とは寿命が合わない。
# ephemeral 層の Container Apps は data "azurerm_key_vault" で参照する（terraform_remote_state は
# 使わない。ADR-0015 の 7）。
#
# ロール割当（Container Apps の identity に Key Vault Secrets User、所有者アカウントに
# Key Vault Secrets Officer。いずれもこの Key Vault のスコープ）は Terraform に含めない。
# roleAssignments/write を Terraform 実行主体に持たせない境界（ADR-0012）を維持するため、
# 手動作成 + 台帳 azure-resource-inventory.md §B で管理する（AcrPull / Cognitive Services
# OpenAI User と同じ扱い）。Secrets Officer が付くまで下の azurerm_key_vault_secret は作れない
# （data plane の setSecret が 403 になる。2026-09-22 実測）ため、初回は Key Vault 本体だけを
# -target で先に apply し、ロール割当を挟んでから全体を apply する（台帳の revive runbook）。
resource "azurerm_key_vault" "main" {
  name                = var.key_vault_name
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # アクセス制御は Azure RBAC（access policy は使わない）。
  rbac_authorization_enabled = true

  # soft-delete の保持は最小の 7 日、purge protection は無効（ADR-0032 決定 6）。
  # purge protection を有効にすると保持期間が過ぎるまで同名で作り直せず、revive runbook
  # （destroy 後に apply だけで戻す）が成立しない。誤削除で失う値は、Easy Auth は Entra で再発行、
  # chat API キーは Terraform で再生成できる。
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  # firewall / private endpoint は付けない（Container Apps は trusted services に無く、
  # 有効化には VNet ルールか private endpoint が要る。ADR-0018 と同じ判断軸で別 Issue。ADR-0032 決定 7）
  public_network_access_enabled = true
}

# 誰の identity がいつ secret を読んだかの証跡（AuditEvent）を Log Analytics に送る。
# 診断設定が無いと SecretGet などは記録されない（2026-09-22 の検証環境で確認）。
# メトリクス（ServiceApiHit など）は platform metrics として診断設定なしで読めるので送らない。
resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  name                       = "diag-kv-felisaichatbot-dev"
  target_resource_id         = azurerm_key_vault.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "AuditEvent"
  }
}

# Key Vault 参照の同期失敗を検知する log search alert（ADR-0032 決定 5）。
# identity のロールが外れても、Container Apps は解決済みの値を保持して動き続け、30 分ごとの
# 同期だけが SyncingSecretFromAzureKeyVaultForContainerAppFailed で失敗する（2026-09-22 実測）。
# アプリの死活監視では検知できないため、ContainerAppSystemLogs_CL の Reason_s を直接見る。
# ウィンドウ 1 時間 / 評価 15 分: 同期周期 30 分に対して、失敗 1 回を取りこぼさない幅。
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "kv_secret_sync_failed" {
  name                 = "alert-kv-secret-sync-failed"
  resource_group_name  = data.azurerm_resource_group.dev.name
  location             = data.azurerm_resource_group.dev.location
  scopes               = [azurerm_log_analytics_workspace.main.id]
  description          = "Container Apps failed to sync a secret from Azure Key Vault (SyncingSecretFromAzureKeyVaultForContainerAppFailed). Apps keep running on the cached value, so this is the only signal until the next restart or rotation. Check the Key Vault Secrets User role assignment of the referencing identity."
  severity             = 2
  evaluation_frequency = "PT15M"
  window_duration      = "PT1H"
  enabled              = true

  # 作成時のクエリ検証を省く。ContainerAppSystemLogs_CL は Container Apps 環境（ephemeral 層）が
  # ログを送り始めて初めて workspace に作られるテーブルで、revive runbook（destroy → persistent apply
  # → ephemeral apply）では persistent apply の時点で存在しない。検証が有効（azurerm 5.1.0 の既定は
  # false = 検証する）だと、テーブルが無いことでこのルールの作成が失敗し、persistent apply 全体が止まる。
  # クエリ自体は 2026-09-23 に、Issue #287 の検証用アプリが既存 workspace に残した実際の同期失敗 2 件
  # （2026-09-22T08:43:53Z）に対して同じ条件で 2 件返ることを確認済み
  # （docs/verification/key-vault-secret-references/observations.md）。
  skip_query_validation = true

  criteria {
    query                   = <<-QUERY
      ContainerAppSystemLogs_CL
      | where Reason_s == "SyncingSecretFromAzureKeyVaultForContainerAppFailed"
      | summarize FailedCount = count() by ContainerAppName_s
    QUERY
    time_aggregation_method = "Total"
    metric_measure_column   = "FailedCount"
    operator                = "GreaterThan"
    threshold               = 0

    dimension {
      name     = "ContainerAppName_s"
      operator = "Include"
      values   = ["*"]
    }

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  auto_mitigation_enabled = true

  action {
    action_groups = [azurerm_monitor_action_group.email.id]
  }
}

# chat API キー（/chat 保護。Issue #107）を生成し、Key Vault に write-only argument で書く。
# 【ephemeral について】ここの ephemeral は Terraform 言語の ephemeral resource（値を state / plan に
# 保存しない。 https://developer.hashicorp.com/terraform/language/resources/ephemeral ）で、
# 層名の ephemeral（ADR-0015）とは無関係。
# 仕様は ephemeral 層の旧 random_password.chat_api_key と同じ（長さ 64 の英数字。backend の最小長 32 を
# 十分上回り、記号を含めないのはヘッダ値・シェル経由の扱いを単純にするため）。
ephemeral "random_password" "chat_api_key" {
  length  = 64
  special = false
}

# value_wo は write-only argument で、値は state に入らない（2026-09-22 実測）。
# ephemeral resource は plan / apply のたびに新しい値を作るが、Azure に送られるのは
# value_wo_version が変わったときだけ。ローテーションは chat_api_key_version を +1 して apply する
# （新バージョンは Container Apps が 30 分以内に取り込み、revision を再起動する。ADR-0032 決定 3）。
# data "azurerm_key_vault_secret" は値を state に読み込むので使わない。
resource "azurerm_key_vault_secret" "chat_api_key" {
  name             = "chat-api-key"
  key_vault_id     = azurerm_key_vault.main.id
  value_wo         = ephemeral.random_password.chat_api_key.result
  value_wo_version = var.chat_api_key_version
}
