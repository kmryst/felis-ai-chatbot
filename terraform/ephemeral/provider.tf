# ephemeral 層: 使わない時間帯は destroy して時間課金を止めるリソース
# （ACR / Container Apps Environment / Container App。
#  day3-5-execution-plan.md §3-2 / §3-6 / §8）。
# persistent 層（PostgreSQL Flexible Server / Log Analytics。ADR-0016）とは
# ディレクトリ・state を分離する。

terraform {
  # ローカル正本は .mise.toml（1.14.8）。CI pin との一致は toolchain-version-check が検査する。
  # state の前方互換がないため、下限を .mise.toml と揃え、勝手に下げない（persistent 層と同じ方針）。
  required_version = ">= 1.14.8"

  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      # persistent 層と同じ明示 pin（範囲指定にしない）。更新は Dependabot / 明示的な PR で行う。
      version = "5.1.0"
    }
    # frontend の Easy Auth 設定（Microsoft.App/containerApps/authConfigs）用。
    # azurerm 5.1.0 に該当リソースが無いため AzAPI で管理する（ADR-0027 決定 1）。
    azapi = {
      source  = "Azure/azapi"
      version = "2.12.0"
    }
  }
}

provider "azurerm" {
  features {
    # 空ブロックだが azurerm では features {} 自体が必須。
    # 旧 log_analytics_workspace { permanently_delete_on_destroy = true } は
    # ADR-0016 の移設（この層の state に残っていた旧 workspace を destroy で完全削除し、
    # persistent 層での同名即時再作成を保証する）のためだけに必要だった設定で、
    # 移設完了（2026-08-21 実施）に伴い削除した。この層は Log Analytics を管理しない。
  }
  # subscription_id はコードに書かず ARM_SUBSCRIPTION_ID 環境変数
  # （CI では azure/login が設定する環境変数）から解決する。
}

provider "azapi" {
  # azurerm と同じく subscription は ARM_SUBSCRIPTION_ID 環境変数から解決する。
  # 認証も azurerm と同一（Azure CLI / OIDC）。
}
