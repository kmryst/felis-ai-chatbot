# ADR-0031: DB と Azure OpenAI の認証を Microsoft Entra 認証（managed identity）へ移し、残す秘密値を限定する

## ステータス

Accepted

## 日付

2026-09-20

## 決定内容

1. **PostgreSQL Flexible Server と Azure OpenAI への認証は、Container Apps に付与した
   user-assigned managed identity（`id-felisaichatbot-dev`）の Microsoft Entra アクセストークンで行う。**
   パスワード認証（PostgreSQL）と API キー認証（Azure OpenAI）は無効化した。
   - PostgreSQL: `authentication { active_directory_auth_enabled = true, password_auth_enabled = false }`。
     アプリ・Job・ops はスコープ `https://ossrdbms-aad.database.windows.net/.default` のトークンを
     `password` として渡す（接続ごとに取得。キャッシュと期限管理は `azure-identity` に委ねる）
   - Azure OpenAI: ロール `Cognitive Services OpenAI User` をリソーススコープで割り当て、
     `Authorization: Bearer <token>`（スコープ `https://cognitiveservices.azure.com/.default`）で呼ぶ。
     `disableLocalAuth = true` でキー認証を閉じた
2. **Entra 管理者はプロジェクト所有者のアカウント（`principal_type = "User"`）とし、Terraform
   （persistent 層）で管理する。** object ID と principal name は変数で渡し、コードには書かない。
