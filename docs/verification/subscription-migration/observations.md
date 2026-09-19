# 検証環境のサブスクリプション移行の実測記録（Issue #274）

検証環境を新しいサブスクリプションへ移行（再構築）した記録。
手順の正本はローカルの構築手順書（リポジトリ外）と、
[bootstrap.md](../../operations/bootstrap.md) /
[vnet-integration-cutover.md](../../operations/vnet-integration-cutover.md) §2・§7 /
[entra-easy-auth-setup.md](../../operations/entra-easy-auth-setup.md) /
[seed-and-embedding-backfill.md](../../operations/seed-and-embedding-backfill.md)。
時刻はすべて UTC。サブスクリプション ID・テナント ID・アカウント名・秘密値は記録しない。

## 0. 構成

- グローバル一意名を持つ 4 リソース（tfstate Storage Account / ACR / PostgreSQL Flexible Server /
  Azure OpenAI）は旧環境に名前が残るため、末尾 `02` の新名で作成した（ADR-0013 の命名規則に
  対する例外。ADR は別途）。それ以外のリソース名は旧環境と同一
- デプロイイメージ: `DEPLOY_SHA=f67fcb6`（`main` と同一コミットの worktree から backend /
  backend-ops / frontend の 3 本を同一 SHA で build・push。ADR-0027 決定 7）
- 秘密値（DB 管理者パスワード / OpenAI キー / chat API キー / Easy Auth client secret）は
  すべて新規発行し、`terraform/<層>/terraform.tfvars`（gitignore 済み）で Terraform に渡した。
  `TF_VAR_*` の export との混在は避けた
- frontend の安定 FQDN: `ca-felisaichatbot-dev-front.<CAE 既定ドメイン>`（CAE 既定ドメインは
  旧環境と別値になった）

## 1. 段階 1: 手動リソース（Terraform の前提）

2026-09-18 に 1 セッションで実施。すべて手順書の期待値どおり。

| ステップ | 結果 |
| --- | --- |
| リソースプロバイダー登録（7 namespace） | 全 11 namespace が `Registered`。`Microsoft.Insights` も `NotRegistered` だったため登録した |
| リソースグループ 3 件 | `japaneast` / `Succeeded` |
| tfstate Storage Account + `tfstate` コンテナ + blob versioning | `Standard_LRS` / TLS1_2 / public blob access 無効 / versioning 有効。自分への `Storage Blob Data Contributor` は割当直後（リトライ 1 回目）でデータプレーン操作が通った |
| user-assigned managed identity | `rg-felisaichatbot-dev-tf` に作成 |
| `AcrPull` 割当（RG スコープ） | ACR 作成前に付与できた（スコープが RG のため） |
| Azure OpenAI + `chat` / `embedding` デプロイ | `gpt-4.1-mini 2025-04-14` GlobalStandard cap 10 / `text-embedding-3-small 1` Standard cap 10、いずれも `Succeeded` |

## 2. 段階 2: リポジトリ変更と Terraform apply

### 2-1. リポジトリ変更（4 行）

`terraform/persistent/backend.tf` / `terraform/ephemeral/backend.tf` の `storage_account_name`、
`terraform/persistent/variables.tf` の `server_name` default、`terraform/ephemeral/variables.tf` の
`acr_name` default。作業は `main` から切った別 worktree（`.worktrees/`。`.git/info/exclude` で除外）で行い、
進行中の別ブランチの未コミット変更には触れていない。

### 2-2. persistent 層

- `terraform init -reconfigure` 直後に `state list` が空であることを確認（旧 state を掴んでいない証拠）
- plan: **14 to add, 0 to change, 0 to destroy**（VNet 1 / サブネット 2 / private DNS zone 1 /
  VNet link 1 / PostgreSQL Flexible Server 1 / `azure.extensions` 1 / Log Analytics 1 /
  Action Group 1 / メトリクスアラート 5）
- apply: `14 added`。PostgreSQL は Ready / version 17 / `Standard_B1ms` / geo 冗長バックアップ
  Enabled / public access Disabled、`azure.extensions = VECTOR,PGSTATTUPLE`
- apply 後の `plan -detailed-exitcode` → exit 0

### 2-3. ephemeral 層（2 段）

- 第 1 段（`-target=azurerm_container_registry.main`、`container_image` は暫定値）:
  **1 to add** → ACR `Basic` / admin user 無効
- イメージ 3 本を build・push（§0）。ops イメージの psql は 17.11（dump の `\restrict` 対応 = 17.6 以上）
- 第 2 段（frontend なし・`chat_disabled = true`・`llm_provider = azure-openai`）:
  **7 to add**（CAE 1 / backend 1 / ops 1 / Job 4 = migrate / obs / seed / embed）
