# 設計値の正本は docs/operations/day3-5-execution-plan.md §3-1（PostgreSQL）と ADR-0016（Log Analytics）。
# 保持期間 7 日・geo 冗長無効の判断は docs/adr/0011、ネットワーク境界（VNet 統合 / private access）は
# docs/adr/0018 に記録。

data "azurerm_resource_group" "dev" {
  name = var.resource_group_name
}

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

  administrator_login    = var.administrator_login
  administrator_password = var.administrator_password

  # 保持 7 日（既定のまま）: 検証期間 3 日 < 復旧ウィンドウ 7 日（ADR-0011）
  backup_retention_days = 7
  # geo 冗長は作成時にしか決められない。無効の判断根拠は ADR-0011
  geo_redundant_backup_enabled = false

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
    ignore_changes = [zone]
  }

  # VNet link が完成する前にサーバー作成を始めると名前解決の結線ができず失敗し得るため、
  # 依存を明示する（link はサーバーから属性参照されず、暗黙依存が発生しない）
  depends_on = [azurerm_private_dns_zone_virtual_network_link.pgsql]
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
