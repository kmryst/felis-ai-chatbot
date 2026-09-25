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
    # chat API キーを ephemeral resource（random_password）で生成し、Key Vault に write-only
    # argument（value_wo）で書く（Issue #286 / ADR-0032）。ephemeral resource は random 3.7.0 以降。
    # ephemeral 層と同じ明示 pin。
    random = {
      source  = "hashicorp/random"
      version = "3.9.1"
    }
  }
}

provider "azurerm" {
  features {
    cognitive_account {
      # 【現時点では何の効果もない設定】features は Terraform 管理下のリソースにしか効かず、
      # Azure OpenAI（felisaichatbot-openai-dev-02）は管理外（ADR-0014・管理外リソース台帳）。
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

    key_vault {
      # 既定値に依存せず明示する（ADR-0032 決定 6。Key Vault は soft-delete 保持 7 日・purge protection 無効）。
      # destroy では soft-delete を経由して purge まで行い、同名の即時再作成を可能にする
      # （revive runbook は「destroy 後に apply だけで戻す」前提。Log Analytics と同じ理由）。
      # 失う値は再発行（Easy Auth）・再生成（chat API キー）できる。
      purge_soft_delete_on_destroy          = true
      purge_soft_deleted_secrets_on_destroy = true
      # soft-delete 中の同名リソースを黙って回復しない。回復は旧い値・旧い設定を持ち込むため、
      # 作り直しは purge を挟んだ新規作成に限る（az keyvault create は同名で回復してしまう。
      # 2026-09-22 実測）。soft-delete 中の同名があれば apply はエラーで止まる。
      recover_soft_deleted_key_vaults = false
      recover_soft_deleted_secrets    = false
    }
  }
  # subscription_id はコードに書かず ARM_SUBSCRIPTION_ID 環境変数
  # （CI では azure/login が設定する環境変数）から解決する。
}