- apply 後: `/readyz` → 200 `{"status":"ok","db":"ok","obs":null}`（obs スキーマ復元前）、
  ops replica Running 1、`plan -detailed-exitcode` → exit 0
- `caj-felisaichatbot-dev-obs` は作成直後から毎分起動し、obs スキーマ復元まで **Failed が 7 回**
  並んだ（想定内。復元完了の次の実行から Succeeded に転じた）

## 3. 段階 3: obs スキーマ復元・seed / embed

### 3-1. obs スキーマ復元（migrate Job は起動しない）

順序: `alembic upgrade 0001` → dump（`pg_dump -n obs`）を `psql --single-transaction` で復元 →
`CREATE EXTENSION pgstattuple` → `alembic stamp head`。migration 0002 が `CREATE SCHEMA obs` と
初期行 INSERT を行うため、0002 を流すと復元と衝突する。

- 持ち込み経路: tfstate Storage Account の一時コンテナ `restore-staging` に gz を置き、
  読み取り専用 2 時間の user delegation SAS で ops コンテナから `python3 urllib` で取得
  （gz / sql とも sha256 一致）。復元後に blob とコンテナを削除
- `az containerapp exec` は `script(1)` で TTY 化し、FIFO 経由で行単位にコマンドを投入した
  （手貼り付けと同内容。1 セッション通しで 429 なし）
- 前提確認: `alembic_version` なし / `obs` スキーマなし
- 復元: RC=0、`alembic current` = `0004 (head)`

復元後の検証（退避時の `MANIFEST.txt` と全項目一致）:

| 項目 | 実測 |
| --- | --- |
| 行数 | bloat_stats 1236 / counter 1 / db_stats 6690 / heartbeat 37338 / phase_config 1 / phase_log 1 / table_stats 82263 |
| シーケンス | `obs.marker_id_seq` 37389 / `obs.phase_log_id_seq` 1 |
| heartbeat | min `2026-08-23 07:16:18.843824+00` / max `2026-09-18 06:19:18.004122+00` |
| phase_config | `1 / baseline / 2026-08-23 07:15:41.678169+00` |
| 拡張 | vector 0.8.2 / pgstattuple 1.5（旧環境と同じ） |
| obs のリレーション数 | 13 |

復元の約 2 分後の `/readyz` →
`{"status":"ok","db":"ok","obs":{"heartbeat_age_seconds":59,"stats_age_seconds":111,"pgstattuple_age_seconds":111}}`。

### 3-2. seed → embed

`caj-felisaichatbot-dev-seed` → Succeeded、`caj-felisaichatbot-dev-embed` → Succeeded。
ops exec で `documents = 38 / embedding_null = 0`。

## 4. Entra ID（移行先での作り直し）

[entra-easy-auth-setup.md](../../operations/entra-easy-auth-setup.md) §1〜§4 を移行先で実施
（移行先には移行元の Entra ID オブジェクトが存在しないため。署名者は移行先の Global Administrator。
CLI で権限不足・MFA 要求なし）。

- app registration `felis-ai-chatbot-dev-easyauth`（新 appId。app role `Chat.Use` =
  `allowedMemberTypes: ["User", "Application"]`）。redirect URI は frontend 作成前に
  `https://<frontend FQDN>/.auth/login/aad/callback` を予測登録
- client secret（1 年）は `terraform/ephemeral/terraform.tfvars` に直接書き込み、画面に出していない
- service principal に `appRoleAssignmentRequired = true`、`oauth2PermissionGrants`
  （`openid profile email User.Read`、AllPrincipals）
- 割当: owner + `felis test user (assigned)` の 2 者（synthetic 用 SP は未作成のため保留）
- 非管理者テストユーザー 2 名: `felis-test@…`（割当あり）/ `felis-test-unassigned@…`（割当なし）。
  どちらも directory role の membership 0

**テストユーザーのパスワードの扱い（§4 の記述からの変更）**: entra-easy-auth-setup.md §4 は
「パスワードは生成して `.env` に保存」と書くが、`.env` はプロセスが読む設定値の置き場所であり、
人間がブラウザに入力する認証情報の置き場所ではない。かつこのパスワードは実測 1 回で用済みになり、
同文書自体がローテーションを求めている。今回は **保存せず、チャット実測の完了後にユーザーごと削除する**
運用にした（削除のタイミングを誤って作り直した経緯は §6-3）（旧環境の
[frontend-easy-auth-cutover/observations.md §10](../frontend-easy-auth-cutover/observations.md)
と同じ使い捨て運用）。