3. **managed identity の DB ロールは `pgaadauth_create_principal('id-felisaichatbot-dev', false, false)`
   で作り、`GRANT felisadmin TO "id-felisaichatbot-dev"` で既存管理者ロールの権限を継承させる。**
   最小権限化（アプリ用ロールと migrate 用ロールの分離）は本 ADR の範囲外とし、
   [Issue #86](https://github.com/kmryst/felis-ai-chatbot/issues/86) の残課題として
   [Issue #280](https://github.com/kmryst/felis-ai-chatbot/issues/280)（identity の用途別分割）と
   同じ作業単位で扱う。
4. **残す秘密値は 2 種類に限定する。**
   - Easy Auth（Container Apps 組み込み認証）のクライアントシークレット: 残す（1 年ごとのローテーション運用）
   - `/chat` 保護の API キー: 残すが、人が扱う秘密値から外し **Terraform（`random_password`）が生成する**
5. **切替は段階的に行う。** 旧経路（パスワード / API キー）を残したまま新経路の疎通を実測で確認し、
   その後に旧経路を閉じる。各段階に「変更・検証・戻し方」を持たせる
   （手順の正本は [entra-auth-cutover.md](../operations/entra-auth-cutover.md)、実測は
   [docs/verification/entra-auth/observations.md](../verification/entra-auth/observations.md)）。
6. **アプリ側は認証方式を環境変数で切り替えられるようにし、既定は従来どおり（`password` / `api-key`）とする。**
   `DB_AUTH_MODE` / `AZURE_OPENAI_AUTH_MODE` / `AZURE_CLIENT_ID`（`backend/app/config.py`）。
   ローカル開発（docker compose の PostgreSQL + stub LLM）は無変更で動く。

## 背景

- 平文の秘密値が 5 種類（PostgreSQL 管理者パスワード / パスワード込み DSN / Azure OpenAI API キー /
  chat API キー / Easy Auth クライアントシークレット）あり、ローカルの環境変数ファイル・Terraform の
  変数ファイル・Terraform state のいずれか（または複数）に存在していた
  （[production-readiness.md](../production-readiness.md) §2 の「DB 認証」「Azure OpenAI の認証」
  「tfstate 内の平文 secret」）。
- managed identity（`id-felisaichatbot-dev`）は ACR pull 用に既に存在し、backend / ops / Job の
  すべてに付与済みだった（[ADR-0015](0015-ephemeral-layer-acr-container-apps-design.md)）。
- 現行コードは psycopg 3 の `AsyncConnection.connect()` をリクエストごとに開く（プール無し）ため、
  接続ごとにトークンを取得して `password` に渡す実装が自然に収まる。LLM transport は httpx で
  ヘッダを直接指定しており、`api-key` と `Authorization: Bearer` の切替は 1 か所で済む。
- PostgreSQL Flexible Server の Entra 認証は 3 モード（パスワードのみ / Entra のみ / 併存）を持ち、
  有効化時に `PGAadAuth` 拡張が有効になってサーバーが再起動する（公式ドキュメント）。

## 検討した選択肢

### 認証方式

- **A. managed identity + Entra 認証（採択）**: 秘密値を生成せず、接続ごとに有効期限つきの
  アクセストークンを取得する。identity は既存を流用
- B. Key Vault に秘密値を集約して参照する: 秘密値は存在し続け、保管場所とアクセス制御が変わるだけで、
  Key Vault 分のリソースと権限管理が増える
- C. Terraform の write-only argument で state から外す: state には入らないが tfvars と Azure 側の
  secret には残る。Container Apps の `secret` ブロックに write-only 版が無く、Easy Auth と chat API
  キーには適用できない。Entra 認証に移せなかった場合の次善策として保持する

### Easy Auth のクライアントシークレット

- **A. 残す（採択）**: 公式ドキュメントはシークレット省略時に implicit flow になり、implicit flow を
  避けるよう警告している。秘密値の数を減らすためにセキュリティ水準を下げない
  > "When the client secret isn't set, implicit flow is used and only an ID token is returned."
  > （クライアントシークレットが未設定の場合は implicit flow が使われ、ID トークンのみが返る）
  > "Whenever possible, avoid using implicit grant flow."（可能な限り implicit grant flow は避けること）
  > 出典: <https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra>
- B. シークレットを省略する: 上記の理由で却下
- C. federated identity credential でシークレットを代替する: App Service には手順があるが、
  Container Apps の公式ドキュメントには無い。将来の候補として記録するに留める

### chat API キー

- **A. 残して Terraform 生成に移す（採択）**: backend は internal ingress
  （[ADR-0027](0027-frontend-azure-deployment-and-public-surface.md) 決定 1）だが、誤って external
  に戻した場合でも、`X-API-Key` ヘッダによる API キー認証が `/chat` へのアクセスを制御する
  （`backend/app/main.py` の `_enforce_chat_gate`。キー未設定・空白のみ・最小長 32 文字未満は 404、
  不一致・未提示は 401 を返す fail-closed）。network 到達制御（internal ingress）とは別の層で効くため、
  ADR-0027 決定 6 / 決定 10 と同じ多層防御（defense in depth）の一層として残す。
  `random_password` で生成すれば人が値を扱わず、state にだけ存在する
- B. 廃止する: `/chat` の認証が無くなり、上記の多層防御が internal ingress による network 到達制御の
  一層だけになる。ingress の設定ミスがそのまま無認証の LLM 課金経路の公開になる
- C. Entra のサービス間認証（frontend の managed identity が backend を audience とするトークンを
  取り、backend が検証する）に置き換える: 本 ADR の範囲外。別 Issue で扱う

### DB ロールの権限

- **A. `GRANT felisadmin` で管理者権限を継承（採択）**: alembic の `ALTER TABLE` は所有者権限を要し、
  既存オブジェクトはすべて `felisadmin` 所有。継承させれば所有権移転も個別 GRANT も不要で、
  従来（全経路で `felisadmin` を共用）と権限の広さは変わらない
- B. アプリ用の最小権限ロールを別に作る: migrate 用とアプリ用でロールを分ける必要があり、それは
  identity を用途別に分ける #280 と同じ設計判断になる。identity 1 つで権限を分けるには DB 側の
  `SET ROLE` 経路が要り、アプリ改修が増える。#86 / #280 の作業単位に委ねる

### Entra 管理者

- **A. プロジェクト所有者のユーザーアカウント（採択）**: 1 人運用で最も単純。アカウントは
  `userType = Member`（個人 Microsoft アカウントでディレクトリを作成した形で、UPN に `#EXT#` を含む）。
  公式ドキュメントはゲストユーザーも含めて管理者にできると明記し、ゲストの場合は `#EXT#` 付きの
  UPN を使うと定めている（出典:
  <https://learn.microsoft.com/en-us/azure/postgresql/security/security-manage-entra-users>
  「For guest users, include the full name in their home domain with the #EXT# tag.」）
- B. セキュリティグループを管理者にする: 複数人運用や個人アカウント名をロール名に出したくない
  場合に有効。1 人運用では層が 1 つ増えるだけ。#280 と併せて再検討の余地あり
- C. service principal を管理者にする: 人が `pgaadauth_create_principal` を実行するのに SP の
  資格情報が要り、秘密値を減らす目的と逆行

### 切替の進め方

- **A. 段階的（併存 → 新経路の実測 → 旧経路を閉じる。採択）**: 各段階で戻し方を持てる。
  PostgreSQL の再起動を伴う変更を 1 回ずつ実測できる
- B. 一括切替: 失敗時にどの経路が原因か切り分けられず、DB に入る手段を同時に失うリスクがある

## 採択理由

- 秘密値の保管場所を変えるのではなく、秘密値の生成そのものを不要にできる唯一の選択肢が
  Entra 認証で、identity とロール割当の仕組みは既に運用中だった（ACR pull）。
- Easy Auth と chat API キーは、廃止するとセキュリティ水準が下がる
  （implicit flow への後退 / `/chat` の API キー認証というアクセス制御の層の喪失）。
  残す代わりに「人が扱う秘密値」から外せるものは外した（chat API キーは Terraform 生成）。
- 段階的な切替により、各段階の実測（再起動時間、`/readyz` の低下、observability データの空白、
  旧経路の拒否応答）を記録でき、公式ドキュメントに無い情報を手順書に残せた。

## 影響

- **消えた秘密値**: PostgreSQL 管理者パスワード（Azure 側でパスワード認証を無効化。Terraform state の
  `administrator_password` は空文字列になったことを長さ判定で確認）、パスワード込み DSN
  （DSN からパスワードが消えた）、Azure OpenAI API キー（`disableLocalAuth = true`。旧キーは
  `403 AuthenticationTypeDisabled` で拒否される）、人が扱う chat API キー（Terraform 生成へ）
- **state に残る秘密値**: Easy Auth のクライアントシークレット、Terraform 生成の chat API キー。
  いずれも Container Apps の `secret` ブロックに write-only 版が無いため
- **アプリ**: `DB_AUTH_MODE` / `AZURE_OPENAI_AUTH_MODE` / `AZURE_CLIENT_ID` を追加。既定は従来どおり。
  組み立て規則は `backend/app/credentials.py` に集約し、serving と ingest CLI で共有する。
  ops 用に `python -m app.entra_auth db|openai` でトークンを取り出せる（obs Job の psql と
  ops コンテナの対話接続が使う）。alembic は `migrations/env.py` が同じ環境変数を読む
- **Terraform**: persistent 層に `authentication` ブロックと Entra 管理者、変数
  `entra_administrator_object_id` / `entra_administrator_principal_name`。ephemeral 層に
  `db_auth_mode`（既定 `managed-identity`。`password` は rollback 用）、`chat_api_key_rotation`、
  `random_password.chat_api_key`、sensitive output `chat_api_key`。`azure_openai_api_key` /
  `chat_api_key` / `administrator_password` 変数は削除。`hashicorp/random 3.9.1` を追加
- **Terraform 管理外（台帳に記録）**: Azure OpenAI のロール割当と `disableLocalAuth`、PostgreSQL 内の
  DB ロール `id-felisaichatbot-dev`（SQL で作成）
- **ローカル開発**: docker compose の PostgreSQL（パスワード認証）+ stub LLM は無変更。
  **ローカルから実 Azure OpenAI を API キーで呼ぶ経路は閉じた**（`disableLocalAuth`）。ローカルから
  実 Azure OpenAI を使うには開発者アカウントの資格情報（Azure CLI 等）で Bearer トークンを取る実装が
  要り、本 ADR では扱わない（必要になった時点で Issue 化）
- **運用**: managed identity の経路が壊れても、Entra 管理者（所有者のアカウント）は managed identity と
  独立にトークンで接続でき、Terraform の `authentication` 変更は ARM 経由で DB 接続を要しない。
  **パスワード認証の一時的な再有効化（最後の手段）は Terraform ではなく az CLI で行い、構成は変えない**
  （`--password-auth Enabled --admin-password` を ARM 1 回で。修復後の通常 apply が Disabled へ戻す収束操作になる。
  修復までは apply しない）。Terraform で戻す設計を採らなかった理由: azurerm 5.1.0 の Update はパスワード認証を
  有効にする apply で `administrator_login` とパスワード引数を同時に要求し、そのパスワード引数
  （write-only `administrator_password_wo`）を sensitive / ephemeral 変数で常設すると、値が null でも
  plan に空の in-place update が出続ける（原因はマーク。実測記録 §10）。長期維持が要る場合だけ override file
  で一時的に構成を持つ（手順書 付録 A）。
  **新規作成した Entra 認証のみのサーバーには管理者ログインが無く、パスワードによる復旧は構造的に不可能**
  （復旧経路は Entra 管理者アカウントのみ）。復旧経路の詳細は手順書 §6
- **新規作成（destroy 後の再構築）**: Entra 認証のみの Create では `administrator_login` を送れない
  （azurerm 5.1.0 の Create が拒否する）ため、新規 DB に `felisadmin` は存在しない。identity のロールは
  Entra 管理者が `pgaadauth_create_principal('id-felisaichatbot-dev', true, false)`（管理者）として作り、
  migrate Job が全オブジェクトを identity 所有で作る（手順書 §3「新規作成時」）
- **残課題**: 最小権限化（#86 / #280）、Easy Auth の federated identity credential 化（Container Apps
  の公式手順が出た時点で再検討）、chat API キーの Entra サービス間認証への置き換え（別 Issue）

## 関連

- [Issue #86](https://github.com/kmryst/felis-ai-chatbot/issues/86) — 本 ADR の作業 Issue
  （当初 #275 で起票し、#86 へ統合。ブランチ名とコミットの `Refs #275` はその名残）
- [Issue #280](https://github.com/kmryst/felis-ai-chatbot/issues/280) — identity の用途別分割（最小権限化はここで扱う）
- [ADR-0009](0009-azure-openai-as-llm-provider.md) — Azure OpenAI の採用（managed identity 化の検討予告）
- [ADR-0014](0014-keep-azure-openai-out-of-terraform.md) — Azure OpenAI を Terraform 管理外に据え置く
  （ロール割当と `disableLocalAuth` が手動 + 台帳になる理由）
- [ADR-0015](0015-ephemeral-layer-acr-container-apps-design.md) — managed identity の払い出し（ACR pull）
- [ADR-0018](0018-postgresql-private-access-and-vnet-integration.md) — ops コンテナが唯一の DB 対話経路
- [ADR-0027](0027-frontend-azure-deployment-and-public-surface.md) — Easy Auth / BFF / chat API キーの位置づけ
- [entra-auth-cutover.md](../operations/entra-auth-cutover.md) — 手順の正本
- [docs/verification/entra-auth/observations.md](../verification/entra-auth/observations.md) — 実測記録
- [azure-resource-inventory.md](../operations/azure-resource-inventory.md) — 管理外リソース台帳
