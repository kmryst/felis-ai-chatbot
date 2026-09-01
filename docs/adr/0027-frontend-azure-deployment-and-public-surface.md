# ADR-0027: frontend の Azure デプロイと公開面の構成（Easy Auth + BFF + backend internal ingress）

## ステータス

Accepted

## 日付

2026-09-01（起案）/ 2026-09-01（Accepted 化・追記。下記「追記」）

## 決定内容

frontend（Next.js）を Azure Container Apps へデプロイし、公開面を次の構成で固定する。

### 1. 公開面の構成: Easy Auth + BFF + backend internal ingress

- frontend を専用の Container App（external ingress）としてデプロイし、
  **Easy Auth（Entra ID）** で認証する。認証設定（`Microsoft.App/containerApps/authConfigs`）は
  azurerm 5.1.0（本層の pin）に該当リソースがないため、**AzAPI provider の `azapi_resource`** で
  Terraform 管理する
- frontend の Next.js Route Handler を **BFF** とし、`POST /api/chat` を受けて backend の
  `POST /chat` を server 側で呼ぶ。**`CHAT_API_KEY` は BFF が server 側で付与**し、
  ブラウザには一切配らない
- backend の ingress は external から **internal へ切り替える**（切替は Easy Auth 経由の疎通が
  実測で成立した後。手順は cutover runbook 改訂で固定）。internet から直接到達できる面は
  frontend のみになる
- **deployed frontend を唯一の supported client とする**（SLO 文書のサービス範囲の改訂は別 PR。
  「影響」参照）
- `/chat` のレート制限は**認証ゲート成功後にのみ quota を消費する** route dependency として
  backend に置く（未認証・遮断中のリクエストが quota を消費しない順序）
- Easy Auth の除外パス（未認証で通すパス）が構成上成立しない場合のフォールバックは
  「backend external ingress の維持」（`/readyz` の正本も backend のまま）とし、その場合は
  本 ADR の該当部分を追記で改訂する

### 2. `NEXT_PUBLIC_CHAT_API_KEY` の廃止

Next.js は `NEXT_PUBLIC_` 接頭辞の環境変数を **build 時に client bundle へ埋め込む**
（出典: <https://nextjs.org/docs/app/guides/environment-variables> ）。現行
`frontend/app/chat.tsx` は `NEXT_PUBLIC_CHAT_API_KEY` を読んで `X-API-Key` ヘッダで送る実装で、
コード内コメントにも「ローカル開発専用。公開デプロイでキーを秘匿する仕組みではない」と明記済み
（Issue #113 の 3）。このままデプロイすると、配布 JS から鍵を取り出した任意の匿名 caller が
backend `/chat` = LLM 課金経路を無認証で使える。よって `NEXT_PUBLIC_CHAT_API_KEY` を**廃止**し、
鍵の保持と付与を BFF（server 側）に一本化する。ビルド成果物（client 配布 JS）に鍵の値が
含まれないことを grep で検証する（実装 PR の受け入れ条件）。

### 3. upstream base URL は server 専用変数 `BACKEND_ORIGIN`

BFF が backend を呼ぶ base URL は **server 専用の非 `NEXT_PUBLIC_` 環境変数 `BACKEND_ORIGIN`**
（Route Handler が実行時に読む。ローカル開発の既定値 `http://localhost:8000`）とする。
`chat.tsx` は**相対パス `/api/chat` のみ**を呼び、`NEXT_PUBLIC_BACKEND_URL` は削除する。
`NEXT_PUBLIC_` を使わない理由は 2 つ: (i) 値が全 client に配布される、(ii) 値の変更に image の
再ビルドが要る（runtime 環境変数なら Terraform の env 変更 = 新 revision で済む）。
Terraform 側は frontend app の env に `BACKEND_ORIGIN` を持ち、初期値は backend の external FQDN、
internal ingress 切替時に internal FQDN へ付け替える。

### 4. Entra app role は `allowedMemberTypes = ["User", "Application"]`

app role の定義と assignment required は**別オブジェクト上の設定**であるため、対象を分けて
記録する。

