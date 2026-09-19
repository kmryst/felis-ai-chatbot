# ADR-0030: 検証環境のサブスクリプション移行と `02` サフィックス命名

## ステータス

Accepted

## 日付

2026-09-19

## 決定内容

検証環境を新しい Azure サブスクリプションへ移行するにあたり、次を決定する。

1. **グローバル一意名を持つ 4 リソースは末尾にゼロ詰め 2 桁の `02` を付けた新名で作成する**
   （[ADR-0013](0013-azure-resource-naming-convention.md) の命名規則に対する例外として記録する）。
   それ以外のリソース名は移行元と同一にする。

   | 種別 | 移行元 | 移行先 |
   | --- | --- | --- |
   | Storage Account（tfstate） | `felisaichatbottfstate` | `felisaichatbottfstate02` |
   | Container Registry | `felisaichatbotacrdev` | `felisaichatbotacrdev02` |
   | PostgreSQL Flexible Server | `pgsql-felisaichatbot-dev` | `pgsql-felisaichatbot-dev-02` |
   | Azure OpenAI（custom subdomain も同名） | `felisaichatbot-openai-dev` | `felisaichatbot-openai-dev-02` |

2. **移行元の環境は destroy せず、そのまま残す。** Terraform state も移行元の Storage Account に残す。
3. **秘密値（DB 管理者パスワード / Azure OpenAI キー / chat API キー / Easy Auth client secret）は
   すべて新規発行し、移行元の値を使い回さない。** Terraform へは層ごとの `terraform.tfvars`
   （gitignore 済み）で渡し、`TF_VAR_*` の export と混在させない。
4. **GitHub Actions 用の OIDC service principal（[ADR-0012](0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)）は移行先では作らない。**
   deploy workflow（Issue #82）に着手する時点で、移行先で作り直す。
5. **DB の初期化は migrate Job（`alembic upgrade head`）ではなく、`alembic upgrade 0001` →
   退避した obs スキーマの復元 → `CREATE EXTENSION pgstattuple` → `alembic stamp head` の順で行う。**
   復元後は毎分の heartbeat を移行元の系列に追記する（世代識別列は追加しない）。

## 背景

- 検証環境を新しい Azure サブスクリプションへ移行する必要が生じた。
- Storage Account / ACR / PostgreSQL Flexible Server / Azure OpenAI は DNS 名になるグローバル一意名を
  持ち、移行元に同名のリソースが存在する間は同じ名前を取得できない（移行前に `check-name` /
  `checkNameAvailability` 系の読み取りで 4 件とも `02` 付きの空きを確認済み）。
- Terraform の `backend` ブロックは変数を受け付けないため、tfstate 用 Storage Account の名前は
  `backend.tf` の書き換えで切り替えるしかない。
- 観測データ（`obs` スキーマ）は移行前に `pg_dump -n obs` で退避してあり、Alembic の migration 0002
  が `CREATE SCHEMA obs` と初期行の INSERT を行うため、migration を先に流すと復元と衝突する。
- 移行先には移行元の Entra ID オブジェクト（app registration / SP / federated credential）が
  存在しないため、作り直す。

## 検討した選択肢

### 命名

- **A. `02` サフィックス（採択）**: 4 件だけ変えて他は同名。差分は `backend.tf` 2 か所と
  `variables.tf` の default 2 か所の計 4 行に収まる
- B. 移行元のリソースを削除して同名を再取得: Azure OpenAI は削除後 48 時間の名前予約と purge が要り、
  Storage Account も削除直後は同名を再利用できないことがある。移行元を残す判断（2）とも矛盾する
- C. 全リソースを新しい命名（環境名の変更など）に揃える: 変更しなくてよい名前まで変わり、
  台帳・手順書・実測記録との突き合わせが全面的に必要になる

### 移行元の扱い

- **A. 残す（採択）**: `backend.tf` / `variables.tf` を revert して `terraform init -reconfigure`
  すれば移行元の state を読み戻せるため、ロールバック経路が残る。過去の実測記録が参照する
  リソースをそのまま確認できる
- B. destroy する: ロールバック経路と参照先が消える。移行先の稼働確認前に行う理由がない

### 秘密値

- **A. 全て新規発行（採択）**: 移行元と移行先で同じ秘密値を共有しない
- B. 移行元の値を使い回す: 2 環境で同一の秘密値が有効な期間ができる

### OIDC service principal

- **A. 作らない（採択）**: 2026-09-19 時点で Azure 資格情報を使う workflow は存在しない
  （`terraform-checks.yml` は `-backend=false` の静的検査、`readyz-probe.yml` は repository variables
  のみ）。使われない資格情報を作らない
- B. 移行元と同じ構成で作る: deploy workflow が無いうちは検証できない資格情報が残る

### DB 初期化

- **A. `upgrade 0001` → 復元 → `stamp head`（採択）**: dump が持つ `obs` スキーマと migration 0002〜0004
  の実体が二重にならない
- B. `alembic upgrade head` → 復元: `schema "obs" already exists` で衝突する
- C. 復元 → `upgrade head`: 0002 の初期行 INSERT が主キー衝突する

## 採択理由

- 変更を「動作に必須な 4 行」に限定でき、命名規則（ADR-0013）の逸脱を 4 件に留められる
- 移行元を残すことでロールバックと過去記録の参照先を失わない
- 秘密値の全更新と OIDC SP の見送りは、使われない・共有される資格情報を作らない方針に沿う
- DB 初期化の順序は、退避した観測データを欠損なく引き継ぐ唯一の順序である

## 影響

- `terraform/persistent/backend.tf` / `terraform/ephemeral/backend.tf` の `storage_account_name`、
  `terraform/persistent/variables.tf` の `server_name` default、`terraform/ephemeral/variables.tf` の
  `acr_name` default を変更する（4 行）
- ADR-0013 の「全リソースの名前」表は移行元の名前のまま残し、本 ADR を例外として参照する
- 管理外リソース台帳（`docs/operations/azure-resource-inventory.md`）の §B #1 / #5 / #8 / #9 / #12 と
  リソースプロバイダー表を移行先の値に更新する。#6 / #7（OIDC SP とロール割当）は「移行先では未作成」
  と記載する
- Azure OpenAI のエンドポイントと CAE の既定ドメインが変わるため、ローカルの環境変数と
  `READYZ_URL`（repository variable）を付け替える
- Easy Auth の app registration / SP / 同意 / 割当は移行先で作り直す
  （`openIdIssuer` は `data.azurerm_client_config` から組み立てるためコード変更は不要）
- 実測は [docs/verification/subscription-migration/observations.md](../verification/subscription-migration/observations.md)

## 関連

- [ADR-0009](0009-azure-openai-as-llm-provider.md)、[ADR-0012](0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)、
  [ADR-0013](0013-azure-resource-naming-convention.md)、[ADR-0014](0014-keep-azure-openai-out-of-terraform.md)、
  [ADR-0021](0021-heartbeat-table-as-recovery-marker.md)、[ADR-0027](0027-frontend-azure-deployment-and-public-surface.md)
- Issue #274
