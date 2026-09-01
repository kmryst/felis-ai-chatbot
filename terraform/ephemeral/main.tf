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

  # /chat 保護の API キー（#107）。未指定なら secret / env とも作らず、backend は
  # fail-closed（/chat 404）で動く
  dynamic "secret" {
    for_each = var.chat_api_key == "" ? [] : ["chat-api-key"]
    content {
      name  = "chat-api-key"
      value = var.chat_api_key
    }
  }

  # Azure OpenAI の API キー（Issue #195。ADR-0009）。database-url / chat-api-key と同方針で
  # Container Apps の secret として保持し、環境変数から参照する。未指定なら secret / env とも
  # 作らない（llm_provider = "azure-openai" のときの必須検査は下の precondition）
  dynamic "secret" {
    for_each = var.azure_openai_api_key == "" ? [] : ["azure-openai-api-key"]
    content {
      name  = "azure-openai-api-key"
      value = var.azure_openai_api_key
    }
  }

  template {
    # secret（database-url）の更新は既存 revision に自動反映されない（新しい revision の作成
    # または restart が必要。出典: https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets ）。
    # DSN が変わる apply（Day 4 の PITR 後の復元先への向け替え等）で新 revision の作成をコードで
    # 担保するため、DSN のハッシュを template 内の非 secret 環境変数（DSN_CONFIG_CHECKSUM。下の
    # container ブロック）として持たせる。revision_suffix への埋め込みは使わない: revision 名は
    # 一意必須（"Every revision in Container Apps is assigned a unique identifier."）で、非アクティブ
    # revision は最大 100 件保持されるため、Day 4 の 元サーバー → 復元先 → 元サーバー の往復では
    # 戻しの apply が過去に使った suffix を再利用して既存 revision と衝突する（詳細は ADR-0018 追記）。
    # suffix を指定しなければ Azure が一意な名前を自動生成する。
    # 出典: https://learn.microsoft.com/en-us/azure/container-apps/revisions

    # min_replicas 1（当初 0 = スケールゼロ。2026-08-30 変更 = ADR-0025）: min_replicas 0 の
    # cold start（AssigningReplica→ContainerStarted p50 15.45s / max 39.78s、n=172）が外形監視の
    # 可用性 SLI を汚染し、probe 失敗 3 件がすべて「アプリは正常起動していたのに --max-time 30 が
    # 先に諦めた」偽陽性だったことが実測で確定したため、観測期間中は 1 レプリカ常駐に切り替える。
    # ADR-0015 の「コールドスタートの遅延は許容する」は walking skeleton 段階の前提であり、
    # 外形監視で SLI を蓄積する現フェーズでは成り立たない（前提の変化。ADR-0025 が正本）。
    min_replicas = 1
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
      # 命名: 「設定のハッシュを pod / revision 定義に埋めて、設定変更で必ず再作成させる」のは
      # Helm 公式が `checksum/config` アノテーションとして文書化しているパターン。
      # 出典: https://helm.sh/docs/howto/charts_tips_and_tricks/
      # （env 名を DSN_CONFIG_CHECKSUM としたのはこの標準語に接続するため。Issue #133。
      #   値のプレフィクス "dsn-" は既存 revision との差分の意味を保つため変えていない）
      dynamic "env" {
        for_each = var.database_url == "" ? [] : ["dsn-config-checksum"]
        content {
          name  = "DSN_CONFIG_CHECKSUM"
          value = "dsn-${nonsensitive(substr(sha256(var.database_url), 0, 8))}"
        }
      }

      # /chat 保護（#107）
      dynamic "env" {
        for_each = var.chat_api_key == "" ? [] : ["chat-api-key"]
        content {
          name        = "CHAT_API_KEY"
          secret_name = "chat-api-key"
        }
      }

      # 緊急遮断フラグ（値の変更は revision-scope なので必ず新 revision が作られ、
      # 反映漏れが起きない = DSN_CONFIG_CHECKSUM と同じ理屈）
      env {
        name  = "CHAT_DISABLED"
        value = var.chat_disabled ? "true" : "false"
      }

      # CHAT_API_KEY rotation の revision 反映担保（ADR-0027「付随する決定」）。
      # secret 更新は既存 revision に自動反映されないため、鍵のハッシュを revision-scope の
      # 非 secret env として frontend と backend serving の両 template に同一値で持たせ、
      # rotation の apply が両 app で必ず新 revision を作るようにする（DSN_CONFIG_CHECKSUM と
      # 同型。sha256 先頭 8 桁のみで不可逆）。cross-app の同時性・原子性は主張しない
      # （revision 切替は app ごとに独立。partial apply 時の収束手順は
      # vnet-integration-cutover.md §6-2）。
      dynamic "env" {
        for_each = var.chat_api_key == "" ? [] : ["chat-api-key-config-checksum"]
        content {
          name  = "CHAT_API_KEY_CONFIG_CHECKSUM"
          value = "key-${nonsensitive(substr(sha256(var.chat_api_key), 0, 8))}"
        }
      }

      # LLM provider 切替（Issue #195。ADR-0009）。空なら env を注入せず backend の既定
      # "stub"（ADR-0004）のまま動く。rollback = 変数を空へ戻して apply
      # （手順は docs/operations/llm-provider-cutover.md）
      dynamic "env" {
        for_each = var.llm_provider == "" ? [] : ["llm-provider"]
        content {
          name  = "LLM_PROVIDER"
          value = var.llm_provider
        }
      }

      # Azure OpenAI 接続設定（Issue #195）。endpoint は secret ではない接続先 URL。
      # api-version / deployment 名は空なら注入せず backend の既定
      # （backend/app/config.py: "2024-10-21" / "chat" / "embedding"）が使われる
      dynamic "env" {
        for_each = var.azure_openai_endpoint == "" ? [] : ["azure-openai-endpoint"]
        content {
          name  = "AZURE_OPENAI_ENDPOINT"
          value = var.azure_openai_endpoint
        }
      }

      dynamic "env" {
        for_each = var.azure_openai_api_key == "" ? [] : ["azure-openai-api-key"]
        content {
          name        = "AZURE_OPENAI_API_KEY"
          secret_name = "azure-openai-api-key"
        }
      }

      dynamic "env" {
        for_each = var.azure_openai_api_version == "" ? [] : ["azure-openai-api-version"]
        content {
          name  = "AZURE_OPENAI_API_VERSION"
          value = var.azure_openai_api_version
        }
      }

      dynamic "env" {
        for_each = var.azure_openai_chat_deployment == "" ? [] : ["azure-openai-chat-deployment"]
        content {
          name  = "AZURE_OPENAI_CHAT_DEPLOYMENT"
          value = var.azure_openai_chat_deployment
        }
      }

      dynamic "env" {
        for_each = var.azure_openai_embedding_deployment == "" ? [] : ["azure-openai-embedding-deployment"]
        content {
          name  = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
          value = var.azure_openai_embedding_deployment
        }
      }

      # AZURE_OPENAI_API_KEY rotation の revision 反映担保（ADR-0027「付随する決定」が規定した
      # AZURE_OPENAI_CONFIG_CHECKSUM。DSN_CONFIG_CHECKSUM / CHAT_API_KEY_CONFIG_CHECKSUM と同型）。
      # secret 更新は既存 revision に自動反映されないため、key のハッシュを revision-scope の
      # 非 secret env として template に持たせ、rotation の apply が必ず新 revision を作るように
      # する。ハッシュは sha256 の先頭 8 桁のみで不可逆（key は復元できない）。
      # この key を参照するのは backend serving のみのため片側適用（CHAT_API_KEY と異なり
      # cross-app の同期対象がない）
      dynamic "env" {
        for_each = var.azure_openai_api_key == "" ? [] : ["azure-openai-config-checksum"]
        content {
          name  = "AZURE_OPENAI_CONFIG_CHECKSUM"
          value = "aoai-${nonsensitive(substr(sha256(var.azure_openai_api_key), 0, 8))}"
        }
      }
    }
  }

  ingress {
    # ADR-0027 決定 1: 恒久構成では internal ingress（backend_ingress_external = false）にし、
    # internet から直接到達できる面を frontend のみにする。切替は Easy Auth 経由の疎通実測が
    # 成立した後（手順は vnet-integration-cutover.md §7）。true の間は従来どおり外部公開
    # （/readyz 検証・bootstrap 段階の経路）。
    external_enabled = var.backend_ingress_external

    # internal 切替後の app 間通信は http で行う（frontend の BACKEND_ORIGIN =
    # http://<internal FQDN>。local.backend_origin 参照）。公式ドキュメントは同一環境内の
    # app 間呼び出しに `http://<APP_NAME>` を推奨し、環境内トラフィックは環境外に出ない
    # （出典: https://learn.microsoft.com/en-us/azure/container-apps/connect-apps ）。
    # internal FQDN（<app>.internal.<default domain>）への https は、環境の既定証明書が
    # この 1 階層深い名前をカバーするか公式に断定できないため使わない。
    # external の間（= internet に露出している間）は既定どおり https を強制する。
    allow_insecure_connections = !var.backend_ingress_external

    target_port = var.container_target_port

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  lifecycle {
    precondition {
      # LLM_PROVIDER=azure-openai の env だけ注入して接続変数が欠ける計画を弾く
      # （backend は起動時 MissingEnvError で落ちる = 気づくのが apply 後になる。
      # plan 時に検査して事故を前倒しする。Issue #195。ADR-0009 の必須変数）
      condition     = var.llm_provider != "azure-openai" || (var.azure_openai_endpoint != "" && var.azure_openai_api_key != "")
      error_message = "llm_provider = \"azure-openai\" のときは azure_openai_endpoint / azure_openai_api_key が必須です（欠けると backend が起動時 MissingEnvError で落ちる。ADR-0009）。"
    }
  }
}

