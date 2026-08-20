# persistent 層: destroy しても残す・作り直さないリソース（PostgreSQL Flexible Server）。
# ephemeral 層（ACR / Container Apps）とはディレクトリ・state を分離する
# （day3-5-execution-plan.md §3-1 / bootstrap.md §12）。

terraform {
  # ローカル正本は .mise.toml（1.14.8）。CI pin との一致は toolchain-version-check が検査する。
  # state の前方互換がないため、下限を .mise.toml と揃え、勝手に下げない（idp-golden-path ADR-0014）。
  required_version = ">= 1.14.8"

  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      # 明示 pin（範囲指定にしない）。更新は Dependabot / 明示的な PR で行う。
      version = "5.1.0"
    }
  }
}

provider "azurerm" {
  features {}
  # subscription_id はコードに書かず ARM_SUBSCRIPTION_ID 環境変数
  # （CI では azure/login が設定する環境変数）から解決する。
}
