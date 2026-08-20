variable "resource_group_name" {
  description = "既存の dev 用 resource group 名。Azure OpenAI が同居しているため Terraform 管理（作成・削除）はしない"
  type        = string
  default     = "rg-felisaichatbot-dev"
}

variable "server_name" {
  description = "PostgreSQL Flexible Server 名（グローバル一意。bootstrap.md §3 で空き確認済み）"
  type        = string
  default     = "felisaichatbot-pg-dev"
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

variable "firewall_allowed_client_ips" {
  description = <<-DESC
    サーバーレベル firewall rule で許可するクライアント IP（rule 名 → IPv4 アドレス）。
    作業端末のグローバル IP は当日 `curl -s ifconfig.me` で確認し、gitignore 対象の
    terraform.tfvars か TF_VAR_firewall_allowed_client_ips で渡す（コードにハードコードしない）。
    Container Apps の egress IP は ephemeral 層が apply 後に自層の firewall rule で許可する。
  DESC
  type        = map(string)
  default     = {}

  validation {
    condition     = alltrue([for ip in values(var.firewall_allowed_client_ips) : can(cidrnetmask("${ip}/32"))])
    error_message = "firewall_allowed_client_ips の値は IPv4 アドレス（例: 203.0.113.10）で指定してください。"
  }
}