# ---------------------------------------------------------------------------
# 運用経路（ops Container App + マイグレーション Job。ADR-0018）
# ---------------------------------------------------------------------------

# private access 化後、DB へは VNet 内からしか到達できない。手元の psql / alembic の代わりに、
# VNet 内の運用コンテナを唯一の対話経路とする（「本番 DB へ手元から直接繋がない」運用。ADR-0018）。
# - ingress なし: 外に晒す必要が一切ない
# - min_replicas 1（当初 0。2026-08-22 是正 = ADR-0015 追記）: ingress なしの Container App には
#   スケールインを駆動する仕組みが無く、min_replicas = 0 を宣言してもプロビジョン時のレプリカ 1 が
#   常駐し続けることを実測（同一設定の serving は ingress の暗黙 HTTP スケールルールで Replicas 0 まで
#   縮退することを同日実測。公式 scale-app の「ingress 無し + rule 無しはゼロに落ちて起き上がれない」
#   という Important 記述とは逆の実挙動）。さらに 0 宣言は idle 課金の適格条件
#   "To be eligible for idle charges, a revision must be: Configured with a minimum replica count
#    greater than zero / Scaled to the minimum replica count"
#   （出典: https://learn.microsoft.com/en-us/azure/container-apps/billing ）を外し、常駐レプリカが
#   active 単価で課金されていた。宣言を実態（常駐 1）に合わせて食い違いを解消する。exec は Running
#   レプリカがあれば直接つながる（実測）ため、使うたびに min-replicas を上下させる運用も廃止
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
    # 非 secret 環境変数 DSN_CONFIG_CHECKSUM（revision-scope。下の container ブロック）で行い、
    # revision_suffix 固定は往復 apply での名前衝突のため使わない（ADR-0018 追記）

    # 1 の理由は resource 冒頭のコメント（0 宣言は実態と食い違い、idle 適格も外していた）
    min_replicas = 1
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
        name  = "DSN_CONFIG_CHECKSUM"
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
# Container App 側のような DSN_CONFIG_CHECKSUM によるコード担保は不要。secret 更新後の挙動
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
    }
  }

  lifecycle {
    precondition {
      condition     = var.database_url != ""
      error_message = "ops_container_image を指定する場合は database_url も必須です（migration Job は DB 接続のためだけに存在する）。"
    }
  }
}


