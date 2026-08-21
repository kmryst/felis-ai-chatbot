# ADR-0016: Log Analytics workspace を ephemeral 層から persistent 層へ移す

## ステータス

Accepted

（[ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) の決定内容のうち **Log Analytics workspace の配置（ephemeral 層）のみ**を supersede する。ADR-0015 の他の決定 — ACR / Container Apps の設計・SKU・認証方式・保持 30 日・日次取込上限 1 GB — は引き続き有効）

## 日付

2026-08-21

## 決定内容

- Log Analytics workspace `log-felisaichatbot-dev` を `terraform/ephemeral/` の管理から **`terraform/persistent/` の管理へ移す**。設定値（PerGB2018 / 保持 30 日 / 日次取込上限 1 GB）は据え置く
- `terraform/ephemeral/` は `data "azurerm_log_analytics_workspace"` による**読み取り参照**に変える（Container Apps Environment の `log_analytics_workspace_id` に data source の `id` を渡す）
- `terraform/ephemeral/` の provider `features` に `log_analytics_workspace { permanently_delete_on_destroy = true }` を設定する（移設時の destroy で旧 workspace を完全削除し、soft delete の名前予約を回避するため。下記「移設手順」）
- 移設の実操作は **destroy → apply → apply**（下記）。`terraform state mv` / `state rm` は使わない

## 背景