- **app registration（application object）側**: app role を
  `allowedMemberTypes = ["User", "Application"]` で定義する。`"Application"` を含む app role は
  application object 上の定義でのみサポートされる（出典:
  <https://learn.microsoft.com/en-us/graph/api/resources/approle?view=graph-rest-1.0> ）。
  `["Application"]` のみでは**人間ユーザーをその role に割り当てられず**、非管理者ブラウザ
  利用者の割当と成功確認が構造的に不可能になる（レビュー 4 周目 #5）
- **enterprise application（service principal）側**: **`appRoleAssignmentRequired = true`** を
  設定し（出典:
  <https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/application-properties> ）、
  synthetic transaction 用 service principal と人間ユーザー（下記 5）への割当をこちらに置く
- **実際に到達制御として効いているのは role の値ではなく `appRoleAssignmentRequired` である**。
  Easy Auth（ACA の組み込み認証）は token 内の role claim の検証を行わず、role の検証は
  アプリコード側の責務とされている（出典:
  <https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra> ）。role は
  あくまで「assignment required の割当対象を表現する器」であり、role ベースの認可を
  ACA 層に期待しない

### 5. 成功試験の証跡は非管理者の専用テストユーザーに限定する

assignment required は daemon（service principal）だけでなく人間ユーザーにも適用される。
Global Administrator は assignment required をすり抜け得るため、**owner 自身のブラウザ成功は
「割当が効いている」証跡にならない**。よって:

- **管理者ロールを持たない専用テストユーザー**を作成・割当し、成功試験の証跡はこのユーザーの
  ブラウザ実測に限定する（owner の成功は補助記録）
- 未割当ユーザーのサインインが **`AADSTS50105`** で拒否されることを対で記録する（出典:
  <https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/error-code-aadsts50105-user-not-assigned-role> ）
- 割当は (i) intended user（project owner）、(ii) 非管理者テストユーザー、(iii) synthetic 用
  service principal の 3 者とし、割当一覧を検証記録に含める

### 6. bootstrap の apply 順序（fail-closed）

frontend は external ingress で作られるのに対し、`authConfigs` は**別の ARM 子リソース**である
（出典: <https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps/authconfigs> ）。
そのため「frontend が外部到達可能 かつ authConfigs 未適用」の時間帯が構造的に存在し、その窓では
匿名 caller の `POST /api/chat` が BFF に到達し、BFF が正しい `CHAT_API_KEY` を付けて backend を
呼べてしまう（匿名の LLM 課金経路）。**apply 後の匿名拒否試験ではこの窓を検出できない**
（試験時点で窓は閉じているか、失敗時は窓が開いたまま残る）ため、試験ではなく**順序**で塞ぐ:

1. 既存 cutover runbook §2 の 2 段階 apply（`-target` で ACR のみ → 全体）を拡張し、
   **`chat_disabled = true` かつ frontend 未作成**の段階で apply する。apply 後、
   **100% traffic を持つ revision の template に `CHAT_DISABLED=true` があること**（ARM 読み取り）と、
   **正しい key 付き `POST /chat` が 404 になること**を確認する。
   revision 単位の確認まで行うのは、apply 完了と実効設定の反映が同時ではないため
2. 1 の確認後に frontend + `authConfigs` を作成（apply）し、**匿名 `POST /api/chat` の拒否**と
   **backend ログに chat 実行記録が不在であること**を確認する
3. 最後に `chat_disabled = false` で apply し、認証済み（非管理者テストユーザー）の成功を
   確認する。**2 の検証に不合格、または authConfigs が適用不能なら、この段に進まず
   `chat_disabled = true` を維持するか frontend を destroy する（fail-closed）**
4. 将来の frontend 再作成でも同順序を適用する（cutover runbook に固定）

この順序は既存機構だけで成立する。`terraform/ephemeral/variables.tf:121` の `chat_disabled` と
`main.tf:220` の `CHAT_DISABLED` env は**既存**であり、secret ではなく template の環境変数のため
**値の変更が必ず新 revision を作る**（`main.tf` の該当コメントどおり。`DSN_CONFIG_CHECKSUM` と
同じ理屈）。backend は `CHAT_DISABLED=true` で `/chat` を 404 にする（`backend/app/main.py` の
`_enforce_chat_gate`）ため、窓の間は鍵の有無にかかわらず LLM に到達しない。

