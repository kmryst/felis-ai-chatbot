# Azure リソース台帳（全リソース一覧 + Terraform 管理外リソースの詳細）

本書は、このプロジェクトが Azure 上に持つ**全リソースの正本台帳**です。前半（§A）は Terraform 管理下も含めた全リソースの一覧と寿命・課金、後半（§B）は Terraform 管理外リソースの詳細（なぜ管理外か / 作り直す手順 / 確認コマンド）を扱います。

（履歴: 本書は管理外 9 件のみの台帳 `terraform-unmanaged-resources.md` として作られ、#76 で全リソース一覧へ拡張・改名した。管理外の詳細節の内容は据え置き）

## この台帳の役割

Terraform 管理下のリソースには `terraform plan` による差分検出（コードと実物のずれの機械的な検出）があるが、**管理外リソースにはそれがない**。本台帳と §B 各節の読み取り確認コマンドがその代替であり、**この手順書が実質的な「コード」の役割を果たす**。

- リソースを追加・変更・削除したときは、**同じ PR で本台帳（§A の一覧と、管理外なら §B の詳細節の両方）を更新する**
- §B の「確認コマンド」はすべて**読み取り系**で、そのまま実行できる。実行結果が「あるべき値」列と食い違ったら、それが管理外リソースにおける「plan 差分」である
- §B の実測値は 2026-08-20〜21 に各確認コマンドを実行して記録した

## §A. 全リソース一覧（誰の管理下で・いつ消えるか）

### 用語（読み違えるとこの表全体を誤読する）

- **管理区分**: `管理外` = Terraform の管理下にない（詳細は §B）。`persistent` / `ephemeral` = それぞれ `terraform/persistent/` / `terraform/ephemeral/` の管理下
- **persistent** は「**ephemeral を destroy しても残る層**」の意味であって「永続」ではない。プロジェクト終了時には destroy する（層分割の定義は [bootstrap.md §5-4](./bootstrap.md) が正本）
- **「日々の運用」と「プロジェクト終了時」は別の時間軸**である。「日々は残す（stop もしない）が、終了時には destroy する」（persistent 層）のように、両者は独立に決まる

### 一覧

| リソース | 管理区分 | 日々の運用 | プロジェクト終了時 | 残した場合の課金 |
| --- | --- | --- | --- | --- |
| RG ×3 / OIDC アプリ + federated credential / マネージド ID / ロール割当 3 件（§B #2〜#4 / #6〜#9） | 管理外 | 触らない | 残す | $0 |
| Azure OpenAI + デプロイ 2 件（§B #1） | 管理外 | 触らない | 残す | アイドル $0（トークン従量。ADR-0014 (d)） |
| tfstate Storage Account + container（§B #5） | 管理外 | 触らない | 残す | 誤差（数 MB の LRS blob） |
| PostgreSQL Flexible Server（**private access**。ADR-0018。**geo 冗長バックアップ有効**。ADR-0019） / `azure.extensions` | persistent | 残す（**stop しない**。ADR-0017） | destroy | 無料枠内（本書「12か月無料枠」節。ネットワーク方式で無料枠が変わるかは未確定 = ADR-0018。geo 冗長有効でバックアップ消費は 2 倍だが、実測約 2.7 MiB × 2 は無料枠 32 GB の桁外れ下 = ADR-0019） |
| VNet `vnet-felisaichatbot-dev` / サブネット `snet-felisaichatbot-dev-aca`（`10.10.0.0/26`・CAE 委任）+ `snet-felisaichatbot-dev-pgsql`（`10.10.0.64/27`・PostgreSQL 委任） / private DNS zone `felisaichatbot-dev.private.postgres.database.azure.com` + VNet link（ADR-0018） | persistent | 残す | destroy | private DNS zone のみ 0.5 USD/zone/月（Retail Prices API 実測。ADR-0018）。VNet / サブネット / link は無料 |
| Log Analytics workspace | persistent | 残す | destroy | 未確認（取込ゼロなら取込課金 0、保持 30 日は取込料金に含まれるが、放置時の総額は実測していない） |
| ACR / Container Apps Environment（VNet 統合・workload profiles） / Container App / ops Container App / migration Job（ADR-0018。**2026-08-22 ステップ B で作成済み・稼働中** = [実測記録](../verification/vnet-cutover/observations.md)） / **obs cron Job `caj-felisaichatbot-dev-obs`**（Schedule トリガー・毎分。Issue #104。**2026-08-23T07:14:58Z 作成・稼働中** = [フェーズ 1 実測記録](../verification/observation-phase1/observations.md)） | ephemeral | 残す（**夜間 destroy しない**。ops 経路が唯一の DB アクセス経路のため。ADR-0018 追記・計画書 §3-6。destroy は失効前の最終 teardown のみ = [ADR-0020](../adr/0020-credit-window-resource-strategy.md) / [credit-window-execution-plan.md](./credit-window-execution-plan.md) §9、2026-09-15 目安（当初 2026-09-16 想定 → フェーズ 1 の 72h 化で 2026-09-03〜09-04 へ前倒し → 2026-08-30 の作業窓再設定（8/27〜9/14）で 9/15 に確定 = 計画 §10-5） 予定） | destroy | ACR 約 5 USD/月（0.1666 USD/日 × 30。ADR-0015 実測単価。**請求実績は 0.145 USD/日** = 2026-08-30 取得の usageDetails で `Basic Registry Unit` 8/19〜8/29 合計 1.305 USD）。CAE 稼働中は custom VNet の managed resources（Standard LB + static public IP）分が加わる（24h 換算含め ADR-0018。destroy で止まる）。Container App / ops / Job 群は **2026-08-27 分から `microsoft.app` のメーターが `usageDetails` に現れるようになり、リソース単位の按分ができる**（2026-08-30 取得。**8/26 以前は 1 件も無い**という当時の実測 = [フェーズ 1 実測記録 §9-4](../verification/observation-phase1/observations.md) は誤りではなく、前提のほうが変わった）。8 月合計 **1.145 USD**（`Standard vCPU Active` 0.692 / `Standard vCPU Idle` 0.089 / `Standard Memory Idle` 0.185 / `Standard Memory Active` 0.180）。リソース別の累計は `ca-felisaichatbot-dev` 0.455 / `ca-felisaichatbot-dev-ops` 0.279 / `caj-felisaichatbot-dev-obs` 0.412。**8/27 に出始めた理由は未検証**（`- Free` 対のメーターが 1 件も無く、無料付与枠の消費過程を `usageDetails` から観測できない。月次付与枠の使い切りは**推測**であって確認していない）。**平常運転の日額は確定していない**: 8/28 は HA ドリル日かつ測定用 Monitor の停止忘れ（約 14h）で汚染、8/29 はその残り（推定 ~0.5h・終了時刻未確認）を含む。追跡は Issue #115（同 Issue のコールドスタートコスト実測は、外形監視 probe が設計頻度で動いていないため未達） |
| Action Group `ag-felisaichatbot-dev-email` / メトリクスアラート 5 件（§B #10 / #11。Issue #145 で 3 件、Issue #148 で `storage_free` 系 2 件。**2026-08-27 作成・稼働中**。az CLI 作成分を **2026-08-27 に `terraform import` で persistent 層へ移行**（Issue #151 / [ADR-0022](../adr/0022-import-azure-monitor-into-terraform.md)。リソース ID は不変 = 発火試験の証跡は有効なまま）） | persistent | 残す | destroy | **未実測**（Action Group のメール通知には無料枠があり、メトリクスアラートはルール単位の月額課金だが、いずれも本プロジェクトで請求実績を確認していない。Issue #145 時点では単価を裏取りしていないため数字を書かない） |

### 「管理外＝残す、Terraform 管理下＝消す」の一致は偶然ではない

管理外にしたのは「Terraform で作ると自分の足を撃つ」もの（鶏と卵・destroy すると権限や認証が壊れる・据え置き判断。§B の理由区分）であり、いずれも寿命が長い。だから終了時の後片付けは **`terraform -chdir=terraform/ephemeral destroy` と `terraform -chdir=terraform/persistent destroy` の 2 本で済み、`az group delete` は不要**である（手順は「プロジェクト終了時の後片付け」節）。

かつて §B #10 / #11（Azure Monitor のリソース 6 件 = Action Group 1 + メトリクスアラート 5）が「管理外だが終了時に消す」というこの一致から外れる唯一の例外だったが、**2026-08-27 に `terraform import` で persistent 層へ移行して例外は解消した**（Issue #151 / [ADR-0022](../adr/0022-import-azure-monitor-into-terraform.md)）。現在は管理外リソースに例外はなく、終了時の後片付けは `terraform destroy` 2 本（+ ロック解除）で完結する。

## サブスクリプションのリソースプロバイダー登録（手動側の前提作業）

リソースプロバイダー登録は**サブスクリプション単位の設定変更**であり、リソースではない。当初（Day 3）は
「リソースではないため台帳の対象に追加しない」と判断した（[walking-skeleton/observations.md](../verification/walking-skeleton/observations.md)）が、
**未登録 namespace は apply を `409 MissingSubscriptionRegistration` で確実に失敗させる前提条件**であり、
plan 差分にも出ないため、本台帳の「管理外リソースの読み取り確認」と同じ役割が要ると判断を改めて一覧化する（#84）。

- **登録は Terraform に任せず、手動（ローカルの Owner）で行う**。CI の service principal は
  RG スコープの Contributor で、`/register/action`（サブスクリプションスコープ）を実行できない
  （Day 3 に 409 を実測し Owner の手動登録で解消した記録が上記 observations.md にある）。
  Terraform の自動登録に任せると「ローカルでは通るが CI では落ちる」構成になる（Issue #82 で踏む）
