# ADR-0029: authenticated synthetic transaction の実行・認証・保存構成

## ステータス

Proposed

## 日付

2026-09-16

## 背景

[Issue #271](https://github.com/kmryst/felis-ai-chatbot/issues/271) は、定義済みの
[SLI specification](../operations/slo/slo-document.md) と
[測定スキーマ](../observability/slo/sli-measurement-schema.md) を実装へつなぐ設計を対象とする。
ブラウザで通常回答・notice の基本動作は確認されたが、自動測定の validation や baseline は未実施である。

SLI は公開 frontend の supported client による parse / render を含む。
HTTP probe で SSE の `done` event を受理するだけでは測れず、予定が実行されなかった場合も結果不在を検出できる構成が必要になる。
[ADR-0027](0027-frontend-azure-deployment-and-public-surface.md) は synthetic 用 service principal の
割当を想定しており、Easy Auth と BFF の認証経路を使う。

## 決定内容

1. **実行**: Japan East の測定専用 Azure Container Apps Workload profiles environment（Consumption workload profile）に scheduled Job を置き、
   Playwright / Chromium で deployed frontend を操作する。serving Environment / VNet と分離し、
   公開 frontend の安定 FQDN を入口とする。同一 Azure region に依存する限界は残す。
   image / Playwright / Chromium は固定参照で記録する。
2. **認証**: 専用 user-assigned managed identity の service principal に `Chat.Use` を割り当て、
   frontend を audience とする Entra access token を取得する。ACR pull 用の既存 identity は流用しない。
   runtime に directory 管理権限や backend の `CHAT_API_KEY` は与えない。
   MI token の取得と更新は runner で行い、token 値を記録・永続化しない。
3. **ブラウザへの認証適用**: 初期 HTML / static assets の GET は exact origin を確認して
   `route.fetch({ maxRedirects: 0 })` で取得し、3xx は拒否して実 response をブラウザへ渡す。
   測定対象 POST は supported client の synthetic 用準備処理で exact origin / path を確認し、
   Bearer と `redirect: "error"` を設定する。準備完了後に開始時刻を取得し、native `fetch` を呼ぶ。
   POST の SSE は proxy / buffer / 再構成せず、既存 consumer と React の描画を観測する。
   初期 GET の取得方式・HTTP cache 無効・service worker 無効は測定条件として固定する。
4. **予定と実行**: 有限の campaign の予定を実行開始前に保存する。初期候補は 35 日、
   毎時 UTC `:07` に通常回答、`:37` に notice の 1 試行ずつとする。
   ACA cron は runner の起動契機とし、事前予定と実行履歴の対応付けは Reconciler が行う。
   lease と実行状態で campaign 全体を直列化し、期限を過ぎた予定の HTTP request を後から補充しない。
   `parallelism = 1` だけで execution 間の同時実行が防げるとは扱わない。
5. **保存と再計算**: アプリケーション PostgreSQL と分離した Azure Blob Storage に、予定、
   実行証拠、immutable payload、append-only receipt、固定した集計入力 snapshot と出力を保持する。
   coordination 用の可変 Blob と測定証拠を分離する。schema の状態値・coverage 規則を変更しない。
   ACA 実行履歴や Log Analytics は補助証拠とし、唯一の正本にはしない。

component の責任、記録項目の取得元、保存・照合手順、configuration、費用、停止方法と
検証条件の詳細は [測定設計](../observability/slo/sli-measurement-design.md) を正本とする。

## 検討した選択肢

| 選択肢 | 観測範囲・coverage | 費用・運用負担と採否 |
| --- | --- | --- |
| 測定専用 ACA scheduled Job + Chromium | 公開 frontend と実 client の parse / render。serving Environment と分離できるが Azure / region の共通障害は残る | 実行中の CPU / memory 従量。既存 ACA 運用を再利用でき、MI を使用可能。採用 |
| GitHub Actions schedule + Chromium | Azure の外側から測れる。schedule の遅延・drop が公式の制約で、別の予定台帳が必要 | public repository の標準 hosted runner は無料。coverage の追加制約があるため primary baseline には不採用。手動検証・外部からの補助確認の候補 |
| 外部 scheduler + 専用 VM / container runner | 実行場所を独立させられる。scheduler と runner の履歴を別途保存する必要がある | VM 常時費用、OS / browser の保守、別 provider の認証・運用が増える。初回は不採用。Azure 外の観測点が必要になった時に再検討 |
| 既存 serving Environment 内の Job | supported client は動かせるが、同じ Environment 内の通信は内部経路に留まり得る | 追加構成は少ないが、入口の観測範囲と障害の共通性を優先して不採用 |
| HTTP synthetic のみ | SSE の到達・終了は測れるが、当該試行の React 描画を証明しない | 単純で安価。parse / render を含む primary SLI には不採用 |
| 人間ユーザーの password / 保存 cookie による定期ログイン | interactive sign-in の一部も対象にできるが、MFA・session 更新を別途管理する必要がある | 長期 credential と再認証の運用を増やすため不採用。非管理者ユーザーの手動 sign-in 試験は別に維持する |

## 採択理由

- SLI は supported client の parse / render を含むため、実際の Chromium で公開 frontend を操作する構成だけが primary SLI の
  measurement point を満たす。SSE の到達・終了しか測れない HTTP synthetic のみの構成は採らない。
- 測定専用の Workload profiles environment を serving Environment / VNet から分離し、公開 frontend の安定 FQDN を入口にすることで、
  既存の ACA 運用と Managed Identity を再利用しつつ、同一 Environment 内の内部経路に留まる観測を避ける。
- 専用 user-assigned managed identity への app role 割当により、人間ユーザーの password / cookie や backend の `CHAT_API_KEY` を
  runtime に置かず、ADR-0027 が想定した synthetic 用 service principal の経路に揃える。
- 実行開始前に保存した予定と append-only receipt により、job execution 未起動・保存障害・再送・payload conflict でも結果不在を検出でき、
  測定スキーマの状態値と coverage 規則をそのまま実装できる。GitHub Actions schedule の遅延・drop と、外部 runner の常時費用・
  別 provider の認証運用は、初回 baseline では引き受けない。

## 影響

以下は本決定の影響と、prototype で確認するまで未検証の前提である。設計上の判断と区別して扱う。

- MI は人間ユーザーの interactive sign-in、MFA、session cookie 更新を再現しない。
  認証 material の準備と初期画面読込は `attempt_started_at` より前であり、失敗は予定 coverage に残す。
- 現行 Easy Auth の issuer / audience に MI token が受理されることは未実測。
  application ID URI、token の `iss` / `aud`、app role 割当を確認し、割当済み成功と未割当・
  wrong audience・期限切れの拒否を prototype の gate にする。必要な設定変更は後続実装で行う。
- GET の redirect 拒否、POST の redirect error、credential 非出力、測定処理の非干渉を
  prototype で検証する。初期 GET の代理取得を含むため、ブラウザのページロード性能を測ったとは扱わない。
- scheduler の等間隔起動は保証とせず、遅延・未実行・同時起動・再起動を事前予定と照合する。
  ACA 実行履歴は直近 100 execution に制限されるため、照合結果と必要な実行証拠を保存する。
- 35 日・30 分間隔などは baseline 用 configuration の初期候補である。
  latency threshold、SLO target、Published 化を決めず、実装・validation・baseline 開始にも代えない。
- Issue #271 では設計文書のみを作成する。Azure / Entra ID の変更、scheduler / collector の実装、
  deployment、継続収集は後続作業とする。

## 関連

- [Issue #271](https://github.com/kmryst/felis-ai-chatbot/issues/271) — 本決定を記録する設計 Issue
- [Issue #264](https://github.com/kmryst/felis-ai-chatbot/issues/264) — 測定スキーマの定義
- [測定設計](../observability/slo/sli-measurement-design.md) — component の責任、記録項目の取得元、保存・照合、configuration、費用、検証計画の正本
- [測定スキーマ](../observability/slo/sli-measurement-schema.md) — 記録項目・状態値・coverage 規則の正本
- [ADR-0027](0027-frontend-azure-deployment-and-public-surface.md) — Easy Auth + BFF の公開面と synthetic 用 service principal の想定
- [ADR-0028](0028-chat-sse-response-contract.md) — SSE 応答契約と共有 fixture
- [ADR-0004](0004-stub-llm-and-no-llm-in-ci.md) — CI から実 LLM を呼ばない。検証計画の故障注入で維持する

## 参考

- [ACA Jobs: schedule / retries / parallelism / execution history](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [ACA built-in environment variables](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables#built-in-environment-variables)
- [ACA Entra daemon authentication](https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra#daemon-client-application-service-to-service-calls)
- [Managed identity への app role 割当](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/assign-app-role-managed-identity-powershell)
- [ACA managed identity と token cache](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [同一 Environment 内の通信](https://learn.microsoft.com/en-us/azure/container-apps/connect-apps)
- [GitHub Actions schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [ACA pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/)
- [Playwright route.fetch](https://playwright.dev/docs/api/class-route#route-fetch)
- [Playwright routing と cache / service worker](https://playwright.dev/docs/api/class-browsercontext#browser-context-route)
- [Fetch Standard: redirect mode](https://fetch.spec.whatwg.org/#concept-request-redirect-mode)