### 7. frontend image の契約

- frontend は専用 image（Next.js standalone・非 root・secret 焼き込みなし）とし、Terraform 変数
  **`frontend_container_image`** で参照する。validation は既存 `container_image` と同一方針
  （タグ付き完全参照・`latest` 禁止。ADR-0015 のイメージタグ方針をそのまま適用）
- cutover runbook §2 の build / push を **2 本（backend / backend-ops）から 3 本へ**拡張し、
  `DEPLOY_SHA` の単一正本を共有する

### 8. `READYZ_URL` の正本を frontend の FQDN に付け替える（ADR-0026 の追記）

- frontend に `/readyz` の**透過 proxy**（backend `/readyz` への素通し）を置き、外形監視
  `readyz-probe` の `READYZ_URL`（repository variable。ADR-0026 の正本）を frontend の FQDN へ
  付け替える。backend が internal ingress になった後も外形監視が成立し、かつ監視経路が
  supported client と同じ入口を通る
- パスは **`/readyz`** とする（`/api/readyz` にしない）。ADR-0026 が固定した URL 契約
  （`https://<host>/readyz` のみ許可）と、その実装である workflow の検証正規表現
  `^https://[^/]+/readyz$`（`.github/workflows/readyz-probe.yml`）の両方に適合させ、
  workflow・検証スクリプト・runbook の同時改修を避ける
- `/readyz` は Easy Auth の除外パス（未認証で通す）にする。切替は ADR-0026 の順序
  （probe 停止 → apply → 新 URL 検証 → variable 更新 → probe 再開）に従う
- frontend の安定 FQDN を Terraform output として正本化する（既存 `container_app_fqdn` と
  同型。revision 固有 FQDN は使わない。Issue #135 の教訓を踏襲）

### 9. frontend の `min_replicas = 1`

frontend は `min_replicas = 1` / `max_replicas = 1` とする。ADR-0025 と同型の判断で、
scale-to-zero の cold start が `/readyz` proxy 経由の外形監視と client-visible latency の
偽障害になることを作成時から排除する。ADR-0025 は backend の実測（cold start 起因の偽陽性 3 件）
が根拠だが、**frontend 自身の cold start は未実測**であり、本決定は「同型リスクの予防」として
記録する（frontend 固有の cold start 実測は行わない）。

### 10. 深層防御としての principal header 確認

BFF は、Easy Auth sidecar が注入する認証済み principal header（`X-MS-CLIENT-PRINCIPAL-*`）を
持たない request には `CHAT_API_KEY` を付与せず 401 を返す（ローカル開発向けの無効化フラグを
環境変数で持ち、既定は有効 = fail-closed）。ただし:

- 「sidecar 稼働時、外部 caller が同名 header を偽装しても sidecar が上書き・除去する」は
  公式文書で断定できておらず、**未検証の前提**である（実装 PR で偽装試験を行い実挙動を記録する）
- bootstrap 窓の間は sidecar 自体が存在せず header は偽装可能であるため、この防御は
  **決定 6 の順序の代替にはならない**（多層防御の 2 枚目としてのみ位置づける）

### 付随する決定: `CHAT_API_KEY` rotation の revision 反映