- 登録手順と確認コマンドは [vnet-integration-cutover.md](./vnet-integration-cutover.md) §0-1

| Namespace | 状態（2026-08-22 読み取り実測） | 経緯 / 必要とする理由 |
| --- | --- | --- |
| `Microsoft.DBforPostgreSQL` | Registered | bootstrap 時点で登録済み（observations.md）。PostgreSQL Flexible Server |
| `Microsoft.Storage` | Registered | bootstrap（tfstate Storage Account）時点で登録済み |
| `Microsoft.ManagedIdentity` | Registered | bootstrap（マネージド ID 手動作成）時点で登録済み |
| `Microsoft.App` | Registered | Day 3（2026-08-21）に 409 を踏んで手動登録。Container Apps / CAE / Job |
| `Microsoft.ContainerRegistry` | Registered | Day 3（2026-08-21）に 409 を踏んで手動登録。ACR |
| `Microsoft.OperationalInsights` | Registered | Day 3（2026-08-21）に 409 を踏んで手動登録。Log Analytics |
| `Microsoft.Network` | Registered | VNet 統合カットオーバー（ADR-0018）の前提として §0-1 の手順で手動登録。ステップ A/B の apply 前に Registered であることを読み取り実測（2026-08-22 12:02Z）。VNet / サブネット / private DNS zone |
| `Microsoft.ContainerService` | Registered | 同上（2026-08-22 12:02Z 読み取り実測で Registered）。CAE の custom VNet 構成の前提（出典: <https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom> に "Register the `Microsoft.ContainerService` provider" と明記） |

## 12か月無料枠（PostgreSQL Flexible Server）

2026-08-19 サインアップの Azure 無料アカウントには、$200 クレジット（30 日）とは別に **12 か月の無料サービス枠**があり、PostgreSQL Flexible Server が含まれる。

- 原文: 「750 hours of Flexible Server—Burstable B1MS Instance, 32 GB storage, and 32 GB backup storage」（出典: <https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account> ）
- **$200 クレジット期間中も適用される**: 「As long as you have unexpired credit or you use only free services within the limits, you're not charged.」（出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account> ）
- 24 時間 × 31 日 = **744 時間 < 750 時間**。B1ms 1 台なら**常時稼働でも無料枠内**に収まる（PostgreSQL を夜間 stop しない判断の根拠のひとつ。ADR-0017）
- 対象は **Burstable B1MS のみ**（上記原文）。General Purpose へのスケールと HA standby（[credit-window-execution-plan.md](./credit-window-execution-plan.md) §6）はこの枠の対象外で、クレジットからの控除になる（クレジットが残る限り実支出は $0）

### 750 時間の消費状況の確認手段

