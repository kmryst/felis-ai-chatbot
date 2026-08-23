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

# --- フェーズ 2 負荷生成 Job（Issue #112。計画 §5-5） ---

variable "load_duration_seconds" {
  description = <<-EOT
    負荷生成 Job の 1 実行あたりの継続秒数（load_generate.sh の LOAD_DURATION_SECONDS）。
    replica_timeout はこの値 + 300 秒（後片付けマージン）で自動計算する。
    既定 3600（1 時間）。段階投入は実行時に -var で上書きする
  EOT
  type        = number
  default     = 3600

  validation {
    condition     = var.load_duration_seconds >= 60 && var.load_duration_seconds <= 86400
    error_message = "load_duration_seconds は 60〜86400（24 時間）の範囲で指定してください（フェーズ 2a は最大 48h だが 1 実行は最長 1 日で区切り、日次のコスト確認と歩調を揃える）。"
  }
}

variable "load_batch_rows" {
  description = "負荷生成の 1 イテレーションあたり INSERT 行数（LOAD_BATCH_ROWS）。既定 500 = 控えめな出発点。CPU Credits Remaining を見ながら段階投入（計画 §5-5）"
  type        = number
  default     = 500
}

variable "load_sleep_seconds" {
  description = "負荷生成イテレーション間の待機秒数（LOAD_SLEEP_SECONDS）。既定 1"
  type        = number
  default     = 1
}
