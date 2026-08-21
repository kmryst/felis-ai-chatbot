terraform {
  backend "azurerm" {
    # persistent 層と同じ tfstate Storage Account（bootstrap.md §12）を共有し、
    # key で層を分ける。ephemeral 層は毎日 destroy / apply を繰り返すが
    # （day3-5-execution-plan.md §3-6）、state 置き場自体は残る。
    resource_group_name  = "rg-felisaichatbot-tfstate"
    storage_account_name = "felisaichatbottfstate"
    container_name       = "tfstate"
    key                  = "ephemeral/terraform.tfstate"
    # アクセスキーではなく Entra ID（Storage Blob Data Contributor。bootstrap.md §11-3）で
    # blob data plane にアクセスする。state lock は blob lease 組み込み。
    use_azuread_auth = true
  }
}
