# Terraform 管理外リソース台帳

本書は、Azure 上に存在するが **Terraform の管理下にないリソースの正本台帳**です。

## この台帳の役割

Terraform 管理下のリソースには `terraform plan` による差分検出（コードと実物のずれの機械的な検出）があるが、**管理外リソースにはそれがない**。本台帳と各節の読み取り確認コマンドがその代替であり、**この手順書が実質的な「コード」の役割を果たす**。

- 管理外リソースを追加・変更・削除したときは、**同じ PR で本台帳を更新する**
- 各節の「確認コマンド」はすべて**読み取り系**で、そのまま実行できる。実行結果が「あるべき値」列と食い違ったら、それが管理外リソースにおける「plan 差分」である
- 本台帳の実測値は 2026-08-20 に各確認コマンドを実行して記録した

現時点（2026-08-20、main = PR #64 マージ後）で **Terraform が管理しているリソースは 1 つもない**。`terraform/persistent/` の `terraform plan` は通っているが初回 apply 前であり、Azure 上の全リソースが本台帳の対象である。

## 一覧

| # | リソース | 種類 | 場所 | 管理外の理由区分 |
| --- | --- | --- | --- | --- |
| 1 | `felisaichatbot-openai-dev` + デプロイ `chat` / `embedding` | Azure OpenAI（kind=OpenAI, sku=S0） | RG `rg-felisaichatbot-dev` / japaneast | 据え置き判断（ADR-0014） |
| 2 | `rg-felisaichatbot-dev` | Resource group | japaneast | 据え置き判断（管理外の Azure OpenAI が同居） |
| 3 | `rg-felisaichatbot-dev-tf` | Resource group | japaneast | 権限の器（SP の Contributor スコープそのもの） |
| 4 | `rg-felisaichatbot-tfstate` | Resource group | japaneast | 鶏と卵（tfstate の置き場） |
| 5 | `felisaichatbottfstate` + container `tfstate` | Storage Account（tfstate backend） | RG `rg-felisaichatbot-tfstate` / japaneast | 鶏と卵（tfstate の置き場） |
| 6 | `felis-ai-chatbot-github-actions` + federated credential 1 本 | Entra ID アプリ登録 + service principal | Entra ID（リージョン概念なし） | 鶏と卵（Terraform 実行主体の認証基盤） |
| 7 | ロール割当 2 件（Contributor / Storage Blob Data Contributor） | Role assignment | #3 / #5 のスコープ | destroy すると CI の権限が壊れる |

理由区分の意味:

- **鶏と卵**: Terraform を動かすために先に存在しなければならないもの。Terraform 自身では作れない（作ると自分の足場を自分で管理することになり、destroy で足場ごと消える）
- **権限が壊れる / 権限の器**: Terraform（CI の service principal）の権限そのもの、またはそのスコープ。誤 destroy が以後の apply / destroy 自体を不能にする
- **据え置き判断**: import 可能だが、あえて管理外に据え置くと判断したもの。判断の記録は [ADR-0014](../adr/0014-keep-azure-openai-out-of-terraform.md)

---

## 1. Azure OpenAI `felisaichatbot-openai-dev` + デプロイ `chat` / `embedding`

| 項目 | あるべき値 |
| --- | --- |
| 名前 / 種類 | `felisaichatbot-openai-dev` / Microsoft.CognitiveServices/accounts（kind `OpenAI`, sku `S0`） |
| custom subdomain | `felisaichatbot-openai-dev`（アカウント名と同名） |
| 場所 | RG `rg-felisaichatbot-dev` / japaneast |
| デプロイ `chat` | gpt-4.1-mini `2025-04-14` / GlobalStandard / capacity 10 |
| デプロイ `embedding` | text-embedding-3-small `1` / Standard / capacity 10 |

