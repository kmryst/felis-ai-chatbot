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
