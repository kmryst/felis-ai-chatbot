# frontend + Easy Auth bootstrap と backend internal ingress 切替の実測記録（Issue #194）

[vnet-integration-cutover.md §7](../../operations/vnet-integration-cutover.md) の手順を
2026-09-01 に実走した記録。実装 PR は #200（squash `2df47f9`）、手順の根拠は
[ADR-0027](../../adr/0027-frontend-azure-deployment-and-public-surface.md)（決定 5 / 6 / 8）。
時刻はすべて UTC。

## 0. 構成

- デプロイイメージ: `DEPLOY_SHA=2df47f9`（backend / backend-ops / frontend の 3 本を同一 SHA で
  build・push。ADR-0027 決定 7）
- frontend: `ca-felisaichatbot-dev-front`（安定 FQDN
  `ca-felisaichatbot-dev-front.blackbush-a1db7f50.japaneast.azurecontainerapps.io`）
- Entra（[entra-easy-auth-setup.md](../../operations/entra-easy-auth-setup.md) の手順で owner の
  ローカル az から作成。CI SP の権限外 = ADR-0012 の境界）:
  - app registration `felis-ai-chatbot-dev-easyauth`（appId
    `98267536-618f-49a6-a7e4-79fdf81c22a8`。app role `Chat.Use` =
    `allowedMemberTypes: ["User", "Application"]`）
  - service principal（object id `0544d912-7bd3-467f-b1f1-62ecec24d351`）に
    `appRoleAssignmentRequired = true`（az 読み取りで `true` を確認）
  - 割当 2 者: owner（K Y）と `felis test user (assigned)`。synthetic 用 SP の割当（3 者目）は
    synthetic transaction SLI の作業単位で SP を作成した時点で追加する（未作成のため保留）
  - 非管理者テストユーザー 2 名: `felis-test@…`（割当あり）/ `felis-test-unassigned@…`（割当なし）。
    どちらも管理者ロールなし（作成時既定のまま）。**検証完了後に削除済み**（§10）

## 1. 第 1 段（§7-1）: `chat_disabled = true`・frontend 未作成で apply

- plan: 4 件の in-place 更新のみ（image 3 種の SHA 更新・`CHAT_DISABLED` false→true・
  `CHAT_API_KEY_CONFIG_CHECKSUM` 追加）。destroy 0
- 100% traffic revision `ca-felisaichatbot-dev--0000004` の template に `CHAT_DISABLED=true` と
  image `backend:sha-2df47f9` を ARM 読み取りで確認
- 正しい key 付き `POST /chat` → **404**（13:55:10。backend 構造化ログにも
  `"path": "/chat", "status_code": 404` として記録）
- backend `/readyz`（当時まだ external）→ 200（外形監視は無傷）

## 2. 第 2 段（§7-2）: frontend + `authConfigs` を apply（`chat_disabled = true` のまま）

- plan / apply: `azurerm_container_app.front[0]` と `azapi_resource.front_auth[0]` の 2 add のみ
- authConfigs 適用により Easy Auth sidecar（container 名 `http-auth`）入りの replica へ
  入れ替わるまで数分の Activating 期間があり、その間は環境 proxy が 503
  （`delayed connect error`）を返した（外形監視は backend 直接のままなので影響なし）
- Ready 後の実測:
  - 匿名 `POST /api/chat`（Accept が HTML でない）→ **401**
  - ブラウザ相当（`Accept: text/html` + Mozilla UA）の `GET /` → **302**、`Location` は
    `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize?...`（redirect URI は
    apply 前に予測登録した `https://<frontend FQDN>/.auth/login/aad/callback` と一致）
  - `/readyz`（`excludedPaths`）→ **200**、`.obs` 3 キーとも存在（透過 proxy 成立）
- backend ログ（Log Analytics `ContainerAppConsoleLogs_CL`、13:40〜14:00:30 の窓）:
  `/chat` に関する行は §1 の自分の 404 検証 1 行のみで、chat 実行
  （`rag guard` / LLM 系のログ）は**不在**

## 3. `READYZ_URL` の付け替え（§7-3。ADR-0026 の順序）