## 5. frontend + Easy Auth（cutover §7-2）と `READYZ_URL` 付け替え（§7-3）

- plan / apply: `azurerm_container_app.front[0]` と `azapi_resource.front_auth[0]` の **2 add** のみ
  （`chat_disabled = true` のまま、backend ingress は external のまま）
- apply 直後 1〜2 分は環境 proxy が 503（`delayed connect error`）。replica の `front` / `http-auth`
  両コンテナが ready になってから復旧
- Ready 後の実測:
  - 匿名 `POST /api/chat`（JSON、Accept が HTML でない）→ **401**
  - ブラウザ相当（`Accept: text/html` + Mozilla UA）の `GET /` → **302**、`Location` は
    `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize?...`
  - `/readyz`（`excludedPaths`）→ **200**、`.obs` 3 キーあり
- `READYZ_URL` 付け替え（ADR-0026 の順序）: `PROBE_ENABLED=false` → 新 URL の `.obs` 契約検証
  （`heartbeat_age_seconds` 47 / `stats_age_seconds` 169 / `pgstattuple_age_seconds` 822）→
  `READYZ_URL` 更新（読み返しで一致確認）→ `PROBE_ENABLED=true` → `workflow_dispatch` で 1 回実行:
  **success**（07:39:13 起動）。直前 2 回の schedule 実行は旧 URL 宛てで failure（想定内）

## 6. Easy Auth のブラウザ実測（ADR-0027 決定 5。§7-4 の前提）

ブラウザ（Chrome シークレットウィンドウ）で 2026-09-19 07:5x に実測。

実測は 2 回行った。1 回目（07:5x）の後にテストユーザーを削除してしまい（§6-3）、作り直して
2 回目（08:0x）を行った。**証跡として採用するのは 2 回目**である。2 回目は割当あり / なしの両方を
同一条件（再作成後・全シークレットウィンドウを閉じてセッションを切った状態）で揃えたのに対し、
1 回目は成功側のアカウントが確定できていない（6-2）。1 回目も事実として残す。

### 6-1. 未割当ユーザーの拒否（対の証跡）

`felis-test-unassigned@…` のサインインは、1 回目・2 回目とも password 通過直後に **`AADSTS50105`**
でブロックされた:

- 1 回目（削除前）: Request Id `d112fe2e-4474-4bab-85d7-01427aef3b00`、Timestamp 2026-09-19T07:52:13Z
- 2 回目（再作成後。採用する証跡）: Request Id `ef7de0cc-0149-426f-a766-e1e41ff03c00`、
  Timestamp 2026-09-19T08:04:41Z。メッセージは 1 回目と同一

画面のメッセージは「signed in user が blocked。グループメンバーでも直接割当でもないため」の趣旨で、
旧環境の実測記録（[frontend-easy-auth-cutover/observations.md §4-1](../frontend-easy-auth-cutover/observations.md)）
と同文。パスワード認証は通過しており、**認可段階（`appRoleAssignmentRequired = true`）での拒否**
であることが確認できる。**MFA 登録には進まない**（password 通過直後に認可で拒否されるため。
割当ありユーザーが MFA 登録を求められた 6-2 と対照的で、未割当ユーザーは MFA 登録の手前で止まる）。

### 6-2. 割当ありユーザーのサインイン成功（2 回目の実測で確定）

1 回目の実測（07:5x）では、あるブラウザセッションで frontend の画面が表示されたものの、
**どのアカウントのサインインによるものか確定できなかった**（Chrome のシークレットウィンドウが
ウィンドウ間でセッションを共有する = §7 ため、owner セッションの流用を否定できない）。
Entra のサインインログ（`auditLogs/signIns`）による確定は、移行先の Entra ID に premium license が
無いため取得できない（Graph が `Authentication_RequestFromNonPremiumTenantOrB2CTenant` を返す）。
このため 1 回目は成功と記録せず、§7-4 の後に再実測した。

2 回目の実測（§7-4 の apply 後、2026-09-19 08:03 UTC 前後 = 17:03 JST 前後。全シークレット
ウィンドウを閉じてから実施）で観測した事実:

- `https://<frontend FQDN>/` → `login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize` の
  サインイン画面が表示され、画面にアカウント名 `felis-test@…` が明示された
- **MFA 登録を求められた**（Entra ID のセキュリティの既定値による Microsoft Authenticator の登録）。
  登録して通過（移行元での TOTP 登録と同様。新規ユーザーは初回サインインで必ず要る）
