# 設計値の正本は docs/operations/day3-5-execution-plan.md §3-2（walking skeleton）と ADR-0015 / ADR-0018。
# この層は使わない期間は destroy して時間課金を止める（当初は毎日 destroy。private access 化後は
# ops 経路が唯一の DB アクセス経路のため夜間 destroy をやめ、destroy は Day 5 の最終 teardown のみ。
# ADR-0018 追記 2026-08-22 / 計画書 §3-6）。
#
# 【apply 手順の注意（段階 apply）】
# 旧構成にあった「firewall rule の for_each が outbound_ip_addresses に依存するための 2 段階 apply」は、
# private access 化（ADR-0018）で firewall rule ごと消えたため不要になった。
# ただし ACR が空のままでは Container App / Job がイメージを pull できないため、
# 初回・destroy 後の再構築は次の 2 段階で行う（イメージ押し込みの都合であり、for_each 制約ではない）:
#   1. terraform apply -target=azurerm_container_registry.main   # ACR だけ先に作成
#   2. docker push（または az acr import）でイメージ投入 → terraform apply   # 残り全部
# 手順の全体は docs/operations/vnet-integration-cutover.md を参照。

data "azurerm_resource_group" "dev" {
  name = var.resource_group_name
}

# persistent 層が管理する VNet 上の Container Apps 用委任サブネット（ADR-0018）。
# この層では読み取り参照のみ。サブネット本体の変更は persistent 層でしか行わない
# （terraform_remote_state は使わない。ADR-0015 の 7 と同じ理由）。
data "azurerm_subnet" "aca" {
  name                 = var.aca_subnet_name
  virtual_network_name = var.vnet_name
  resource_group_name  = data.azurerm_resource_group.dev.name
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
# Log Analytics Workspace（persistent 層が管理。この層は読み取り参照のみ）
# ---------------------------------------------------------------------------

# workspace 本体は persistent 層が管理する（ADR-0016）。この層を destroy しても
# 監視ログが消えないようにするため（Day 5 の閾値決定は Day 3〜4 の実測レンジが前提。計画書 §7）。
# terraform_remote_state は使わず data source で参照する（ADR-0015 の 7 と同じ理由:
# persistent の state には sensitive 値が入るため読み取り面を増やさない）。
data "azurerm_log_analytics_workspace" "main" {
  name                = var.log_analytics_workspace_name
  resource_group_name = data.azurerm_resource_group.dev.name
}

# ---------------------------------------------------------------------------
# Container Apps Environment + Container App
# ---------------------------------------------------------------------------

# VNet 統合（ADR-0018）: workload profiles 環境 + custom VNet + External。
# - workload profiles を選ぶ理由: Consumption-only 環境の VNet 統合は legacy 表記で最小 /23・
#   UDR / NAT Gateway 非対応。workload profiles は最小 /27 で足りる
#   （出典: https://learn.microsoft.com/en-us/azure/container-apps/networking ）
# - Consumption プロファイルのみ使う限りプラン管理の固定費はない
#   （出典: https://learn.microsoft.com/en-us/azure/container-apps/billing ）
# - custom VNet では managed resources（Standard LB + Standard static public IP）が課金対象になる
#   （出典: https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks 。
#    単価と 24h 換算は ADR-0018）。この層の destroy でこの課金も止まる（destroy のタイミングは
#    ADR-0018 追記のとおり Day 5 の最終 teardown）
# - External のまま（internal_load_balancer_enabled = false）: /readyz を作業端末から叩く検証経路を維持する。
#   DB 側は private access なので、DB の到達性はこの設定の影響を受けない
# - ネットワーク種別は CAE 作成後に変更不可（同 networking 出典）。この層は毎日作り直すため制約にならない
resource "azurerm_container_app_environment" "main" {
  name                = "cae-felisaichatbot-dev"
  resource_group_name = data.azurerm_resource_group.dev.name
  location            = data.azurerm_resource_group.dev.location

  logs_destination           = "log-analytics"
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.main.id

  infrastructure_subnet_id       = data.azurerm_subnet.aca.id
  internal_load_balancer_enabled = false

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

# ACR pull 用 user-assigned managed identity（ADR-0015 選択肢 6-(b) で確定）。
# identity 本体と AcrPull ロール割当（RG スコープ）は Terraform 管理外・手動作成
# （docs/operations/azure-resource-inventory.md #8 / #9 が正本）。ID と権限は据え置き、
# ACR / Container Apps は毎日 destroy / apply という寿命の分離のため、この層は読み取り参照のみ。
data "azurerm_user_assigned_identity" "acr_pull" {
  name                = var.acr_pull_identity_name
  resource_group_name = data.azurerm_resource_group.dev.name
}

resource "azurerm_container_app" "main" {
  name                         = "ca-felisaichatbot-dev"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = data.azurerm_resource_group.dev.name
  revision_mode                = "Single"

  # workload profiles 環境では app がどのプロファイルで動くかを明示する（Consumption のみ使う。ADR-0018）
  workload_profile_name = "Consumption"

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
    # secret（database-url）の更新は既存 revision に自動反映されない（新しい revision の作成
    # または restart が必要。出典: https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets ）。
    # DSN が変わる apply（Day 4 の PITR 後の復元先への向け替え等）で新 revision の作成をコードで
    # 担保するため、DSN のハッシュを template 内の非 secret 環境変数（DSN_REVISION_MARKER。下の
    # container ブロック）として持たせる。revision_suffix への埋め込みは使わない: revision 名は
    # 一意必須（"Every revision in Container Apps is assigned a unique identifier."）で、非アクティブ
    # revision は最大 100 件保持されるため、Day 4 の 元サーバー → 復元先 → 元サーバー の往復では
    # 戻しの apply が過去に使った suffix を再利用して既存 revision と衝突する（詳細は ADR-0018 追記）。
    # suffix を指定しなければ Azure が一意な名前を自動生成する。
    # 出典: https://learn.microsoft.com/en-us/azure/container-apps/revisions

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

      # 新 revision 作成のコード担保（アプリはこの変数を読まない）。環境変数は
      # properties.template にあり revision-scope、secret は properties.configuration にあり
      # application-scope のため、secret の更新だけでは新 revision が作られない。
      # 出典（https://learn.microsoft.com/en-us/azure/container-apps/revisions ）:
      #   "A revision-scope change is any change to the parameters in the
      #    properties.template section of the container app resource template."
      #   "Application-scope changes are defined as any change to the parameters in the
      #    properties.configuration section of the container app resource template.
      #    These parameters include: Secret values (revisions must be restarted before
      #    a container recognizes new secret values)" — "A new revision isn't created."
      # ハッシュは sha256 の先頭 8 桁のみで不可逆（DSN・パスワードは復元できない）。値自体は
      # 秘匿情報ではなく（従来は revision 名として Azure 上に露出していた値）、nonsensitive() は
      # その明示 + plan 出力を無用にマスクさせないため。
      dynamic "env" {
        for_each = var.database_url == "" ? [] : ["dsn-revision-marker"]
        content {
          name  = "DSN_REVISION_MARKER"
          value = "dsn-${nonsensitive(substr(sha256(var.database_url), 0, 8))}"
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
# 運用経路（ops Container App + マイグレーション Job。ADR-0018）
# ---------------------------------------------------------------------------

# private access 化後、DB へは VNet 内からしか到達できない。手元の psql / alembic の代わりに、
# VNet 内の運用コンテナを唯一の対話経路とする（「本番 DB へ手元から直接繋がない」運用。ADR-0018）。
# - ingress なし: 外に晒す必要が一切ない
# - min_replicas 0: 平常時はレプリカ 0 で課金ゼロ。使うときだけ min_replicas を一時的に
#   1 へ上げて `az containerapp exec` で入る（手順は docs/operations/vnet-integration-cutover.md）
# - イメージは backend の ops ターゲット（runtime + postgresql-client + migrations/ + alembic.ini）。
#   serving イメージには運用ツールを混ぜない（backend/Dockerfile）
# - ops_container_image が空の間は作らない（hello-world 段階や ops イメージ未 push の状態でも
#   apply が通るようにするため）
resource "azurerm_container_app" "ops" {
  count = var.ops_container_image == "" ? 0 : 1

  name                         = "ca-felisaichatbot-dev-ops"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = data.azurerm_resource_group.dev.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [data.azurerm_user_assigned_identity.acr_pull.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = data.azurerm_user_assigned_identity.acr_pull.id
  }

  secret {
    name  = "database-url"
    value = var.database_url
  }

  template {
    # serving 側と同じ理由（secret 更新は既存 revision に自動反映されない）で、DSN 変更の apply が
    # 必ず新 revision を作るようにする。ops コンテナは Day 4 の RTO / RPO 計測経路そのもののため、
    # 古い revision が元サーバーの DSN を見続けると計測が偽になる。担保は serving 側と同じく
    # 非 secret 環境変数 DSN_REVISION_MARKER（revision-scope。下の container ブロック）で行い、
    # revision_suffix 固定は往復 apply での名前衝突のため使わない（ADR-0018 追記）

    min_replicas = 0
    max_replicas = 1

    container {
      name   = "ops"
      image  = var.ops_container_image
      cpu    = 0.25
      memory = "0.5Gi"

      # serving 用 CMD（uvicorn）を上書きし、exec で入るためだけに待機させる
      command = ["sleep", "infinity"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      # 新 revision 作成のコード担保（詳細コメントは serving 側の同名 env を参照）
      env {
        name  = "DSN_REVISION_MARKER"
        value = "dsn-${nonsensitive(substr(sha256(var.database_url), 0, 8))}"
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.database_url != ""
      error_message = "ops_container_image を指定する場合は database_url も必須です（ops コンテナは DB 接続のためだけに存在する）。"
    }
  }
}

# Alembic マイグレーション実行用の Container Apps Job（Manual トリガー。ADR-0018）。
# `az containerapp job start` で起動し、`alembic upgrade head` を 1 回実行して終了する。
# 課金は実行中のレプリカ分のみ（Manual トリガーで放置中はゼロ）。
# Job には revision の概念がなく（azurerm 5.1.0 の実スキーマでも template に revision_suffix なし。
# 2026-08-22 に providers schema で確認）、実行のたびに新しい execution が作られるため、
# Container App 側のような DSN_REVISION_MARKER によるコード担保は不要。secret 更新後の挙動
# （新 execution が更新後の値を読むか）は cutover 実測時に確認する（未実測）。
resource "azurerm_container_app_job" "migrate" {
  count = var.ops_container_image == "" ? 0 : 1

  name                         = "caj-felisaichatbot-dev-migrate"
  location                     = data.azurerm_resource_group.dev.location
  resource_group_name          = data.azurerm_resource_group.dev.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"

  # マイグレーション 1 本に 10 分あれば十分（現状の migration は CREATE EXTENSION + DDL のみ）。
  # 超えたら設計を疑うべきで、無限に待たない
  replica_timeout_in_seconds = 600
  # 失敗時に自動で叩き直さない（スキーマ変更の再試行は人間が状態を確認してから）
  replica_retry_limit = 0

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [data.azurerm_user_assigned_identity.acr_pull.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = data.azurerm_user_assigned_identity.acr_pull.id
  }

  secret {
    name  = "database-url"
    value = var.database_url
  }

  template {
    container {
      name   = "migrate"
      image  = var.ops_container_image
      cpu    = 0.25
      memory = "0.5Gi"

      command = ["alembic", "upgrade", "head"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      # 新 revision 作成のコード担保（詳細コメントは serving 側の同名 env を参照）
      env {
        name  = "DSN_REVISION_MARKER"
        value = "dsn-${nonsensitive(substr(sha256(var.database_url), 0, 8))}"
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.database_url != ""
      error_message = "ops_container_image を指定する場合は database_url も必須です（migration Job は DB 接続のためだけに存在する）。"
    }
  }
}
