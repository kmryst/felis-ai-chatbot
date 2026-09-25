output "server_fqdn" {
  description = "PostgreSQL Flexible Server の FQDN（private DNS zone 配下の名前。VNet 内からのみ解決・到達できる。DATABASE_URL のホスト部に使う）"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "server_id" {
  description = "PostgreSQL Flexible Server のリソース ID（az monitor metrics などの読み取りコマンドで使う）"
  value       = azurerm_postgresql_flexible_server.main.id
}

output "server_name" {
  description = "PostgreSQL Flexible Server 名"
  value       = azurerm_postgresql_flexible_server.main.name
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace のリソース ID（ログ確認クエリで使う）"
  value       = azurerm_log_analytics_workspace.main.id
}

output "key_vault_name" {
  description = "Azure Key Vault 名（読み取りコマンドとロール割当のスコープ指定で使う）"
  value       = azurerm_key_vault.main.name
}

output "key_vault_id" {
  description = "Azure Key Vault のリソース ID（ロール割当の --scope に使う）"
  value       = azurerm_key_vault.main.id
}

output "key_vault_uri" {
  description = "Azure Key Vault の URI（Container Apps の Key Vault 参照 URL の組み立てに使う。末尾 / 付き）"
  value       = azurerm_key_vault.main.vault_uri
}
