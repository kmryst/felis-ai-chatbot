# ADR-0013: Azure リソース命名規則（CAF 略語準拠）の制定と未作成リソース名の統一

## ステータス

Accepted

## 日付

2026-08-20

## 決定内容

Azure リソースの命名規則を次のとおり制定し、**未作成のリソース名のみ**をこの規則に合わせて統一する。既に Azure 上に存在するリソースは改名・再作成しない。

### 規則

1. **ハイフンが使える資源**: `<type>-felisaichatbot-<env>[-<qualifier>]`
   - `<type>` は [Microsoft Cloud Adoption Framework の推奨略語](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations)（2026-08-20 確認）をそのまま使う。推測で略語を作らない
   - `<env>` は環境名（現状 `dev` のみ）。**環境をまたいで共有する資源には付けない**（下記 3）
   - `<qualifier>` は同一 type・同一環境内で用途を区別する場合のみ末尾に付ける（例: `-tf`、`-restored`、`-tfstate`）
2. **ハイフンが使えない資源**（Storage Account・ACR）: `felisaichatbot<用途><env>` の小文字連結（例: `felisaichatbotacrdev`）。これは規則違反ではなく **Azure 側の文字種制約**（Storage Account は小文字英数字のみ 3〜24 文字、ACR は英数字のみ 5〜50 文字）による別形式である
3. **環境サフィックス `<env>` の要否**: 環境のライフサイクル（作成・destroy）に従う資源には付ける。**環境をまたいで共有し、環境の destroy で消えない資源（tfstate 用 RG / Storage Account）には付けない**
4. **グローバル一意名**（DNS 名になる資源）は、名前の確定・変更のたびに読み取り系の空き確認（`az acr check-name` / `az storage account check-name` / `checkNameAvailability` API）をやり直す（bootstrap.md §3）

### 全リソースの名前（この表が正本）

| リソース | CAF 略語 | 名前 | 旧名（変更した場合） | Azure 上の存在 |
| --- | --- | --- | --- | --- |
| Resource group（Azure OpenAI 同居） | `rg` | `rg-felisaichatbot-dev` | —（規則適合） | 存在する |
| Azure OpenAI | `oai` | `felisaichatbot-openai-dev` | —（**例外**。下記） | 存在する |
| Resource group（Terraform 管理用） | `rg` | `rg-felisaichatbot-dev-tf` | —（規則適合。qualifier `-tf`） | 未作成 |
| Resource group（tfstate） | `rg` | `rg-felisaichatbot-tfstate` | `felisaichatbot-rg-tfstate` | 未作成 |
| PostgreSQL Flexible Server | `pgsql` | `pgsql-felisaichatbot-dev` | `felisaichatbot-pg-dev` | 未作成 |
| PostgreSQL PITR 復元先（Day 4。証跡取得後に削除） | `pgsql` | `pgsql-felisaichatbot-dev-restored` | `felisaichatbot-pg-dev-restored` | 未作成 |
| Key Vault | `kv` | `kv-felisaichatbot-dev` | —（規則適合） | 未作成 |
| ACR | `cr` | `felisaichatbotacrdev` | —（文字種制約の連結形式） | 未作成 |
| tfstate Storage Account | `st` | `felisaichatbottfstate` | —（文字種制約の連結形式・環境非依存） | 未作成 |
| Container Apps（Day 3 予定） | `ca` | `ca-felisaichatbot-dev` | —（本 ADR で予約） | 未作成 |
| Container Apps Environment（Day 3 予定） | `cae` | `cae-felisaichatbot-dev` | —（本 ADR で予約） | 未作成 |
| Log Analytics workspace（導入する場合） | `log` | `log-felisaichatbot-dev` | —（本 ADR で予約） | 未作成 |
| Managed Identity（user-assigned。導入する場合） | `id` | `id-felisaichatbot-dev` | —（本 ADR で予約） | 未作成 |

### 既存リソースの例外（改名しない）

`felisaichatbot-openai-dev` は規則どおりなら `oai-felisaichatbot-dev` だが、**改名・再作成しない**。

- 既に稼働中で、Day 2 で結線した RAG（chat / embedding デプロイ）がこの名前のエンドポイントに依存している
- FreeTrial のクォータで取得したリソースであり、作り直してクォータを再取得できる保証がない（ADR-0009）
- Azure OpenAI アカウント名は改名不可のため、規則に合わせるには再作成しかない

黙って規則違反を放置するのではなく、本 ADR を例外の記録とする。今後この例外を増やさないことが規則の一部である。

## 背景

命名規則がどこにも明文化されておらず、`rg-` 前置（`rg-felisaichatbot-dev`）・中置（`felisaichatbot-rg-tfstate` / `felisaichatbot-pg-dev`）・連結（`felisaichatbottfstate`）が場当たりに混在していた。