ACA の secret 更新は既存 revision に自動反映されない（出典:
<https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets> ）。
`CHAT_API_KEY_CONFIG_CHECKSUM` env（`DSN_CONFIG_CHECKSUM` と同型。sha256 先頭 8 桁・不可逆）を
**frontend と backend serving の両方の template に同一値で**持たせる。checksum が担保するのは
**「各 app の template diff が、その app の新 revision 作成を発生させる」ことのみ**である。
revision の作成時刻・ready 到達・traffic 切替は app ごとに独立に進み（ACA は revision を
app 単位で扱い、旧 revision は当該 app の新 revision が ready になるまで traffic を受け続ける。
出典: <https://learn.microsoft.com/en-us/azure/container-apps/revisions> ）、Terraform apply にも
複数リソースを原子的に commit / rollback する性質はない。cross-app の同時性・原子性は
主張しない。apply が片側の反映後に失敗した場合（partial apply）は自動 rollback されないため、
**両 app の 100% traffic revision の template に同一 checksum があること**を確認し、不一致なら
再 apply で収束させることを回復手順として cutover runbook に含める。`AZURE_OPENAI_API_KEY` にも
同型の checksum env（`AZURE_OPENAI_CONFIG_CHECKSUM`）を適用する。ただし混在窓は残る
（「影響」参照）。

## 背景

- 現行の supported client は「ローカルで実行する frontend」であり、Azure に frontend は
  デプロイされていない（`docs/operations/slo/slo-document.md` のサービス範囲）。SLI を
  supported client boundary で継続測定するには、frontend のデプロイが前提になる
- 現行 `frontend/app/chat.tsx` は `NEXT_PUBLIC_BACKEND_URL` と `NEXT_PUBLIC_CHAT_API_KEY` を
  使っており、どちらも client bundle に埋め込まれる。前者は upstream の付け替えに再ビルドを
  強い、後者はデプロイすると無認証の LLM 課金経路の公開になる（Issue #113 の 3）
- backend の `/chat` ゲート（`_enforce_chat_gate`）は API key の一致だけを見る。`chat_disabled`
  の Terraform 既定値は `false` であり、frontend を無防備に公開した瞬間から課金経路が開く
- 本構成は外部レビュー 4 周（Codex）を経て確定した。特に「Easy Auth bootstrap 窓での匿名
  LLM 消費」（3 周目の新規クリティカル指摘）、「`allowedMemberTypes = ["Application"]` のみでは
  人間ユーザーを割当不能」（4 周目 #5）、「共有 `CHAT_API_KEY` rotation の両側 revision 反映」
  （3 周目 #6）は、レビューで発見され本 ADR の決定に組み込まれた

## 検討した選択肢

### 1. Easy Auth + BFF + backend internal ingress（採択）

鍵を server 側に閉じ、認証を ACA プラットフォーム層（Easy Auth）に任せ、backend を internet
から消す。上記「決定内容」のとおり。

### 2. backend を external ingress のまま維持し、frontend から直接呼ぶ（却下）

`NEXT_PUBLIC_` の鍵配布問題がそのまま残る上、backend `/chat` が匿名 internet から到達可能な
面として残り続ける。SLI の measurement point（supported client boundary）とユーザーの実経路も
一致しない。認証を backend 側に自作する案も、Easy Auth が既に提供する OIDC フローの再実装に
なるだけで、実装量とレビュー面積が増える。

### 3. frontend を Static Web Apps 等の別サービスに置く（却下）

ACA に揃えれば、image 契約（SHA 不変タグ）、cutover runbook、Terraform 層、Log Analytics、
`min_replicas` の考え方（ADR-0025）をそのまま frontend に再利用でき、backend internal ingress
への到達も同一 CAE 内で閉じる。別サービスでは internal backend への private 到達・認証・IaC の
持ち方をサービス固有に設計し直すことになり、検証済みの資産がない。マネージド外リソースを
増やさない方針（ADR-0014 の系譜）にも反する。

### 4. `NEXT_PUBLIC_` の鍵のままレート制限だけで守る（却下）

bundle 内の鍵は誰でも取り出せるため、レート制限は「無認証課金経路の消費速度を抑える」だけで
経路自体は残る。鍵の rotation にも client の再ビルド・再配布が要る。認証の代替にならない。

### 5. bootstrap を単一 apply で行い、事後の匿名拒否試験で担保する（却下）

匿名到達可能な窓は apply の**最中**（frontend 作成後・authConfigs 適用前）に存在するため、
apply 成功後の試験では原理的に検出できない。さらに apply が authConfigs の手前で失敗した場合、
frontend が無認証で公開されたまま残る。順序（決定 6）でなければ塞げない。

