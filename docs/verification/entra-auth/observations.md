# DB / Azure OpenAI の Microsoft Entra 認証への切替の実測記録（Issue #86）

手順の正本は [entra-auth-cutover.md](../../operations/entra-auth-cutover.md)、判断は
[ADR-0031](../../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md)。
時刻はすべて UTC。トークン・パスワード・API キー・アカウント名は記録しない。
外形監視（`PROBE_ENABLED`）は 2026-09-19 13:39 から段階 7 の検証完了まで**計画停止**した
（この間の可用性 SLI の欠測は計画停止によるもので障害ではない）。

## 0. 構成

- 対象: PostgreSQL Flexible Server `pgsql-felisaichatbot-dev-02`（PG17、B1ms）、Azure OpenAI
  `felisaichatbot-openai-dev-02`、managed identity `id-felisaichatbot-dev`（ACR pull 用の既存 identity を流用）
- デプロイイメージ: backend / backend-ops / frontend の 3 本を `sha-3e5240c` で build・push（段階 4）
- ユニットテスト: 変更前 163 passed / 13 skipped → 変更後 190 passed / 13 skipped（新規 27 件。
  skip は `TEST_DATABASE_URL` 未設定の DB テスト）

## 1. 段階 2: Entra 認証の有効化（persistent apply。2026-09-19）

plan は 1 to add（Entra 管理者）/ 1 to change（`authentication`）/ 0 to destroy。

| 項目 | 実測 |
| --- | --- |
| サーバー `state` | Ready → **Updating 13:40:11** → **Ready 13:41:17**（約 66 秒。10 秒間隔のポーラー） |
| frontend `/readyz` | 13:39:59〜13:43:47 の全サンプル 200（低下なし） |
| obs Job（毎分） | 13:04〜13:43 の全 execution が Succeeded |
| `obs.heartbeat` | **欠落ゼロ**。id 37765 = 13:40:22（Updating 中）、37766 = 13:41:18（Ready 復帰直後）が連続 |
| `obs.marker_id_seq` | `last_value` 37789 = `max(id)` 37789（飛びなし） |
| `authConfig` | `activeDirectoryAuth: Enabled` / `passwordAuth: Enabled`、管理者 1 件（`principalType: User`） |

事前説明との差: 「再起動中は obs Job が失敗し heartbeat に数分の空白ができる」と説明していたが、
実測は Job の失敗 0 件・空白ゼロだった（更新は約 66 秒で、毎分の Job の間に収まった）。

## 2. 段階 3: DB ロールの作成（ops コンテナ、Entra 管理者のトークン）

- `pgaadauth_create_principal('id-felisaichatbot-dev', false, false)` → `Created role for "id-felisaichatbot-dev"`
- `GRANT felisadmin TO "id-felisaichatbot-dev"` → `GRANT ROLE`（Entra 管理者で実行可能。fallback 不要）
- 継承: `id-felisaichatbot-dev` → `felisadmin`（`inherit_option = t`）
- 権限: `public.documents` DML = t、`obs.heartbeat` INSERT = t、`obs.marker_id_seq` USAGE = t
- 所有者: スキーマ `public` は `azure_pg_admin`、`obs` は `felisadmin`。テーブル・シーケンスはすべて
  `felisadmin` 所有（public: テーブル 5 / シーケンス 4、obs: テーブル 7 / シーケンス 2）
- 落とし穴: `pgaadauth_list_principals` の列名は `rolname`（当初 `rolename` と書いてエラー）。
  `#EXT#` を含む UPN は keyword 形式で渡した

## 3. 段階 4: DB 接続を managed identity へ（ephemeral apply）

plan は 0 to add / 7 to change（serving / ops / frontend / migrate / obs / seed / embed）/ 0 to destroy。
`db_auth_mode = password` での plan は No changes（rollback モードは現行と同一）。

| 項目 | 実測 |
| --- | --- |
| serving の env | `DB_AUTH_MODE` / `AZURE_CLIENT_ID` が追加 |
| `/readyz` | `{"status":"ok","db":"ok","obs":{"heartbeat_age_seconds":21,...}}` |
| migrate Job | Succeeded（alembic が managed identity で接続） |
| ops から psql | **`current_user = id-felisaichatbot-dev`**、`obs.heartbeat` 37759 行（パスワード不使用の接続を実証） |
| obs Job | 直近 3 回 Succeeded（14:23 / 14:24 / 14:25） |

## 4. 段階 5: Azure OpenAI を managed identity へ

- ロール割当 `Cognitive Services OpenAI User`（スコープ = Azure OpenAI リソース）を 14:26:37 に作成
- plan は 0 to add / 2 to change（serving / embed Job）/ 0 to destroy。serving の env から
  `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_CONFIG_CHECKSUM` が消え `AZURE_OPENAI_AUTH_MODE` に置換、
  secret は `database-url` / `chat-api-key` の 2 つのみ

