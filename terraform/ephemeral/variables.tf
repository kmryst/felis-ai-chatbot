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
  default     = "felisaichatbotacrdev02"
}

variable "container_image" {
  description = <<-DESC
    Container App にデプロイするイメージの完全参照（例: felisaichatbotacrdev02.azurecr.io/hello-world:sha-abc1234）。
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

  validation {
    # managed-identity モードでは DSN にパスワードを含めない（Issue #275。ADR-0031）。
    # ユーザー情報部（`user:password@`）にコロンがあればパスワード入りと見なして弾く。
    # DSN のユーザー名は managed identity の表示名（pgaadauth_create_principal で作ったロール名）。
    condition     = var.db_auth_mode != "managed-identity" || var.database_url == "" || !can(regex("^postgresql://[^/@]*:[^/@]*@", var.database_url))
    error_message = "db_auth_mode = \"managed-identity\" のときは database_url にパスワードを含めないでください（接続時に Entra のアクセストークンを password として渡す。ADR-0031）。"
  }
}

variable "db_auth_mode" {
  description = <<-DESC
    backend / Job / ops が DB へ接続するときの認証方式（Issue #275。ADR-0031）。
    "managed-identity"（既定）= Container Apps の user-assigned managed identity
    （acr_pull_identity_name）で Entra のアクセストークンを取得し password として渡す。
    DB_AUTH_MODE と AZURE_CLIENT_ID を各コンテナに注入し、database_url はパスワード無しの DSN にする。
    "password" = 従来どおり database_url に含まれるパスワードで接続する（rollback 用。
    PostgreSQL 側の password_auth_enabled が true の間だけ機能する）。
  DESC
  type        = string
  default     = "managed-identity"

  validation {
    condition     = contains(["password", "managed-identity"], var.db_auth_mode)
    error_message = "db_auth_mode は \"password\" か \"managed-identity\" を指定してください（backend/app/config.py の DB_AUTH_MODE と同じ語彙）。"
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
    （例: felisaichatbotacrdev02.azurecr.io/backend-ops:sha-abc1234。backend/Dockerfile の ops ターゲット）。
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

variable "key_vault_name" {
  description = <<-DESC
    /chat 保護用 API キー（Issue #107）を置く Azure Key Vault 名（persistent 層が作る。
    Issue #286 / ADR-0032。ADR-0013 の予約名）。この層は data "azurerm_key_vault" で参照し、
    secret `chat-api-key` をバージョン無しの Key Vault 参照で Container Apps に渡す。
    値は tfvars にも state にも入らない。ローテーションは persistent 層の chat_api_key_version を
    +1 して apply する（この層の apply は不要）。
  DESC
  type        = string
  default     = "kv-felisaichatbot-dev"

  validation {
    condition     = length(trimspace(var.key_vault_name)) > 0
    error_message = "key_vault_name は空にできません。"
  }
}

variable "chat_disabled" {
  description = "/chat の緊急遮断フラグ（消費超過時の打ち切りスイッチ。credit-window-execution-plan.md §9）。true で /chat が 404 になる。/readyz は影響を受けない"
  type        = bool
  default     = false
}

variable "frontend_container_image" {
  description = <<-DESC
    frontend Container App のイメージ完全参照
    （例: felisaichatbotacrdev02.azurecr.io/frontend:sha-abc1234。frontend/Dockerfile）。
    空のままなら frontend Container App と authConfigs は作られない（ADR-0027 決定 6 の
    fail-closed bootstrap 順序: chat_disabled = true かつ frontend 未作成の第 1 段 apply を
    成立させるため）。指定する場合は easy_auth_client_id と、Key Vault の secret
    easy-auth-client-secret（ADR-0032。人が投入する）も必須
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
    client secret はこの層の変数ではなく Key Vault の secret easy-auth-client-secret に
    置き、frontend の secret（microsoft-provider-authentication-secret）が Key Vault 参照で
    読む（Issue #286 / ADR-0032。旧変数 easy_auth_client_secret は廃止）。
    投入・復旧・1 年ごとのローテーションは docs/operations/entra-easy-auth-setup.md §1 / §6 / §7。
  DESC
  type        = string
  default     = ""
}

variable "llm_provider" {
  description = <<-DESC
    backend serving の LLM provider 切替（Issue #195。ADR-0009）。
    空（既定）= LLM_PROVIDER env を注入しない = backend/app/config.py の既定 "stub"（ADR-0004）。
    "azure-openai" = 実 Azure OpenAI へ切り替える（azure_openai_endpoint が必須になる。
    azurerm_container_app.main の precondition が検査する）。Azure OpenAI への認証は
    user-assigned managed identity（Cognitive Services OpenAI User ロール。Issue #275 / ADR-0031）で
    行い、API キーは扱わない。
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
