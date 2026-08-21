output "server_fqdn" {
  description = "PostgreSQL Flexible Server の FQDN（アプリの接続文字列・psql が使う）"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "server_id" {
  description = "PostgreSQL Flexible Server のリソース ID（ephemeral 層が firewall rule 追加時に参照）"
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