- [bootstrap.md](../operations/bootstrap.md) の層分割の説明は「Log Analytics を persistent に置くのも正しい。ephemeral を destroy しても監視ログ・検証証跡が消えない」と明記しているが、実装（ADR-0015）は ephemeral 層に置いており、**ドキュメントと実装が食い違っていた**
- 実害がある。ephemeral 層は毎日 destroy する層（計画書 §3-6 / §8）のため、**このままでは監視ログが毎日消える**。Day 5 の Monitoring は「閾値は Day 3〜4 の実測レンジを見て決め、根拠を証跡に書く」設計（[day3-5-execution-plan.md §7](../operations/day3-5-execution-plan.md#7-monitoring-指標と閾値の根拠成果物-5-の設計)）であり、**数日分のログが残っていないと閾値の根拠を作れない**
- ACR は ephemeral のままでよい。イメージは `az acr import` / CI push で作り直せる資産であり、Basic SKU の固定費 0.1666 USD/日（ADR-0015 実測単価）を毎日の destroy で消せる利点が勝つ。ログは作り直せない

## 検討した選択肢

### 1. 配置

- **(a) persistent 層へ移す（採択）**: ephemeral の毎日 destroy からログを切り離せる。bootstrap.md の説明とも一致する。workspace 自体の固定費はなく（PAYG。取込した分だけ課金 + 日次 1 GB 上限ガード）、persistent に常駐させてもコスト構造は変わらない
- (b) ephemeral のまま（却下）: ログが毎日消え、計画書 §7 の閾値決定が成立しない。ドキュメントとの食い違いも残る

### 2. ephemeral 層からの参照方式

- **(a) `data "azurerm_log_analytics_workspace"`（採択）**: azurerm 5.1.0 の provider スキーマで実確認した（2026-08-21、`terraform providers schema -json`）。data source は `id` を computed 属性として提供し、`azurerm_container_app_environment` が要求するのは `log_analytics_workspace_id`（workspace のリソース ID）のみ。**必要な属性は取れる**。なお data source は `primary_shared_key`（sensitive）も読むため ephemeral 層の state に載るが、resource として管理していた現行でも同じ値が state に載っており、読み取り面は増えない
- (b) `terraform_remote_state` で persistent の outputs を読む（却下）: persistent の state には DB 管理者パスワード等の sensitive 値が平文で入っており、読み取り面を増やさない（ADR-0015「7. Terraform 上の実装形」で確定済みの方針をそのまま踏襲）

### 3. 移設の実操作

- **(a) destroy → apply → apply（採択）**:
  1. `terraform -chdir=terraform/ephemeral destroy`（ephemeral は毎日 destroy する層であり、日次のリハーサル済み操作。旧 workspace は下記 features 設定により完全削除される）
  2. `terraform -chdir=terraform/persistent apply`（workspace を persistent 管理で新規作成）
  3. `az acr import` でイメージ再投入 → `terraform -chdir=terraform/ephemeral apply` の段階 apply（ACR も destroy で消えているため再投入が必須。手順の正本は `terraform/ephemeral/main.tf` 冒頭コメントと [walking-skeleton/observations.md](../verification/walking-skeleton/observations.md) のタイムライン）

  失うものは移設時点までに workspace に溜まったログのみ（walking skeleton 段階の数時間〜数日分。必要な証跡は `docs/verification/` にコミット済み）
- (b) `terraform state mv` で state 間を移動（却下）: `state mv` の層間移動は、両層の remote state を pull してローカルコピー間で `-state` / `-state-out` 移動し、双方を `terraform state push` で書き戻す **state 手術**になる。tfstate blob への plan / apply を経ない直接書き込みであり、失敗時に両層の state を同時に壊し得る。得られるのは「移設時点のログを残せる」ことだけで、上記のとおり残す価値のあるログがまだない。リスクと釣り合わない（`terraform state rm` 系の操作は CLAUDE.md の要確認・原則禁止の操作でもある）

### 4. soft delete（名前予約）への対処

- Log Analytics workspace の削除は既定で **soft delete** になり、**workspace 名は 14 日間予約されて同名の新規作成ができない**（「The name of the deleted workspace is preserved during the soft-delete period and can't be used to create a new workspace.」出典: <https://learn.microsoft.com/en-us/azure/azure-monitor/logs/delete-workspace> ）。azurerm provider の既定も soft delete（`permanently_delete_on_destroy` の既定は `false`。出典: azurerm 5.1.0 の features-block ガイド <https://registry.terraform.io/providers/hashicorp/azurerm/5.1.0/docs/guides/features-block> ）
- 対処として ephemeral 層の features に **`permanently_delete_on_destroy = true`** を設定する。移設の手順 1 の destroy が旧 workspace を完全削除し、名前が即時解放されるため、手順 2 の同名作成が確実に通る。毎日 destroy / apply する層に 14 日の名前予約はそもそも成立しないため、この設定は移設後にこの層へ workspace を置かない限り無効果だが、層の性質に合う既定として残す
- **フォールバック**（手順 2 が「This workspace name is already in use」/ conflict で失敗した場合）: 公式トラブルシューティングの手順で soft delete 状態の旧 workspace を `az monitor log-analytics workspace recover` で復旧 → `az monitor log-analytics workspace delete --force`（完全削除）→ 手順 2 を再実行する（出典: 上記 delete-workspace ページの Troubleshooting 節）
- persistent 層には `permanently_delete_on_destroy` を設定しない（既定 false = soft delete のまま）。誤 destroy 時に 14 日間の復旧の窓（ログ・設定ごと recover 可能）を残すためで、「監視ログ・検証証跡を消えないようにする」という本 ADR の目的と整合する。プロジェクト終了時の意図した destroy では soft delete 状態の workspace が最大 14 日残り、その後 30 日以内に purge される（放置してよい。[azure-resource-inventory.md](../operations/azure-resource-inventory.md) の「プロジェクト終了時の後片付け」節）

## 採択理由

- 「ログは作り直せない・イメージは作り直せる」という資産の性質が、persistent / ephemeral の層の定義（ephemeral を destroy しても残るか）とそのまま対応する。ACR を ephemeral に残し Log Analytics だけを persistent へ移すのは、この対応関係の適用である
- ドキュメント（bootstrap.md）と実装の食い違いを、ドキュメント側の説明が正しい（ログ保全が必要）と判断して実装側を直す形で解消する

## 影響

- `terraform/persistent/`: `azurerm_log_analytics_workspace` リソース・`log_analytics_daily_quota_gb` 変数・`log_analytics_workspace_id` output を追加
- `terraform/ephemeral/`: リソース定義と quota 変数・output を削除し、data source 参照 + `log_analytics_workspace_name` 変数に変更。provider features に `log_analytics_workspace { permanently_delete_on_destroy = true }` を追加
- 移設の実操作（destroy → apply → apply）は本 ADR のマージ時点では**未実施**。ユーザーの実行判断を待つ（Azure への書き込みは本 PR のスコープ外）
- 移設時点で workspace 内のログはリセットされる。以後は ephemeral の毎日 destroy でログが消えない
- [bootstrap.md](../operations/bootstrap.md) §5-4 の層分割ツリーを実装後の姿に更新（ACR の配置変更・Key Vault 不採用の注記を含む）

## 関連

- [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) — 本 ADR が配置のみ supersede する元の設計（設定値・参照方針はそのまま引き継ぐ）
- [ADR-0017](./0017-no-nightly-stop-for-postgresql.md) — 同時に改訂した稼働方針（persistent 層の運用）
- [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §7（閾値決定が数日分のログを前提とする根拠）
- [azure-resource-inventory.md](../operations/azure-resource-inventory.md) — 全リソースの層・寿命の一覧
- Issue: #76