1. `PROBE_ENABLED=false`
2. 新 URL `https://<frontend FQDN>/readyz` を直接検証（200・`db: ok`・`.obs` 3 キー）
3. `READYZ_URL` を新 URL へ更新（値の一致を読み返しで確認）
4. `PROBE_ENABLED=true` → `workflow_dispatch` で 1 回実行:
   **success**（`PROBE ts=2026-09-01T13:56:53.721Z http_code=200 latency_ms=705 obs=present
   heartbeat_age=36 stats_age=211 pgstattuple_age=2616 enforce=true`。鮮度ゲート含め合格）

## 4. Easy Auth の証跡（ADR-0027 決定 5。ブラウザ実測 = Playwright）

### 4-1. 未割当ユーザーの拒否（対の証跡）

`felis-test-unassigned@…` のサインインは password 通過直後に **`AADSTS50105`** でブロックされた
（Request Id `afa8219d-b906-4ed2-836a-88ffd4841300`、Timestamp 2026-09-01T13:57:47Z）。画面の
メッセージ（逐語）:

> AADSTS50105: Your administrator has configured the application
> felis-ai-chatbot-dev-easyauth ('98267536-…') to block users unless they are specifically
> granted ('assigned') access to the application. The signed in user
> 'felis-test-unassigned@…' is blocked because they are not a direct member of a group with
> access, nor had access directly assigned by an administrator.

（訳: 管理者はこのアプリケーションを、明示的にアクセスを割り当てられたユーザー以外を
ブロックするよう構成している。サインインしたユーザーはアクセスを持つグループの直接の
メンバーでも、管理者から直接割当を受けてもいないためブロックされた。）

### 4-2. 割当済み・非管理者ユーザーの成功

`felis-test@…` のサインインは 2 つの前提作業を経て成功した:

1. **MFA 登録の強制**（テナントの既定動作）: 初回サインインで「Let's keep your account
   secure」（アカウント保護のため別の確認方法を設定せよ）画面になり、
   「Set up a different authentication app」経路で TOTP（authenticator アプリの手動キー）を
   登録して通過した
2. **管理者同意**: MFA 通過後に「Need admin approval」（`AADSTS90094` = この操作は管理者のみが
   実行できる）で停止した。テナントがユーザー同意を許可していないため、OIDC の delegated
   scope（`openid profile email`）に管理者同意が必要だった。
   `az ad app permission admin-consent` は app registration に requiredResourceAccess が
   無いため効果がなく、Graph の `oauth2PermissionGrants` へ `consentType: AllPrincipals` の
   grant を直接作成して解消した（手順は entra-easy-auth-setup.md §2 に追記）

同意後の再サインインで frontend のチャット UI が表示され（`felis-ai-chatbot` ページ）、
認証済みセッションで `/chat` の SSE 応答を受信した（§5 / §6）。owner の成功は補助記録
（4-1 / 4-2 が正の証跡）。

## 5. 第 3 段（§7-4）: `chat_disabled = false`

- apply は serving 1 件の in-place 更新のみ。100% traffic revision の `CHAT_DISABLED=false` を
  ARM 読み取りで確認
- 非管理者テストユーザーのブラウザから送信 → bot 応答を受信（stub LLM + 空 DB のため
  hallucination guard の定型応答「参照資料に記載がないため、お答えできません。…」が返る。
  ADR-0010 の guard 経路が working as intended。実データ応答は `LLM_PROVIDER` 切替と
  seed / backfill の後続 Issue の範囲）

## 6. backend internal ingress への切替（§7-5）

- 1 回目の apply は `azurerm_container_app.main` の internal 化
  （`external_enabled=false`・`allow_insecure_connections=true`）成功後、
  `azurerm_container_app.front[0]` の `BACKEND_ORIGIN` 更新で
  **Provider produced inconsistent final plan** エラーになった（plan 時点では backend の
  `ingress[0].fqdn` が旧 external 値で確定済みなのに、apply 中に internal FQDN へ変わったため。
  azurerm 5.1.0 の既知パターン）。**再 apply（1 件の in-place 更新）で収束**し、以後
  `plan -detailed-exitcode` は **exit 0**（差分ゼロ）。§7-7 の「不整合は再 apply で収束」と
  同型の回復で、手順の追記は §7-5 に反映した
