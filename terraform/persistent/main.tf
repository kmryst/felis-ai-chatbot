# 設計値の正本は docs/operations/day3-5-execution-plan.md §3-1（PostgreSQL）と ADR-0016（Log Analytics）。
# 保持期間 7 日・geo 冗長無効の判断は docs/adr/0011 に記録。

data "azurerm_resource_group" "dev" {
  name = var.resource_group_name
}

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

  # public access + サーバーレベル firewall rule（§3-1。VNet 統合は採らない）
  public_network_access_enabled = true

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
}

# CREATE EXTENSION は azure.extensions への allowlist 追加が前提（§2-1 No.27）。
# vector は Alembic 0001_initial_schema の CREATE EXTENSION IF NOT EXISTS vector が必要とし、
# pgstattuple は Day 4 の bloat 実測で使う。
resource "azurerm_postgresql_flexible_server_configuration" "azure_extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR,PGSTATTUPLE"
}

# firewall rule を作るまで全接続拒否（§2-1 No.26）。作業端末の IP は変数で渡す。
resource "azurerm_postgresql_flexible_server_firewall_rule" "client" {
  for_each = var.firewall_allowed_client_ips

  name             = each.key
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}

# ---------------------------------------------------------------------------
# Log Analytics Workspace（Container Apps Environment のログ出力先）
# ---------------------------------------------------------------------------

# ephemeral 層ではなくこの層に置く（ADR-0016。bootstrap.md の層分割の説明と一致させる）。
# ephemeral 層は毎日 destroy されるため、workspace を同居させると監視ログが毎日消える。
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