### 6. Easy Auth の認可（role 検証）に依存する（却下）

Easy Auth は ACA 層で app role を検証しないため、role 定義だけでは tenant 内の任意 client が
audience への token を取得して通過し得る。到達制御は `appRoleAssignmentRequired` で行う（決定 4）。

### 7. proxy パスを `/api/readyz` にする（却下）

ADR-0026 の URL 契約（`https://<host>/readyz` のみ許可）と、その workflow 実装の検証正規表現
`^https://[^/]+/readyz$`（`.github/workflows/readyz-probe.yml`）に適合せず、workflow・
検証スクリプト・cutover 手順の 3 点同時変更が必要になる。`/readyz` なら変更は
repository variable の値だけで済む。

### 8. dual-key 受理で rotation の混在窓を消す（今回は採らない・将来の選択肢）

`CHAT_API_KEY_CONFIG_CHECKSUM` の両側適用でも、2 つの Container App の revision 切替は独立に
進むため、切替中は「新 key の frontend × 旧 key の backend」（またはその逆）が併存し得る。
**静的共有鍵ではこの窓は原理的に消えない**（checksum で消せるという案はレビューで不成立と
確定）。窓を消すには backend が新旧 2 鍵を同時受理する期間（dual-key）が必要だが、それは
backend 認証ゲートの拡張 = 本決定のスコープ外の設計変更のため、今回は採らず将来の選択肢として
記録する。漏えい時の**即時遮断は rotation ではなく `CHAT_DISABLED`（既存の緊急遮断）が担う**。

## 採択理由

- 鍵をブラウザに配らない構成は BFF（server 側付与）だけが満たす。`BACKEND_ORIGIN` を runtime
  環境変数にすることで、external → internal の付け替えが image 再ビルドなしの apply で完結する
- Easy Auth は認証フローをプラットフォーム層で持ち、アプリコードの認証実装を増やさない。
  到達制御は `appRoleAssignmentRequired` + 割当（人間 2 者 + SP 1 者）で成立し、証跡は
  「非管理者の成功 / 未割当の `AADSTS50105`」の対で管理者バイパスの疑義を排除できる
- bootstrap 窓は、既存の `chat_disabled` / `CHAT_DISABLED`（revision-scope env で反映漏れが
  ない）を使う順序制御だけで塞げる。新規の遮断機構を作らないため、fail-closed の検証も
  「404 と ログ不在」という既存の観測手段で完結する
- `/readyz` proxy と frontend FQDN への正本付け替えは、ADR-0026 の fail-closed 検証と
  URL 契約（workflow 実装の検証正規表現を含む）をそのまま生かし、外形監視の経路を
  supported client と一致させる

## 影響

- 変更対象: `frontend/app/chat.tsx`（相対パス化・`NEXT_PUBLIC_*` 2 変数の削除）、
  `frontend/app/api/chat/route.ts` と `frontend/app/readyz/route.ts`（新設 BFF / proxy）、
  `terraform/ephemeral/`（frontend app・authConfigs・`frontend_container_image`・
  `BACKEND_ORIGIN`・checksum env 両側適用・AzAPI provider 追加）、
  `docs/operations/vnet-integration-cutover.md`（3 image 化・bootstrap 順序の固定・
  internal ingress 切替手順）
- SLO 文書のサービス範囲（supported client = deployed frontend）の改訂は**別 PR** で行う
  （測定意味論の変更として変更履歴に記録する）
- **`CHAT_API_KEY` rotation の混在窓は limitation として残る**（検討した選択肢 8）。運用は
  「同一 apply・計画的 rotation・緊急時は `CHAT_DISABLED`」とし、rotation rehearsal を実施した
  場合のみ成功と記録する（見送り時は未実測 limitation として記録）
- Entra ID の app registration・割当・テストユーザー作成は Terraform 管理外のユーザー実行
  （CI service principal の権限外。ADR-0012 の権限境界）
- コスト: frontend 常駐 1 replica の目安は 0.0769 USD/日（ADR-0025 と同じ ops コンテナの
  2026-08-29 課金実測の転用）。**frontend 自身の値は未実測**であり、実測で確定させる
