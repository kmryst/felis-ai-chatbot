# ADR-0022: Azure Monitor の監視リソース 6 件を terraform import で persistent 層へ移行する

## ステータス

Accepted

（[azure-resource-inventory.md](../operations/azure-resource-inventory.md) §B #10 / #11 が記録していた「Azure Monitor は管理外・最終 teardown で手動削除」の整理を置き換える。[ADR-0014](./0014-keep-azure-openai-out-of-terraform.md)（Azure OpenAI の据え置き）には触れない — 据え置き理由が異なるため後述）

## 日付

2026-08-27

## 決定内容

- az CLI で作成済みの Azure Monitor リソース 6 件（Action Group `ag-felisaichatbot-dev-email` + メトリクスアラート 5 件。Issue #145 / #148）を **`terraform import` で `terraform/persistent/` の管理下へ移す**。削除・再作成はしない
- 閾値・severity・条件・受信者は**現在の実値をそのまま HCL に写す**（この移行で監視の設計値は変更しない）
- 受信者メールアドレスはコードに書かず、変数 `alert_email_address`（`TF_VAR_alert_email_address`。`.env`）で渡す
- 台帳の「管理外＝残す、管理下＝消す」の唯一の例外（この 6 件 = 管理外だが終了時に消す）を解消し、最終 teardown から手動削除の一手を撤去する

## 背景

- アラート新設時（Issue #145）は「persistent 層への apply が PostgreSQL 本体を含む層に触るのでリスクが高い」「PostgreSQL より寿命を長くしたい」として Terraform 管理外を選んだ
- しかし本プロジェクトは IaC を主成果物に掲げており、**監視だけ手作業なのは一貫していない**（ユーザー指摘により方針変更）。保存 plan（`terraform plan -out=`）で destroy ゼロと変更対象を確認してから同じ plan を apply する手順を守れば、persistent 層に触るリスクは管理できる
- 2026-08-27 実施の発火試験の証跡（`alert-pgsql-storage-percent-80` の 05:17:38Z 発火 → 05:32:44Z 解消）は**既存のリソース ID に紐づいている**。管理方式を変えるなら ID を変えない手段が必要

## 検討した選択肢

### 1. 管理区分

- **(a) Terraform 管理下へ移す（採択）**: IaC の一貫性。teardown が `terraform destroy` 2 本（+ ロック解除）で完結し、台帳の例外が消える
- (b) 管理外のまま（却下）: 「IaC が主成果物なのに監視だけ手作業」という不整合が残る。当初理由の「寿命を PostgreSQL より長く」は、destroy が失効前の最終 teardown のみ（ADR-0020）となった現在、アラートだけ残して監視する対象がない
- (c) ADR-0014 との整合: Azure OpenAI は据え置きのまま。あちらの理由（Day 0 手動作成の経緯 + 専用 RG 分離 + CI SP の権限スコープ外）は監視リソースには当てはまらない — この 6 件は最初から CI SP が Contributor を持つ `rg-felisaichatbot-dev-tf` 内にある

### 2. 配置層

- **(a) persistent 層（採択）**: scope（監視対象）が persistent 層の PostgreSQL Flexible Server であり、アラートの寿命は監視対象の寿命に一致させるのが自然。ephemeral 層は destroy / 再作成される層で、そこに置くとアラートも一緒に消える（Log Analytics workspace を persistent に置いた ADR-0016 と同じ判断構造）。HCL から `azurerm_postgresql_flexible_server.main.id` を直接参照でき、scope のリソース ID を文字列で持たなくて済む
- (b) ephemeral 層（却下）: destroy のたびに監視が消える。scope 参照も data source 経由になり複雑化する
- (c) 第 3 の層を新設（却下）: state・ディレクトリ・CI の増設に見合う利得がない

### 3. 移行操作

- **(a) `terraform import`（採択）**: state への書き込みのみで Azure 側リソースに触れない。リソース ID が不変のため発火試験の証跡が有効なまま
- (b) az で削除して Terraform で作り直す（却下）: リソース ID が変わり、発火試験の証跡の対象が消える

## 移行後の追随 apply（メタデータのみ。実測記録）

import 後の `terraform plan` に残った差分は次の 2 点のみで、いずれも監視の動作に影響しない。
保存 plan で **0 add / 5 change / 0 destroy** を確認してから同じ plan を apply した。

1. `criteria.metric_namespace`: azurerm 5.1.0 では**必須属性**だが、az CLI 作成のアラートは ARM 上
   `metricNamespace` 未設定（`az rest` の raw GET で実確認）。apply で `Microsoft.DBforPostgreSQL/flexibleServers`
   （既定で評価されている名前空間と同値）が明示された
2. `action.action_group_id` の大文字小文字正規化（`microsoft.insights` → `Microsoft.Insights`。ARM は case-insensitive）

apply の副作用として条件の内部名が `cond0` → `Metric1` に変わった（azurerm provider の固定値。plan 差分には現れない）。
**閾値・severity・operator・集計・window / freq・enabled・autoMitigate・scopes・受信者は 6 件とも不変**であることを
`az monitor metrics alert show` / `az monitor action-group show` の import 前後スナップショットの diff で確認した。
発火試験の証跡はアラートのリソース ID（不変）に紐づくため影響なし。

## 採択理由

- IaC の一貫性（主成果物との整合）が、管理外に残す消極的理由（apply リスク）を上回った
- import + 保存 plan 運用により、移行そのもののリスクを「state 書き込み + メタデータ 2 点の in-place 更新」に限定できた

## 影響

- 最終 teardown（credit-window-execution-plan.md §9 / 台帳「プロジェクト終了時の後片付け」）から Azure Monitor 6 件の手動削除が消え、persistent destroy に統合される
- persistent 層の apply / destroy に `TF_VAR_alert_email_address` の設定が必要になる（`.env`）
- 台帳 §B #10 / #11 は閾値の設計値・根拠の正本として残すが、管理区分は Terraform 管理下になる
- 以後、閾値・severity の変更は az CLI ではなく HCL の編集 → PR → apply で行う（az 直接変更はドリフト）

## 関連

- Issue [#145](https://github.com/kmryst/felis-ai-chatbot/issues/145) / [#148](https://github.com/kmryst/felis-ai-chatbot/issues/148)（アラートの新設）、Issue [#151](https://github.com/kmryst/felis-ai-chatbot/issues/151)（本移行）
- [ADR-0014](./0014-keep-azure-openai-out-of-terraform.md) — Azure OpenAI は引き続き管理外（理由が異なる）
- [ADR-0016](./0016-log-analytics-workspace-in-persistent-layer.md) — 監視系を persistent 層に置く同型の判断
- [ADR-0020](./0020-credit-window-resource-strategy.md) — destroy は最終 teardown のみ（「寿命を長く」理由の失効）
- [azure-resource-inventory.md](../operations/azure-resource-inventory.md) §B #10 / #11（設計値の正本）
