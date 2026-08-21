output "acr_login_server" {
  description = "ACR のログインサーバー（docker push / image 参照のホスト部）"
  value       = azurerm_container_registry.main.login_server
}

output "container_app_fqdn" {
  description = "Container App の公開 FQDN（walking skeleton の検証は https://<FQDN>/readyz）"
  value       = azurerm_container_app.main.latest_revision_fqdn
}

output "container_app_outbound_ips" {
  description = "Container App の outbound IP（PostgreSQL firewall rule の許可対象。静的保証なし）"
  value       = azurerm_container_app.main.outbound_ip_addresses
}
