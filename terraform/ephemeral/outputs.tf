output "acr_login_server" {
  description = "ACR のログインサーバー（docker push / image 参照のホスト部）"
  value       = azurerm_container_registry.main.login_server
}

# アプリ FQDN（ingress[0].fqdn）を返す。常に現役 revision へトラフィックが流れる安定名で、
# revision が入れ替わっても値が変わらない。
# 以前は latest_revision_fqdn（`<APP名>--<revision suffix>.<CAE サフィックス>...` という
# revision 固有名）を返していたため、次の 2 つを実際に踏んだ（Issue #135）:
#   1. デプロイ直後にこの output の URL を叩くと、revision が上がった直後は古い revision を
#      指していて 404 になる（= 一番検証したいタイミングでデプロイ失敗と誤診する）
#   2. revision が変わるたびに値が変わるため、リソース差分ゼロでも
#      `plan -detailed-exitcode` が 2 を返す
# 特定 revision を名指しで叩きたい場合（カナリア検証など）は
# `az containerapp revision list -g <RG> -n <APP名> --query "[].properties.fqdn"` を使う。
# revision 固有 FQDN を output として持たせない理由は 2 で、値が revision ごとに動くため
# 上記の偽の差分がそのまま残るから。
# 属性の存在は azurerm 5.1.0（この層の pin）の `terraform providers schema -json` で確認済み
# （azurerm_container_app.block_types.ingress.attributes.fqdn / computed / "The FQDN of the ingress."）。
output "container_app_fqdn" {
  description = "Container App の公開 FQDN（安定。revision が変わっても不変。walking skeleton の検証は https://<FQDN>/readyz）"
  value       = azurerm_container_app.main.ingress[0].fqdn
}