- **なぜ管理外か**: 据え置き判断。Day 0 フェーズBの可否判定（[bootstrap.md §2](./bootstrap.md#2-azure-openai-可否判定タイムボックス-2h最優先)）で az CLI により手動作成した（[ADR-0009](../adr/0009-azure-openai-as-llm-provider.md)）。import は技術的に可能だが据え置く。判断の全文は [ADR-0014](../adr/0014-keep-azure-openai-out-of-terraform.md)
- **作り直す手順**: [bootstrap.md §2](./bootstrap.md#2-azure-openai-可否判定タイムボックス-2h最優先) の判定手順と同じ（`az cognitiveservices account create` → `az cognitiveservices account deployment create` ×2）。設計値（モデル・SKU・capacity）は上表と ADR-0009 が正本。**ただし下記リスクのとおり、同名での作り直しは論理削除の purge が先に必要**
- **確認コマンド**:

  ```bash
  az cognitiveservices account show -n felisaichatbot-openai-dev -g rg-felisaichatbot-dev \
    --query '{name:name, kind:kind, sku:sku.name, location:location, customDomain:properties.customSubDomainName, state:properties.provisioningState}' -o json
  az cognitiveservices account deployment list -n felisaichatbot-openai-dev -g rg-felisaichatbot-dev \
    --query "[].{name:name, model:properties.model.name, version:properties.model.version, sku:sku.name, capacity:sku.capacity}" -o table
  ```

- **固有のリスク・注意**:
  - **削除すると同名リソースは 48 時間作れない**（論理削除による名前予約）。「Once you delete a resource, you can't create another one with the same name for 48 hours. To create a resource with the same name, you need to purge the deleted resource.」48 時間以内・未 purge なら recover 可能。purge にはサブスクリプションの Contributor 以上が必要（実行者は Owner なので実行可能）。出典: <https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources>
  - **デプロイを残したままアカウントを削除すると、クォータ割当は purge されるまで最大 48 時間解放されない**。出典（Resource deletion 節）: <https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/quota>
  - **このサブスクリプションで Azure OpenAI アカウントは 1 つしか作れない**: `OpenAI.S0.AccountCount` = limit 1 / current 1（2026-08-20 実測）。検証用の複製アカウントは作れない。**未確定**: 論理削除中のアカウントがこの AccountCount を消費し続けるかは公式に明文がない。TPM クォータが purge まで 48 時間拘束される明記があるため、**同様に拘束されると想定して運用する**（＝削除したら即 purge しない限り 48 時間は再作成不能と見なす）
  - **モデルデプロイのクォータ（TPM）はリソースではなくサブスクリプションに帰属する**: 「Quota is assigned to your subscription on a per-region, per-model, per-deployment-type basis in units of Tokens-per-Minute (TPM)」（出典: <https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/quota>）。本サブスクリプションの quota tier は Free Tier で（quotaTiers API 実測）、実測クォータ（gpt-4.1-mini GlobalStandard 200 / gpt-5-mini 500 / text-embedding-3-small GlobalStandard 1000）は公式 Tier 0 表と一致する。**リソースを消してもクォータ自体は失われない**。出典: <https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits>
  - **モデルには寿命がある**: japaneast の gpt-4.1-mini `2025-04-14` は lifecycleStatus **Legacy** で推論の廃止は **2027-04-14**、text-embedding-3-small `1` は GA で廃止は **2028-02-09**。Deprecated 段階でも「そのモデルをデプロイしたことのあるサブスクリプション」は新規デプロイ可。出典: <https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements>
  - Day 2 で結線済みの RAG（chat / embedding）がこのエンドポイント名に依存する。アカウント名は改名不可（[ADR-0013](../adr/0013-azure-resource-naming-convention.md) の例外記録）
  - API キーは本台帳・リポジトリには書かない（`.env` のみ。コミット禁止）

## 2. Resource group `rg-felisaichatbot-dev`

- **なぜ管理外か**: 据え置き判断の巻き添え。Day 0 フェーズBで Azure OpenAI と同時に手動作成（[bootstrap.md §2](./bootstrap.md#2-azure-openai-可否判定タイムボックス-2h最優先) / ADR-0009）。中身が管理外の Azure OpenAI のみである以上、RG だけ Terraform 管理にする意味がなく、CI の service principal にはこの RG への権限を**意図的に与えていない**（[ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)）
- **作り直す手順**: `az group create --name rg-felisaichatbot-dev --location japaneast`（1 コマンド。ただし中身の Azure OpenAI の作り直しは #1 参照）
- **確認コマンド**:

  ```bash
  az group show -n rg-felisaichatbot-dev --query '{name:name, location:location, state:properties.provisioningState}' -o json
  az resource list -g rg-felisaichatbot-dev --query "[].{name:name, type:type}" -o table   # felisaichatbot-openai-dev の 1 件のみのはず
  ```

- **固有のリスク・注意**: `az group delete` は中の Azure OpenAI ごと消す（#1 の 48 時間予約・AccountCount リスクがそのまま発動する）。全消し手順（[day3-5-execution-plan.md §8](./day3-5-execution-plan.md#8-コスト見張り)）で「面談デモ用に残すなら保留する行」と明記されているのはこのため

## 3. Resource group `rg-felisaichatbot-dev-tf`

- **なぜ管理外か**: 権限の器。CI 用 service principal の Contributor スコープをこの RG に限定する設計（[ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)）のため、RG 自体は [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) で手動作成した。Terraform 管理（作成・削除）にすると、`terraform destroy` が自分の権限スコープの器を消してしまい、以後の apply が権限エラーで不能になる。service principal は RG スコープの Contributor しか持たないため、そもそもサブスクリプションレベルの RG 作成権限がない
- **作り直す手順**: [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) の `az group create` 1 コマンド + #7 のロール割当の再作成
- **確認コマンド**:

  ```bash
  az group show -n rg-felisaichatbot-dev-tf --query '{name:name, location:location, state:properties.provisioningState}' -o json
  az resource list -g rg-felisaichatbot-dev-tf -o table   # 初回 apply 前は空のはず（apply 後は PostgreSQL 等が入る）
  ```

- **固有のリスク・注意**: 消すと中の Terraform 管理リソース（Day 3 以降の PostgreSQL 等）とロール割当（#7 の Contributor）が一緒に消え、tfstate だけが「実在しないリソースの記録」として残る（state と実物の乖離）。Terraform 側は `data "azurerm_resource_group"` で参照しており、RG が無いと plan の時点で失敗する

## 4. Resource group `rg-felisaichatbot-tfstate`

- **なぜ管理外か**: 鶏と卵。Terraform backend が使う Storage（#5）の器であり、Terraform より先に存在しなければならない（[bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h)）。環境をまたいで共有し、dev の destroy でも消えない persistent / ephemeral 分離の一貫として、名前に `<env>` を付けていない（[ADR-0013](../adr/0013-azure-resource-naming-convention.md)）
- **作り直す手順**: [bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h) の手順 1（`az group create`）。ただし作り直し＝tfstate の喪失を意味する（#5 参照）
- **確認コマンド**:

  ```bash
  az group show -n rg-felisaichatbot-tfstate --query '{name:name, location:location, state:properties.provisioningState}' -o json
  ```

- **固有のリスク・注意**: 消すと tfstate（#5）ごと消える。apply 後にこれをやると、全 Terraform 管理リソースが「実物はあるのに state がない」孤児になる

## 5. Storage Account `felisaichatbottfstate` + container `tfstate`

| 項目 | あるべき値 |
| --- | --- |
| 名前 / 種類 | `felisaichatbottfstate` / Microsoft.Storage/storageAccounts（Standard_LRS） |
| 場所 | RG `rg-felisaichatbot-tfstate` / japaneast |
| 設定 | `minimumTlsVersion: TLS1_2` / `allowBlobPublicAccess: false` / blob versioning 有効 |
| container | `tfstate`（key `persistent/terraform.tfstate` 等で層を区別） |

- **なぜ管理外か**: 鶏と卵。Terraform backend の state 置き場を Terraform で作ることはできないため、[bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h) で 1 回だけ手動作成した（terraform-hannibal が S3 state bucket で採った方式と同型）
- **作り直す手順**: [bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h)（Storage Account 作成 → 実行者自身への Storage Blob Data Contributor 割当 → 反映待ちリトライで container 作成 → versioning 有効化、の 4 手順。データプレーン権限の罠と出典は同節に記載）
- **確認コマンド**:

  ```bash
  az storage account show -n felisaichatbottfstate -g rg-felisaichatbot-tfstate \
    --query '{name:name, sku:sku.name, minTls:minimumTlsVersion, publicBlobAccess:allowBlobPublicAccess}' -o json
  az storage account blob-service-properties show --account-name felisaichatbottfstate \
    --resource-group rg-felisaichatbot-tfstate --query isVersioningEnabled   # true のはず
  az storage container list --account-name felisaichatbottfstate --auth-mode login --query "[].name" -o tsv   # tfstate のはず
  ```

- **固有のリスク・注意**: apply 後の tfstate には sensitive 値（PostgreSQL 管理者パスワード等）が平文で入る（出典: <https://developer.hashicorp.com/terraform/language/manage-sensitive-data>）。アクセスできる主体は実行者本人と CI 用 service principal（#7）に限定してある。state の誤削除・破損への備えは blob versioning（S3 の versioning 相当）。接続文字列・アクセスキーは使わない（`use_azuread_auth = true`）し、本台帳にも書かない

## 6. Entra ID アプリ登録 `felis-ai-chatbot-github-actions` + federated credential

| 項目 | あるべき値 |
| --- | --- |
| 名前 / 種類 | `felis-ai-chatbot-github-actions` / Entra ID アプリ登録 + service principal |
| appId | `3a79df61-4c85-4f92-9368-1ca8588a1d17` |
| SP object id | `a428458b-fd66-4cb3-b25d-fc1c360f7f37` |
| federated credential | `github-actions-main` の **1 本のみ**。subject `repo:kmryst@205493351/felis-ai-chatbot@1336699843:ref:refs/heads/main` |

- **なぜ管理外か**: 鶏と卵 + 権限が壊れる。GitHub Actions の Terraform 実行主体そのものであり、これを Terraform 管理にすると destroy が自分の認証手段を消す。また azurerm provider の管理対象（ARM）ではなく Entra ID（Microsoft Graph）側のオブジェクトで、管理するなら azuread provider の追加が必要になる。PR 用 credential を意図的に登録していない判断は [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)
- **作り直す手順**: [bootstrap.md §11-1 / §11-2](./bootstrap.md#11-entra-id-アプリ登録--federated-credential--ロール割当1h)（アプリ登録 → SP 作成 → immutable subject 形式での federated credential 登録。subject の実測値・形式の罠は同節に記載）。appId は再作成で変わるため、再作成したら #7 のロール割当もやり直し、本台帳の appId / SP object id を更新する
- **確認コマンド**:

  ```bash
  az ad app show --id 3a79df61-4c85-4f92-9368-1ca8588a1d17 --query '{displayName:displayName, appId:appId}' -o json
  az ad app federated-credential list --id 3a79df61-4c85-4f92-9368-1ca8588a1d17 --query "[].{name:name, subject:subject}" -o json   # 1 本のみのはず
  az ad sp show --id 3a79df61-4c85-4f92-9368-1ca8588a1d17 --query '{objectId:id}' -o json
  ```

- **固有のリスク・注意**: credential が main 用 1 本より増えていたら、それは「誰かが権限経路を追加した」重大な差分（ADR-0012 の決定に反する）。appId / SP object id は識別子であり秘密ではない（secret レスの OIDC 構成のため、このアプリにクライアントシークレットは存在しないのが正常。`az ad app credential list --id <appId>` が空であること）

## 7. ロール割当 2 件（CI 用 service principal 向け）

| ロール | スコープ |
| --- | --- |
| `Contributor` | `rg-felisaichatbot-dev-tf`（#3） |
| `Storage Blob Data Contributor` | Storage Account `felisaichatbottfstate`（#5） |

- **なぜ管理外か**: 権限が壊れる。CI の Terraform がこの 2 件を前提に動くため、Terraform 管理にすると destroy が「state を読む権限」「リソースを作る権限」を自分で消す。また管理するには service principal に `Role Based Access Control Administrator` 相当が必要になり、[ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) で却下した権限昇格経路を開くことになる
- **作り直す手順**: [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) の `az role assignment create` ×2
- **確認コマンド**:

  ```bash
  az role assignment list --assignee 3a79df61-4c85-4f92-9368-1ca8588a1d17 --all \
    --query "[].{role:roleDefinitionName, scope:scope}" -o json   # 上表の 2 件のみのはず
  ```

- **固有のリスク・注意**: 2 件より**多い**のは権限昇格の兆候、**少ない**のは CI の apply / state アクセスが壊れる予兆。どちらも即調査する。付与しないと決めたもの（サブスクリプション Contributor / RBAC Administrator）は [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) と ADR-0012 に記録済み

---

## 関連

- [ADR-0009](../adr/0009-azure-openai-as-llm-provider.md) — Azure OpenAI 採用と手動作成の経緯
- [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — SP 最小権限・RG 分離（#3 / #6 / #7 の設計判断）
- [ADR-0013](../adr/0013-azure-resource-naming-convention.md) — 命名規則と Azure OpenAI の改名しない例外
- [ADR-0014](../adr/0014-keep-azure-openai-out-of-terraform.md) — Azure OpenAI を Terraform 管理外に据え置く判断（#1 の正本）
- [bootstrap.md](./bootstrap.md) §2 / §11 / §12 — 各リソースの作成手順の正本
- [day3-5-execution-plan.md](./day3-5-execution-plan.md) §8 — 全消し手順（3 RG の削除順と保留判断）