- 切替後の実測:
  - 旧 external FQDN `https://ca-felisaichatbot-dev.blackbush-…/readyz` → **404**
    （環境 proxy が拒否。internet から backend へ直接到達不能）
  - internal FQDN への internet からのアクセス → **404**（同上）
  - frontend `/readyz` → **200**（proxy が `http://ca-felisaichatbot-dev.internal.…` へ向いた）
  - `workflow_dispatch` の probe → **success**（2026-09-01T14:03:14Z 起動の run）
  - 認証済みブラウザから `/chat` → SSE 応答受信（frontend → BFF → internal backend の全経路）

## 7. セキュリティ確認（deployed 環境）

- **bundle 秘匿**: frontend コンテナ内で
  `grep -rF "$CHAT_API_KEY" .next/static/` → 不検出（`BUNDLE_CLEAN`）。同シェルで
  `$CHAT_API_KEY` が非空（`ENV_PRESENT`）であることも確認 = 「runtime env には在るが
  client 配布物には無い」を deployed 実機で確認（#193 のローカル検証の deployed 再確認）
- **principal header 偽装**: 無認証 + `X-MS-CLIENT-PRINCIPAL`（偽装 JSON の base64）+
  `-ID` / `-NAME` / `-IDP` 偽装で `POST /api/chat` / `GET /` → いずれも **401**。
  偽装 header は認証として扱われない（#183 の実測（除去・置換）と整合。ADR-0027 決定 10 の
  前提維持）

## 8. 逸脱・保留・発見事項

| 事項 | 扱い |
| --- | --- |
| 割当 3 者のうち synthetic 用 SP | SP 未作成のため保留。synthetic transaction SLI の作業単位で割当を追加する |
| MFA 登録の強制（テナント既定） | テストユーザーは TOTP で登録済み（secret は `.env` 管理）。ブラウザ実測に使ったパスワードは実測後にローテーション済み |
| OIDC scope への管理者同意（`AADSTS90094`） | `oauth2PermissionGrants`（AllPrincipals）で解消。entra-easy-auth-setup.md §2 に追記 |
| apply の provider 不整合（`BACKEND_ORIGIN`） | 再 apply で収束・差分ゼロ確認済み。§7-5 に注意書きを追記 |
| cron probe の観測密度 | schedule 実行は既知の起動遅延 / gap がある（本切替とは独立の既知事象）。切替前後の probe 成功は `workflow_dispatch` で実測した |
| authConfigs 適用直後の 503 | sidecar 入り replica への入れ替え中（Activating）の想定内挙動。当時の外形監視は backend 直接のため SLI 影響なし |
| frontend の副題が「Day 1: LLM はスタブ。RAG 接続は Day 2」のまま | 表記が古い（事実の記録のみ。本 Issue の対象外。`LLM_PROVIDER` 切替 / seed の後続 Issue の際に見直す） |

## 10. テストユーザーの削除（検証後の後片付け）

証跡取得完了後、テストユーザー 2 名を削除した（使い捨て運用。再検証時は
entra-easy-auth-setup.md §4 で作り直す）。

```console
$ az ad user delete --id "felis-test@gatsbykenjigmail.onmicrosoft.com"
$ az ad user delete --id "felis-test-unassigned@gatsbykenjigmail.onmicrosoft.com"
$ az ad user list --filter "startswith(userPrincipalName,'felis-test')" --query "length(@)" -o tsv
0
$ az rest --url ".../servicePrincipals/0544d912-…/appRoleAssignedTo" \
    --query "value[].{p:principalDisplayName,t:principalType}" -o json
[ { "p": "K Y", "t": "User" } ]   # 残る割当は owner のみ
```

削除により app role の割当も消えるため、以後の割当は owner 1 者（+ 将来の synthetic 用 SP）。
ブラウザ実測に使ったパスワードは実測直後（削除前）にローテーション済みで、値はログ・記録の
いずれにも残していない。

## 9. コスト

- 追加の常駐は frontend 1 replica（0.25 vCPU / 0.5 GiB）のみ。目安 0.0769 USD/日
  （ops コンテナの 2026-08-29 課金実測の転用。ADR-0027「影響」どおり frontend 自身の実測値は
  `usageDetails` に `ca-felisaichatbot-dev-front` のメーターが現れた時点で確定させる）
- ACR は frontend image 1 本分のストレージ増（Basic の included 10 GiB 内）