- サインイン後、frontend の画面（チャット UI）が表示された。同意画面は出ていない
  （`oauth2PermissionGrants` の AllPrincipals 同意が効いている）
- チャット送信の結果は §7-4 の項

### 6-3. テストユーザーの扱い（順序の誤りと作り直し）

当初の運用は「証跡取得直後に削除」で、6-1 の証跡取得後にテストユーザー 2 名を削除し、
`az ad user list --filter "startswith(userPrincipalName,'felis-test')"` → 0 件まで確認した。
しかし §7-4（`chat_disabled = false`）後のチャット実測も **非管理者テストユーザーで行う必要がある**
（ADR-0027 決定 5: 成功試験の証跡は管理者ロールを持たない専用テストユーザーに限定）ため、
削除が早すぎた。§4 の手順で同じ UPN の 2 名を作り直し（07:56。`Chat.Use` 割当あり / なし、
どちらも directory role の membership 0）、削除のタイミングを **チャット実測（§7-4 の後）の
完了後** に改めた。パスワードは前回同様に保存せず、記録・ログのいずれにも残していない。

再作成後の割当: owner + `felis test user (assigned)` の 2 者。

§6-5 の検証 6 まで完了した後（08:2x UTC）、テストユーザー 2 名を削除した。
`az ad user list --filter "startswith(userPrincipalName,'felis-test')"` → 0 件。削除により app role の
割当も消え、残る割当は owner 1 者（+ 将来の synthetic 用 SP）。パスワードは記録・ログのいずれにも
残していない。

### 6-4. 第 3 段（cutover §7-4）: `chat_disabled = false` とチャット実測

- plan / apply: `azurerm_container_app.main` の in-place 更新 1 件のみ（env `CHAT_DISABLED`
  `"true" → "false"`）。apply 後、100% traffic revision `ca-felisaichatbot-dev--0000001` の
  template に `CHAT_DISABLED=false` を ARM 読み取りで確認。`plan -detailed-exitcode` → exit 0
- 非管理者テストユーザー `felis-test@…`（6-2 の 2 回目のセッション）のブラウザから
  「最弱の台風は？」を送信 → 気象庁の定義（最大風速 17 m/s 以上、10 分間平均風速、風力 8 /
  34 ノット、33 m/s 未満は「強さ」の区分なし、強風域半径 500 km 未満）に基づく応答を受信。
  実 Azure OpenAI（`llm_provider = azure-openai`）+ seed / embed 済み 38 件の検索が効いている
  ことが応答内容から確認できる（旧環境の同段は stub LLM + 空 DB で guard の定型応答だった）

### 6-5. backend internal ingress への切替（cutover §7-5）

- plan: `azurerm_container_app.main` の `external_enabled` `true → false` と `front[0]` の
  `BACKEND_ORIGIN` 更新の 2 件 in-place（destroy 0）
- 1 回目の apply は予告どおり **"Provider produced inconsistent final plan"** で失敗（plan 時点の
  `BACKEND_ORIGIN` は external FQDN を `http://` にした値で、apply 中に internal FQDN へ変わるため。
  旧環境の実測と同じ）。backend の internal 化自体は成功（`Modifications complete after 17s`）
- 2 回目の apply（同じ変数）で `front[0]` の `BACKEND_ORIGIN` が
  `http://ca-felisaichatbot-dev.internal.<CAE 既定ドメイン>` に収束: `0 added, 1 changed, 0 destroyed`。
  2 回目は `!` 経由の実行が対話入力を受け付けないため、plan 出力で差分（1 件・destroy なし）を
  確認した上で `-auto-approve` を付けた
- 切替後の検証（08:09 UTC）:
  1. 旧 external FQDN `https://ca-felisaichatbot-dev.<CAE 既定ドメイン>/readyz` → internet から **404**
     （internal FQDN `…internal.<CAE 既定ドメイン>` も同様に 404 = internet から到達不能）
  2. `az containerapp show`: backend の `ingress.external = false`、fqdn は
     `ca-felisaichatbot-dev.internal.<CAE 既定ドメイン>`
  3. frontend 経由 `/readyz` → **200**
     `{"status":"ok","db":"ok","obs":{"heartbeat_age_seconds":16,"stats_age_seconds":16,"pgstattuple_age_seconds":2650}}`
     （proxy が internal FQDN に向いた証拠）
  4. `terraform plan -detailed-exitcode` → exit 0（差分なし）
  5. `readyz-probe.yml` を `workflow_dispatch` で 1 回実行 → **success**（08:09:49 起動）
  6. 認証済みブラウザ（非管理者テストユーザー `felis-test@…`、08:15 UTC 前後）での `/chat` 疎通:
     frontend 経由でチャットが引き続き動作し、502/503 は発生しなかった。質問「弱い風は？」に対し
     「参照資料には『弱い風』という区分の記載はありません」と答えたうえで、気象庁の実在する
     4 段階（やや強い風 / 強い風 / 非常に強い風 / 猛烈な風）と「非常に強い風は 20 m/s 以上
     30 m/s 未満」を提示した。**参照資料に無い概念を捏造せず、根拠のある情報だけを返している**
     （ADR-0010 の grounding 方針どおりの RAG の挙動）

