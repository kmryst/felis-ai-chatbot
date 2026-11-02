# felis-ai-chatbot 構成図用 inventory（突き合わせ版）

- 作成日: 2026-10-31
- 入力: 3 担当（インフラ・CI/CD・データ運用）の調査報告と、食い違い・自己矛盾の箇所についてのリポジトリ確認。調査報告の原文はリポジトリに入れていない
- 対象: 現行環境（移行先サブスクリプション。`02` サフィックス）。根拠は `terraform/persistent/backend.tf` と `terraform/ephemeral/backend.tf` の state 置き場が `felisaichatbottfstate02` であること、`docs/adr/0030-subscription-migration-and-02-suffix-naming.md` 決定 1・2
- リージョン: japaneast（`docs/operations/azure-resource-inventory.md` §B の一覧）
- 「作図」列: **描く** / **描かない（理由）**。描かないのは、不明なもの・現行環境に無いもの（削除済み・旧環境）・設計のみで未実装のもの・Azure 構成に関与しないもの
- 根拠のパスはリポジトリルートからの相対パス。`:数字` は行番号
- 一部の現在値は、git 管理外（`.gitignore:15` の `*.tfvars`）のローカルファイル `terraform/ephemeral/terraform.tfvars` で確認した。secret を含むファイルのため、非 secret のキー（`llm_provider` / `backend_ingress_external` / `chat_disabled`）だけを読んだ

## 1. リソース一覧

管理方法の「Terraform（persistent）」は `terraform/persistent`、「Terraform（ephemeral）」は `terraform/ephemeral` のルートモジュール。Terraform 管理リソースはすべて resource group `rg-felisaichatbot-dev-tf` に入る（`terraform/persistent/variables.tf:1-10`、`terraform/ephemeral/variables.tf:1-10`、各 resource の `resource_group_name = data.azurerm_resource_group.dev.name`）。

### 1-1. ユーザーからのアクセス

| サービス名 | リソース名 | 役割 | 管理方法 | 作図 | 根拠 |
| --- | --- | --- | --- | --- | --- |
| （外部）ユーザーのブラウザ | — | チャット UI の利用者 | — | 描く | `terraform/ephemeral/main.tf:949`（frontend だけが external ingress） |
| Microsoft Entra ID | テナント（`login.microsoftonline.com/<tenant>/v2.0`） | Easy Auth のサインイン（OpenID Connect）。managed identity のトークン発行元 | 管理外 | 描く | `terraform/ephemeral/main.tf:977-1008`（`openIdIssuer`） |
| Microsoft Entra ID アプリ登録 | `felis-ai-chatbot-dev-easyauth`（+ service principal） | frontend の Easy Auth 用クライアント | 管理外 | 描く（Entra ID の中に置く） | `docs/operations/azure-resource-inventory.md:268`（§B #12）、`terraform/ephemeral/variables.tf:191-204` |
| Container Apps 認証（Easy Auth） | `azapi_resource.front_auth`（`Microsoft.App/containerApps/authConfigs`、名前 `current`） | 未認証は `RedirectToLoginPage`。`/readyz` は `excludedPaths` で認証除外 | Terraform（ephemeral） | 描く（frontend の前段として） | `terraform/ephemeral/main.tf:977-1008` |

### 1-2. アプリ

