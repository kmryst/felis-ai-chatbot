output "acr_login_server" {
  description = "ACR のログインサーバー（docker push / image 参照のホスト部）"
  value       = azurerm_container_registry.main.login_server
}

output "container_app_fqdn" {
  description = "Container App の公開 FQDN（walking skeleton の検証は https://<FQDN>/readyz）"
  value       = azurerm_container_app.main.latest_revision_fqdn
}
