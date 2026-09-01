variable "resource_group_name" {
  description = <<-DESC
    Terraform 管理リソース専用の resource group 名（bootstrap.md §11-3 で手動作成）。
    persistent 層と同じ RG を使う。CI 用 service principal の Contributor スコープは
    この RG に限定されている（ADR-0012）。
  DESC
  type        = string
  default     = "rg-felisaichatbot-dev-tf"
}

variable "acr_name" {
  description = "ACR 名（グローバル一意・英数字のみ。ADR-0013 の予約名。bootstrap.md §3 で空き確認済み）"
  type        = string
  default     = "felisaichatbotacrdev"
}

variable "container_image" {
  description = <<-DESC
    Container App にデプロイするイメージの完全参照（例: felisaichatbotacrdev.azurecr.io/hello-world:sha-abc1234）。
    タグは git commit SHA 由来の不変タグを使い、latest は使わない（ADR-0015）。
    walking skeleton は hello-world イメージから始め、経路開通後に backend イメージへ差し替える
    （bootstrap.md「Day 3 の方針」方針1）。
  DESC
  type        = string

  validation {
    # タグ部が空（"image:"）や空白入り（"image:bad tag"）の参照を弾き、latest を禁止する。
    # digest 併記（image@sha256:<hex>）も末尾が ":<hex>" のためこの regex を満たす。
    condition     = can(regex(":[a-zA-Z0-9._-]+$", var.container_image)) && !endswith(var.container_image, ":latest")
    error_message = "container_image はタグ付きの完全参照（タグは英数字と . _ - のみ）を指定し、latest タグは使わないでください（ADR-0015 のイメージタグ方針）。"
  }
}

variable "container_target_port" {
  description = "コンテナが listen するポート。backend（uvicorn）は 8000。hello-world イメージの場合はそのイメージの listen ポートに合わせて上書きする"
  type        = number
  default     = 8000
}

variable "database_url" {
  description = <<-DESC
    backend が読む DATABASE_URL（postgresql://... 形式。backend/app/db.py は psycopg で
    素の libpq DSN を受ける）。Container App の secret として渡す。
    hello-world 段階（DB 接続なし）では空のままでよく、その場合 secret / 環境変数自体を作らない。
    実値はコミットせず TF_VAR_database_url 環境変数（CI では GitHub Secrets）で渡す。
  DESC
  type        = string
  sensitive   = true
  default     = ""

  validation {
    # 形式誤りをコンテナ実行時ではなく plan 時に弾く。backend/app/db.py（psycopg）が受けるのは
    # 素の libpq DSN（postgresql:// スキーム）。SQLAlchemy 方言付き（postgresql+asyncpg:// 等）は
    # psycopg には渡せないため、ここでは受け付けない。
    condition     = var.database_url == "" || can(regex("^postgresql://", var.database_url))
    error_message = "database_url は空か postgresql:// で始まる libpq DSN を指定してください（backend/app/db.py は psycopg で接続する）。"
  }
}

variable "acr_pull_identity_name" {
  description = <<-DESC
    Container App が ACR pull に使う user-assigned managed identity 名（ADR-0013 の予約名）。
    identity 本体と AcrPull ロール割当（RG スコープ）は Terraform 管理外・手動作成
    （ADR-0015 選択肢 6-(b)。台帳 azure-resource-inventory.md #8 / #9 が正本）。
    手動作成が済むまで、この層の apply は通らない前提。
  DESC
  type        = string
  default     = "id-felisaichatbot-dev"
}

variable "log_analytics_workspace_name" {
  description = "persistent 層が管理する Log Analytics workspace 名（ADR-0016。data source 参照のみ。この層では作成・変更しない）"
  type        = string
  default     = "log-felisaichatbot-dev"
}

variable "vnet_name" {
  description = "persistent 層が管理する VNet 名（ADR-0018。data source 参照のみ。この層では作成・変更しない）"
  type        = string
  default     = "vnet-felisaichatbot-dev"
}

variable "aca_subnet_name" {
  description = <<-DESC
    persistent 層が管理する Container Apps Environment 用委任サブネット名（ADR-0018）。
    `Microsoft.App/environments` へ委任済みの /27。この層は CAE の infrastructure_subnet_id として
    data source 参照するのみで、サブネット本体の変更は persistent 層でしか行わない。
  DESC
  type        = string
  default     = "snet-felisaichatbot-dev-aca"
}

variable "ops_container_image" {
  description = <<-DESC
    運用コンテナ（ops Container App / migration Job）のイメージ完全参照
    （例: felisaichatbotacrdev.azurecr.io/backend-ops:sha-abc1234。backend/Dockerfile の ops ターゲット）。
    空のままなら ops Container App と migration Job は作られない（hello-world 段階や
    ops イメージ未 push の状態でも apply を通すため）。指定する場合は database_url も必須
    （各リソースの precondition が検査する）。
  DESC
  type        = string
  default     = ""

  validation {
    condition     = var.ops_container_image == "" || (can(regex(":[a-zA-Z0-9._-]+$", var.ops_container_image)) && !endswith(var.ops_container_image, ":latest"))
    error_message = "ops_container_image は空か、タグ付きの完全参照（タグは英数字と . _ - のみ）を指定し、latest タグは使わないでください（ADR-0015 のイメージタグ方針）。"
  }
}

variable "chat_api_key" {
  description = <<-DESC
    /chat 保護用の API キー（Issue #107。ADR-0020 の常時稼働の先行ゲート）。
    secret のため tfvars に書かず TF_VAR_chat_api_key で渡す（.env 管理。コミット禁止）。
    空のままなら backend は fail-closed（/chat が 404）で起動する。
  DESC
  type        = string
  sensitive   = true
  default     = ""
}