# recovery marker の刻み + スナップショット採取 Job（Issue #104。Schedule トリガー・毎分。
# 設計の正本: docs/operations/credit-window-execution-plan.md §5-3。
# 位置づけの正本: docs/adr/0021-heartbeat-table-as-recovery-marker.md — 毎分の書き込みは
# PITR の復旧時点を確定させる recovery marker であり、負荷生成ではない。負荷生成
# （churn generator）は Issue #112 / PR #120 の別 Job で、2026-08-27 時点で未マージ）。
# - cron_expression が azurerm 5.1.0 の schedule_trigger_config に存在することは
#   `terraform providers schema -json` で確認済み（2026-08-23。必須属性は cron_expression のみ）
# - 実行内容は ops イメージ内の /app/observability/collect.sql（heartbeat INSERT +
#   カウンタ UPDATE を毎分、統計スナップショットは分 % 5 = 0、pgstattuple は分 = 0 のみ）
# - コスト目安: 実行数秒 × 1440 回/日 × active 単価 0.0000075 USD/秒 ≈ 0.05 USD/日前後
#   + Consumption 無料枠吸収（#104 の受け入れ条件でデプロイ後に実測する）
# - migration Job と同じく revision の概念なし。失敗はリトライしない（毎分の次回実行が
#   事実上のリトライ。連続失敗は /readyz の鮮度（#106 の系列別ゲート）が検出する）
resource "azurerm_container_app_job" "obs_collect" {
  count = var.ops_container_image == "" ? 0 : 1

  name                         = "caj-felisaichatbot-dev-obs"
  location                     = data.azurerm_resource_group.dev.location
  resource_group_name          = data.azurerm_resource_group.dev.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"

  # 毎分実行のため 55 秒で必ず打ち切る（次回実行と重ねない）。psql 1 本は数秒で終わる想定。
  #
  # この値は意図的に上げない（Issue #131 の切り分け結果。2026-08-26 決定）:
  # - DeadlineExceeded 失敗（フェーズ 1 で 0.95%）の実体は SQL ではなく ACA 側の
  #   コンテナ起動パイプライン（起動遅延 or 完了イベント喪失）で、採取データの欠落は 0 件
  # - 90〜110s へ延長すると毎分 cron と重なって同時 2 execution が併走し得る。
  #   collect.sql のゲートは経過時間ベースなので二重採取は防げるが、heartbeat が
  #   同一分に 2 行入り得て、分単位の完全性カウント（名目件数との一致判定）の意味が変わる
  # - 完了イベント喪失型の失敗は timeout をいくら延ばしても救えない
  # 合否は採取データの完全性で判定し、DeadlineExceeded は別指標として数える
  # （正本: docs/operations/obs-job-success-criteria.md）
  replica_timeout_in_seconds = 55
  replica_retry_limit        = 0

  schedule_trigger_config {
    cron_expression          = "* * * * *"
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
      name   = "obs-collect"
      image  = var.ops_container_image
      cpu    = 0.25
      memory = "0.5Gi"

      # $DATABASE_URL の展開にシェルが必要（exec 形式では環境変数が展開されない。
      # az containerapp exec で実測済みの挙動と同型）
      command = ["/bin/sh", "-c", "psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 -f /app/observability/collect.sql"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.database_url != ""
      error_message = "ops_container_image を指定する場合は database_url も必須です（採取 Job は DB へ書き込むためだけに存在する）。"
    }
  }
}

