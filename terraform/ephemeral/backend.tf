# 【層名 ephemeral について】この層名はリソースの寿命（毎回 destroy して作り直せる層かどうか。
# ADR-0015）を指す。Terraform 1.10 以降の言語構文 ephemeral（state / plan に永続化されない
# 値・リソース。 https://developer.hashicorp.com/terraform/language/resources/ephemeral ）とは
# 無関係で、語義はむしろ逆 — この層の state は下記のとおり ephemeral/terraform.tfstate へ
# 通常どおり永続化される。衝突を認識した上で改名しない判断と理由は ADR-0015 の追記（#132）を参照。
terraform {
  backend "azurerm" {
    # persistent 層と同じ tfstate Storage Account（bootstrap.md §12）を共有し、
    # key で層を分ける。ephemeral 層は destroy / apply を繰り返すが
    # （day3-5-execution-plan.md §3-6 / §5-6）、state 置き場自体は残る。
    resource_group_name  = "rg-felisaichatbot-tfstate"
    storage_account_name = "felisaichatbottfstate"
    container_name       = "tfstate"
    key                  = "ephemeral/terraform.tfstate"
    # アクセスキーではなく Entra ID（Storage Blob Data Contributor。bootstrap.md §11-3）で
    # blob data plane にアクセスする。state lock は blob lease 組み込み。
    use_azuread_auth = true
  }
}
