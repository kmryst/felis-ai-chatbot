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
| 6b. 旧経路を閉じる（PostgreSQL） | 6b-1: `password_auth_enabled = false`。6b-2: `administrator_password` 変数を削除 | 6b-1: **再起動相当の更新が起きる**（実測 71 秒）。パスワード接続が `pg_hba.conf rejects connection`。6b-2: state の `administrator_password` が空文字列（長さ判定） | `true` に戻して apply し、`az postgres flexible-server update --admin-password` で再設定 |
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

- **Terraform の `authentication` 変更は ARM の管理 API だけで完結し、DB 接続を要しない。** managed identity
  の経路が壊れても `password_auth_enabled = true` へ戻す apply は実行できる。戻した後は
  `az postgres flexible-server update -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-02 --admin-password '<新しいパスワード>'`
  で管理者パスワードを再設定する（旧パスワードは使い回さない）
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

## 関連

- [ADR-0031](../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md)
- [azure-resource-inventory.md](./azure-resource-inventory.md) §B #1 / #8 / #13 / #14
- [llm-provider-cutover.md](./llm-provider-cutover.md)（API キー方式の切替手順。キー認証の無効化後は §2 の API キー注入は行わない）
- [vnet-integration-cutover.md](./vnet-integration-cutover.md) §3-2（ops コンテナの exec 作法）
