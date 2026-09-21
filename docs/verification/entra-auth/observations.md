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

## 9-1. レビュー対応（2026-09-21）: 新規作成と rollback の provider 検査

PR レビューの指摘 2 件を azurerm 5.1.0 のソースで確認した。

- Create: `password_auth_enabled = false` のとき `administrator_login` / `administrator_password` /
  `administrator_password_wo` の指定をエラーにする → `administrator_login` の既定を null にした。既存サーバーは
  Optional + Computed のため plan は **No changes**（state の `felisadmin` が保たれる）
- Update: `password_auth_enabled = true` にする apply で `administrator_login` とパスワード引数の両方を要求する →
  Terraform で rollback する設計をやめ、az CLI（手順書 §6）に切り替えた

### 9-2. rollback の実地検証（2026-09-21。手順書 §6 の往復をそのまま実施）

外形監視は 07:52〜08:04 の間だけ計画停止。一時パスワードはスクリプト内で生成し、検証後に認証ごと無効化した。

| 段階 | 実測 |
| --- | --- |
| 有効化: `az postgres flexible-server update --password-auth Enabled --admin-password …` | コマンド 07:55:27 → 07:57:42（**2 分 15 秒**）。サーバー `state`: Ready → **Updating 07:55:38** → **Ready 07:56:48**（約 70 秒） |
| 有効化後の接続 | `felisadmin` + 一時パスワード: **accepted**。managed identity: **`current_user = id-felisaichatbot-dev`（継続。壊れない）** |
| 収束: 通常の `terraform plan` / `apply`（構成は `password_auth_enabled = false` のまま） | plan は `0 to add, 1 to change, 0 to destroy`、差分は `password_auth_enabled = true -> false` のみ（replacement なし）。apply 07:59:53 → 08:02:11（**2 分 13 秒**）。`state`: **Updating 08:00:05** → **Ready 08:01:15**（約 70 秒） |
| 収束後の接続 | `felisadmin`: **rejected**（`FATAL: pg_hba.conf rejects connection`）。managed identity: 継続。最終 plan **No changes** |
| `/readyz`（frontend。10 秒間隔） | 07:52:51〜08:03:36 の全サンプル 200（低下なし） |
| obs Job | 07:50〜08:03 の全 execution が Succeeded（2 回の更新中を含む。heartbeat の空白なし） |

確認できたこと:

- **「構成が正であり、次の通常 apply が自動的に収束させる」設計**が実証された（CLI で変えた状態を Terraform が
  差分として検出し、apply で戻し、plan が No changes に戻る）
- **パスワード認証を有効化しても managed identity 経路は壊れない**（両方式が併存する。緊急時にアプリを止めずに
  復旧作業ができる）
- 手順書 §6 の記述と実際の挙動に差は無かった。所要時間の見込み「約 70 秒」はサーバーの `Updating` 区間で、
  コマンド完了（ARM の完了待ちを含む）は約 2 分 15 秒 — 手順書はコマンド完了時間で書き直した
- 更新の所要は段階 2（Entra 有効化 66 秒）・6b-1（71 秒）・今回 2 回（各約 70 秒）で一貫しており、
  `authConfig` の変更は方向によらず約 70 秒の再起動相当の更新を伴う

## 10. Terraform の write-only 引数と「空の in-place update」の切り分け（2026-09-21）

当初「write-only の `administrator_password_wo` / `_version` を常設すると（値が null でも）plan に属性差分なしの
in-place update が出続ける」と報告したが、最小再現で切り分けた結果、**原因は write-only ではなく、値に付いた
sensitive / ephemeral のマーク**だった。persistent 層で `main.tf` の 2 行だけを差し替え、plan の JSON
（`before` / `after` / `after_sensitive`）を比較した（apply はしていない。Terraform 1.14.8 + azurerm 5.1.0）。

| `administrator_password_wo` | `administrator_password_wo_version` | plan |
| --- | --- | --- |
| リテラル `null` | リテラル `null` | No changes |
| 通常変数（未設定 = null。sensitive でも ephemeral でもない） | 通常変数（null） | No changes |
| **sensitive** 変数（未設定 = null） | 通常変数（null） | 空 update（`after_sensitive` に wo が載る。属性差分なし） |
| **ephemeral** 変数（未設定 = null） | 通常変数（null） | 空 update（同上） |
| `ver > 0 ? var.ephemeral_pw : null`（= null） | `ver > 0 ? var.ver : null`（= null） | 空 update（同上。条件式でもマークが残る） |
| ephemeral 変数に値あり | `0` | 空 update（値を毎回 provider へ渡す） |
| 片方だけ指定（`0` / null との組み合わせ） | — | provider の `RequiredWith` エラー（両方同時指定が必須。ephemeral の null も「指定あり」扱い） |

整理:

- 公式（SDKv2 の write-only arguments）の「Write-only argument values cannot produce a Terraform plan difference」は
  **属性値の差分**についての記述で、実測とも一致する（差分は無い）。マーク付きの値が update を計画させるのは別の問題
- 一致する公開 Issue・修正予定は確認できなかった
- 帰結: パスワードを sensitive / ephemeral 変数で渡す限り write-only 引数は常設できない（非 sensitive の通常変数なら
  常設できるが、パスワードを非 sensitive にする案は採らない）。よって rollback は Terraform の構成外（az CLI）で行い、
  長期維持が要る場合だけ override file で一時的に構成へ足す（手順書 §6 / 付録 A）

## 11. ユニットテストで確認できず実測で確認した範囲

実トークン取得（Container Apps の identity endpoint）、DB への Entra ログイン、`pgaadauth_create_principal`
後の権限継承、ロール割当の伝播、`disableLocalAuth` の反映、パスワード認証無効化の再起動挙動。