# ---------------------------------------------------------------------------
# RAG データ投入経路（seed Job + embedding backfill Job。Issue #196）
# ---------------------------------------------------------------------------

# 気象庁シードデータの投入 Job（Manual トリガー。migrate Job と同型）。
# `az containerapp job start` で起動し、`python -m app.ingest`（diff-sync）を 1 回実行して終了する。
# シードに現れない行を削除して同期する destructive な操作を含むため、再実行安全な
# backfill Job（下の embed_backfill）とはリソースを分離する（frontend-sse-execution-plan.md §1 の 4
# の作業単位区分）。投入自体は冪等（再実行しても行数は増えない。backend/app/ingest/runner.py）。
# ops イメージは runtime ステージ（app/ + .venv）を継承しており `python -m app.ingest` を
# 実行できる（backend/Dockerfile）。
# Job には revision の概念がないため CONFIG_CHECKSUM 系のコード担保は不要（migrate Job と同じ理屈）。
resource "azurerm_container_app_job" "seed" {
  count = var.ops_container_image == "" ? 0 : 1

  name                         = "caj-felisaichatbot-dev-seed"
  location                     = data.azurerm_resource_group.dev.location
  resource_group_name          = data.azurerm_resource_group.dev.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"

  # シードは 4 テーブル計 119 行（38 documents + 53 properties + 15 objects + 13 sources）の
  # INSERT / DELETE のみで数秒で終わる想定。migrate Job と同じ 10 分で打ち切り、無限に待たない
  replica_timeout_in_seconds = 600
  # 失敗時に自動で叩き直さない（destructive な diff-sync の再試行は人間が状態を確認してから。
  # migrate Job と同じ方針）
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
      name   = "seed"
      image  = var.ops_container_image
      cpu    = 0.25
      memory = "0.5Gi"

      command = ["python", "-m", "app.ingest"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.database_url != ""
      error_message = "ops_container_image を指定する場合は database_url も必須です（seed Job は DB へ書き込むためだけに存在する）。"
    }
  }
}