- **未検証の前提**（実装 PR の実測で確定させ、結果次第で本 ADR に追記する）:
  - Easy Auth sidecar 稼働時の `X-MS-CLIENT-PRINCIPAL-*` header の上書き・除去挙動（決定 10）
  - revision 切替の実時間と rotation 混在窓の実時間幅（実測値でのみ主張する）
  - frontend の cold start 特性（決定 9 は予防採用であり実測しない）

## 追記（2026-09-01。#183 実測反映と実装 PR での確定事項）

- **Accepted 化の根拠**: 前提としていた実測（#183）が完了し、ADR の前提と一致した
  （[実測記録](../verification/easy-auth-container-app/observations.md)）。
  - 決定 10 の未検証前提「sidecar 稼働時の header 偽装の上書き・除去」は**実測と一致**
    （無認証 + 偽装 4 種はアプリ到達前に完全除去、認証済み + 偽装は実 principal に完全置換）
  - revision 切替の実時間は 20.31 / 35.02 / 28.41 / 32.48 秒（4 回実測。観測記録としてのみ扱い、
    閾値の根拠に流用しない）
  - ingress 既定 240 秒はアイドル（バイト間）timeout（総リクエスト時間ではない）
- **実装 PR（Issue #194）で確定した具体値**:
  - frontend Container App 名は `ca-felisaichatbot-dev-front`（ADR-0013 の規則。qualifier
    `-front`）
  - `authConfigs` の管理は AzAPI provider 2.12.0・API バージョン `2025-07-01`（stable）
  - internal ingress 切替後の `BACKEND_ORIGIN` は **`http://<internal FQDN>`**（決定 3 の
    「internal FQDN へ付け替え」の scheme を確定）。同一環境内の app 間通信は Envoy 経由で
    環境外に出ず、公式ドキュメントが app 間呼び出しに http を推奨する（出典:
    <https://learn.microsoft.com/en-us/azure/container-apps/connect-apps> ）。internal FQDN
    （`<app>.internal.<既定ドメイン>`）への https は、環境の既定証明書がこの 1 階層深い名前を
    カバーするか公式に断定できないため使わない。合わせて internal 切替時のみ backend ingress の
    `allow_insecure_connections = true` とする（external の間は https 強制を維持）

## 関連

- [ADR-0009](./0009-azure-openai-as-llm-provider.md) — LLM 課金経路の源。保護対象の確定元
- [ADR-0010](./0010-rag-wiring-and-hallucination-guard.md) — `/chat` の応答系（guard 経路含む）
- [ADR-0012](./0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — Entra 操作を
  ユーザー実行とする権限境界
- [ADR-0013](./0013-azure-resource-naming-convention.md) — frontend 関連リソースの命名は
  この規則に従う（具体名は実装 PR で確定）
- [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) — イメージタグ方針を
  frontend image へ適用。cutover runbook §2 の段階 apply を本 ADR 決定 6 で拡張
- [ADR-0018](./0018-postgresql-private-access-and-vnet-integration.md) — VNet 統合と
  cutover runbook の枠組み
- [ADR-0025](./0025-serving-min-replicas-1-for-sli-integrity.md) — 決定 9（frontend
  `min_replicas = 1`）の同型判断
- [ADR-0026](./0026-readyz-repository-variables-as-source-of-truth.md) — **決定 8 は本 ADR に
  よる追記**（`READYZ_URL` の正本を frontend FQDN へ付け替える。URL 契約・切替順序は維持。
  検証正規表現の実体は `.github/workflows/readyz-probe.yml` の workflow 実装）
- [ADR-0028](./0028-chat-sse-response-contract.md)— BFF が中継する SSE 応答契約
- Issue: #113（の 3 = `NEXT_PUBLIC_` 鍵、の 4 = レート制限）/ #107（`/chat` 保護ゲート）/
  #106（外形監視）/ #135（安定 FQDN output）
- [SLI / SLO 文書](../operations/slo/slo-document.md) /
  [VNet 統合 cutover 手順](../operations/vnet-integration-cutover.md)