以上で移行（段階 1〜3）と cutover §7 の全段が完了した。

## 7. 手順書・運用文書の記述と実測の食い違い

| 記述 | 実測 | 対応 |
| --- | --- | --- |
| cutover §7-2「匿名 `POST /api/chat` → 302」 | Accept が HTML でない API 呼び出しは **401**。302 はブラウザ相当の GET のみ（旧環境の実測記録 §2 と同じ） | 手順書側の記述が古い。cutover §7-2 の期待値を 401 に直す |
| apply 直後の frontend の応答 | 1〜2 分は 503（revision 起動待ち） | 手順書に待ち時間を追記 |
| `pgstattuple_age_seconds` は毎時 0 分の採取後に埋まる | 復元直後の obs Job 実行で埋まった（111 秒） | 記述を見直す |
| tfstate の blob は apply 後に現れる | `terraform init -reconfigure` の時点で空 state（181 B、resources 0）の blob が両層とも作られる | 手順書 §2-3 の検証記述を修正 |
| 段階 1 / persistent 後の期待リソース一覧 | VNet 作成に伴い `NetworkWatcher_japaneast`（RG `NetworkWatcherRG`）が自動作成される（Terraform 管理外） | 台帳に注記 |
| entra-easy-auth-setup.md §4「パスワードは `.env` に保存」 | 保存せず、チャット実測の完了後にユーザーごと削除する運用に変更（§4 / §6-3。初回は削除が早すぎて作り直した） | 同文書の記述を更新 |
| 手順書 §2-6「Entra はユーザー実行（ポータル）」 | テストユーザー作成を含め CLI で完了 | — |
| entra-easy-auth-setup.md §4 のブラウザ実測手順 | Chrome のシークレットウィンドウはウィンドウ間でセッションを共有するため、2 人目の実測前に**すべてのシークレットウィンドウを閉じる**必要があった | 同文書に追記 |
| entra-easy-auth-setup.md §4（テストユーザーの初回サインイン） | 新規テストユーザーは Entra ID のセキュリティの既定値により **初回サインインで MFA 登録（Microsoft Authenticator）が必須**。未割当ユーザーは認可拒否が先に来るため MFA 登録に進まない | 同文書に追記（実測者が Authenticator を用意する前提を明記） |
| cutover §7-4 の期待応答 | 旧環境は stub LLM + 空 DB で guard の定型応答だったが、今回は実 Azure OpenAI + seed 済みのため実データ応答が返る | 記述を現状に合わせる |
| cutover §7-5 の再 apply（`terraform apply` を対話で承認） | Claude Code の `!` 経由の実行は対話入力を受け付けないため、差分を plan 出力で確認した上で `-auto-approve` を付ける必要があった | 手順書に「`!` 実行では対話 apply ができないので、差分確認後に `-auto-approve`」を追記 |

## 8. 完了判定と残作業

**移行は完了した**（2026-09-19 08:2x UTC 時点）:

- persistent / ephemeral の両層で `terraform plan -detailed-exitcode` → exit 0
- frontend 経由の `/readyz` が 200 + `.obs` 契約、`readyz-probe.yml` の直近 run が success
- obs Job の直近 execution が Succeeded、obs スキーマの行数・シーケンスが退避時の記録と一致
- 非管理者テストユーザーの認証済みブラウザで `/chat` が実 LLM + seed 済みデータの応答を返す
- テストユーザーは削除済み。移行元の環境は destroy せず残す（ADR-0030）

残作業（このリポジトリでの後続）:

- 台帳（azure-resource-inventory.md）§B #1 / #5 / #8 / #9 / #12、リソースプロバイダー表、
  サブスクリプション節の更新。#6 / #7（CI 用 OIDC SP）は新環境では未作成である旨を記載
- §7 の食い違い一覧に基づく手順書・運用文書の修正
- 台帳（azure-resource-inventory.md）と新 ADR の更新