# embedding backfill Job（Manual トリガー。migrate Job と同型）。
# `python -m app.ingest --embed` を 1 回実行して終了する。--embed は ingest（diff-sync）→
# backfill の順を CLI 内部で担保し（ADR-0010: この順で実行すれば文面改訂も自然に再生成対象に
# なる）、backfill 自体は `embedding IS NULL` の行のみを対象とする冪等な実行（再実行安全。
# backend/app/ingest/embeddings.py）。
# 実 embedding の生成には LLM_PROVIDER=azure-openai と AZURE_OPENAI_* の注入が必要
# （backend serving と同じ作法。Issue #195 / ADR-0009）。
resource "azurerm_container_app_job" "embed_backfill" {
  # llm_provider が azure-openai のときだけ作る。stub のまま backfill を実行すると決定的な
  # ダミーベクトルが embedding 列を埋めてしまい、以後の backfill が対象外（NOT NULL）として
  # スキップする = 実データに対してベクトル検索が成立しない状態が固定化されるため、
  # その経路をリソースの不在で塞ぐ（ADR-0004 の stub は CI・テスト用であり deployed 環境の
  # backfill に使う経路を作らない）
  count = var.ops_container_image != "" && var.llm_provider == "azure-openai" ? 1 : 0

  name                         = "caj-felisaichatbot-dev-embed"
  location                     = data.azurerm_resource_group.dev.location
  resource_group_name          = data.azurerm_resource_group.dev.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"

  # 対象は最大でも documents 全 38 行の embedding 生成（1 行ずつ直列。retry 込みでも数分想定）。
  # migrate Job と同じ 10 分で打ち切り、無限に待たない。打ち切られても未 commit 分は巻き戻り、
  # 次回実行が NULL の行だけを再対象にする（backend/app/ingest/embeddings.py）
  replica_timeout_in_seconds = 600
  # 失敗時に自動で叩き直さない（token 課金を伴う実行の再試行は人間が消費実測を確認してから）
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

  secret {
    name  = "azure-openai-api-key"
    value = var.azure_openai_api_key
  }

  template {
    container {
      name   = "embed-backfill"
      image  = var.ops_container_image
      cpu    = 0.25
      memory = "0.5Gi"

      command = ["python", "-m", "app.ingest", "--embed"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      # LLM provider と Azure OpenAI 接続設定（backend serving と同じ注入作法。Issue #195）。
      # count のガードにより、この Job が存在する時点で llm_provider は "azure-openai"
      env {
        name  = "LLM_PROVIDER"
        value = var.llm_provider
      }

      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = var.azure_openai_endpoint
      }

      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "azure-openai-api-key"
      }

      # api-version / deployment 名は空なら注入せず backend の既定
      # （backend/app/config.py: "2024-10-21" / "chat" / "embedding"）が使われる
      dynamic "env" {
        for_each = var.azure_openai_api_version == "" ? [] : ["azure-openai-api-version"]
        content {
          name  = "AZURE_OPENAI_API_VERSION"
          value = var.azure_openai_api_version
        }
      }

      dynamic "env" {
        for_each = var.azure_openai_chat_deployment == "" ? [] : ["azure-openai-chat-deployment"]
        content {
          name  = "AZURE_OPENAI_CHAT_DEPLOYMENT"
          value = var.azure_openai_chat_deployment
        }
      }

      dynamic "env" {
        for_each = var.azure_openai_embedding_deployment == "" ? [] : ["azure-openai-embedding-deployment"]
        content {
          name  = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
          value = var.azure_openai_embedding_deployment
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.database_url != ""
      error_message = "ops_container_image を指定する場合は database_url も必須です（backfill Job は DB へ書き込むためだけに存在する）。"
    }
    precondition {
      # serving 側と同じ検査（Issue #195 の lifecycle precondition と同型）。count のガードで
      # llm_provider = "azure-openai" のときにしか評価されないが、接続変数の欠落は Job 実行時の
      # MissingEnvError まで気づけないため plan 時に前倒しで弾く
      condition     = var.azure_openai_endpoint != "" && var.azure_openai_api_key != ""
      error_message = "embedding backfill Job には azure_openai_endpoint / azure_openai_api_key が必須です（欠けると Job が実行時 MissingEnvError で落ちる。ADR-0009）。"
    }
  }
}

# ---------------------------------------------------------------------------
# frontend Container App + Easy Auth（ADR-0027。Issue #194）
# ---------------------------------------------------------------------------

# Easy Auth の openIdIssuer 組み立てに tenant ID が要る（値はコードに書かない）
data "azurerm_client_config" "current" {}

locals {
  # BFF / /readyz proxy が backend を呼ぶ base URL（ADR-0027 決定 3）。
  # - external の間: https://<external FQDN>（従来の公開経路）
  # - internal 切替後: http://<internal FQDN>。同一環境内の app 間通信は Envoy 経由で
  #   環境外に出ず、公式ドキュメントも app 間呼び出しに http を推奨する
  #   （出典: https://learn.microsoft.com/en-us/azure/container-apps/connect-apps ）。
  #   internal FQDN への https を使わない理由は serving 側 ingress のコメントを参照。
  # ingress[0].fqdn は external / internal の切替に追従して同じ apply 内で新 FQDN に変わるため、
  # 切替と BACKEND_ORIGIN の付け替えが 1 回の apply で完結する。
  backend_origin = "${var.backend_ingress_external ? "https" : "http"}://${azurerm_container_app.main.ingress[0].fqdn}"
}

# frontend（Next.js standalone。BFF + /readyz 透過 proxy）。
# frontend_container_image が空の間は作らない（ADR-0027 決定 6 の fail-closed bootstrap:
# 第 1 段は chat_disabled = true かつ frontend 未作成で apply する）。
resource "azurerm_container_app" "front" {
  count = var.frontend_container_image == "" ? 0 : 1

  # ADR-0013 の命名規則（qualifier `-front`）。ops（`-ops`）と同じ付け方
  name                         = "ca-felisaichatbot-dev-front"
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

  # BFF が server 側で付与する /chat の API キー（ADR-0027 決定 2。ブラウザには配らない）
  secret {
    name  = "chat-api-key"
    value = var.chat_api_key
  }

  # Easy Auth（authConfigs）が参照する client secret。secret 名は ACA の Entra 構成が使う
  # 既定名に合わせる（出典: https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra ）
  secret {
    name  = "microsoft-provider-authentication-secret"
    value = var.easy_auth_client_secret
  }

  template {
    # ADR-0027 決定 9: scale-to-zero の cold start が /readyz proxy 経由の外形監視と
    # client-visible latency の偽障害になることを作成時から排除する（ADR-0025 と同型の予防採用）
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "front"
      image  = var.frontend_container_image
      cpu    = 0.25
      memory = "0.5Gi"

      # BFF / /readyz proxy の upstream（runtime に読む server 専用変数。ADR-0027 決定 3）
      env {
        name  = "BACKEND_ORIGIN"
        value = local.backend_origin
      }

      env {
        name        = "CHAT_API_KEY"
        secret_name = "chat-api-key"
      }

      # rotation の revision 反映担保（backend serving 側と同一値。ADR-0027「付随する決定」。
      # 詳細コメントは serving 側の同名 env を参照）
      env {
        name  = "CHAT_API_KEY_CONFIG_CHECKSUM"
        value = "key-${nonsensitive(substr(sha256(var.chat_api_key), 0, 8))}"
      }
    }
  }

  ingress {
    # 公開面は frontend のみ（ADR-0027 決定 1）。認証は authConfigs（Easy Auth）が担う
    external_enabled = true
    # Next.js standalone server の listen ポート（frontend/Dockerfile の PORT=3000）
    target_port = 3000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  lifecycle {
    precondition {
      # authConfigs 無しの frontend を計画に載せない（ADR-0027 決定 6 の fail-closed。
      # Easy Auth の資材が揃うまで frontend は作成できない）
      condition     = var.easy_auth_client_id != "" && var.easy_auth_client_secret != ""
      error_message = "frontend_container_image を指定する場合は easy_auth_client_id / easy_auth_client_secret も必須です（authConfigs 無しの frontend 公開を防ぐ。ADR-0027 決定 6）。"
    }
    precondition {
      # BFF は CHAT_API_KEY を server 側で付与するためだけに存在する（鍵なし公開を防ぐ）
      condition     = var.chat_api_key != ""
      error_message = "frontend_container_image を指定する場合は chat_api_key も必須です（BFF が server 側で付与する鍵。ADR-0027 決定 2）。"
    }
  }
}

# Easy Auth 設定（Microsoft.App/containerApps/authConfigs）。azurerm 5.1.0 に該当リソースが
# 無いため azapi_resource で管理する（ADR-0027 決定 1。子リソース名は ARM の固定名 "current"。
# 出典: https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps/authconfigs ）。
# API バージョンは Microsoft.App の stable（2025-07-01。az provider show で確認済み）。
#
# 注意（ADR-0027 決定 6）: frontend 作成〜authConfigs 適用の間には匿名到達可能な窓が
# 構造的に存在する。この窓は chat_disabled = true の維持（bootstrap 第 2 段）で塞ぐ。
resource "azapi_resource" "front_auth" {
  count = var.frontend_container_image == "" ? 0 : 1

  type      = "Microsoft.App/containerApps/authConfigs@2025-07-01"
  name      = "current"
  parent_id = azurerm_container_app.front[0].id

  body = {
    properties = {
      platform = {
        enabled = true
      }
      globalValidation = {
        # ブラウザ利用者を Entra ID のサインインへ誘導する（supported client はブラウザのみ）
        unauthenticatedClientAction = "RedirectToLoginPage"
        redirectToProvider          = "azureactivedirectory"
        # /readyz 透過 proxy だけを未認証で通す（ADR-0027 決定 8。外形監視 readyz-probe の
        # 経路。ADR-0026 の URL 契約 https://<host>/readyz に適合）
        excludedPaths = ["/readyz"]
      }
      identityProviders = {
        azureActiveDirectory = {
          registration = {
            openIdIssuer            = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
            clientId                = var.easy_auth_client_id
            clientSecretSettingName = "microsoft-provider-authentication-secret"
          }
        }
      }
    }
  }
}
