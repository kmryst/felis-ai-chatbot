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
  }
}

provider "azurerm" {
  features {
    # cognitive_account の purge 抑止（persistent 層 provider.tf 参照）は、
    # この層が Cognitive Services を一切管理しないため書かない。

    log_analytics_workspace {
      # destroy 時に soft delete を飛ばして完全削除する（既定は false = soft delete。
      # 出典: azurerm 5.1.0 features-block ガイド）。soft delete は workspace 名を
      # 14 日間予約し、その間は同名の新規作成ができない（出典:
      # https://learn.microsoft.com/en-us/azure/azure-monitor/logs/delete-workspace ）。
      # 毎日 destroy / apply するこの層に 14 日の名前予約は成立しないため true にする。
      # ADR-0016 の移設手順（この層の state に残る旧 workspace を destroy で完全削除し、
      # persistent 層での同名作成を確実にする）もこの設定が前提。移設後にこの層が
      # workspace を管理することはないが、上記理由により設定は残す。
      permanently_delete_on_destroy = true
    }
  }
  # subscription_id はコードに書かず ARM_SUBSCRIPTION_ID 環境変数
  # （CI では azure/login が設定する環境変数）から解決する。
}
