variable "resource_group_name" {
  description = <<-DESC
    Terraform 管理リソース専用の resource group 名（bootstrap.md §11-3 で手動作成）。
    Terraform 管理外の Azure OpenAI が同居する rg-felisaichatbot-dev とは分離し、
    CI 用 service principal の Contributor スコープをこの RG に限定する（ADR-0012）。
    RG 自体は Terraform 管理（作成・削除）にしない。
  DESC
  type        = string
  default     = "rg-felisaichatbot-dev-tf"
}

variable "server_name" {
  description = "PostgreSQL Flexible Server 名（グローバル一意。bootstrap.md §3 で空き確認済み）"
  type        = string
  default     = "pgsql-felisaichatbot-dev"
}

variable "administrator_login" {
  description = "PostgreSQL 管理者ユーザー名"
  type        = string
  default     = "felisadmin"
}

variable "administrator_password" {
  description = "PostgreSQL 管理者パスワード。コード・tfvars のコミット対象には書かず、TF_VAR_administrator_password 環境変数で渡す"
  type        = string
  sensitive   = true

  # Azure の実要件（8〜128 文字・英大文字/英小文字/数字/記号の 4 カテゴリ中 3 種以上）を
  # plan 時に検査し、空文字や弱いパスワードでの apply を弾く。
  # 出典: https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-server
  validation {
    condition = (
      length(var.administrator_password) >= 8 &&
      length(var.administrator_password) <= 128 &&
      (
        (length(regexall("[A-Z]", var.administrator_password)) > 0 ? 1 : 0) +
        (length(regexall("[a-z]", var.administrator_password)) > 0 ? 1 : 0) +
        (length(regexall("[0-9]", var.administrator_password)) > 0 ? 1 : 0) +
        (length(regexall("[^A-Za-z0-9]", var.administrator_password)) > 0 ? 1 : 0)
      ) >= 3
    )
    error_message = "administrator_password は 8〜128 文字で、英大文字・英小文字・数字・記号のうち 3 カテゴリ以上を含めてください（Azure の要件）。"
  }
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

variable "alert_email_address" {
  description = "Azure Monitor Action Group（ag-felisaichatbot-dev-email）のメール受信者。個人のアドレスをコード・tfvars のコミット対象に書かないため、TF_VAR_alert_email_address 環境変数（.env）で渡す"
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email_address))
    error_message = "alert_email_address はメールアドレス形式で指定してください。"
  }
}
