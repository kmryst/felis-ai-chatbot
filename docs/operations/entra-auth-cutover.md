# DB / Azure OpenAI の認証を Microsoft Entra 認証（managed identity）へ切り替える手順（Issue #86）

PostgreSQL Flexible Server と Azure OpenAI への認証を、パスワード / API キーから
user-assigned managed identity（`id-felisaichatbot-dev`）の Microsoft Entra アクセストークンへ
切り替える手順と、切替後の運用（Entra 管理者としての接続、ops コンテナからの接続、rollback）の正本。
設計判断は [ADR-0031](../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md)、
実測は [docs/verification/entra-auth/observations.md](../verification/entra-auth/observations.md)。

> 実行前提: apply と Azure への書き込みは CLAUDE.md の確認必須操作であり、**ユーザーの明示承認を
> 得てから**実行する。本書は手順の正本であって実行許可ではない。

## 0. 停止条件

- plan に destroy / replacement が出たら apply しない（PostgreSQL の再作成は復元済みの obs 実データを失う）
- 段階ごとに apply → 検証 → 次へ。まとめて apply しない
- 秘密値（トークン・パスワード・API キー）を画面・ログ・記録に出さない

## 1. 前提と用語

- managed identity `id-felisaichatbot-dev` が backend serving / ops / Job のすべてに付与されている
  （[台帳 §B #8](./azure-resource-inventory.md)）
- Azure OpenAI は Terraform 管理外（ADR-0014）。ロール割当と `disableLocalAuth` は az CLI で行い台帳に記録する
- トークンのスコープ: DB は `https://ossrdbms-aad.database.windows.net/.default`、Azure OpenAI は
  `https://cognitiveservices.azure.com/.default`。user トークンは最大 1 時間、managed identity は最大 24 時間
- **UPN に `#EXT#` を含むアカウント**（個人 Microsoft アカウントで作ったディレクトリのユーザー、
  またはゲスト）は、URL 形式の DSN では `#` がフラグメント扱いになって壊れる。keyword 形式
  （`psql "host=… user=<UPN> dbname=postgres sslmode=require"`）か `PGUSER` で渡す。名前は大文字小文字を区別する
- `az containerapp exec` に流し込む行は **ASCII にする**（コンテナ側のロケール設定が無く、日本語は
  エコーが化ける。処理には影響しないが記録が読めなくなる）

## 2. 段階と検証・戻し方

| 段階 | 変更 | 検証 | 戻し方 |
| --- | --- | --- | --- |
| 1. アプリ | `DB_AUTH_MODE` / `AZURE_OPENAI_AUTH_MODE` / `AZURE_CLIENT_ID`（既定は password / api-key） | ユニットテスト `backend/tests/test_entra_auth.py`。既存テスト無変更で pass | 既定が旧モードで挙動不変 |
| 2. persistent | `authentication` ブロック（Entra + パスワード併存）+ Entra 管理者 | plan は 1 add / 1 change / 0 destroy。**サーバーが再起動する**（実測 66 秒）。`activeDirectoryAuth: Enabled` | `authentication` を外して apply |
| 3. DB ロール | §3 | `pgaadauth_list_principals(false)` に `id-felisaichatbot-dev`。`GRANT felisadmin` の継承 | `DROP ROLE` |
| 4. ephemeral | パスワード無し DSN + `DB_AUTH_MODE=managed-identity` + `AZURE_CLIENT_ID` を全 DB 利用コンテナへ。obs Job の psql は `PGPASSWORD="$(python -m app.entra_auth db)"` | `/readyz` 200、migrate Job Succeeded、ops から `select current_user` が `id-felisaichatbot-dev`、obs Job Succeeded | `-var db_auth_mode=password` と旧 DSN で apply（PostgreSQL のパスワード認証が有効な間のみ） |
| 5. Azure OpenAI | ロール割当 + `AZURE_OPENAI_AUTH_MODE=managed-identity`、API キーの変数 / secret / precondition を削除 | ops から Bearer で embeddings が 200、`/chat` が 200 | ロール割当を削除し、段階 4 のコードで apply |
| 6a. 旧経路を閉じる（Azure OpenAI） | `disableLocalAuth = true` | 旧キーが **403 `AuthenticationTypeDisabled`**（実測は約 1 分で反映） | `disableLocalAuth = false` |
| 6b. 旧経路を閉じる（PostgreSQL） | 6b-1: `password_auth_enabled = false`。6b-2: `administrator_password` 変数を削除 | 6b-1: **再起動相当の更新が起きる**（実測 71 秒）。パスワード接続が `pg_hba.conf rejects connection`。6b-2: state の `administrator_password` が空文字列（長さ判定） | §6: az CLI で `--password-auth Enabled --admin-password <新>` を 1 回（Terraform の構成は変えない。修復後の通常 apply が Disabled へ戻す） |
| 7. chat API キー | `random_password.chat_api_key`（`keepers.rotation = var.chat_api_key_rotation`） | `/chat` 200。secret は `database-url` / `chat-api-key` のみ | 変数を戻す |

再起動を伴う段階（2 / 6b-1）の前に `gh variable set PROBE_ENABLED --body false` で外形監視を止め、
最後の apply の検証後に `true` へ戻す。再起動中は毎分の obs Job が失敗し得るが、次の分で復帰する
（実測では失敗 0 件・heartbeat の空白ゼロ）。

## 3. Entra 管理者として接続し、managed identity 用ロールを作る（段階 3）

ops コンテナ内で実行する（private access のため作業端末から DB へは届かない。ADR-0018）。
トークンと UPN は `read -s` で流し込み、画面に出さない。

```bash
# 作業端末（Entra 管理者のアカウントで az login 済み）
az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv   # → PGPASSWORD へ
az ad signed-in-user show --query userPrincipalName -o tsv                          # → PGUSER へ

# ops コンテナ内（az containerapp exec -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --container ops --command bash）
read -s PGPASSWORD; export PGPASSWORD      # トークンを貼る（エコーされない）
read -s PGUSER; export PGUSER              # UPN を貼る（#EXT# 付きのまま）
export PGHOST=$(python3 -c 'import os,urllib.parse as u; print(u.urlparse(os.environ["DATABASE_URL"]).hostname)')
export PGDATABASE=postgres PGSSLMODE=require PGCONNECT_TIMEOUT=10
psql -X -c "select rolname, principaltype, isadmin from pgaadauth_list_principals(false);"
psql -X -c "select * from pgaadauth_create_principal('id-felisaichatbot-dev', false, false);"
psql -X -c "GRANT felisadmin TO \"id-felisaichatbot-dev\";"
psql -X -c "select has_table_privilege('id-felisaichatbot-dev','public.documents','SELECT,INSERT,UPDATE,DELETE'), has_table_privilege('id-felisaichatbot-dev','obs.heartbeat','INSERT'), has_sequence_privilege('id-felisaichatbot-dev','obs.marker_id_seq','USAGE');"
unset PGPASSWORD
```

- ロール名は managed identity の**表示名**と一致させる（`pgaadauth_create_principal` は名前で Entra
  オブジェクトを引く。照合自体は object ID で行われる）
- `pgaadauth_list_principals` の列名は `rolname`（`rolename` ではない）
- `GRANT felisadmin` は Entra 管理者で実行できる（実測）。既存オブジェクトはすべて `felisadmin` 所有のため、
  継承で alembic の `ALTER TABLE` も通る。最小権限化は #86 / #280

### 新規作成時（destroy 後の再構築。台帳の revive runbook）

Entra 認証のみで新規作成したサーバーには `felisadmin` が**存在しない**（azurerm 5.1.0 の Create は
`password_auth_enabled = false` のとき `administrator_login` の指定をエラーにするため、persistent 層は
login を送らない）。この場合 `GRANT felisadmin` は使えないので、identity のロールを**管理者として**作る:

```sql
select * from pgaadauth_create_principal('id-felisaichatbot-dev', true, false);   -- isAdmin = true
```

`isAdmin = true` は `azure_pg_admin` のメンバー + `CREATEROLE` / `CREATEDB`（公式）。migrate Job（alembic）が
`CREATE EXTENSION vector` と全オブジェクトを identity のロールで作るため、以後の所有者は identity になる。
既存環境（felisadmin 継承）と権限の広さは同等で、最小権限化の扱いも同じ（#86 / #280）。
revive runbook の順序: persistent apply → 本節（Entra 管理者で実行）→ ephemeral apply → migrate Job。

## 4. Azure OpenAI のロール割当とキー認証の無効化（段階 5 / 6a）

```bash
PRINCIPAL_ID=$(az identity show -g rg-felisaichatbot-dev-tf -n id-felisaichatbot-dev --query principalId -o tsv)
AOAI_ID=$(az cognitiveservices account show -g rg-felisaichatbot-dev -n felisaichatbot-openai-dev-02 --query id -o tsv)
az role assignment create --role "Cognitive Services OpenAI User" \
  --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --scope "$AOAI_ID"
# 反映（数分）を待ち、段階 5 の apply と検証を済ませてから:
az resource update --ids "$AOAI_ID" --set properties.disableLocalAuth=true --query properties.disableLocalAuth -o tsv
```

- custom subdomain が必須（設定済み。台帳 §B #1）。トークンの resource は `https://cognitiveservices.azure.com/`
- 検証: ops コンテナで `python -m app.entra_auth openai` のトークンを `Authorization: Bearer` に付けて
  embeddings を呼ぶ（200）。旧キーは `api-key` ヘッダで **403 + `AuthenticationTypeDisabled`**
  （公式ドキュメントは 401 と読めるが実測は 403）
- `az cognitiveservices account update` には該当オプションが無いため `az resource update` を使う

## 5. 切替後の接続方法

### ops コンテナ（managed identity）

```bash
az containerapp exec -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --container ops --command bash
# コンテナ内
PGPASSWORD="$(python -m app.entra_auth db)" psql "$DATABASE_URL" -c 'select current_user;'   # → id-felisaichatbot-dev
```

`DATABASE_URL` はパスワード無し（`postgresql://id-felisaichatbot-dev@<host>:5432/postgres?sslmode=require`）。
`AZURE_CLIENT_ID` / `DB_AUTH_MODE` は Terraform が注入する。migrate / seed / embed Job も同じ経路。

### Entra 管理者（所有者のアカウント。managed identity と独立した復旧経路）

§3 と同じ（トークン + `#EXT#` 付き UPN、keyword 形式）。managed identity のロールや割当が壊れても
この経路で `GRANT` や `pgaadauth_create_principal` をやり直せる。

### ローカル開発

- DB: docker compose の PostgreSQL（パスワード認証。`.env.example` の `DATABASE_URL`）。`DB_AUTH_MODE` は既定の `password`
- LLM: 既定の stub（ADR-0004）。**実 Azure OpenAI を API キーで呼ぶ経路は `disableLocalAuth` で閉じた。**
  ローカルから実 Azure OpenAI を使う実装（開発者アカウントの資格情報で Bearer を取る）は本 Issue の範囲外
- `AZURE_CLIENT_ID` は managed identity モードのときだけ必須（`backend/app/config.py`）

## 6. rollback と復旧

- **パスワード認証の一時的な再有効化（緊急復旧）は az CLI で行い、Terraform の構成は変えない。**
  managed identity の経路が壊れ、Entra 管理者の経路（§5）でも直せない場合の最後の手段。
  ARM の管理 API だけで完結し、DB 接続を要しない。

  ```bash
  # 認証の有効化と新しいパスワードの設定を 1 回で行う（8〜128 文字・4 カテゴリ中 3 種以上。値を履歴に残さない）
  read -s NEW_PW
  az postgres flexible-server update -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-02 \
    --password-auth Enabled --admin-password "$NEW_PW"
  unset NEW_PW
  az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-02 --query authConfig -o json
  ```

  - 更新中は 6b-1 と同程度の再起動相当の更新が起きる（**2026-09-21 実測**: CLI の完了まで 2 分 15 秒、サーバー
    `state` が `Updating` の区間は約 70 秒。`/readyz` の低下なし、obs Job の失敗なし。実施時は `PROBE_ENABLED` を
    止め、ポーラーで記録する。詳細は [実測記録 §9-1](../verification/entra-auth/observations.md)）
  - パスワード認証を有効にしても managed identity 経路は影響を受けない（実測: 有効化中も `current_user =
    id-felisaichatbot-dev` で接続できた）
  - **この間は `terraform -chdir=terraform/persistent apply` を実行しない。** 構成（`password_auth_enabled = false`）が
    正であり、apply すると Disabled へ戻る（= 修復後の収束操作）。plan は `password_auth_enabled true -> false` の
    差分を示す（意図どおり）
  - managed identity を修復（ロール / 割当 / DSN を確認）→ managed identity 接続を実測（§5）→ 通常の apply で
    Disabled へ戻す → plan が No changes になることを確認。一時パスワードは以後使えない
    （**2026-09-21 実測**: plan は `password_auth_enabled = true -> false` の 1 行のみ・replacement なし、apply 2 分 13 秒
    （`Updating` 区間は約 70 秒）、直後に `felisadmin` の接続が `pg_hba.conf rejects connection`、plan は No changes。
    「構成が正で、次の通常 apply が収束させる」設計はこの往復で実証済み）
  - 手順書の記述と実際の挙動の差: この節の手順どおりに往復できた。見込みと違ったのは所要時間の書き方だけで、
    「約 70 秒」はサーバーの `Updating` 区間であり、コマンドの完了（ARM の操作完了待ちを含む）は 2 分 15 秒かかる。
    本節はコマンド完了時間で書き直した
  - azurerm 5.1.0 の Update は `password_auth_enabled = true` を apply するときに `administrator_login` と
    `administrator_password` / `administrator_password_wo` のいずれかを**同時に**要求する。フラグだけ true にした
    Terraform 構成は provider が拒否するため、Terraform で戻す設計は採らなかった（ADR-0031「影響」）
- **新規作成（Entra 認証のみ）のサーバーにはパスワード認証の管理者ログインが存在せず、パスワードによる復旧は
  構造的に不可能**（作成後に管理者ログインを追加する API は無い）。復旧経路は Entra 管理者アカウント（§5）のみ。
  destroy 後に再構築したサーバーはこの状態になる
- **パスワード認証を長期間維持せざるを得ない場合**（Terraform で構成として持つ必要が出た場合）は override file を使う
  （付録 A）。常設しないのは、write-only の password 引数を sensitive / ephemeral 変数で書くと plan に空の in-place
  update が出続けるため（[実測記録 §10](../verification/entra-auth/observations.md)）
- Azure OpenAI: `disableLocalAuth=false` に戻せばキー認証が復活する（キー自体は失効していない）
- chat API キー: `chat_api_key_rotation` を変えて apply すれば再生成される。値が要るときは
  `terraform -chdir=terraform/ephemeral output -raw chat_api_key`（ファイルや履歴に残さない）
- tfvars の編集は編集前のコピーを `backup-before-*.tfvars`（gitignore 済み。Terraform は自動読込しない）に
  残してから行う

## 7. 状態の確認コマンド（読み取りのみ）

```bash
az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-02 --query authConfig -o json
#   → activeDirectoryAuth: Enabled / passwordAuth: Disabled
az cognitiveservices account show -g rg-felisaichatbot-dev -n felisaichatbot-openai-dev-02 --query properties.disableLocalAuth -o tsv   # → true
az role assignment list --assignee "$(az identity show -g rg-felisaichatbot-dev-tf -n id-felisaichatbot-dev --query principalId -o tsv)" --all \
  --query "[].{role:roleDefinitionName,scope:scope}" -o table   # → AcrPull（RG）と Cognitive Services OpenAI User（Azure OpenAI）
az containerapp show -n ca-felisaichatbot-dev -g rg-felisaichatbot-dev-tf --query "properties.configuration.secrets[].name" -o tsv
#   → chat-api-key / database-url のみ
```

## 付録 A. パスワード認証を Terraform の構成として一時的に持つ（override file）

§6 の CLI 復旧後、Disabled へ戻せない期間が長引く場合だけ使う。Terraform の
[override file](https://developer.hashicorp.com/terraform/language/files/override)（`*_override.tf`）は同じ
resource ブロックへ属性を合成する公式機能で、手編集なしに置く・撤去するで切り替えられる（特殊用途向けと案内されている）。

```hcl
# terraform/persistent/rollback_override.tf（gitignore 対象にはなっていないので、コミットしないこと。撤去で元に戻る）
variable "rollback_administrator_password" {
  type      = string
  sensitive = true
  ephemeral = true
}

variable "rollback_administrator_password_version" {
  type = number
}

resource "azurerm_postgresql_flexible_server" "main" {
  administrator_login               = "felisadmin"
  administrator_password_wo         = var.rollback_administrator_password
  administrator_password_wo_version = var.rollback_administrator_password_version
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }
}
```

- `TF_VAR_rollback_administrator_password` で渡し、version は前回より大きい値にする。`administrator_login` は ForceNew
  属性なので state と同じ `felisadmin`（新規作成したサーバーには存在しないため、この付録は移行元のサーバーにしか使えない）
- この構成が置かれている間は plan に空の in-place update が出続ける（sensitive / ephemeral マークによる。実測記録 §10）。
  「暫定構成を維持中」の印として扱い、撤去して通常の apply で Disabled へ戻せば消える
- **未検証**（plan のみで形を確認。apply はしていない）

## 関連

- [ADR-0031](../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md)
- [azure-resource-inventory.md](./azure-resource-inventory.md) §B #1 / #8 / #13 / #14
- [llm-provider-cutover.md](./llm-provider-cutover.md)（API キー方式の切替手順。キー認証の無効化後は §2 の API キー注入は行わない）
- [vnet-integration-cutover.md](./vnet-integration-cutover.md) §3-2（ops コンテナの exec 作法）