RG 名は後から変えると tfstate の移行が発生し、PostgreSQL サーバー名は後から変えるとサーバーの作り直しになる。残り 3 日の計画（Day 3 に初回 apply）でそれは実質やり直せない。**未作成のいまなら、変更対象はドキュメントとコードの文字列だけで、Azure 側の作業はゼロ**である。

## 検討した選択肢

1. **CAF 略語の前置 `<type>-felisaichatbot-<env>` に統一する（採択）**
2. 現状のまま（明文化のみ・改名なし）: 中置・前置の混在が Day 3 以降のリソース追加のたびに再生産される。却下
3. 中置 `felisaichatbot-<type>-<env>` に統一する: 既存の `rg-felisaichatbot-dev` と Key Vault 予定名が前置で、稼働中リソース側を動かせない以上、前置に寄せるほうが変更箇所が少ない。また CAF の公式例（`pip-sharepoint-prod-westus-001` 等）も type 前置であり、業界慣行に沿う。却下
4. PostgreSQL の略語に `psql` を使う: CAF の一次情報は `pgsql`（`Microsoft.DBforPostgreSQL/flexibleServers` → `pgsql`）であり、`psql` は CLI クライアント名との混同を招く独自略語になる。却下

## 採択理由

- **CAF 準拠**: 略語を一次情報から取ることで「推測の独自略語」を排除し、以後のリソース追加時も同じ表を引くだけで名前が決まる
- **tfstate 用 RG / Storage Account に `<env>` を付けない理由**: tfstate は `key`（`persistent/terraform.tfstate` 等）で層・環境を区別する設計で、Storage Account 自体は環境をまたいで 1 つを共有する。また dev を destroy しても state は残す persistent / ephemeral 分離（bootstrap.md §12）のとおり、環境のライフサイクルに従わない。`dev` を付けると「dev の全消しで消してよいもの」に見え、誤削除を誘発する
- **連結形式を CAF 前置（`crfelisaichatbotdev` / `stfelisaichatbot...`）にしない理由**: ハイフンなしでは区切りが読めず type 前置の判読性の利点がない。既定名 `felisaichatbotacrdev` / `felisaichatbottfstate` は空き確認済み（bootstrap.md §3）で、変えると空き確認のやり直しだけが増える

## 影響

- `terraform/persistent/backend.tf`（tfstate RG 名）と `variables.tf`（サーバー名の既定値）を新名に変更（apply 前・state 未作成のため移行作業なし）
- `docs/operations/bootstrap.md` §3 / §11 / §12、`docs/operations/day3-5-execution-plan.md` の該当コマンド・設計値をすべて新名に更新
- 変更後のグローバル一意名の空き確認（2026-08-20 実施・読み取り系のみ）: `pgsql-felisaichatbot-dev` は `checkNameAvailability` で `nameAvailable: true`。`rg-felisaichatbot-tfstate` は RG（サブスクリプション内一意）のため空き確認不要、`az group exists` = false を確認
- ADR-0011 本文のサーバー名表記は本 ADR 制定後の名前に更新した（apply 前の予定名段階での変更であり、ADR-0011 の決定内容そのもの—保持 7 日・geo 冗長無効—は不変）
- 本 ADR の表にない新規リソースを作る場合は、まず CAF の略語を確認して本 ADR の表に行を追加してから作る

## 数値・略語の出典

- CAF 推奨略語（`rg` / `pgsql` / `kv` / `cr` / `st` / `ca` / `cae` / `log` / `id` / `oai`）: [Abbreviation recommendations for Azure resources](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations)（2026-08-20 確認）
- 名前の制約: [Naming rules and restrictions for Azure resources](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-name-rules)（2026-08-20 確認）。RG 1〜90 文字（サブスクリプション内一意）、PostgreSQL サーバー 3〜63 文字・小文字英数字とハイフン（グローバル一意）、Key Vault 3〜24 文字（グローバル一意）、ACR 5〜50 文字・英数字のみ（グローバル一意）、Storage Account 3〜24 文字・小文字英数字のみ（グローバル一意）、Container Apps 2〜32 文字、Log Analytics workspace 4〜63 文字
- 採用名の文字数: `pgsql-felisaichatbot-dev` 24/63、`pgsql-felisaichatbot-dev-restored` 33/63、`kv-felisaichatbot-dev` 21/24、`felisaichatbotacrdev` 20/50、`felisaichatbottfstate` 21/24、`ca-felisaichatbot-dev` 21/32 — すべて上限内

## 関連

- [ADR-0009](./0009-azure-openai-as-llm-provider.md) — 例外とする Azure OpenAI（`felisaichatbot-openai-dev`）の採用経緯とクォータ制約
- [ADR-0011](./0011-backup-retention-and-geo-redundancy.md) — サーバー名表記を本 ADR の名前に更新
- [ADR-0012](./0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — `rg-felisaichatbot-dev-tf` / tfstate Storage Account の分離判断（名前は本規則に適合）
- `docs/operations/bootstrap.md` §3（空き確認手順）・§11・§12
- `docs/operations/day3-5-execution-plan.md` §3-1（設計値の正本）