| サービス名 | リソース名 | 役割 | 管理方法 | 作図 | 根拠 |
| --- | --- | --- | --- | --- | --- |
| Azure Container Apps environment | `cae-felisaichatbot-dev`（workload profiles、custom VNet、`internal_load_balancer_enabled=false`） | アプリと Job の実行基盤。ログを Log Analytics へ送る | Terraform（ephemeral） | 描く（枠として） | `terraform/ephemeral/main.tf:78-93` |
| Azure Container Apps（frontend） | `ca-felisaichatbot-dev-front`（Next.js、ポート 3000、external ingress） | BFF（`POST /api/chat`）と `/readyz` の透過 proxy | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:880-968`、`frontend/app/api/chat/route.ts`、`frontend/app/readyz/route.ts:16-19` |
| Azure Container Apps（backend） | `ca-felisaichatbot-dev`（FastAPI、internal ingress） | RAG API（`/chat` を SSE で返す、`/readyz`、`/livez`） | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:172-385`、`backend/app/main.py:80,94,201` |
| Azure Container Apps（ops） | `ca-felisaichatbot-dev-ops`（ingress なし。ops イメージ） | 運用者が `az containerapp exec` で入り、VNet 内から psql / pg_dump を使う経路 | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:408-481`、`backend/Dockerfile:77`（`AS ops`） |
| Azure Container Apps jobs（migrate） | `caj-felisaichatbot-dev-migrate`（Manual トリガー、`replica_retry_limit = 0`） | `alembic upgrade head` | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:490-548` |
| Azure Container Apps jobs（obs） | `caj-felisaichatbot-dev-obs`（Schedule トリガー `* * * * *`） | `collect.sql` で heartbeat・統計・pgstattuple を `obs` スキーマへ採取 | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:572-656`（名前 :575、cron :596）、`backend/observability/collect.sql` |
| Azure Container Apps jobs（seed） | `caj-felisaichatbot-dev-seed`（Manual） | RAG データの投入 | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:663-730`（名前 :666） |
| Azure Container Apps jobs（embed） | `caj-felisaichatbot-dev-embed`（Manual） | embedding の backfill | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:739-856`（名前 :747） |
| Azure OpenAI | `felisaichatbot-openai-dev-02`（kind OpenAI、S0。デプロイ `chat` = gpt-4.1-mini、`embedding` = text-embedding-3-small。`disableLocalAuth = true`） | 回答生成と embedding | 管理外（resource group `rg-felisaichatbot-dev`） | 描く | `docs/operations/azure-resource-inventory.md:256,281-293`、`docs/adr/0014-keep-azure-openai-out-of-terraform.md` |
| Azure Container Registry | `felisaichatbotacrdev02`（Basic、admin 無効） | イメージ `backend`（serve）/ `backend-ops`（ops）/ `frontend` の置き場 | Terraform（ephemeral） | 描く | `terraform/ephemeral/main.tf:32-46`、`docs/operations/vnet-integration-cutover.md:180-197` |
| User-assigned managed identity | `id-felisaichatbot-dev`（resource group `rg-felisaichatbot-dev-tf`） | 全 Container Apps / Job の共通 identity。ACR pull、PostgreSQL の Entra 認証、Azure OpenAI、Key Vault 参照に使う | 管理外（data source で参照） | 描く | `terraform/ephemeral/variables.tf:86-95`（既定値 :94）、`terraform/ephemeral/main.tf:99-135`、`docs/operations/azure-resource-inventory.md:264`（§B #8） |
| ロール割当 | AcrPull（identity → `rg-felisaichatbot-dev-tf`）、Cognitive Services OpenAI User（identity → Azure OpenAI）、Key Vault Secrets User（identity → Key Vault）、Key Vault Secrets Officer（所有者アカウント → Key Vault） | 権限 | 管理外 | 描かない（接続線のラベルで表す。個別アイコンにしない） | `docs/operations/azure-resource-inventory.md:265,269,271`（§B #9 / #13 / #15） |

### 1-3. データ

| サービス名 | リソース名 | 役割 | 管理方法 | 作図 | 根拠 |
| --- | --- | --- | --- | --- | --- |
| Azure Virtual Network | `vnet-felisaichatbot-dev`（10.10.0.0/24） | 基盤ネットワーク | Terraform（persistent） | 描く（枠として） | `terraform/persistent/main.tf:22-31` |
| Subnet（委任先 `Microsoft.App/environments`） | `snet-felisaichatbot-dev-aca`（10.10.0.0/26） | Container Apps environment 用 | Terraform（persistent） | 描く（枠として） | `terraform/persistent/main.tf:41-61` |
| Subnet（委任先 `Microsoft.DBforPostgreSQL/flexibleServers`、service endpoint `Microsoft.Storage`） | `snet-felisaichatbot-dev-pgsql`（10.10.0.64/27） | PostgreSQL の private access（VNet integration）用 | Terraform（persistent） | 描く（枠として） | `terraform/persistent/main.tf:63-113` |
| Azure Private DNS zone + virtual network link | `felisaichatbot-dev.private.postgres.database.azure.com` | VNet 内でサーバー名を解決する | Terraform（persistent） | 描く | `terraform/persistent/main.tf:118-130` |
| Azure Database for PostgreSQL flexible server | `pgsql-felisaichatbot-dev-02`（PostgreSQL 17、B_Standard_B1ms、32 GiB、`public_network_access_enabled = false`、`active_directory_auth_enabled = true` / `password_auth_enabled = false`） | RAG データ（pgvector。`documents` の HNSW インデックス）と観測用の `obs` スキーマ | Terraform（persistent） | 描く | `terraform/persistent/main.tf:136-264`（認証 :179-181）、`terraform/persistent/variables.tf:12-16`、`backend/migrations/versions/0001_initial_schema.py:97-99` |
| （同サーバーの Microsoft Entra 管理者） | `azurerm_postgresql_flexible_server_active_directory_administrator.owner` | DB 内に managed identity のロールを作る主体 | Terraform（persistent） | 描かない（サーバーの設定。図の粒度に合わない） | `terraform/persistent/main.tf:271-278` |
| （同サーバーのサーバーパラメーター） | `azure.extensions = VECTOR,PGSTATTUPLE` | 拡張機能の allowlist | Terraform（persistent） | 描かない（サーバーの設定。PostgreSQL の注記に書く程度） | `terraform/persistent/main.tf:283-287` |
| （PostgreSQL 内のロール） | DB ロール `id-felisaichatbot-dev`（Entra principal） | managed identity の DB ログイン | 管理外（SQL で作成） | 描かない（DB 内オブジェクト） | `docs/operations/azure-resource-inventory.md:270`（§B #14） |
| Azure Key Vault | `kv-felisaichatbot-dev`（RBAC、`public_network_access_enabled = true`） | secret `chat-api-key` と `easy-auth-client-secret` の保管 | Terraform（persistent） | 描く | `terraform/persistent/main.tf:507-527`、`terraform/ephemeral/main.tf:142-170` |
| （Key Vault secret） | `chat-api-key`（`value_wo` で書き込み）/ `easy-auth-client-secret`（人が `az keyvault secret set` で投入） | frontend → backend の API キー / Easy Auth のクライアントシークレット | 前者 Terraform（persistent）、後者 管理外 | 描かない（Key Vault の注記に名前だけ書く） | `terraform/persistent/main.tf:603-618`、`terraform/ephemeral/main.tf:150-163` |

### 1-4. バックアップ・監視

| サービス名 | リソース名 | 役割 | 管理方法 | 作図 | 根拠 |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL flexible server の自動バックアップ | （サーバーの設定）保持 7 日、geo-redundant backup 有効 | Azure 管理のバックアップストレージ（ペアリージョンへ geo 冗長）。point-in-time restore の元 | Terraform（persistent。サーバーの属性） | 描く（Azure 管理のバックアップストレージとして 1 つ） | `terraform/persistent/main.tf:184-195`、`docs/adr/0019-enable-geo-redundant-backup.md`（geo-redundant backup） |
| Long-term retention | — | 使っていない | — | 描かない（未使用） | `docs/production-readiness.md:65` |
| Maintenance window | 毎週水曜 17:00 UTC | 計画メンテナンスの時間帯 | Terraform（persistent。サーバーの属性） | 描かない（設定値。PostgreSQL の注記に書く程度） | `terraform/persistent/main.tf:205-210` |
| Log Analytics workspace | `log-felisaichatbot-dev`（保持 30 日、日次上限あり） | Container Apps のログ（`ContainerAppSystemLogs_CL` ほか）と Key Vault の AuditEvent の保存先 | Terraform（persistent） | 描く | `terraform/persistent/main.tf:299-314` |
| Diagnostic setting | `diag-kv-felisaichatbot-dev` | Key Vault の AuditEvent を Log Analytics へ送る | Terraform（persistent） | 描く（接続線として） | `terraform/persistent/main.tf:532-540` |
| Azure Monitor metric alerts ×5 | `alert-pgsql-is-db-alive` / `alert-pgsql-storage-free-low` / `alert-pgsql-storage-free-critical` / `alert-pgsql-cpu-credits-remaining-low` / `alert-pgsql-storage-percent-80` | PostgreSQL のプラットフォームメトリクス監視 | Terraform（persistent） | 描く（1 つにまとめて「×5」） | `terraform/persistent/main.tf:368-487` |
| Azure Monitor log search alert | `alert-kv-secret-sync-failed`（評価 15 分ごと） | Log Analytics の `ContainerAppSystemLogs_CL` から Key Vault 参照の同期失敗を検知 | Terraform（persistent） | 描く | `terraform/persistent/main.tf:547-595` |
| Azure Monitor action group | `ag-felisaichatbot-dev-email-02` | アラート通知（メール受信者と Azure mobile app の push 受信者） | Terraform（persistent） | 描く | `terraform/persistent/main.tf:345-365` |
| PostgreSQL の diagnostic settings（サーバーログ → Log Analytics） | — | IaC に無い | — | 描かない（存在しない） | `terraform/persistent/main.tf`（該当 resource なし） |
| 移行元サーバー | `pgsql-felisaichatbot-dev` ほか移行元サブスクリプションの全リソース | PITR ドリル 3 回・HA failover ドリルの実施先。destroy せず残置 | 移行元の state（IaC はリポジトリに無い） | 描かない（現行環境ではない） | `docs/adr/0030-subscription-migration-and-02-suffix-naming.md` 決定 2、`docs/verification/restore-drill/pitr-drill.md:25` |
| PITR の復元先サーバー | `pgsql-felisaichatbot-dev-restored` | ドリル時の一時リソース | 管理外（az CLI） | 描かない（削除済み・旧環境） | `docs/verification/restore-drill/pitr-drill.md:26,280-290` |
| SLO の authenticated synthetic transaction | （Container Apps の Playwright Job + Blob Storage） | 設計のみ | — | 描かない（未実装） | `docs/operations/slo/slo-document.md:7`、`docs/adr/0029-sli-synthetic-execution-authentication-and-storage.md` |

### 1-5. 開発・運用

| サービス名 | リソース名 | 役割 | 管理方法 | 作図 | 根拠 |
| --- | --- | --- | --- | --- | --- |
| （外部）開発者のローカル環境 | — | `docker build/push`、`terraform apply`、`az containerapp job start` / `exec`、`gh variable set` を人が実行する。デプロイ経路はこれだけ | — | 描く | `docs/operations/vnet-integration-cutover.md:76-87,169-226`、`docs/production-readiness.md:86,90` |
| Storage Account（Terraform state） | `felisaichatbottfstate02` / container `tfstate`（resource group `rg-felisaichatbot-tfstate`） | Terraform state の backend | 管理外 | 描く | `terraform/persistent/backend.tf:6-12`、`terraform/ephemeral/backend.tf:11-17`、`docs/operations/azure-resource-inventory.md:260` |
| Resource group | `rg-felisaichatbot-dev-tf`（Terraform 管理リソース）/ `rg-felisaichatbot-dev`（Azure OpenAI）/ `rg-felisaichatbot-tfstate`（state） | 入れ物 | 管理外 | 描く（枠として） | `docs/operations/azure-resource-inventory.md:257-259` |
| GitHub Actions `readyz-probe` | `.github/workflows/readyz-probe.yml`（schedule `*/5 * * * *`。repository variables `READYZ_URL` / `PROBE_ENABLED` / `OBS_FRESHNESS_ENFORCE`） | 外から `/readyz` を叩く外形監視と obs の鮮度判定。Azure の資格情報は使わない | GitHub 側 | 描く | `.github/workflows/readyz-probe.yml:28-31,44-62,92` |
| GitHub Actions のその他 10 本 | terraform-checks / backend-tests / frontend-checks / markdown-lint / pr-commitlint / pr-policy-check / security-scan / toolchain-version-check / issue-template-check / sync-labels | PR・Issue の CI。Azure の資格情報を使わない | GitHub 側 | 描かない（Azure 構成に関与しない） | `.github/workflows/`（`azure/login` と `id-token: write` は 0 件） |
| Dependabot | `.github/dependabot.yml` | 依存更新 PR | GitHub 側 | 描かない（Azure 構成に関与しない） | `.github/dependabot.yml` |
| GitHub Actions 用 OIDC service principal | `felis-ai-chatbot-github-actions` + federated credential + ロール割当 2 件 | 設計のみ。移行先では未作成（Issue #82 着手時に作る） | — | 描かない（現行環境に無い） | `docs/adr/0030-subscription-migration-and-02-suffix-naming.md:30`、`docs/operations/azure-resource-inventory.md:262-263` |
| docker-compose の pgvector | `docker-compose.yml` | ローカル開発用 | — | 描かない（Azure 構成に関与しない） | `docker-compose.yml` |

## 2. 接続関係

接続 #1〜#7 がユーザーのチャット 1 回分のリクエストの流れ（番号順。図の ①〜⑦）。#8 は応答で、図では矢印を描かず #3・#4・#7 の技術欄に SSE と書く。#9 以降は番号に順序の意味は無い。（2026-11-02 PR #340〜#346 に合わせて修正）

| # | 通信元 | 通信先 | プロトコル・方式 | 目的 | 作図 | 根拠 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ブラウザ | frontend（Easy Auth が前段） | HTTPS（external ingress）。未認証なら Easy Auth が Entra ID へ 302 リダイレクト | チャット画面の表示 | 描く | `terraform/ephemeral/main.tf:949,977-1008`、`docs/verification/subscription-migration/observations.md:133-135` |
| 2 | ブラウザ（サインイン画面）、built-in authentication（Easy Auth。token 取得） | Microsoft Entra ID | OpenID Connect。client secret（`easy-auth-client-secret`）を設定しているため hybrid flow で、ブラウザは Entra ID のサインイン画面へリダイレクトされ、token は Easy Auth（サーバー側）が client secret を使って Entra ID の token endpoint から取得する | サインイン | 描く（ブラウザ → Entra ID の 1 本。Easy Auth → Entra ID の token 取得は図の粒度で省略し、補足に書く） | `terraform/ephemeral/main.tf:916,977-1008`（`clientSecretSettingName` :997-1002）、<https://learn.microsoft.com/azure/container-apps/authentication-entra>（2026-10-31 検証で修正） |
| 3 | ブラウザ | frontend の BFF | JSON/HTTPS（`POST /api/chat`、`Content-Type: application/json`）。応答は SSE。Easy Auth が認証済み principal のヘッダー `X-MS-CLIENT-PRINCIPAL` を付ける。図の技術欄 `[JSON/HTTPS, SSE]` | 質問の送信 | 描く | `frontend/app/api/chat/route.ts:8,16,26-49`、`frontend/app/chat.tsx:66-68`（2026-11-02 PR #340〜#346 に合わせて修正） |
| 4 | frontend の BFF | backend | JSON/HTTP で internal FQDN（`BACKEND_ORIGIN = http://ca-felisaichatbot-dev.internal.<既定ドメイン>`）の `POST /chat`。応答は SSE（backend の `text/event-stream` を BFF がそのまま中継）。図の技術欄 `[JSON/HTTP, SSE]`。`x-api-key` に `CHAT_API_KEY`。principal が無い要求にはキーを付けない（fail-closed） | RAG API の呼び出し | 描く | `terraform/ephemeral/main.tf:356-365,864-875,933-941`、`frontend/app/api/chat/route.ts:26-49`、`backend/app/sse.py:25`（2026-11-02 PR #340〜#346 に合わせて修正） |
| 5 | backend | Azure OpenAI（デプロイ `embedding`） | HTTPS。`Authorization: Bearer`（managed identity の Entra トークン） | 質問文の embedding | 描く | `backend/app/main.py:218`、`backend/app/llm/client.py:247-299`、`terraform/ephemeral/main.tf:117-125` |
| 6 | backend | PostgreSQL flexible server | PostgreSQL protocol/TLS（psycopg。接続文字列は `sslmode=require`: `docs/operations/entra-auth-cutover.md:118`。図の技術欄 `[PostgreSQL protocol/TLS]`）。VNet 内の private access。パスワードの代わりに managed identity の Entra トークン（DSN は Container Apps の secret `database-url`） | cosine 類似度検索（HNSW）と `object_properties` の取得 | 描く | `backend/app/main.py:228-270`、`backend/app/rag.py:68`、`terraform/ephemeral/main.tf:104-115,193-199` |
| 7 | backend | Azure OpenAI（デプロイ `chat`） | HTTPS ストリーミング（Azure OpenAI の SSE を `[DONE]` まで parse）。`Authorization: Bearer`（managed identity）。類似度がしきい値未満なら呼ばずに定型応答。図の技術欄 `[HTTPS, SSE]` | 回答の生成 | 描く | `backend/app/main.py:243-282`（:278 `chat_stream`）、`backend/app/llm/client.py:247-299`、`backend/app/llm/streaming.py:24-25,39`（2026-11-02 PR #340〜#346 に合わせて修正） |
| 8 | backend → frontend → ブラウザ | — | Server-Sent Events（`StreamingResponse`）を BFF が中継 | 回答のストリーミング返却 | 描かない（応答の矢印は描かない。#3・#4・#7 の技術欄の SSE と README 本文で示す）（2026-11-02 PR #340〜#346 に合わせて修正） | `backend/app/main.py:279-283`、`frontend/app/api/chat/route.ts` |
| 9 | (a) アプリコード: backend・ops・Job（`AZURE_CLIENT_ID` を注入されたもの）／(b) platform 側: 全 Container Apps / Job | Microsoft Entra ID | user-assigned managed identity のトークン取得。(a) は scope `ossrdbms-aad` / `cognitiveservices` を `AZURE_CLIENT_ID` で identity を指定して取得。(b) は Container Apps platform が ACR pull（#11）と Key Vault references（#10）のために取得。frontend には `AZURE_CLIENT_ID` が注入されず、アプリコードでのトークン取得は無い | #5〜#7、#10、#11、#13、#14 の認証 | 描く（通信の向きどおり Container Apps environment → Microsoft Entra ID の 1 本。managed identity は線なしのアイコン）（2026-11-02 PR #340〜#346 に合わせて修正） | `terraform/ephemeral/main.tf:104-125`（`db_auth_envs` / `azure_openai_auth_envs` の注入先）、`:920-945`（frontend の env）、`backend/app/entra_auth.py`、`backend/app/credentials.py`（2026-10-31 検証で修正） |
| 10 | Container Apps（backend、frontend） | Key Vault | Key Vault 参照（`key_vault_secret_id` + user-assigned identity、バージョン指定なし。30 分以内に同期） | `chat-api-key`（両方）と `easy-auth-client-secret`（frontend）の取得 | 描く | `terraform/ephemeral/main.tf:145-163,204-208,902-918` |
| 11 | 全 Container Apps / Job | Azure Container Registry | managed identity でのイメージ pull（`registry.identity`、AcrPull） | イメージの取得 | 描く | `terraform/ephemeral/main.tf:186-189` ほか各 app / job |
| 12 | 開発者のローカル環境 | Azure Container Registry | `az acr login` → `docker push`（タグ `sha-<短縮SHA>`） | イメージの登録 | 描く | `docs/operations/vnet-integration-cutover.md:180-197` |
| 13 | ops、migrate / obs / seed / embed Job | PostgreSQL flexible server | psql / psycopg / Alembic。VNet 内の private access、Entra トークン | 運用作業、マイグレーション、観測値の採取（毎分）、データ投入、embedding の書き込み | 描く | `terraform/ephemeral/main.tf:126-135,408-856` |
| 14 | embed Job | Azure OpenAI（デプロイ `embedding`） | HTTPS。managed identity | 既存文書の embedding 生成 | 描く | `terraform/ephemeral/main.tf:737-839` |
| 15 | 開発者のローカル環境 | Azure（Azure Resource Manager） | `terraform apply`（persistent / ephemeral）、state は `felisaichatbottfstate02` | インフラの作成・更新 | 描く | `docs/operations/vnet-integration-cutover.md:199-202`、`terraform/*/backend.tf` |
| 16 | 開発者のローカル環境 | ops / Job | `az containerapp exec` / `az containerapp job start` | DB 操作とマイグレーションの起動 | 描く | `terraform/ephemeral/main.tf:391-407,490-508` |
| 17 | GitHub Actions `readyz-probe` | frontend の `/readyz`（Easy Auth の認証除外）→ backend の `/readyz` | HTTPS（curl、5 分ごと）。frontend が internal FQDN の backend へ透過 proxy | 外形監視と obs 3 系列の鮮度判定 | 描く | `.github/workflows/readyz-probe.yml:51,92`、`frontend/app/readyz/route.ts:16-19`、`docs/verification/subscription-migration/observations.md:138-141,224-229` |
| 18 | Container Apps environment | Log Analytics workspace | `logs_destination = log-analytics` | コンテナログとシステムログ | 描く | `terraform/ephemeral/main.tf:83-84` |
| 19 | Key Vault | Log Analytics workspace | Diagnostic setting（AuditEvent） | secret 読み取りの証跡 | 描く | `terraform/persistent/main.tf:532-540` |
| 20 | log search alert rule `alert-kv-secret-sync-failed` | Log Analytics workspace | alert rule が 15 分ごとに workspace へ KQL クエリ（`ContainerAppSystemLogs_CL`）を実行する（`scopes = [workspace]`。2026-10-31 検証で向きを修正） | Key Vault references の同期失敗の検知 | 描く | `terraform/persistent/main.tf:547-595` |
| 21 | metric alert rules ×5 | PostgreSQL flexible server（監視対象 = `scopes`） | Azure Monitor が自動収集する platform metrics を alert rule が評価する（評価 PT1M / PT5M）。PostgreSQL から alert へ通信するわけではないため、向きは alert rule → 監視対象とする（2026-10-31 検証で修正） | DB の死活・容量・CPU クレジットの監視 | 描く | `terraform/persistent/main.tf:368-487` |
| 22 | metric alerts ×5、log search alert | action group → メール / Azure mobile app | Azure Monitor の通知 | アラート通知 | 描く | `terraform/persistent/main.tf:345-365` |
| 23 | PostgreSQL flexible server | backup storage（Microsoft-managed storage accounts。geo-redundant backup storage で paired region へ複製） | automated backups（保持 7 日。データボリュームは managed disk の incremental snapshot）と WAL のアップロード。service endpoint `Microsoft.Storage` を経由するのは WAL のアップロード経路（2026-10-31 検証で修正） | point-in-time restore の元データ | 描く | `terraform/persistent/main.tf:84-112,184-195` |
| 24 | ブラウザ | backend | — | backend は internal ingress のため internet から到達不能（2026-09-19 実測で 404） | 描かない（通信が存在しない） | `terraform/ephemeral/main.tf:356`、`docs/verification/subscription-migration/observations.md:220-229`、ローカルの `terraform/ephemeral/terraform.tfvars`（`backend_ingress_external = false`） |
| 25 | GitHub Actions | Azure（OIDC） | — | 移行先では service principal 未作成。デプロイ workflow も無い | 描かない（未実装） | `docs/adr/0030-subscription-migration-and-02-suffix-naming.md:30` |
| 26 | Container Apps | Key Vault / Azure OpenAI のネットワーク経路 | — | どの egress を通るか不明（NAT Gateway / UDR / private endpoint の定義なし） | 描かない（不明。線は論理接続として #5〜#7・#10 で描く） | `terraform/ephemeral/main.tf:78-93` |

