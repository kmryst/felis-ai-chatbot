# ephemeral 層: 使わない時間帯は destroy して時間課金を止めるリソース
# （ACR / Log Analytics / Container Apps Environment / Container App。
#  day3-5-execution-plan.md §3-2 / §3-6 / §8）。
# persistent 層（PostgreSQL Flexible Server）とはディレクトリ・state を分離する。

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
  }
}

provider "azurerm" {
  features {
    # cognitive_account の purge 抑止（persistent 層 provider.tf 参照）は、
    # この層が Cognitive Services を一切管理しないため書かない。
  }
  # subscription_id はコードに書かず ARM_SUBSCRIPTION_ID 環境変数
  # （CI では azure/login が設定する環境変数）から解決する。
}
