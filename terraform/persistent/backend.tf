terraform {
  backend "azurerm" {
    # tfstate 用 Storage Account は bootstrap.md §12 の手動作成（1回だけの鶏と卵解消）。
    # Terraform 管理リソース用 RG（rg-felisaichatbot-dev-tf。ADR-0012）と分けるのは、
    # dev を destroy しても state が残る persistent / ephemeral 分離の一貫。
    resource_group_name  = "rg-felisaichatbot-tfstate"
    storage_account_name = "felisaichatbottfstate"
    container_name       = "tfstate"
    key                  = "persistent/terraform.tfstate"
    # アクセスキーではなく Entra ID（Storage Blob Data Contributor。bootstrap.md §11-3）で
    # blob data plane にアクセスする。state lock は blob lease 組み込み。
    use_azuread_auth = true
  }
}
