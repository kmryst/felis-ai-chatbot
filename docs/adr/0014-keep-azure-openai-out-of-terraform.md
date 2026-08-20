# ADR-0014: Azure OpenAI を Terraform 管理外に据え置く

## ステータス

Accepted

## 日付

2026-08-20

## 決定内容

- Azure OpenAI `felisaichatbot-openai-dev`（RG `rg-felisaichatbot-dev` / japaneast）とそのデプロイ 2 件（`chat` / `embedding`）を、**Terraform 管理外に据え置く**（import しない）
- 管理外リソースとしての差分検出の代替は、[Terraform 管理外リソース台帳](../operations/terraform-unmanaged-resources.md) の読み取り確認コマンドで担う
- 将来 import する場合の前提条件と手順を本 ADR に固定しておく（下記「将来 import する場合」）

## 背景

Azure OpenAI は Day 0 フェーズBの可否判定で az CLI により手動作成した（ADR-0009、bootstrap.md §2）。Day 3 の初回 apply を前に、これを Terraform に import するか管理外に据え置くかを確定させる必要がある。

**当初は「FreeTrial のクォータを再取得できる保証がない（リソースを消すとクォータを失う恐れ）」を据え置きの理由にしていた**（ADR-0012 / ADR-0013 の背景記述）。しかし調査の結果、**この理由は誤りと判明した**:

- クォータ（TPM）はリソースではなく**サブスクリプションに帰属**する。「Quota is assigned to your subscription on a per-region, per-model, per-deployment-type basis in units of Tokens-per-Minute (TPM)」（出典: <https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/quota>）
- 本サブスクリプションの quota tier は **Free Tier**（quotaTiers API で実測。2026-08-20）。実測クォータ（gpt-4.1-mini GlobalStandard 200 / gpt-5-mini 500 / text-embedding-3-small GlobalStandard 1000）は公式の Tier 0 表と一致する（出典: <https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits>）
- つまり現在のクォータは「偶然空いていた枠を確保できた」ものではなく **tier 由来の既定割当であり、リソースを消しても失われない**

理由が消えた以上、判断を白紙から引き直す必要がある。それが本 ADR である。

## 検討した選択肢

1. **Terraform 管理外に据え置く（採択）**
2. `terraform import` で管理下に入れる（却下）

## 採択理由（= import の却下理由）

正直に書く。「クォータを失う恐れ」はもう理由にならない。それでも据え置くのは次の理由による。

- **(a) 主成果物ではない**: 5 日間の主成果物は PostgreSQL の Backup / PITR / Maintenance / Monitoring（day3-5-execution-plan.md §0）であって、Azure OpenAI の構成管理ではない。import と保護設計に使う時間は主成果物から差し引かれる
- **(b) `prevent_destroy` が層の destroy を丸ごと壊す**: 誤 destroy 対策に `lifecycle { prevent_destroy = true }` を付けると、**その層の `terraform destroy` は plan の時点でエラーになる**（出典: <https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle>）。Day 5 の全 destroy（day3-5-execution-plan.md §5-6 / §8）を成立させるには Azure OpenAI 専用の第 3 の state 層を切る必要があり、5 日制約下でレイヤ設計が 1 枚増える
- **(c) 管理下に入れると新しい事故経路が生まれる**: このリポジトリが pin する azurerm 5.1.0 の既定は `cognitive_account { purge_soft_delete_on_destroy = true }` であり、Terraform 管理下では **destroy が論理削除を越えて purge まで実行し、復旧不能になる**。手動運用ならそもそも `terraform destroy` の射程外で、この経路自体が存在しない
- **(d) destroy する動機がそもそもない**: Azure OpenAI の Standard / GlobalStandard デプロイは**トークン従量課金**で、呼ばなければアイドル課金は発生しない（capacity は予約ではなくレート制限。出典: <https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/deployment-types>）。「使わない時は消す」というコスト圧力が働かないため、Terraform のライフサイクル管理（作って消す）の恩恵がない
- **(e) 失うものは差分検出だけであり、代替を用意した**: 管理外の代償は `terraform plan` による drift 検出がないこと。これは [Terraform 管理外リソース台帳](../operations/terraform-unmanaged-resources.md) の読み取り確認コマンドで代替する

なお ADR-0012 が「Azure OpenAI を守る」手段として権限スコープからの分離（届かなくする）を選んだのと同型で、本 ADR も「気をつけて管理する」より「そもそも管理対象・破壊経路に入れない」を選んでいる。

## 却下理由の含意（誤 destroy 時の実害）

据え置きでも手動削除の事故はあり得るため、実害の大きさを記録しておく（台帳 #1 にも同じ記載がある）。

