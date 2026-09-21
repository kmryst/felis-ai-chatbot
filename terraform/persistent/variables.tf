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
  default     = "pgsql-felisaichatbot-dev-02"
}

variable "administrator_login" {
  description = <<-DESC
    PostgreSQL 管理者（パスワード認証）のユーザー名。既定 null = 指定しない（ADR-0031）。
    Entra 認証のみで新規作成するときは指定してはいけない（azurerm 5.1.0 の Create が
    password_auth_enabled = false との併用をエラーにする）。既存サーバーでは Optional + Computed のため
    null でも state の値（felisadmin）が保たれ、差分は出ない。ForceNew 属性なので、指定するなら
    state と同じ値にすること。
  DESC
  type        = string
  default     = null
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

variable "entra_administrator_object_id" {
  description = <<-DESC
    PostgreSQL Flexible Server の Microsoft Entra 管理者にするアカウントの object ID
    （プロジェクト所有者のアカウント。Issue #275 / ADR-0031）。
    `az ad signed-in-user show --query id -o tsv` で取得できる。個人のアカウントに紐づく値のため
    コード・tfvars のコミット対象には書かず、terraform.tfvars（gitignore 済み）で渡す。
  DESC
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.entra_administrator_object_id))
    error_message = "entra_administrator_object_id は GUID 形式で指定してください。"
  }
}

variable "entra_administrator_principal_name" {
  description = <<-DESC
    上記管理者の principal name（ユーザーの場合は user principal name）。
    `az ad signed-in-user show --query userPrincipalName -o tsv` で取得できる。
    個人のアカウント名のためコード・tfvars のコミット対象には書かず、terraform.tfvars（gitignore 済み）で渡す。
    PostgreSQL 側ではこの名前が管理者ロール名になる。
  DESC
  type        = string

  validation {
    condition     = length(trimspace(var.entra_administrator_principal_name)) > 0
    error_message = "entra_administrator_principal_name は空にできません。"
  }
}