## 3. 突き合わせで解消した点

| 論点 | 担当間の差 | 結論と根拠 |
| --- | --- | --- |
| backend の ingress が今 internal か | インフラ担当が冒頭で「internal」と断定しつつ、不明点の表では「今も続いているか不明」とした（自己矛盾）。変数の既定値は `true`（external） | **internal**。2026-09-19 に `true → false` の切替と internet から 404 を実測（`docs/verification/subscription-migration/observations.md:213-229`）。ローカルの `terraform/ephemeral/terraform.tfvars` も `backend_ingress_external = false` |
| `llm_provider` が `azure-openai` か | インフラ担当は不明扱い（既定値は空 = stub） | **azure-openai**。移行先での実 Azure OpenAI による応答を実測（`observations.md:206-211`）。ローカルの tfvars も `llm_provider = "azure-openai"`。チャット流れ #5・#7 を描く根拠 |
| `READYZ_URL` の宛先（frontend か backend か） | インフラ担当は frontend と断定、CI/CD 担当・データ運用担当は不明 | **frontend の FQDN**。ADR-0027 決定 8 で正本を付け替え（`docs/adr/0027-frontend-azure-deployment-and-public-surface.md:126-129`）、移行先でも付け替えを実測（`observations.md:138-141`）。backend は internal なので外から届かない |
| Azure OpenAI のネットワーク設定 | インフラ担当が冒頭で「IaC 上は public エンドポイント経由」と書きつつ、不明点の表では「不明」とした（自己矛盾） | **不明**。Azure OpenAI は Terraform 管理外（ADR-0014）で、台帳にもネットワークの項目が無い（`docs/operations/azure-resource-inventory.md:281-293`）。public と描かない |
| AcrPull 用 managed identity の名前 | CI/CD 担当は「default 未確認」、インフラ担当は `id-felisaichatbot-dev` | **`id-felisaichatbot-dev`**（`terraform/ephemeral/variables.tf:94`）。同じ identity が DB / Azure OpenAI / Key Vault にも使われる（`terraform/ephemeral/main.tf:104-125,206`） |
| seed / obs Job の正式名 | CI/CD 担当は「読んでいない」、インフラ担当は名前を記載 | `caj-felisaichatbot-dev-obs`（`terraform/ephemeral/main.tf:575`）、`caj-felisaichatbot-dev-seed`（同 :666） |
| GitHub Actions の OIDC が構築済みか | `docs/production-readiness.md:86` は「構築済み」、ADR-0030 と台帳は「移行先では未作成」 | **移行先では未作成**。ADR-0030 決定 4（`docs/adr/0030-subscription-migration-and-02-suffix-naming.md:30`）と台帳 §B #6・#7（`azure-resource-inventory.md:262-263`）が新しい。`production-readiness.md` は移行前の記述。workflow に `azure/login` も無い。図に描かない |
| デプロイ経路 | インフラ担当は「手元で docker push」と触れるのみ、CI/CD 担当は全手順をローカル実行と記載 | **開発者のローカル環境 → ACR / Azure Resource Manager**（#12・#15・#16）。GitHub Actions から Azure へのデプロイは無い |
| Key Vault を参照するアプリ | インフラ担当は「backend、frontend」、データ運用担当は言及なし | backend は `chat-api-key`、frontend は `chat-api-key` と `easy-auth-client-secret`（`terraform/ephemeral/main.tf:204-208,902-918`）。Job と ops は参照しない |
| DB 認証方式 | インフラ担当「Entra 認証のみ」、データ運用担当「Entra 認証の有効化」 | **Microsoft Entra 認証のみ**（`password_auth_enabled = false`。`terraform/persistent/main.tf:179-181`） |
| PITR ドリルの実施状況 | データ運用担当: ドリル 3 回は移行元で実施。`docs/production-readiness.md:79` は「未実施」 | 図には影響しない。ドリルは**移行元サーバーで 3 回実施済み、移行先では未実施**。`production-readiness.md:79` は古い記述（ドリル記録 `docs/verification/restore-drill/` が新しい） |
| migrate Job の行番号 | インフラ担当 `main.tf:490`、データ運用担当 `main.tf:483-548` | 483 はコメントの開始行、resource 定義は :490。どちらも同じリソース |