- 削除すると**同名リソースは 48 時間作れない**（論理削除の名前予約）。48 時間以内・未 purge なら recover 可能。purge にはサブスクリプション Contributor 以上が必要（実行者は Owner なので可能）。出典: <https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources>
- デプロイを残したまま削除すると、**クォータ割当は purge まで最大 48 時間解放されない**（出典・Resource deletion 節: <https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/quota>）
- `OpenAI.S0.AccountCount` = **limit 1 / current 1**（2026-08-20 実測）のため、別名での代替アカウントも作れない可能性が高い。**未確定**: 論理削除中のアカウントが AccountCount を消費し続けるかは公式に明文がない。TPM が purge まで拘束される明記があるため、同様に拘束されると想定して設計する

## 将来 import する場合の条件と手順

Day 5 以降、Azure OpenAI の構成管理を本気でやる段階（例: SKU 切り替え・capacity 変更を PR レビューに載せたい）になったら、次の順で行う。

1. **先に安全装置を入れる**（import より前。順序を逆にしない）
   - `provider "azurerm"` の `features` に `cognitive_account { purge_soft_delete_on_destroy = false }` — **これは本 ADR の時点で `terraform/persistent/provider.tf` に先回りで設定済み**。features ブロックは Terraform 管理下のリソースにしか効かないため**現時点では何の効果もない**が、将来この既定値を知らないまま import した瞬間に「誤 destroy が purge まで実行される」経路が有効になるのを防ぐため、危険な既定値を危険になる前に潰してある（「import するとき気をつける」ではなく「気をつけなくても安全」にする。ADR-0012 と同じ考え方）。import する人が改めて設定する必要はない
   - `resource` に `lifecycle { prevent_destroy = true }` を付ける
2. **専用レイヤに置く**: `prevent_destroy` はその層の `terraform destroy` を plan 時点で失敗させるため（出典: <https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle>）、`terraform/persistent/`（Day 5 に destroy する層）には置かず、destroy しない専用ディレクトリ・state に分離する
3. **Terraform 1.5+ の `import` ブロックで plan-first に import する**: `import {}` を書いて `terraform plan` を流し、**`No changes`（import のみ・change 0 件）になるまで HCL を実物に合わせて直してから** apply する。`azurerm_cognitive_account` / `azurerm_cognitive_deployment` はともに import 対応。ForceNew（変えると再作成）属性は account: `name` / `resource_group_name` / `location` / `kind` / `custom_subdomain_name`、deployment: `name` / `cognitive_account_id` / `model.name` / `model.version` / `model.format` / `sku.name`（`sku.capacity` のみ in-place 更新可）。plan に replace が出たら HCL が間違っている
4. **検証用の複製は作れない前提で作業する**: AccountCount = 1 のため「別アカウントで import 手順をリハーサルする」ことができない。本番一発になるので、plan の出力を必ず PR に貼ってレビューする

## モデルの寿命（構成の前提）

import するか否かに関わらず、この構成には寿命がある: japaneast の gpt-4.1-mini `2025-04-14` は lifecycleStatus Legacy で**推論の廃止が 2027-04-14**、text-embedding-3-small `1` は GA で**廃止が 2028-02-09**（出典: <https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements>）。それまでにモデル更改（= デプロイの作り直し）が必ず発生するため、「一度作れば不変」を前提にした設計をしない。

## 影響

- `docs/operations/terraform-unmanaged-resources.md`（台帳）を新設し、README からリンクする
- `terraform/persistent/provider.tf` に `cognitive_account { purge_soft_delete_on_destroy = false }` を追加（上記のとおり現時点では無効果。コメントにもその旨を明記済み）
- ADR-0012 / ADR-0013 の背景にある「クォータを再取得できる保証がない」という記述は、本 ADR により**根拠としては失効**する（各 ADR の決定内容そのもの—権限分離・改名しない—は別の根拠で引き続き成立するため、書き換えない）

## 関連

- [ADR-0009](./0009-azure-openai-as-llm-provider.md) — Azure OpenAI の採用と手動作成の経緯。本 ADR はその管理方式を確定させる
- [ADR-0012](./0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — SP の権限スコープから Azure OpenAI を外した判断。「届かなくする」という同じ設計思想。背景中のクォータ喪失懸念は本 ADR で否定された（決定は不変）
- [ADR-0013](./0013-azure-resource-naming-convention.md) — `felisaichatbot-openai-dev` を改名しない例外の記録。「改名には再作成しかない」は本 ADR の 48 時間予約・AccountCount 制約でさらに補強される（クォータ喪失懸念の部分のみ本 ADR で更新）
- [terraform-unmanaged-resources.md](../operations/terraform-unmanaged-resources.md) — 管理外リソース台帳（本 ADR の運用面の正本）
- Issue: #67
