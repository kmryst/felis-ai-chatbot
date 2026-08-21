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

variable "postgres_server_name" {
  description = "persistent 層が管理する PostgreSQL Flexible Server 名（data source 参照のみ。この層では作成・変更しない）"
  type        = string
  default     = "pgsql-felisaichatbot-dev"
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
    （ADR-0015 選択肢 6-(b)。台帳 terraform-unmanaged-resources.md #8 / #9 が正本）。
    手動作成が済むまで、この層の apply は通らない前提。
  DESC
  type        = string
  default     = "id-felisaichatbot-dev"
}

variable "log_analytics_daily_quota_gb" {
  description = <<-DESC
    Log Analytics workspace の日次取込上限（GB）。取込単価は japaneast PAYG で 3.34 USD/GB
    （Retail Prices API 実測 2026-08-21）のため、暴走時の 1 日あたり損失をこの値 × 3.34 USD に抑える。
    walking skeleton のコンソールログは 1 GB/日 に達しない想定（実測は Day 3。ADR-0015）。
  DESC
  type        = number
  default     = 1
}