variable "chat_disabled" {
  description = "/chat の緊急遮断フラグ（消費超過時の打ち切りスイッチ。credit-window-execution-plan.md §9）。true で /chat が 404 になる。/readyz は影響を受けない"
  type        = bool
  default     = false
}

variable "frontend_container_image" {
  description = <<-DESC
    frontend Container App のイメージ完全参照
    （例: felisaichatbotacrdev.azurecr.io/frontend:sha-abc1234。frontend/Dockerfile）。
    空のままなら frontend Container App と authConfigs は作られない（ADR-0027 決定 6 の
    fail-closed bootstrap 順序: chat_disabled = true かつ frontend 未作成の第 1 段 apply を
    成立させるため）。指定する場合は easy_auth_client_id / easy_auth_client_secret も必須
    （frontend の precondition が検査する。authConfigs 無しの frontend を作らない）。
  DESC
  type        = string
  default     = ""

  validation {
    condition     = var.frontend_container_image == "" || (can(regex(":[a-zA-Z0-9._-]+$", var.frontend_container_image)) && !endswith(var.frontend_container_image, ":latest"))
    error_message = "frontend_container_image は空か、タグ付きの完全参照（タグは英数字と . _ - のみ）を指定し、latest タグは使わないでください（ADR-0015 のイメージタグ方針）。"
  }
}

variable "backend_ingress_external" {
  description = <<-DESC
    backend（serving）の ingress を外部公開するか（ADR-0027 決定 1 の cutover スイッチ）。
    true（既定）= external ingress（従来どおり internet から到達可能）。
    false = internal ingress（同一 Container Apps Environment 内からのみ到達可能。
    frontend の BFF / /readyz proxy が唯一の経路になる）。
    false への切替は Easy Auth 経由の疎通実測が成立した後にのみ行う
    （手順は docs/operations/vnet-integration-cutover.md §7）。
  DESC
  type        = bool
  default     = true
}

variable "easy_auth_client_id" {
  description = <<-DESC
    Easy Auth（Entra ID）用 app registration の application (client) ID。
    app registration 本体は Terraform 管理外・ユーザー実行
    （ADR-0012 の権限境界。手順は docs/operations/entra-easy-auth-setup.md）。
    frontend_container_image を指定する場合は必須（precondition が検査する）。
  DESC
  type        = string
  default     = ""
}

variable "easy_auth_client_secret" {
  description = <<-DESC
    Easy Auth 用 app registration の client secret。frontend Container App の secret
    （microsoft-provider-authentication-secret）として保持し、authConfigs が参照する。
    実値はコミットせず TF_VAR_easy_auth_client_secret 環境変数（.env 管理）で渡す。
  DESC
  type        = string
  sensitive   = true
  default     = ""
}

variable "llm_provider" {
  description = <<-DESC
    backend serving の LLM provider 切替（Issue #195。ADR-0009）。
    空（既定）= LLM_PROVIDER env を注入しない = backend/app/config.py の既定 "stub"（ADR-0004）。
    "azure-openai" = 実 Azure OpenAI へ切り替える（azure_openai_endpoint / azure_openai_api_key が
    必須になる。azurerm_container_app.main の precondition が検査する）。
    rollback は空へ戻して apply する（手順は docs/operations/llm-provider-cutover.md）。
  DESC
  type        = string
  default     = ""

  validation {
    condition     = contains(["", "azure-openai"], var.llm_provider)
    error_message = "llm_provider は空（stub 既定のまま）か \"azure-openai\" のみを指定してください（backend/app/llm/client.py がサポートする実 provider は azure-openai のみ。ADR-0009）。"
  }
}

variable "azure_openai_endpoint" {
  description = <<-DESC
    Azure OpenAI のエンドポイント URL（例: https://<account>.openai.azure.com/）。
    リソース本体は Terraform 管理外（ADR-0014）で、ここでは接続先として参照するのみ。
    secret ではないが、実値は .env の TF_VAR_azure_openai_endpoint で渡す（tfvars に書かない）。
  DESC
  type        = string
  default     = ""

  validation {
    condition     = var.azure_openai_endpoint == "" || can(regex("^https://", var.azure_openai_endpoint))
    error_message = "azure_openai_endpoint は空か https:// で始まる URL を指定してください。"
  }
}

variable "azure_openai_api_key" {
  description = <<-DESC
    Azure OpenAI の API キー（ADR-0009。マネージド ID 化までの暫定 = production-readiness §2）。
    Container Apps の secret（azure-openai-api-key）として保持し、tfvars に書かず
    TF_VAR_azure_openai_api_key で渡す（.env 管理。コミット禁止）。
    値の変更は AZURE_OPENAI_CONFIG_CHECKSUM env（ADR-0027「付随する決定」と同型）を通じて
    必ず新 revision を作る。
  DESC
  type        = string
  sensitive   = true
  default     = ""
}

variable "azure_openai_api_version" {
  description = <<-DESC
    Azure OpenAI の api-version。空なら env を注入せず backend の既定（backend/app/config.py の
    "2024-10-21"。ADR-0009 で疎通実測済みの GA 版）が使われる。
  DESC
  type        = string
  default     = ""
}

variable "azure_openai_chat_deployment" {
  description = "Azure OpenAI の chat deployment 名。空なら env を注入せず backend の既定（\"chat\"）が使われる（ADR-0009）"
  type        = string
  default     = ""
}

variable "azure_openai_embedding_deployment" {
  description = "Azure OpenAI の embedding deployment 名。空なら env を注入せず backend の既定（\"embedding\"）が使われる（ADR-0009）"
  type        = string
  default     = ""
}
