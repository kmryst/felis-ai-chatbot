# 設計値の正本は docs/operations/day3-5-execution-plan.md §3-2（walking skeleton）と ADR-0015。
# この層は毎日 destroy / apply を繰り返す（§3-6 の teardown / §8 のコスト見張り）。
#
# 【apply 手順の注意（2 段階 apply）】
# firewall rule の for_each は Container App の outbound_ip_addresses（apply 後にしか
# 確定しない値）に依存するため、リソースが何もない状態からの一発 apply は
# 「Invalid for_each argument」で失敗する。初回・destroy 後の再構築は次の 2 段階で行う:
#   1. terraform apply -target=azurerm_container_app.main   # ACR / LAW / CAE / App まで作成
#   2. terraform apply                                      # outbound IP が確定し firewall rule を追加
# （§3-1「Container Apps の egress IP は ephemeral 層が apply 後に自層の firewall rule で許可する」の実装）

data "azurerm_resource_group" "dev" {
  name = var.resource_group_name
}

# persistent 層が管理する PostgreSQL Flexible Server。この層では読み取り参照のみ
# （firewall rule の親 server_id として使う）。サーバー本体の変更は persistent 層でしか行わない。
data "azurerm_postgresql_flexible_server" "main" {
  name                = var.postgres_server_name
  resource_group_name = data.azurerm_resource_group.dev.name
}

# ---------------------------------------------------------------------------
# ACR
# ---------------------------------------------------------------------------

resource "azurerm_container_registry" "main" {
  name                = var.acr_name
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location

  # Basic で足りる根拠（ADR-0015）: walking skeleton のイメージは hello-world + backend の
  # 2 種・数百 MB 規模で、Basic の included storage 10 GiB に収まる。geo replication /
  # private endpoint 等の上位機能は使わない。単価は Basic 0.1666 USD/日
  # （Retail Prices API 実測 2026-08-21。Standard 0.6666 USD/日 の 1/4）。
  sku = "Basic"

  # admin user は無効のまま（既定値の明示）。ACR pull はマネージド ID + AcrPull で行う
  # （ADR-0015 選択肢 6-(b) で確定。admin user 案 (a) は主体を追跡できない共有パスワードのため却下）。
  admin_enabled = false
}

# ---------------------------------------------------------------------------
# Log Analytics Workspace（Container Apps Environment のログ出力先）
# ---------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-felisaichatbot-dev"
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location

  # PAYG（PerGB2018）。取込 3.34 USD/GB（japaneast、Retail Prices API 実測 2026-08-21）。
  sku = "PerGB2018"

  # 保持は最小の 30 日。Analytics テーブルの interactive retention は 31 日まで
  # 取込料金に含まれ、保持コストは発生しない（出典:
  # https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure ）。
  # この層自体が毎日 destroy されるため、長期保持に意味がない。
  retention_in_days = 30

  # 取込暴走時のコスト上限ガード（変数コメント参照）
  daily_quota_gb = var.log_analytics_daily_quota_gb
}

# ---------------------------------------------------------------------------
# Container Apps Environment + Container App
# ---------------------------------------------------------------------------

resource "azurerm_container_app_environment" "main" {
  name                = "cae-felisaichatbot-dev"
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location

  # VNet 統合はしない（day3-5-execution-plan.md §3-1 / §9。作業量とコストだけ増え、
  # 検証目的に寄与しない）。既定の Azure ネットワーク上の環境として作る。
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

# ACR pull 用 user-assigned managed identity（ADR-0015 選択肢 6-(b) で確定）。
# identity 本体と AcrPull ロール割当（RG スコープ）は Terraform 管理外・手動作成
# （docs/operations/terraform-unmanaged-resources.md #8 / #9 が正本）。ID と権限は据え置き、
# ACR / Container Apps は毎日 destroy / apply という寿命の分離のため、この層は読み取り参照のみ。
# 手動作成が済むまでは実体がなく plan / apply は通らない（validate は通る）。
data "azurerm_user_assigned_identity" "acr_pull" {
  name                = var.acr_pull_identity_name
  resource_group_name = data.azurerm_resource_group.dev.name
}

resource "azurerm_container_app" "main" {
  name                         = "ca-felisaichatbot-dev"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = data.azurerm_resource_group.dev.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [data.azurerm_user_assigned_identity.acr_pull.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = data.azurerm_user_assigned_identity.acr_pull.id
  }

  # DATABASE_URL は secret として保持し、環境変数から参照する。
  # hello-world 段階（var.database_url = ""）では secret / 環境変数とも作らない。
  dynamic "secret" {
    for_each = var.database_url == "" ? [] : ["database-url"]
    content {
      name  = "database-url"
      value = var.database_url
    }
  }

  template {
    # スケールゼロ（min_replicas = 0）: 無リクエスト時にレプリカ 0 まで縮退し、
    # コンピュート課金を止める（§8 のコスト方針。ADR-0015）。walking skeleton に
    # 常駐は不要で、コールドスタートの遅延は許容する。
    min_replicas = 0
    # 検証用に 1 レプリカで十分。上限も 1 に固定してスケールアウト課金の芽を残さない。
    max_replicas = 1

    container {
      name  = "app"
      image = var.container_image
      # Consumption の最小構成（0.25 vCPU / 0.5 GiB）。walking skeleton（/readyz が
      # SELECT 1 するだけ）に十分。単価は active vCPU 0.000024 USD/秒・active memory
      # 0.000003 USD/GiB 秒（Retail Prices API 実測 2026-08-21）。
      cpu    = 0.25
      memory = "0.5Gi"

      dynamic "env" {
        for_each = var.database_url == "" ? [] : ["database-url"]
        content {
          name        = "DATABASE_URL"
          secret_name = "database-url"
        }
      }
    }
  }

  ingress {
    # 検証（作業端末から /readyz を叩く）のため外部公開する。認証なし公開で問題ない
    # エンドポイントのみ（hello-world / readyz）を載せる前提。
    external_enabled = true
    target_port      = var.container_target_port

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ---------------------------------------------------------------------------
# PostgreSQL firewall rule（Container Apps の egress 許可）
# ---------------------------------------------------------------------------

# Container App の outbound IP を persistent 層の PostgreSQL に許可する。
# 【既知の不確実性（ADR-0015）】VNet 統合なしの環境では outbound IP は静的保証がなく
# 「Outbound IPs might change over time」と明記されている（出典:
# https://learn.microsoft.com/en-us/azure/container-apps/networking ）。
# この層は毎日 destroy / apply されるため、rule は毎朝その時点の実 IP で作り直される。
# 稼働中に IP が変わると /readyz が DB 接続エラーで落ちる。その場合は
# terraform apply の再実行で rule を現在値に追随させる（検知は /readyz の 200 監視）。
resource "azurerm_postgresql_flexible_server_firewall_rule" "container_app_egress" {
  for_each = toset(azurerm_container_app.main.outbound_ip_addresses)

  # rule 名にドットは使えないためハイフンに置換（例: aca-egress-20-78-1-2）
  name             = "aca-egress-${replace(each.value, ".", "-")}"
  server_id        = data.azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value
  end_ip_address   = each.value
}
