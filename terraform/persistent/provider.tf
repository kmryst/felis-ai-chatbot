# persistent 層: ephemeral 層を destroy しても残るリソース（PostgreSQL Flexible Server /
# Log Analytics workspace。ADR-0016）。「永続」の意味ではなく、プロジェクト終了時には destroy する。
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
  features {
    cognitive_account {
      # 【現時点では何の効果もない設定】features は Terraform 管理下のリソースにしか効かず、
      # Azure OpenAI（felisaichatbot-openai-dev）は管理外（ADR-0014・管理外リソース台帳）。
      # 「管理外リソースがこれで守られている」と誤解しないこと。
      #
      # それでも入れるのは、危険な既定値（true = destroy が論理削除を飛ばして purge まで実行
      # = 復旧不能）を、危険になる前に潰しておくため。この設定を知らないまま将来 import すると、
      # その瞬間から誤 destroy が purge まで進む経路が有効になる。「import するとき気をつける」
      # ではなく「気をつけなくても安全」にしておく（ADR-0012 の権限分離と同じ考え方。ADR-0014）。
      purge_soft_delete_on_destroy = false
    }

    log_analytics_workspace {
      # destroy 時に soft delete を飛ばして完全削除する（既定は false = soft delete）。
      # soft delete は workspace 名を 14 日間予約し、その間は同名の新規作成ができない（出典:
      # https://learn.microsoft.com/en-us/azure/azure-monitor/logs/delete-workspace ）。
      # revive runbook（azure-resource-inventory.md「再現手順」）は「destroy 後に
      # terraform apply だけでデモ用へ戻す」前提であり、名前予約が残ると persistent 層の
      # apply が同名 workspace を作れず成立しない。誤 destroy 時の 14 日間の復旧の窓
      # （ADR-0016 起案時の判断）より runbook の成立を優先する（改訂の経緯は ADR-0016 追記）。
      permanently_delete_on_destroy = true
    }
  }
  # subscription_id はコードに書かず ARM_SUBSCRIPTION_ID 環境変数
  # （CI では azure/login が設定する環境変数）から解決する。
}