- Azure Portal の Subscription 画面にある free services grid（出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/check-free-service-usage> ）
- **CLI では Microsoft.Consumption の usageDetails を `az rest` で叩く**（2026-08-24 に経路を確立し、2026-08-30 に再取得して追認。`az consumption usage list` は PretaxCost が None で使えないことを 2026-08-21 に実測済み。[day3-5-execution-plan.md §8](./day3-5-execution-plan.md#8-コスト見張り)）。subscription ID はハードコードせず毎回 CLI で取得する:

  ```bash
  SUB=$(az account show --query id -o tsv)
  az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/usageDetails?api-version=2023-05-01&\$filter=properties/usageStart%20ge%20'2026-08-01'%20and%20properties/usageEnd%20le%20'2026-08-31'&metric=actualcost&\$top=1000" -o json
  # 応答に nextLink があればたどってページングし、.value[] を集約する
  # 無料枠の消費: properties.meterName == "B1MS Compute - Free" の quantity（unitOfMeasure = "1 Hour"）を日別に合計
  # 課金の内訳: properties.meterName ごとに costInUSD を合計
  ```

- **`consumedService` は大文字小文字が混在する**（2026-08-30 取得の実測）。同一の API 応答に `Microsoft.Network` と `microsoft.network`、`Microsoft.Insights` と `microsoft.insights` が**両方**現れ、Container Apps は `microsoft.app`（lowercase）のみ、Log Analytics は `microsoft.operationalinsights`（lowercase）のみだった。**サービス単位で集約するときは case-insensitive に正規化しないと、同じサービスが 2 行に割れて見落とす**（`jq` なら `ascii_downcase`）。メーター単位（`meterName`）での集約にはこの問題は出ていないが、確認していないので前提にしない
- **2026-08 の消費実績（2026-08-30 取得）: `B1MS Compute - Free` 合計 192 時間 / 750 時間（25.6%）。コストは 0 USD**。日次内訳は 8/21 = 18h（サーバー作成 05:59Z 以降）、8/22〜8/27 = 各 24h、8/28 = 21h、8/29 = 9h（反映途中）。`Storage Data Stored - Free` も全額 0 USD で、**PostgreSQL は compute / storage とも課金 0**
- **SKU 変更中は `B1MS Compute - Free` メーターが計上されない**（2026-08-30 取得の実測）。8/28 に HA ドリルで B1ms → GP D2ds_v5 → B1ms と往復した日は同メーターが 21h（24h ではない）で、差分の 3h 相当は `vCore` メーター側（GP、無料枠対象外）に出ている。**無料枠時間の欠測ではない**ので、往復した日の 24h 未満は異常として扱わない
- **課金データの反映には 1〜2 日程度の遅延がある**（2026-08-21 の実測に加え、2026-08-30 時点でも 8/29 分が部分計上であることを追認。[day3-5-execution-plan.md §8](./day3-5-execution-plan.md#8-コスト見張り)）。日次の見張りではなく、数日おきの確認でよい

### 2026-08 の課金内訳（consumedService 別。2026-08-30 取得）

上のコマンドの応答（162 レコード / 1 ページ / nextLink なし。期間は 2026-08-19〜08-29 で **8/29 は反映途中**）を
`consumedService` で case-insensitive に集約した値。**この表は 8 月分の累計であり、日額ではない**。

| consumedService | 8 月合計 (USD) | 主なメーター |
| --- | --- | --- |
| `Microsoft.DBforPostgreSQL` | 1.4640 | `B1MS Compute - Free` 0 / `Storage Data Stored - Free` 0 / **`vCore` 1.464**（8/28 の HA ドリルで GP D2ds_v5 へ一時昇格した分。無料枠対象外） |
| `Microsoft.ContainerRegistry` | 1.3047 | `Basic Registry Unit`（0.145 USD/日） |
| `microsoft.app` | 1.1454 | `Standard vCPU Active/Idle Usage`・`Standard Memory Active/Idle Usage`（**8/27 分から出現**。§A の ephemeral 行） |
| `microsoft.network` | 0.8380 | `Standard IPv4 Static Public IP` 0.8293（**CAE が custom VNet で立てる managed resources。本プロジェクトに NAT Gateway は存在しない** = ADR-0018 の 4 / ADR-0015 で却下済み） / `Private Queries` 0.0087 / 他は Free メーター |
| `Microsoft.Network` | 0.1148 | `Private Zone`（private DNS zone） |
| `Microsoft.CognitiveServices` | 0.0144 | gpt 4.1 mini 各種 / text-embedding-3-small |
| `Microsoft.Storage` | 0.0003 | `All Other Operations` / 他は Free メーター |
| `Microsoft.Insights` / `microsoft.insights` | 0 | `Emails` / `Alerts Metric Monitored` |
| `microsoft.operationalinsights` | 0 | `Analytics Logs Data Ingestion` |
| **合計** | **4.8816** | クレジット `estimatedBalance` 195.12 / `originalAmount` 200.00（同日取得の balanceSummary）と整合 |

日次合計（全サービス、USD）: 8/19 0.0144 / 8/20 0 / 8/21 0.1188 / 8/22 0.1820 /
8/23 0.3036 / 8/24 0.3039 / 8/25 0.3039 / 8/26 0.3039 / 8/27 0.3115 / 8/28 **2.6830** / 8/29 0.3566（反映途中）。

- **8/28 は平常日ではない**: HA フェイルオーバードリル（B1ms → GP D2ds_v5 → B1ms）に加え、ドリル後に測定用 Monitor を約 14 時間止め忘れて serving を warm に保ち続けた。**8/29 にもその残り（推定 ~0.5h。正確な終了時刻は未確認）が及んでいる**
- **ACA が課金され始めた 8/27 以降で、汚染のない日は 1 日も無い**。したがって本台帳は「平常運転の日額」を確定値として持たない（日額の扱いは [credit-window-execution-plan.md](./credit-window-execution-plan.md) §1-3）
- **無料枠は暦月単位**（PostgreSQL 750 時間は本書「12か月無料枠」節、ACA の付与枠は月次 = 計画書 §1-3）。**9 月に入ると 0 からリセット**されるため、8 月末の実績（特に 8/27 から ACA が課金され始めた状態）をそのまま 9 月へ外挿しない
- **`ca-felisaichatbot-dev-ops` の 24/7 常設は維持する**（2026-08-30 ユーザー判断 = [credit-window-execution-plan.md](./credit-window-execution-plan.md) §10-6 の M1）。**本台帳ではコストを計上するだけで、構成は変えない**。値札は **0.0769 USD/日**（8/29 実測、8,550 vCPU 秒 = 計画書 §1-3。**平常運転の確定日額ではない**限定つきの値）で、teardown 9/15 までの約 17 日で **≒ 1.3 USD**。同日取得の `estimatedBalance` 195.12 USD に対して **0.7%**。技術的な根拠（private access のため ops が唯一の DB アクセス経路。`min_replicas = 0` にしても課金は止まらず、`az containerapp exec` だけを失う）は ADR-0018 追記 / [day3-5-execution-plan.md](./day3-5-execution-plan.md) §3-6 のまま**変更していない**

### リスクと未確定事項（「確定」と書かない）

- **Day 4 の PITR ドリルでは復元先としてもう 1 台の B1ms が一時的に立つ**。2 台分の稼働時間が 750 時間に合算されるなら当月分を超え得る。超えた場合も**超過分はクレジットから引かれるだけで実支出は $0**（クレジット失効 2026-09-18 まで）
- **2026-08 の実績では超過リスクは無い**: 8/30 取得時点で 192 / 750 時間（本節「750 時間の消費状況の確認手段」）。仮に月末まで連続稼働し、PITR ドリルの復元先 1 台が合算されるとしても 750 時間には届かない
- **未確定**（公式に明文を確認できていない事項。確定として扱わない）:
  - 複数台の B1ms を並行稼働させたとき 750 時間が**合算**されるのか
  - **停止中**の時間が 750 時間を消費するか（停止中もストレージ・バックアップストレージの課金自体は継続する。計画書 §2-1 No.6）
  - 原文の「32 GB」が GB / GiB のどちらの厳密解釈か
  - 上記のうち**合算**と**停止中**の 2 件は、今後の PITR ドリル（復元先としてもう 1 台の B1ms が一時的に立つ）で実測できる見込みがある。**ドリル実施までは未確定のまま扱う**
- **無料枠の終了は公式記述では 2027-08 頃**（サインアップ 2026-08-19 から 12 か月。「Your free services and quantities expire at the end of 12 months.」（訳）「無料サービスと数量は 12 か月の終わりに失効します」。出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account> ）
  - **実測値は 2027-09-19**（2026-08-30 に `az rest` でサブスクリプションを取得。`promotions[].endDateTime: 2027-09-19T06:59:55Z`）。サインアップ 2026-08-19 からは **13 か月**にあたる
  - **公式は一貫して "12 months" と書いており、この 1 か月の差を説明する一次情報は見つかっていない = 未解明**。実測値のほうを運用の目安に使い、**どちらが正しいかは断定しない**（本節の判断期限 2026-09-18 は $200 クレジットの失効日であって無料枠の話ではないため、この差は当面の判断に影響しない）

## 課金アカウントとサブスクリプションの構造（2026-08-30 実測）

`az rest --method get` で課金スコープとサブスクリプションを読み取った結果（2026-08-30 取得）。
**課金アカウントの契約タイプとサブスクリプションのオファーは別の階層であり、混同すると
「請求書が出るかどうか」の判定を間違える。**

識別子は本書にハードコードしない（`$SUB` 等のプレースホルダを使う運用。上の
「750 時間の消費状況の確認手段」節と同じ）。

| 階層 | 項目 | 実測値 |
| --- | --- | --- |
| Billing account | `accountType` | `Individual` |
| Billing account | **`agreementType`** | **`MicrosoftCustomerAgreement`（MCA）** |
| Billing account | `accountStatus` | `Active` |
| Billing profile | `currency` | `JPY` |
| Billing profile | **`invoiceDay`** | **`9`** |
| Billing profile | `spendingLimit` | `On` |
| Billing profile | `billingRelationshipType` | `Direct` |
| Invoices | `totalCount` | **`0`**（2026-08-30 時点でまだ 1 枚も発行されていない） |
| Subscription | `state` | `Enabled` |
| Subscription | **`quotaId`** | **`FreeTrial_2014-09-01`（= オファー MS-AZR-0044P）** |
| Subscription | `spendingLimit` | `On` |
| Subscription | `promotions[].endDateTime` | `2027-09-19T06:59:55Z`（本書「12か月無料枠」節の実測終了日） |

### MCA では invoice が必ず発行される

> "If you have a billing account for a Microsoft Customer Agreement (MCA) or a Microsoft Partner Agreement (MPA), you always receive an invoice."

（訳）

> Microsoft Customer Agreement (MCA) または Microsoft Partner Agreement (MPA) の課金アカウントを
> お持ちの場合、常に請求書が発行されます。

- 出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/understand/download-azure-invoice> （2026-08-30 確認）
- 対比: MOSP なら「使用量が月次クレジット額を超えた場合にのみ発行」。**本アカウントは MCA なので毎月出る**
- 発行日は請求サイクル終了後 5〜12 日（同ページ）。実測の `invoiceDay: 9` と合わせると
  **8 月分 ≒ 2026-09-09**（クレジット失効 2026-09-18T06:59:34Z の 9 日前）、
  **9 月分 ≒ 2026-10-09**（失効の 21 日後）。usage file は請求書発行後 72 時間以内（同ページ）
- `totalCount: 0` は「MCA だが 8 月分がまだ請求サイクル内」という状態であって、
  **「invoice が出ないアカウント」ではない**

### Free Trial オファーでは Cost Management の履歴が invoice と一致しないことがある

> "Historical data for credit-based and pay-in-advance offers might not match your invoice. … The price shown on your invoice might differ from the price used for cost estimation."

（訳）

> クレジットベースおよび前払いオファーの履歴データは、請求書と一致しない場合があります。…
> 請求書に表示される価格は、コスト見積もりに使用された価格と異なる場合があります。

- 出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data> （2026-08-30 確認）。
  対象オファーの一覧に **`Free Trial (MS-AZR-0044P)`** が明記されている = **本サブスクリプションが該当する**
- したがって本書と計画書に載る `usageDetails` 由来の数字は、**invoice の数字と一致する保証がない**。
  **両方を残し、差分そのものを証跡として扱う**（退避運用は
  [credit-window-execution-plan.md](./credit-window-execution-plan.md) §9-1）

### 数値がいつ締まるか

> "Azure finalizes or *closes* the current billing period typically up to 72 hours (three calendar days) after the billing period ends."

（訳）

> Azure は通常、請求期間終了後最大 72 時間（3 暦日）で現在の請求期間を確定（クローズ）します。

クローズしても、そこから数日は金額が動く。

> "Usage charges can continue to accrue and can change until the fifth day after your current billing period ends"

（訳）

> 使用料金は現在の請求期間終了後 5 日目まで累積し続け、変動する可能性があります

請求書が立つまでの期間の数字の性格そのものも、公式が明示している。

> "During the open month (uninvoiced) period, Cost Management data should be considered as estimated only."

（訳）

> オープン月（未請求）期間中、Cost Management のデータは推定値としてのみ扱うべきです。

- 出典: いずれも <https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data> （2026-08-30 確認）
- **9 月分が確定するのは最速 10/5 頃、invoice は 10/9 頃**で、どちらもクレジット失効 2026-09-18 より後。
  **teardown を何日前倒ししても「9 月分の確定値」は失効前に取れない**（この帰結が
  teardown 9/15 を維持する判断の根拠 = [credit-window-execution-plan.md](./credit-window-execution-plan.md) §10-6）

### データ保持

> "When cost and usage data becomes available in Cost Management, it gets retained for at least seven years. Cost Management experiences in the Azure portal provide data for the last 13 months."

（訳）

> コストと使用量データが Cost Management で利用可能になると、少なくとも 7 年間保持されます。
> Azure ポータルの Cost Management 機能は直近 13 か月のデータを提供します。

- 出典: 同上（2026-08-30 確認）
- **ただし「無効化されたサブスクリプションでも同じ保持期間か」は明記が無い = 未確定**（下記）

### 未確定（一次情報を確認できていない。確定として扱わない）

計画書 §10-6 の退避運用は、この一覧を**失効前に潰せない前提**として設計してある。

1. クレジット失効による無効化の**後**に、Cost Management / Consumption API を「読み取り」できるかの明文
2. 無効化されたサブスクリプションのデータ保持期間が、有効時と同じかどうか
3. クレジット失効による無効化の段階的タイムライン（何日後にリソース削除等）。
   **サブスクリプションのキャンセルのケースには 3 日 / 30〜90 日 / 90 日 の記述があるが、
   失効ケースに同じ日数が適用されるとは書かれていない。混同しない**
4. 失効で無効化された後の再有効化の猶予期間（日数）
5. MCA invoice の保持期間・ダウンロード可能期間
6. 無効化後に、同一サブスクリプション内の Storage Account の BLOB をダウンロードできるか
   （「storage is read-only」という間接記述のみで、一次情報が存在しない）
7. `balanceSummary` が失効後に何を返すか（`lots` には明文があるが `balanceSummary` には無い）
8. Exports が Free Trial オファー（MS-AZR-0044P）で動作するかの明文
9. 無料枠の実測終了日 2027-09-19 が公式の "12 months" とずれる理由（本書「12か月無料枠」節）

## 従量課金へのアップグレード（判断期限 2026-09-18）

- **アップグレードしないと、クレジットの失効（2026-09-18。lots API 実測。計画書 §8）でサブスクリプションと全サービスが無効化される**: 「Your subscription and services are disabled when your credit runs out or expires at the end of 30 days. To continue using Azure services, you must upgrade your account.」（訳）「クレジットが尽きたとき、または 30 日の終わりに失効したとき、サブスクリプションとサービスは無効化されます。Azure サービスを使い続けるには、アカウントをアップグレードする必要があります。」（出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account> ）。**「使い切って枯渇」と「余ったまま期限切れ」で扱いは同じ**であり、`spendingLimit: On` のままなら 2026-09-18 に無効化される
- アップグレードそのものに料金はなく、**12 か月無料枠はアップグレード後も継続**し、枠を超えた利用分だけが従量課金になる: 「After you upgrade, you'll have continued access to free services for 12 months and you get charged only for usage beyond the free services and quantities.」（出典: 同上。手順: <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/upgrade-azure-subscription> ）
- つまり「アップグレードして §A の構成を無料枠内で残す」か「2026-09-18 までに全部畳む」かの二択で、**判断期限は 2026-09-18**

## プロジェクト終了時の後片付け

証跡（`docs/verification/`）がすべてコミット済みであることを確認してから実行する。

```bash
# 1. PostgreSQL の CanNotDelete ロックを解除（destroy が失敗するため）。
#    Azure Monitor の 6 件（§B #10 / #11）は 2026-08-27 に Terraform 管理下（persistent 層）へ
#    移行済み（Issue #151 / ADR-0022）のため、手動削除は不要。persistent 層の destroy が
#    依存関係の逆順（アラート → Action Group → サーバー）で消す
az lock delete --name lock-pgsql-source-cannotdelete \
  --resource pgsql-felisaichatbot-dev \
  --resource-group rg-felisaichatbot-dev-tf \
  --resource-type Microsoft.DBforPostgreSQL/flexibleServers

# 2. Terraform 2 層を destroy
terraform -chdir=terraform/ephemeral destroy
terraform -chdir=terraform/persistent destroy

# 3. 残存確認
az resource list -g rg-felisaichatbot-dev-tf -o table   # 空になるはず（マネージド ID を除く）
az monitor metrics alert list -g rg-felisaichatbot-dev-tf -o table   # 空になるはず
az monitor action-group list -g rg-felisaichatbot-dev-tf -o table    # 空になるはず
```

- Azure Monitor の 6 件は Terraform 管理下のため、手順 2 の persistent destroy で消える（手動削除の一手は 2026-08-27 の移行で不要になった。Issue #151 / ADR-0022）
- **`az group delete` は使わない**。§A の一覧のとおり、RG と中の管理外リソース（マネージド ID 等）は意図して残す（残しても $0）。サブスクリプションごと解約する場合のみこの限りではない
- persistent 層の destroy 後、Log Analytics workspace は **soft delete 状態で最大 14 日残り、その後 30 日以内に purge される**（「After the soft-delete period, the workspace resource and its data are non-recoverable and queued for purge completely within 30 days.」出典: <https://learn.microsoft.com/en-us/azure/azure-monitor/logs/delete-workspace> ）。誤 destroy 時はこの 14 日間が復旧の窓になる（意図した destroy なら放置してよい）

## 再現手順（revive runbook: destroy 後にデモ用へ戻す）

前提: 管理外リソース（§B）は残っている。作業端末のグローバル IP を `terraform.tfvars`（gitignore 対象）に設定してから実行する。

| # | 手順 | 所要時間 |
| --- | --- | --- |
| 1 | `terraform -chdir=terraform/persistent apply`（PostgreSQL + Log Analytics） | 約 7 分（2026-08-21 実測。サーバー本体 5m32s。[restore-drill/observations.md](../verification/restore-drill/observations.md)） |
| 2 | ephemeral apply（2 段階: ACR を `-target` で先行 → serving / ops イメージ push → 全体 apply。`terraform/ephemeral/main.tf` 冒頭コメントと [vnet-integration-cutover.md](./vnet-integration-cutover.md) §2） | 旧構成実測 約 4〜5 分（2026-08-21。[walking-skeleton/observations.md](../verification/walking-skeleton/observations.md)）。VNet 統合 CAE の作成時間は未実測（ADR-0018 後に更新） |
| 3 | Alembic マイグレーション適用（`az containerapp job start` で `caj-felisaichatbot-dev-migrate` を起動。[vnet-integration-cutover.md](./vnet-integration-cutover.md) §3） | 未実測（数分見込み） |
| 4 | seed（気象庁データ）投入 | 未実測（数分見込み） |
| 5 | embedding 生成 | 所要は未実測。再生成の API コストは 0.1 円未満（実測済み） |

- 合計見込み: **20〜30 分程度**（3〜5 の未実測分を含む概算。実施したら実測値でこの表を更新する）
- backend イメージへの差し替え後は、`container_image` / `container_target_port` / `database_url` / `ops_container_image` の変数指定も必要（`terraform/ephemeral/variables.tf`）。DATABASE_URL のホスト部は private DNS zone 配下の FQDN（`terraform -chdir=terraform/persistent output server_fqdn`）

## §B. Terraform 管理外リソースの詳細

### 管理外の一覧（詳細節の目次。寿命・課金は §A が正本）

| # | リソース | 種類 | 場所 | 管理外の理由区分 |
| --- | --- | --- | --- | --- |
| 1 | `felisaichatbot-openai-dev` + デプロイ `chat` / `embedding` | Azure OpenAI（kind=OpenAI, sku=S0） | RG `rg-felisaichatbot-dev` / japaneast | 据え置き判断（ADR-0014） |
| 2 | `rg-felisaichatbot-dev` | Resource group | japaneast | 据え置き判断（管理外の Azure OpenAI が同居） |
| 3 | `rg-felisaichatbot-dev-tf` | Resource group | japaneast | 権限の器（SP の Contributor スコープそのもの） |
| 4 | `rg-felisaichatbot-tfstate` | Resource group | japaneast | 鶏と卵（tfstate の置き場） |
| 5 | `felisaichatbottfstate` + container `tfstate` | Storage Account（tfstate backend） | RG `rg-felisaichatbot-tfstate` / japaneast | 鶏と卵（tfstate の置き場） |
| 6 | `felis-ai-chatbot-github-actions` + federated credential 1 本 | Entra ID アプリ登録 + service principal | Entra ID（リージョン概念なし） | 鶏と卵（Terraform 実行主体の認証基盤） |
| 7 | ロール割当 2 件（Contributor / Storage Blob Data Contributor） | Role assignment | #3 / #5 のスコープ | destroy すると CI の権限が壊れる |
| 8 | `id-felisaichatbot-dev` | User-assigned managed identity | RG `rg-felisaichatbot-dev-tf` / japaneast | 据え置き判断（ADR-0015。寿命の分離 + 職務分掌） |
| 9 | AcrPull ロール割当（#8 → RG `rg-felisaichatbot-dev-tf`） | Role assignment | #3 のスコープ | SP がロール割当を作れない（ADR-0012）+ destroy すると pull が壊れる |
| 10 | `ag-felisaichatbot-dev-email` | Action Group（Azure Monitor） | RG `rg-felisaichatbot-dev-tf` / Global | **管理外ではなくなった**: 2026-08-27 に persistent 層へ import（Issue #151 / ADR-0022）。詳細節は設計値の正本として §B に残す |
| 11 | メトリクスアラート 5 件（`alert-pgsql-storage-free-low` / `alert-pgsql-storage-free-critical` / `alert-pgsql-storage-percent-80` / `alert-pgsql-is-db-alive` / `alert-pgsql-cpu-credits-remaining-low`） | Metric alert（Azure Monitor） | RG `rg-felisaichatbot-dev-tf` / Global（scope は PostgreSQL） | **管理外ではなくなった**: 2026-08-27 に persistent 層へ import（Issue #151 / ADR-0022）。詳細節は設計値の正本として §B に残す |

理由区分の意味:

- **鶏と卵**: Terraform を動かすために先に存在しなければならないもの。Terraform 自身では作れない（作ると自分の足場を自分で管理することになり、destroy で足場ごと消える）
- **権限が壊れる / 権限の器**: Terraform（CI の service principal）の権限そのもの、またはそのスコープ。誤 destroy が以後の apply / destroy 自体を不能にする
- **据え置き判断**: import 可能だが、あえて管理外に据え置くと判断したもの。判断の記録は [ADR-0014](../adr/0014-keep-azure-openai-out-of-terraform.md)

---

## 1. Azure OpenAI `felisaichatbot-openai-dev` + デプロイ `chat` / `embedding`

| 項目 | あるべき値 |
| --- | --- |
| 名前 / 種類 | `felisaichatbot-openai-dev` / Microsoft.CognitiveServices/accounts（kind `OpenAI`, sku `S0`） |
| custom subdomain | `felisaichatbot-openai-dev`（アカウント名と同名） |
| 場所 | RG `rg-felisaichatbot-dev` / japaneast |
| デプロイ `chat` | gpt-4.1-mini `2025-04-14` / GlobalStandard / capacity 10 |
| デプロイ `embedding` | text-embedding-3-small `1` / Standard / capacity 10 |

- **なぜ管理外か**: 据え置き判断。Day 0 フェーズBの可否判定（[bootstrap.md §2](./bootstrap.md#2-azure-openai-可否判定タイムボックス-2h最優先)）で az CLI により手動作成した（[ADR-0009](../adr/0009-azure-openai-as-llm-provider.md)）。import は技術的に可能だが据え置く。判断の全文は [ADR-0014](../adr/0014-keep-azure-openai-out-of-terraform.md)
- **作り直す手順**: [bootstrap.md §2](./bootstrap.md#2-azure-openai-可否判定タイムボックス-2h最優先) の判定手順と同じ（`az cognitiveservices account create` → `az cognitiveservices account deployment create` ×2）。設計値（モデル・SKU・capacity）は上表と ADR-0009 が正本。**ただし下記リスクのとおり、同名での作り直しは論理削除の purge が先に必要**
- **確認コマンド**:

  ```bash
  az cognitiveservices account show -n felisaichatbot-openai-dev -g rg-felisaichatbot-dev \
    --query '{name:name, kind:kind, sku:sku.name, location:location, customDomain:properties.customSubDomainName, state:properties.provisioningState}' -o json
  az cognitiveservices account deployment list -n felisaichatbot-openai-dev -g rg-felisaichatbot-dev \
    --query "[].{name:name, model:properties.model.name, version:properties.model.version, sku:sku.name, capacity:sku.capacity}" -o table
  ```

- **固有のリスク・注意**:
  - **削除すると同名リソースは 48 時間作れない**（論理削除による名前予約）。「Once you delete a resource, you can't create another one with the same name for 48 hours. To create a resource with the same name, you need to purge the deleted resource.」48 時間以内・未 purge なら recover 可能。purge にはサブスクリプションの Contributor 以上が必要（実行者は Owner なので実行可能）。出典: <https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources>
  - **デプロイを残したままアカウントを削除すると、クォータ割当は purge されるまで最大 48 時間解放されない**。出典（Resource deletion 節）: <https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/quota>
  - **このサブスクリプションで Azure OpenAI アカウントは 1 つしか作れない**: `OpenAI.S0.AccountCount` = limit 1 / current 1（2026-08-20 実測）。検証用の複製アカウントは作れない。**未確定**: 論理削除中のアカウントがこの AccountCount を消費し続けるかは公式に明文がない。TPM クォータが purge まで 48 時間拘束される明記があるため、**同様に拘束されると想定して運用する**（＝削除したら即 purge しない限り 48 時間は再作成不能と見なす）
  - **モデルデプロイのクォータ（TPM）はリソースではなくサブスクリプションに帰属する**: 「Quota is assigned to your subscription on a per-region, per-model, per-deployment-type basis in units of Tokens-per-Minute (TPM)」（出典: <https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/quota>）。本サブスクリプションの quota tier は Free Tier で（quotaTiers API 実測）、実測クォータ（gpt-4.1-mini GlobalStandard 200 / gpt-5-mini 500 / text-embedding-3-small GlobalStandard 1000）は公式 Tier 0 表と一致する。**リソースを消してもクォータ自体は失われない**。出典: <https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits>
  - **モデルには寿命がある**: japaneast の gpt-4.1-mini `2025-04-14` は lifecycleStatus **Legacy** で推論の廃止は **2027-04-14**、text-embedding-3-small `1` は GA で廃止は **2028-02-09**。Deprecated 段階でも「そのモデルをデプロイしたことのあるサブスクリプション」は新規デプロイ可。出典: <https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements>
  - Day 2 で結線済みの RAG（chat / embedding）がこのエンドポイント名に依存する。アカウント名は改名不可（[ADR-0013](../adr/0013-azure-resource-naming-convention.md) の例外記録）
  - API キーは本台帳・リポジトリには書かない（`.env` のみ。コミット禁止）

## 2. Resource group `rg-felisaichatbot-dev`

- **なぜ管理外か**: 据え置き判断の巻き添え。Day 0 フェーズBで Azure OpenAI と同時に手動作成（[bootstrap.md §2](./bootstrap.md#2-azure-openai-可否判定タイムボックス-2h最優先) / ADR-0009）。中身が管理外の Azure OpenAI のみである以上、RG だけ Terraform 管理にする意味がなく、CI の service principal にはこの RG への権限を**意図的に与えていない**（[ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)）
- **作り直す手順**: `az group create --name rg-felisaichatbot-dev --location japaneast`（1 コマンド。ただし中身の Azure OpenAI の作り直しは #1 参照）
- **確認コマンド**:

  ```bash
  az group show -n rg-felisaichatbot-dev --query '{name:name, location:location, state:properties.provisioningState}' -o json
  az resource list -g rg-felisaichatbot-dev --query "[].{name:name, type:type}" -o table   # felisaichatbot-openai-dev の 1 件のみのはず
  ```

- **固有のリスク・注意**: `az group delete` は中の Azure OpenAI ごと消す（#1 の 48 時間予約・AccountCount リスクがそのまま発動する）。全消し手順（[day3-5-execution-plan.md §8](./day3-5-execution-plan.md#8-コスト見張り)）で「面談デモ用に残すなら保留する行」と明記されているのはこのため

## 3. Resource group `rg-felisaichatbot-dev-tf`

- **なぜ管理外か**: 権限の器。CI 用 service principal の Contributor スコープをこの RG に限定する設計（[ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)）のため、RG 自体は [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) で手動作成した。Terraform 管理（作成・削除）にすると、`terraform destroy` が自分の権限スコープの器を消してしまい、以後の apply が権限エラーで不能になる。service principal は RG スコープの Contributor しか持たないため、そもそもサブスクリプションレベルの RG 作成権限がない
- **作り直す手順**: [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) の `az group create` 1 コマンド + #7 のロール割当の再作成
- **確認コマンド**:

  ```bash
  az group show -n rg-felisaichatbot-dev-tf --query '{name:name, location:location, state:properties.provisioningState}' -o json
  az resource list -g rg-felisaichatbot-dev-tf -o table   # 初回 apply 前は空のはず（apply 後は PostgreSQL 等が入る）
  ```

- **固有のリスク・注意**: 消すと中の Terraform 管理リソース（Day 3 以降の PostgreSQL 等）とロール割当（#7 の Contributor）が一緒に消え、tfstate だけが「実在しないリソースの記録」として残る（state と実物の乖離）。Terraform 側は `data "azurerm_resource_group"` で参照しており、RG が無いと plan の時点で失敗する

## 4. Resource group `rg-felisaichatbot-tfstate`

- **なぜ管理外か**: 鶏と卵。Terraform backend が使う Storage（#5）の器であり、Terraform より先に存在しなければならない（[bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h)）。環境をまたいで共有し、dev の destroy でも消えない persistent / ephemeral 分離の一貫として、名前に `<env>` を付けていない（[ADR-0013](../adr/0013-azure-resource-naming-convention.md)）
- **作り直す手順**: [bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h) の手順 1（`az group create`）。ただし作り直し＝tfstate の喪失を意味する（#5 参照）
- **確認コマンド**:

  ```bash
  az group show -n rg-felisaichatbot-tfstate --query '{name:name, location:location, state:properties.provisioningState}' -o json
  ```

- **固有のリスク・注意**: 消すと tfstate（#5）ごと消える。apply 後にこれをやると、全 Terraform 管理リソースが「実物はあるのに state がない」孤児になる

## 5. Storage Account `felisaichatbottfstate` + container `tfstate`

| 項目 | あるべき値 |
| --- | --- |
| 名前 / 種類 | `felisaichatbottfstate` / Microsoft.Storage/storageAccounts（Standard_LRS） |
| 場所 | RG `rg-felisaichatbot-tfstate` / japaneast |
| 設定 | `minimumTlsVersion: TLS1_2` / `allowBlobPublicAccess: false` / blob versioning 有効 |
| container | `tfstate`（key `persistent/terraform.tfstate` 等で層を区別） |

- **なぜ管理外か**: 鶏と卵。Terraform backend の state 置き場を Terraform で作ることはできないため、[bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h) で 1 回だけ手動作成した（terraform-hannibal が S3 state bucket で採った方式と同型）
- **作り直す手順**: [bootstrap.md §12](./bootstrap.md#12-tfstate-用-storage-account-の手動作成05h)（Storage Account 作成 → 実行者自身への Storage Blob Data Contributor 割当 → 反映待ちリトライで container 作成 → versioning 有効化、の 4 手順。データプレーン権限の罠と出典は同節に記載）
- **確認コマンド**:

  ```bash
  az storage account show -n felisaichatbottfstate -g rg-felisaichatbot-tfstate \
    --query '{name:name, sku:sku.name, minTls:minimumTlsVersion, publicBlobAccess:allowBlobPublicAccess}' -o json
  az storage account blob-service-properties show --account-name felisaichatbottfstate \
    --resource-group rg-felisaichatbot-tfstate --query isVersioningEnabled   # true のはず
  az storage container list --account-name felisaichatbottfstate --auth-mode login --query "[].name" -o tsv   # tfstate のはず
  ```

- **固有のリスク・注意**: apply 後の tfstate には sensitive 値（PostgreSQL 管理者パスワード等）が平文で入る（出典: <https://developer.hashicorp.com/terraform/language/manage-sensitive-data>）。アクセスできる主体は実行者本人と CI 用 service principal（#7）に限定してある。state の誤削除・破損への備えは blob versioning（S3 の versioning 相当）。接続文字列・アクセスキーは使わない（`use_azuread_auth = true`）し、本台帳にも書かない

## 6. Entra ID アプリ登録 `felis-ai-chatbot-github-actions` + federated credential

| 項目 | あるべき値 |
| --- | --- |
| 名前 / 種類 | `felis-ai-chatbot-github-actions` / Entra ID アプリ登録 + service principal |
| appId | `3a79df61-4c85-4f92-9368-1ca8588a1d17` |
| SP object id | `a428458b-fd66-4cb3-b25d-fc1c360f7f37` |
| federated credential | `github-actions-main` の **1 本のみ**。subject `repo:kmryst@205493351/felis-ai-chatbot@1336699843:ref:refs/heads/main` |

- **なぜ管理外か**: 鶏と卵 + 権限が壊れる。GitHub Actions の Terraform 実行主体そのものであり、これを Terraform 管理にすると destroy が自分の認証手段を消す。また azurerm provider の管理対象（ARM）ではなく Entra ID（Microsoft Graph）側のオブジェクトで、管理するなら azuread provider の追加が必要になる。PR 用 credential を意図的に登録していない判断は [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)
- **作り直す手順**: [bootstrap.md §11-1 / §11-2](./bootstrap.md#11-entra-id-アプリ登録--federated-credential--ロール割当1h)（アプリ登録 → SP 作成 → immutable subject 形式での federated credential 登録。subject の実測値・形式の罠は同節に記載）。appId は再作成で変わるため、再作成したら #7 のロール割当もやり直し、本台帳の appId / SP object id を更新する
- **確認コマンド**:

  ```bash
  az ad app show --id 3a79df61-4c85-4f92-9368-1ca8588a1d17 --query '{displayName:displayName, appId:appId}' -o json
  az ad app federated-credential list --id 3a79df61-4c85-4f92-9368-1ca8588a1d17 --query "[].{name:name, subject:subject}" -o json   # 1 本のみのはず
  az ad sp show --id 3a79df61-4c85-4f92-9368-1ca8588a1d17 --query '{objectId:id}' -o json
  ```

- **固有のリスク・注意**: credential が main 用 1 本より増えていたら、それは「誰かが権限経路を追加した」重大な差分（ADR-0012 の決定に反する）。appId / SP object id は識別子であり秘密ではない（secret レスの OIDC 構成のため、このアプリにクライアントシークレットは存在しないのが正常。`az ad app credential list --id <appId>` が空であること）

## 7. ロール割当 2 件（CI 用 service principal 向け）

| ロール | スコープ |
| --- | --- |
| `Contributor` | `rg-felisaichatbot-dev-tf`（#3） |
| `Storage Blob Data Contributor` | Storage Account `felisaichatbottfstate`（#5） |

- **なぜ管理外か**: 権限が壊れる。CI の Terraform がこの 2 件を前提に動くため、Terraform 管理にすると destroy が「state を読む権限」「リソースを作る権限」を自分で消す。また管理するには service principal に `Role Based Access Control Administrator` 相当が必要になり、[ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) で却下した権限昇格経路を開くことになる
- **作り直す手順**: [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) の `az role assignment create` ×2
- **確認コマンド**:

  ```bash
  az role assignment list --assignee 3a79df61-4c85-4f92-9368-1ca8588a1d17 --all \
    --query "[].{role:roleDefinitionName, scope:scope}" -o json   # 上表の 2 件のみのはず
  ```

- **固有のリスク・注意**: 2 件より**多い**のは権限昇格の兆候、**少ない**のは CI の apply / state アクセスが壊れる予兆。どちらも即調査する。付与しないと決めたもの（サブスクリプション Contributor / RBAC Administrator）は [bootstrap.md §11-3](./bootstrap.md#11-3-ロール割当least-privilege) と ADR-0012 に記録済み

## 8. User-assigned managed identity `id-felisaichatbot-dev`

| 項目 | あるべき値 |
| --- | --- |
| 名前 / 種類 | `id-felisaichatbot-dev` / Microsoft.ManagedIdentity/userAssignedIdentities |
| 場所 | RG `rg-felisaichatbot-dev-tf` / japaneast |
| 用途 | Container App `ca-felisaichatbot-dev` が ACR `felisaichatbotacrdev` から pull する際の認証主体（#9 の AcrPull を保持） |
| `principalId` | `6cbb5f58-c59c-42fa-ab51-997b57f56c5a`（2026-08-21 作成時に実測。識別子であり秘密ではない） |
| `clientId` | `6d8d587a-4dcd-4cec-8121-1928ad2a440d`（同上） |

- **なぜ管理外か**: 据え置き判断（[ADR-0015](../adr/0015-ephemeral-layer-acr-container-apps-design.md) 選択肢 6-(b)）。理由は 2 つ。(1) **寿命の分離**: ACR / Container Apps は毎日 destroy / apply される ephemeral 層だが、この ID と #9 の権限は 1 回作れば据え置く。寿命の違うものを同じ層に置くと毎朝の権限再払い出しが発生する。(2) **職務分掌**: アイデンティティと権限の払い出しは人が承認を経て行い、CI の自動実行主体（SP）には権限を配る力を持たせない（ADR-0012 と一貫）。なお Terraform 管理にしても、対になる #9 のロール割当は SP の権限では作れないため片手落ちになる
- **置き場が `rg-felisaichatbot-dev-tf` である理由**: CI 用 SP はこの RG への Contributor しか持たない（ADR-0012）。Terraform（ephemeral 層）が `data "azurerm_user_assigned_identity"` で ID を読み、Container App へ紐付ける（`Microsoft.ManagedIdentity/userAssignedIdentities/assign/action` が必要）には、ID が SP の権限スコープ内にあることが必須。別 RG に置くと CI の plan / apply が失敗する（ADR-0015 選択肢 6 の「付随する 2 つの設計値」）
- **作り直す手順**:

  ```bash
  az identity create \
    --name id-felisaichatbot-dev \
    --resource-group rg-felisaichatbot-dev-tf \
    --location japaneast
  ```

  再作成すると `principalId` が変わるため、**#9 のロール割当も必ず作り直す**（旧 principalId 宛ての割当は Unknown 主体の孤児になる。見つけたら削除する）

- **確認コマンド**:

  ```bash
  az identity show --name id-felisaichatbot-dev --resource-group rg-felisaichatbot-dev-tf \
    --query '{name:name, location:location, principalId:principalId, clientId:clientId}' -o json
  ```

- **固有のリスク・注意**:
  - `terraform destroy`（ephemeral 層）では消えない（state にないものは destroy の対象外）。ただし **`az group delete -n rg-felisaichatbot-dev-tf` は ID ごと消す**。また CI 用 SP は RG Contributor として技術的にはこの ID を削除**できてしまう**（Terraform の管理外なのでコード起因では起きないが、workflow の暴走・誤操作は構造上防げない。消えたら pull 失敗で検知し、上記手順で作り直す）
  - `principalId` / `clientId` は識別子であり秘密ではない。ID にはシークレットが存在しない（マネージド ID の利点そのもの）

## 9. AcrPull ロール割当（#8 → RG `rg-felisaichatbot-dev-tf`）

| 項目 | あるべき値 |
| --- | --- |
| ロール | `AcrPull`（actions は `Microsoft.ContainerRegistry/registries/pull/read` の 1 件のみ。`az role definition list --name AcrPull` 実測 2026-08-21） |
| assignee | #8 の `principalId` = `6cbb5f58-c59c-42fa-ab51-997b57f56c5a`（principal type: ServicePrincipal） |
| スコープ | RG `rg-felisaichatbot-dev-tf`（#3。**ACR 個体ではない**） |

2026-08-21 作成。作成直後に確認コマンドを実測し、**この ID への割当が AcrPull（RG スコープ）の 1 件のみ**であることを確認済み。

- **なぜ管理外か**: CI 用 SP は `Microsoft.Authorization/roleAssignments/write` を持たない（[ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) で RBAC Administrator を意図的に不付与）。Terraform に書くと CI からの apply が必ず権限エラーで失敗する。SP に権限を足す案（ADR-0015 選択肢 6-(c)）は権限昇格経路の新設として却下した。#7 と同じ「権限が壊れる」区分でもある: この割当が消えると Container App のイメージ pull が全部止まる
- **スコープが RG である理由**: ACR `felisaichatbotacrdev` は ephemeral 層で destroy / 再作成を繰り返す（当初は毎日、現在は最終 teardown まで常時稼働 = ADR-0020。いずれにせよマネージド ID より寿命が短い）。ACR 個体スコープの割当はリソース削除と同時に消え、毎朝の手動再作成が必要になる。**RG スコープなら ACR を作り直しても割当が生き残る**。AcrPull は pull 専用ロールのため、RG に広げても届く先は RG 内の ACR（現状 1 個）からの pull だけ（[ADR-0015](../adr/0015-ephemeral-layer-acr-container-apps-design.md) 選択肢 6）
- **作り直す手順**（#8 が存在する前提。`--assignee-object-id` + `--assignee-principal-type` は Microsoft Graph への問い合わせと伝搬遅延起因のエラーを避けるため）:

  ```bash
  PRINCIPAL_ID=$(az identity show --name id-felisaichatbot-dev \
    --resource-group rg-felisaichatbot-dev-tf --query principalId -o tsv)
  SCOPE=$(az group show --name rg-felisaichatbot-dev-tf --query id -o tsv)
  az role assignment create \
    --role AcrPull \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --scope "$SCOPE"
  ```

- **確認コマンド**:

  ```bash
  PRINCIPAL_ID=$(az identity show --name id-felisaichatbot-dev \
    --resource-group rg-felisaichatbot-dev-tf --query principalId -o tsv)
  az role assignment list --assignee "$PRINCIPAL_ID" --all \
    --query "[].{role:roleDefinitionName, scope:scope}" -o json   # AcrPull / RG rg-felisaichatbot-dev-tf の 1 件のみのはず
  ```

- **固有のリスク・注意**:
  - 確認結果が 1 件より**多い**のは「誰かがこの ID に権限を足した」兆候（この ID の職務は ACR pull だけ）。**少ない（0 件）** なら Container App の pull が壊れる予兆。どちらも即調査する
  - #8 を再作成した場合、この割当は旧 principalId 宛てのまま残り**効かない**（assignee が Unknown と表示される）。#8 の手順どおり割当も作り直し、孤児の割当は削除する

---

## 10. Action Group `ag-felisaichatbot-dev-email`

| 項目 | あるべき値 |
| --- | --- |
| resource ID | `/subscriptions/<sub>/resourceGroups/rg-felisaichatbot-dev-tf/providers/microsoft.insights/actionGroups/ag-felisaichatbot-dev-email` |
| short name | `felisdev`（アラートメールの件名に入る。12 文字以内の制約あり） |
| receiver | email `opsmail` → 本人のメールアドレス（`useCommonAlertSchema: true`） |
| enabled | `true` |
| location | `Global`（Action Group はリージョンを持たない） |

2026-08-27 作成（Issue #145）。#11 のアラート 5 件すべてがこの 1 件を宛先にしている。

- **管理区分**: **Terraform 管理下（persistent 層）**。当初は az CLI 手動作成の管理外（「PostgreSQL より寿命を長くしたい」判断）だったが、IaC の一貫性を優先して 2026-08-27 に `terraform import` で移行した（Issue #151 / [ADR-0022](../adr/0022-import-azure-monitor-into-terraform.md)。リソース ID 不変）。コードは `terraform/persistent/main.tf`、受信者アドレスは `TF_VAR_alert_email_address`（`.env`）で渡す
- **配送試験の制約**: `az monitor action-group test-notifications create` は CLI としては存在するが、本サブスクリプションでは API が `(Conflict) Free subscription not supported` を返して**実行できない**。配送の実証は #11 の実発火試験で代替した
- **作り直す手順**: persistent 層の `terraform apply`（`TF_VAR_alert_email_address` の設定が前提）。az CLI では作らない（Terraform 管理下のリソースを az で作ると import が再度必要になる）。なお作り直すとリソース ID は同じでも発火履歴は引き継がれない

- **確認コマンド**:

  ```bash
  az monitor action-group show -g rg-felisaichatbot-dev-tf -n ag-felisaichatbot-dev-email \
    --query "{enabled:enabled, short:groupShortName, receivers:emailReceivers[].{name:name, status:status}}" -o json
  ```

  `enabled: true` / receiver の `status: Enabled` が期待値。**`status` が `Disabled` になっていたら通知が飛ばない**（受信者が Azure のメール内リンクから配信停止した場合にこうなる）

- **固有のリスク・注意**:
  - Action Group を消すと #11 の 5 件は**アラート自体は発火し続けるが通知が飛ばない**（沈黙する監視になる）。消すなら 5 件と同時に消す
  - メール通知は月 1,000 通まで無料。それを超える量が飛ぶ状況は、閾値かワークロードのどちらかが壊れている兆候

---

## 11. メトリクスアラート 5 件（PostgreSQL 向け）

すべて scope は PostgreSQL `pgsql-felisaichatbot-dev`、action は #10、`autoMitigate: true`（条件が解消したら自動でクローズ）。

| 名前 | resource ID（RG `rg-felisaichatbot-dev-tf` / `providers/Microsoft.Insights/metricAlerts/` 配下） | メトリクス | 条件 | 集計 | window / freq | severity |
| --- | --- | --- | --- | --- | --- | --- |
| `alert-pgsql-storage-free-critical` | 同名 | `storage_free` | `< 6442450944`（6 GiB） | Minimum | PT5M / PT1M | 1 (Error) |
| `alert-pgsql-storage-free-low` | 同名 | `storage_free` | `< 10737418240`（10 GiB） | Minimum | PT15M / PT5M | 2 (Warning) |
| `alert-pgsql-is-db-alive` | 同名 | `is_db_alive` | `< 1` | Minimum | PT5M / PT1M | 0 (Critical) |
| `alert-pgsql-cpu-credits-remaining-low` | 同名 | `cpu_credits_remaining` | `< 30` | Minimum | PT15M / PT5M | 2 (Warning) |
| `alert-pgsql-storage-percent-80` | 同名 | `storage_percent` | `>= 80` | Average | PT15M / PT5M | **3 (Informational)** |

2026-08-27 作成。`is_db_alive` / `cpu_credits_remaining` / `storage_percent` の 3 件は Issue #145、
`storage_free` 系 2 件は Issue #148。メトリクス名は 5 件とも `az monitor metrics list-definitions` で
実在と unit を確認してから使った（推測ではない）。

**管理区分は Terraform 管理下（persistent 層）**: az CLI 作成分を 2026-08-27 に `terraform import` で
移行した（Issue #151 / [ADR-0022](../adr/0022-import-azure-monitor-into-terraform.md)）。**リソース ID は
不変**のため、2026-08-27T05:17:38Z の実発火試験の証跡は移行後も有効。コードは
`terraform/persistent/main.tf`。移行時の追随 apply（メタデータのみ）で条件の内部名は
`cond0` → `Metric1` に変わったが、閾値・severity・条件・window / freq は不変（ADR-0022 に実測記録）。

| メトリクス | unit | 定義上の集計 |
| --- | --- | --- |
| `storage_free` | **Bytes** | Average / Maximum / Minimum |
| `storage_used` | Bytes | Average / Maximum / Minimum |
| `storage_percent` | Percent | Average / Maximum / Minimum |
| `txlogs_storage_used` | Bytes | Average / Maximum / Minimum |
| `is_db_alive` | Count | Average / Maximum / Minimum |
| `cpu_credits_remaining` | Count | Average / Maximum / Minimum |

### ストレージ監視の主計器は `storage_free`（絶対値）である

**Azure が read-only へ落とす条件は「割合 または 絶対値」の OR** である（公式・逐語）。

> The server automatically switches to read-only mode when the storage usage reaches 95 percent,
> or when the available capacity is less than 5 GiB.
> — <https://learn.microsoft.com/en-us/azure/postgresql/compute-storage/concepts-storage> 「Disk full conditions」

本サーバーの実測（2026-08-27T05:17Z、`az monitor metrics list`）は次のとおりで、
**`storage_percent` の分母は provision した 32 GiB ではない**。

```text
storage_used  4,399,088,708 B = 4.10 GiB
storage_free 29,102,668,731 B = 27.10 GiB
合計                            31.20 GiB   ← これが分母
4.10 / 31.20 = 13.14%                       ← storage_percent 実測 13.1309% と一致
```

| 状態 | 空き | storage_percent |
| --- | --- | --- |
| 現在（2026-08-27） | 27.10 GiB | 13.13% |
| `alert-pgsql-storage-free-low`（Sev2） | 10.00 GiB | 67.95% |
| `alert-pgsql-storage-percent-80`（Sev3） | 6.24 GiB | 80.00% |
| `alert-pgsql-storage-free-critical`（Sev1） | 6.00 GiB | 80.77% |
| **read-only 転落（空き 5 GiB 未満）** | 5.00 GiB | **83.97%** |
| 95% 条件 | 1.56 GiB | 95.00% |

**この構成では 95% 条件は永久に発動しない**（先に空き 5 GiB 条件に当たる）。
つまり `storage_percent >= 95` 系のルールは存在しない破断点を指す。
そのため主計器を**破断条件と同じ単位（バイト）の `storage_free`** に切り替えた。理由は 3 点。

1. **計器の単位を破断条件の単位に合わせる**。read-only の条件は絶対値で定義されている
2. 分母 31.20 GiB が非自明なので、percent 値からは「あと何 GiB 書けるか」が読み取れない
3. **tier を General Purpose へ変更する予定**があり、構成が変わると percent 閾値は黙って意味が変わる。
   絶対値の閾値は構成変更に対して意味が変わらない（read-only 条件の 5 GiB が変わらないため）

なお #145 で本節に書いた「32 GiB では空き 5 GiB = 84.375%」という記述は**分母を 32 GiB と誤ったもの**で、
実測に基づく正しい値は上表の **83.97%** である（差は小さいが、分母を実測で確定させたのが Issue #148 の出発点）。

### 2 段構えにしている理由

Rob Ewaschuk "My Philosophy on Alerting"（page 用の厳しい条件と、ticket / レポート用の緩い条件を分ける）に倣い、
同じ故障モード（ストレージ枯渇）に対して**severity の違う 2 本**を張っている。

- **Sev2 `alert-pgsql-storage-free-low`（空き 10 GiB）** = ticket。read-only まで **まだ 5 GiB** ある段階で気づく。
  この時点なら「不要データの削除」「storage のスケールアップ」「実験の中断」のどれでも間に合う
- **Sev1 `alert-pgsql-storage-free-critical`（空き 6 GiB）** = page。read-only まで **あと 1 GiB**。至急対応

### 閾値の根拠

- **`storage_free < 10 GiB` / `< 6 GiB`（新設 2 件）**:
  **この 10 GiB / 6 GiB という値そのものには一次情報の出典がない。設計値であり暫定値である。**
  一次情報があるのは read-only 転落の **5 GiB** だけで、そこから「余裕 5 GiB」「余裕 1 GiB」と逆算した。
  **見直しの条件: フェーズ 2（高負荷）で単位時間あたりのストレージ消費速度を実測すること。**
  消費速度が分かって初めて「この余裕が何分の猶予に相当するか」が言えるようになり、
  そこで初めて 10 / 6 が妥当かを判断できる。それまでは根拠のある数字として扱わない
- **`storage_percent >= 80`（既存・Sev3 へ格下げ）**: 上表のとおり空き 6.24 GiB に相当し、
  新設 2 件の間に挟まる。**冗長だが削除していない**（下記「格下げの理由」）
- **`is_db_alive < 1`**: 値は生存 = 1 / 不通 = 0 の 2 値。`< 1` は「1 でない」と同義
- **`cpu_credits_remaining < 30`**: B1ms は Burstable。2026-08-27 に 12 時間分を実測したところ **313 で一定**
  （`cpu_credits_consumed` は全区間 0 = 完全にアイドル）。この 313 を満充電時の定常値とみなし、
  その約 10% を残枠切れの手前として 30 とした。**負荷実験で実際の消費速度を観測したら見直す暫定値である**

### `alert-pgsql-storage-percent-80` を「削除せず格下げ」した理由

- **削除しない**: 2026-08-27T05:17:38Z の実発火 → 05:32:44Z 自動解消（受信確認済み）という
  **通知経路の実証記録がこのルールに紐づいている**。ルールを消すと証跡の対象が消える
- **Sev1 → Sev3 に下げる**: 同じ故障モードに page 級のルールが 2 本ある状態は、片方が
  「先に鳴るがより意味の薄いほう」になる。percent は上記のとおり分母が非自明で、tier 変更で黙って意味が変わる。
  Ewaschuk の言う「percent 単独のルールはレポートに格下げする」に倣い、**日次レポート級の Sev3** とした。
  ストレージ枯渇で人を叩き起こす役は `alert-pgsql-storage-free-critical`（Sev1）が持つ
- Azure 側の `description` にも格下げの事実と理由を書いてある（`az monitor metrics alert show` で読める）

### `txlogs_storage_used` を「今は監視しない」と判断した理由

**メトリクスは実在する**（unit Bytes / Average・Maximum・Minimum）。2026-08-27 の実測値は
**469,762,048 B = 448 MiB で、観測区間を通じて一定**（アイドルのため）。**アラートは作っていない。**

判断の根拠:

1. **WAL は同じ provision 済みストレージを食う**ので、WAL の増加は `storage_free` の減少として
   既に新設 2 件に映る。公式・逐語:
   > This storage holds database files, temporary files, transaction logs, and PostgreSQL server logs.
   > — <https://learn.microsoft.com/en-us/azure/postgresql/compute-storage/concepts-storage>

   read-only 転落の条件は「available capacity」で定義されており、それを直接測るのが `storage_free` である。
   **消費者が WAL か heap かは転落条件に関係しない**ので、枯渇そのものの検知に別ルールは要らない
2. **autogrow の FAQ はこのサーバーには当たらない。** 公式・逐語:
   > Storage autogrow isn't triggered when you have high WAL usage.
   > — <https://learn.microsoft.com/en-us/azure/postgresql/compute-storage/concepts-storage-premium-ssd>
   > （「Limitations and considerations of storage autogrow」節）

   これは「autogrow を有効にしていても WAL 起因の逼迫では自動拡張が助けてくれない」という警告である。
   本サーバーは `storage.autoGrow` が **Disabled**（実測）なので、そもそも当てにしている自動拡張がない。
   **この FAQ は今アラートを増やす理由にはならない**
3. **閾値を置く根拠が今はない。** フェーズ 2（高負荷）が後回しになったため、
   アイドル時の 448 MiB 一定という値しか持っていない。ここから閾値を決めても設計値ですらない当てずっぽうになる。
   ルールを増やせばルール単位の月額課金とアラート疲れのコストだけが確実に増える

**いつ作るか: フェーズ 2（高負荷）を開始する前。** 開始前に WAL の増加速度を実測し、
「`txlogs_storage_used` が `storage_used` のうちどれだけを占めるか」を測った上で閾値を決める。
**`storage.autoGrow` を Enabled にする場合、または tier を General Purpose へ変更する場合も、
上記 2 の前提が変わるので同時に再判断する。**

### 評価頻度・ウィンドウの根拠

| アラート | window / freq | 集計 | 理由 |
| --- | --- | --- | --- |
| `alert-pgsql-storage-free-low` | PT15M / PT5M | Minimum | 既存 `storage_percent` / `cpu_credits_remaining` と同じ刻み。ticket 級なので検知遅れ 5 分で十分 |
| `alert-pgsql-storage-free-critical` | PT5M / PT1M | Minimum | page 級。read-only まで 1 GiB しかない段階なので、`is_db_alive` と同じ最短の刻みにして検知遅れを 1 分に詰める |
| `alert-pgsql-storage-percent-80` / `cpu_credits_remaining` | PT15M / PT5M | Average / Minimum | 単発サンプルのノイズで誤検知しないよう 15 分で集計。評価頻度 5 分は検知遅れの上限を 5 分に抑えるため |
| `alert-pgsql-is-db-alive` | PT5M / PT1M | Minimum | 死活は最速で拾いたいので評価頻度は最短の 1 分。ウィンドウを 5 分にしたのは、このメトリクスに欠測区間が出ることがあり 1 分窓だと窓内にデータが無く評価スキップになりうるため |

**`storage_free` の集計に `Minimum` を選んだ理由**: 見たいのは「窓のあいだで空きが最も少なかった瞬間」である。
read-only への転落は瞬間値で決まるので、`Average` にすると窓内の一時的な落ち込みが平均に埋もれる。
`storage_free` はディスクのゲージ値でスパイク性のノイズを持たないため、`Minimum` にしても誤検知は増えない。

### 作り直す手順

persistent 層の `terraform apply` で 5 件とも再作成される（`TF_VAR_alert_email_address` の設定が前提。
Issue #151 / ADR-0022）。az CLI では作らない。閾値・severity を書き換えるときも
`terraform/persistent/main.tf` を編集して PR → apply で行う（az での直接変更は Terraform とのドリフトになる）。

### 確認コマンド

```bash
az monitor metrics alert list -g rg-felisaichatbot-dev-tf -o json \
  | python3 -c "
import json,sys
for a in sorted(json.load(sys.stdin), key=lambda x: x['name']):
    c=a['criteria']['allOf'][0]
    print(a['name'], a['enabled'], 'sev'+str(a['severity']), c['metricName'], c['operator'], c['threshold'], c['timeAggregation'], a['windowSize'], a['evaluationFrequency'])
"
```

**期待値は上の表のとおり 5 行**。とくに次の 3 点を見る（試験のために一時的に閾値を動かす運用があるため）。

- `threshold` が **10737418240 / 6442450944 / 80 / 1 / 30**
- `storage_free` 系 2 件の `timeAggregation` が **Minimum**（`Average` になっていたら誤り）
- `alert-pgsql-storage-percent-80` の severity が **3**（1 に戻っていたら誤り）

### 固有のリスク・注意

- **閾値を一時的に動かして発火試験をしたら、必ず戻す。** `storage_free` 系は `LessThan` なので、
  試験では閾値を**現在値より大きく**して発火させる（#145 の percent / cpu credits は逆に下げて発火させた）。
  戻し忘れると誤検知が続き、やがてメールを無視するようになる（アラート疲れ）。
  試験のたびに上の確認コマンドで戻ったことを確認する
- **10 GiB / 6 GiB は一次情報のない設計値（暫定）である。** フェーズ 2 でストレージ消費速度を実測するまで、
  この 2 つの数字を「検証済みの値」として扱わない
- **`txlogs_storage_used` のアラートは未作成。** フェーズ 2 開始前に作る（上記の判断節）
- **`is_db_alive` は 2026-08-28 の HA ドリルで実発火・自動 Resolve を確認した**（実測:
  [failover-drill/observations.md §9](../verification/failover-drill/observations.md)）。
  ドリルの tier 変更（B1ms ⇄ GeneralPurpose）で意図せず 2 回発火し、いずれも自動 Resolve まで一巡した。
  **これで本節の 5 件すべてが実発火試験済みになった**（従来は本件のみ「安全に発火させられないため未試験」だった）

  | 契機 | downtime | fired | resolved |
  | --- | --- | --- | --- |
  | tier 昇格（B1ms → GP） | 5 分 30 秒 | 2026-08-28T08:33:28.842Z | 08:36:33.746Z |
  | tier 復帰（GP → B1ms） | 7 分 10 秒 | 2026-08-28T10:19:28.077Z | 10:24:32.446Z |

- **ただし 30 秒程度の failover では発火しない。** 同ドリルの planned failover（23.9 秒）と
  forced failover（30.4 秒）では**沈黙した**。原因は **`is_db_alive` の入力が 1 分粒度**であることで、
  failover 前後の 1 分バケットはすべて 1.0 のまま（0 に落ちたバケットが存在しない）だった。
  **これは window / 閾値 / 集計の設定ミスではなく、入力メトリクスの分解能の問題である。**
  window を PT1M に縮めても評価頻度を上げても発火しない。**1 分より短い断は、このメトリクスでは
  原理的に検知できない**（短い断を捕まえたいなら、より細かい粒度を持つ外形監視側の役目になる）
- **検知遅延の実測（発火した 2 回）**: 最初の 0 バケット → fired が **約 6 分 30 秒**、
  復旧 → resolved が **約 5 分 10 秒**。tier 復帰では **アラートが鳴った 13.5 秒前に既にサービスは復旧していた**。
  **5〜7 分級の断に対して本アラートは事後通知になる。** 役割は「短い断の即時検知」ではなく
  「継続的な死亡の検知」と読む
- scope の PostgreSQL を destroy すると、アラートは scope が消えた状態で残る。
  「プロジェクト終了時の後片付け」節のとおり **PostgreSQL より先に消す**
- **tier を General Purpose へ変更したら本節を見直す。** 絶対値の閾値（read-only の 5 GiB）は変わらないが、
  ストレージサイズが変われば「10 GiB の余裕が何時間分か」は変わる。
  `storage_percent` 側の意味（分母）も同時に変わる。
  **なお 2026-08-28 の HA ドリルで tier を B1ms → GeneralPurpose → B1ms と往復させた際、
  `storage` は全工程を通じて 32 のままだった**（実測:
  [failover-drill/observations.md §1](../verification/failover-drill/observations.md)）。
  **tier 変更それ自体はストレージサイズを変えない**ので、tier だけを動かす限り本節の見直しは不要である

---

## 関連

- [ADR-0009](../adr/0009-azure-openai-as-llm-provider.md) — Azure OpenAI 採用と手動作成の経緯
- [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — SP 最小権限・RG 分離（#3 / #6 / #7 の設計判断）
- [ADR-0013](../adr/0013-azure-resource-naming-convention.md) — 命名規則と Azure OpenAI の改名しない例外
- [ADR-0014](../adr/0014-keep-azure-openai-out-of-terraform.md) — Azure OpenAI を Terraform 管理外に据え置く判断（#1 の正本）
- [ADR-0015](../adr/0015-ephemeral-layer-acr-container-apps-design.md) — ACR pull 認証方式（#8 / #9 の正本。選択肢 6）
- [bootstrap.md](./bootstrap.md) §2 / §11 / §12 — 各リソースの作成手順の正本
- [day3-5-execution-plan.md](./day3-5-execution-plan.md) §8 — コスト見張り（クレジット残の確認手段の実測）。全消し手順は本書「プロジェクト終了時の後片付け」節へ移した（`az group delete` ×3 は廃止）
- [ADR-0016](../adr/0016-log-analytics-workspace-in-persistent-layer.md) — Log Analytics を persistent 層に置く判断
- [ADR-0017](../adr/0017-no-nightly-stop-for-postgresql.md) — PostgreSQL を夜間 stop しない判断（無料枠の判明）