## 4. 不明点

| 項目 | 不明な理由 | 関連ファイル |
| --- | --- | --- |
| Azure OpenAI のネットワーク設定（public / private endpoint / IP 制限） | Terraform 管理外で、台帳にもネットワークの項目が無い | `docs/operations/azure-resource-inventory.md:281-293`、`docs/adr/0014-keep-azure-openai-out-of-terraform.md` |
| Container Apps から Key Vault / Azure OpenAI への egress 経路 | NAT Gateway / UDR / private endpoint の定義が無く、プラットフォームの既定 egress と読めるだけで明記が無い | `terraform/ephemeral/main.tf:78-93`、`terraform/persistent/main.tf:22-113` |
| DB 接続の TLS（`sslmode`）とポート | DSN が secret（`database-url`）で、コードに現れない | `terraform/ephemeral/variables.tf:40-66` |
| `PROBE_ENABLED` の現在値（readyz-probe が今動いているか） | repository variable で、コードに値が無い。最後の記録は 2026-09-19 に `true` へ戻した時点 | `.github/workflows/readyz-probe.yml:48,86-88`、`docs/verification/subscription-migration/observations.md:140` |
| 稼働中イメージの SHA | 正本が git 管理外の `.env`（`DEPLOY_SHA`） | `scripts/deploy/check-image-drift.sh` |
| 移行元環境の現在の状態 | ADR-0030 は「残す」とだけあり、IaC もリポジトリに無い | `docs/adr/0030-subscription-migration-and-02-suffix-naming.md` 決定 2 |
| PostgreSQL のサーバーログ・Query Store の収集先 | IaC に PostgreSQL の diagnostic settings が無い。`pg_qs` の記録は移行元の実測のみ | `terraform/persistent/main.tf`、`docs/verification/restore-drill/2026-09-12-pitr-drill-state-verification.md:128` |
| `metrics.autovacuum_diagnostics` が有効か | 計画にあるだけで、IaC にも実施記録にも無い | `docs/operations/day3-5-execution-plan.md:338` |
| HA の状態 | Terraform が `high_availability` を `ignore_changes` しており、現在値がコードから分からない | `terraform/persistent/main.tf:212-258` |
| 移行先サーバーでの point-in-time restore の実績 | ドリル記録はすべて移行元が対象 | `docs/verification/restore-drill/` |

計 10 件。図に影響するのは上 2 件（Azure OpenAI と Key Vault への経路をネットワーク的にどう描くか）で、図では論理接続の線だけを描き、public / private の区別は付けない。