| 項目 | 実測 |
| --- | --- |
| ops から Bearer で embeddings | **`AOAI_DIRECT status=200 dims=1536`** |
| backend `/chat`（内部 ingress） | **`CHAT status=200 events={'message': 484, 'done': 1} reply_chars=630`**（実データに基づく応答。RAG 経路が動作） |

## 5. 段階 6a: Azure OpenAI のキー認証を無効化

- `az resource update --set properties.disableLocalAuth=true`
- 旧 API キーでの embeddings 呼び出し: **`403` + `{"error":{"code":"AuthenticationTypeDisabled","message":"Key based authentication is disabled for this resource."}}`**
- 反映: 設定から**約 1 分**で 403（公式の「通常数分・最大数時間」より速い）
- managed identity 経路は無影響: `AOAI_DIRECT status=200 dims=1536`、`CHAT status=200 events={'message': 844, 'done': 1} reply_chars=1143`

事前説明との差: 計画では旧キーは 401 になると想定していたが、実測は 403 + `AuthenticationTypeDisabled`
（認証情報は有効だが認証方式が無効、という意味で 403 が正しい）。

## 6. 段階 6b: PostgreSQL のパスワード認証を無効化（2026-09-20）

### 6b-1. `password_auth_enabled = false`（変数は残す）

plan は 0 to add / 1 to change（`password_auth_enabled = true -> false` の 1 行）/ 0 to destroy。
apply 所要 2 分 15 秒。

| 項目 | 実測 |
| --- | --- |
| サーバー `state` | Ready → **Updating 08:25:56** → **Ready 08:27:07**（約 71 秒） |
| frontend `/readyz` | 08:25:39〜08:30:05 の全サンプル 200 |
| obs Job | 08:20〜08:31 の全 execution が Succeeded（apply 中の 08:26 / 08:27 も） |
| `felisadmin` のパスワード接続 | **拒否**: `FATAL: pg_hba.conf rejects connection`（正しいパスワードでも pg_hba の段階で拒否） |
| managed identity 接続 | `current_user = id-felisaichatbot-dev` |
| `authConfig` | `passwordAuth: Disabled` / `activeDirectoryAuth: Enabled` |

**公式ドキュメントには記載がないが、パスワード認証の無効化でも Entra 有効化と同程度（約 70 秒）の
再起動相当の更新が起きる。** apply 所要時間のうちサーバー側の更新は約 71 秒で、残りは ARM の完了待ち。

### 6b-2. `administrator_password` 変数の削除

plan は 0 to add / 1 to change（`administrator_password = (sensitive value) -> null`）/ 0 to destroy。
azurerm 5.1.0 の Update は空文字を `administratorLoginPassword` として PATCH する実装だが、API は拒否せず
apply は成功した（1 分 7 秒）。**state の `administrator_password` は空文字列**（`terraform show -json` と
`terraform state pull` の両方で値の長さだけを判定。`ignore_changes` / `state rm` は不要）。
`terraform state show` は sensitive をマスクして表示するため、空か非空かの判定には使えない。

## 7. 段階 7: chat API キーを Terraform 生成へ

plan は 1 to add（`random_password.chat_api_key`）/ 2 to change（serving / frontend）/ 0 to destroy。
secret 名は不変（serving: `chat-api-key` / `database-url`。frontend: `chat-api-key` /
`microsoft-provider-authentication-secret`）。検証: `/readyz` ok、`AOAI_DIRECT status=200 dims=1536`、
**`CHAT status=200 events={'message': 545, 'done': 1} reply_chars=707`**。

## 8. 最終状態

- 秘密値: PostgreSQL 管理者パスワード（無効化・state から消去）、パスワード込み DSN、Azure OpenAI API キー
  （キー認証無効化）、人が扱う chat API キー — の 4 種類が消えた。残るのは Easy Auth のクライアント
  シークレットと Terraform 生成の chat API キー（いずれも state と Container Apps の secret にのみ存在）
- managed identity `id-felisaichatbot-dev` のロール割当: AcrPull（RG）と Cognitive Services OpenAI User
  （Azure OpenAI リソース）の 2 件
- 保存した `terraform plan` のファイルは変数値（旧パスワード・旧 API キー・DSN）を埋め込むため、apply 後に削除した

## 9. ユニットテストで確認できず実測で確認した範囲

実トークン取得（Container Apps の identity endpoint）、DB への Entra ログイン、`pgaadauth_create_principal`
後の権限継承、ロール割当の伝播、`disableLocalAuth` の反映、パスワード認証無効化の再起動挙動。
