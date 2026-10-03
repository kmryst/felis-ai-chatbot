# Key Vault 参照化で増えた費用の 7 日間実測（Issue #286 PR 4）

- 目的: [ADR-0032](../../adr/0032-key-vault-references-for-container-apps-secrets.md)「影響」の「Key Vault Standard の操作数、log search alert 1 件、`AuditEvent` の取り込み。7 日間の実測から月額を推定して記録する（PR 4）」を満たし、[台帳 §A](../../operations/azure-resource-inventory.md) の Key Vault 行の「未実測」を実測値に置き換える
- 計測の起点: **2026-10-03 06:30Z**（Easy Auth のクライアントシークレットが Key Vault 参照になり、すべての secret が Key Vault 参照になった時点。[observations.md](./observations.md) PR 3 の節）。期間は 7 日
- サブスクリプション ID は `<sub>` と書く。費用の生データは日ごとの数量と金額だけを書き、契約情報は書かない。すべて読み取りのみ（Azure への書き込みなし）

## 1. 対象の費用と料金の根拠

Key Vault 参照化で増えたのは次の 3 つ。いずれも Azure Retail Prices API（`https://prices.azure.com/api/retail/prices`。公式の料金データ。2026-10-03 取得）で単価を確認した。
料金ページ（[Key Vault](https://azure.microsoft.com/en-us/pricing/details/key-vault/) / [Azure Monitor](https://azure.microsoft.com/en-us/pricing/details/monitor/)）の価格表は JavaScript で描画され、取得したテキストでは金額が `$-` のため、数値は Retail Prices API を根拠にする。

| # | 費用 | `usageDetails` のメーター（`meterCategory` / `meterName`） | 単価（japaneast、Consumption、USD） | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | Key Vault の操作（Container Apps の 30 分ごとの同期 = `SecretGet`、人の操作、Terraform の refresh） | `Key Vault` / `Operations`（単位 `10K`） | **0.03 USD / 10,000 操作** | Retail Prices API `serviceName eq 'Key Vault' and armRegionName eq 'japaneast'`。料金ページの注記 "Every successfully authenticated REST API call counts as one operation."（認証に成功した REST API 呼び出し 1 回を 1 操作として数える） |
| 2 | 診断設定 `diag-kv-felisaichatbot-dev` の `AuditEvent` の Log Analytics 取り込み | `Log Analytics` / `Analytics Logs Data Ingestion`（単位 `1 GB`） | **3.34 USD / GB**（Pay-As-You-Go。同 API に 0 USD の行もあり = 無料枠分） | Retail Prices API `serviceName eq 'Log Analytics' and armRegionName eq 'japaneast'`。料金ページ "The first 5 GB/month per billing account in this tier are free."（この tier では請求アカウントごとに月 5 GB まで無料） |
| 3 | log search alert `alert-kv-secret-sync-failed`（評価 15 分、dimension `ContainerAppName_s`） | `Azure Monitor` / `Alerts System Log Monitored at 15 Minute Frequency`（単位 `1/Month`）と、発火時に dimension ごとに付く `Alerts Resource Monitored at 15 Minute Frequency` | **0.5 USD / ルール / 月** と **0.05 USD / 監視リソース / 月** | Retail Prices API `serviceName eq 'Azure Monitor' and armRegionName eq 'Global'`。Microsoft Learn [alerts-overview](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview): "Log search alert rules that use splitting by dimensions are charged based on the number of time series created by the dimensions resulting from your query."（dimension で分割する log search alert は、クエリの dimension が生む時系列の数で課金される） |

含めないもの: メトリクスアラート 5 件（`Alerts Metric Monitored`。Retail Prices API では最初の 10 時系列が 0 USD。Key Vault 参照化の前からある）、Action Group のメール / push 通知（月 1,000 通まで 0 USD。#296 の対象）、
`ContainerAppSystemLogs_CL` の取り込み（Container Apps 環境が元から送っている。`SyncingSecret*` の行はその一部だが、Key Vault 参照化による増分は 30 分ごとに数行で、分離して測る意味が無い）。

## 2. 計測の方法

### 2-1. Cost Management の usageDetails（費用 1・3 と、費用 2 の課金側）

```bash
# 読み取りのみ。Consumption API の usageDetails は既定で「現在の請求期間」（月初から）を返す。
# 計測期間 2026-10-03〜10-10 は 10 月の請求期間に収まる
SUB=$(az account show --query id -o tsv)
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/usageDetails?api-version=2023-05-01&\$filter=properties/usageStart ge '2026-10-01T00:00:00Z'&\$top=1000" \
  --query "value[?properties.meterCategory=='Key Vault' || properties.meterCategory=='Log Analytics' || (properties.meterCategory=='Azure Monitor' && contains(properties.meterName, 'Minute Frequency'))].{d:properties.date, cat:properties.meterCategory, meter:properties.meterName, unit:properties.unitOfMeasure, qty:properties.quantity, cost:properties.costInBillingCurrency, cur:properties.billingCurrencyCode, usd:properties.costInPricingCurrency}" -o json \
  | python3 -c '
import json, sys
from collections import defaultdict
agg = defaultdict(lambda: [0.0, 0.0, 0.0, "", ""])
for r in json.load(sys.stdin):
    k = (r["d"][:10], r["cat"], r["meter"])
    a = agg[k]; a[0] += float(r["qty"] or 0); a[1] += float(r["cost"] or 0); a[2] += float(r["usd"] or 0); a[3] = r["cur"]; a[4] = r["unit"]
print("date | category | meter | unit | quantity | cost (billing currency) | cost (USD)")
for k in sorted(agg):
    a = agg[k]; print(k[0], "|", k[1], "|", k[2], "|", a[4], "|", round(a[0], 4), "|", round(a[1], 4), a[3], "|", round(a[2], 6))
'
```

- `costInBillingCurrency` は請求通貨（JPY）、`costInPricingCurrency` は価格通貨（USD）。月額の見積もりは USD の単価 × 数量で行い、JPY は参考に並記する
- 反映の遅れ: Microsoft Learn [Understand Cost Management data](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data):
  "For EA and MCA subscriptions, cost and usage data is typically available in Cost Management within 8-24 hours. For pay-as-you-go subscriptions, it could take up to 72 hours for cost and usage data to become available."
  （EA / MCA では通常 8〜24 時間以内、pay-as-you-go 系では最長 72 時間で利用可能になる）。
  "Estimated charges for the current billing period are updated six times per day."（当月の見込み料金は 1 日 6 回更新される）。
  "During the open month (uninvoiced) period, Cost Management data should be considered as estimated only."（請求書の出る前の月のデータは見込み値として扱う）
- 1 日の数量が確定するのは、その日の終わりから最長 72 時間後。**最終日の値は 2026-10-13 以降に読む**

### 2-2. Log Analytics の取り込み量（費用 2 の実測側。Key Vault 分だけを分離できる）

```bash
WS=$(az monitor log-analytics workspace show -g rg-felisaichatbot-dev-tf -n log-felisaichatbot-dev --query customerId -o tsv)
# Key Vault の AuditEvent（AzureDiagnostics テーブル）の日ごとの行数と課金バイト数
az monitor log-analytics query -w "$WS" --analytics-query '
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT" and TimeGenerated >= datetime(2026-10-03)
| summarize rows = count(), billed_MB = round(sum(_BilledSize) / 1024.0 / 1024.0, 4) by day = bin(TimeGenerated, 1d)
| order by day asc' -o table
# 操作の内訳（同期 = SecretGet、人の操作 = SecretSet / SecretList など）
az monitor log-analytics query -w "$WS" --analytics-query '
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT" and TimeGenerated >= datetime(2026-10-03)
| summarize n = count() by day = bin(TimeGenerated, 1d), OperationName
| order by day asc, n desc' -o table
```

- `_BilledSize` の定義（Microsoft Learn [Standard columns](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-standard-columns)）:
  "The `_BilledSize` column specifies the size in bytes of data that's billed to your Azure account if `_IsBillable` is true."
  （`_IsBillable` が true のとき、Azure アカウントに課金されるデータのサイズをバイトで示す）
- workspace は `PerGB2018`（Pay-As-You-Go）、保持 30 日、日次上限 1 GB。`Usage` テーブルの `AzureDiagnostics` 行は Key Vault 以外の診断設定が無いため Key Vault 分と一致する（2026-10-03 時点で両者の日次値は 0.1 MB 前後で一致）

### 2-3. 定常でない期間の扱い

| 期間・事象 | 扱い |
| --- | --- |
| 2026-10-01 の同期失敗アラートの発火試験 2 回（ops app のテスト用 secret。Key Vault 操作と `AuditEvent` が増え、`Alerts Resource Monitored at 15 Minute Frequency` が付いた） | 計測期間の**前**なので含めない。参考として 10-01〜10-02 の値を「事前確認」に残す |
| 2026-10-03 06:21〜06:40Z の PR 3 の切替作業（secret の投入・確認・削除で `SecretSet` / `SecretGet` / `SecretList` 等が十数回） | 10-03 は部分日（06:30Z 以降が計測対象）かつ作業日なので**参考値**とし、月額の見積もりは 10-04〜10-10 の 7 日分（丸 1 日 × 7）で行う |
| 計測期間中に人が Key Vault を操作した日（Terraform の plan / apply による `azurerm_key_vault_secret` の refresh、`az keyvault secret show` 等） | 操作内訳（2-2 の 2 つ目のクエリ）で `SecretGet` 以外の操作数を数え、日ごとの表の注記に書く。見積もりからは外さない（運用で起きる操作として月額に含める） |
| アラートの発火（計測期間中に起きた場合） | `Alerts Resource Monitored` の数量が増える。発火が無い月はこの項目は 0 なので、「発火なしの月額」と「発火 1 回あたりの増分」を分けて書く |

## 3. 事前確認（2026-10-03 08:5xZ 実施。読み取りのみ）

| 確認 | 結果 |
| --- | --- |
| `usageDetails` で取れる最新の日 | 2026-10-03（当日分が部分的に出ている。10-01 以降の 3 日分が返る。9 月分は既定の請求期間の外） |
| `Key Vault / Operations` | 10-01: 0.0204 × 10K = 204 操作（発火試験の日）/ 10-02: 0.0102 = 102 操作 / 10-03（部分）: 0.006 = 60 操作。単価 `effectivePrice` 0.03 USD。`costInPricingCurrency` は 10-03 で 0.00018 USD、`costInBillingCurrency` 0.028 JPY |
| `Azure Monitor / Alerts System Log Monitored at 15 Minute Frequency` | 毎日 0.0323（= 1 ルール × 1/31 月）、約 2.5 JPY / 日。10-03 は 0.0108（部分） |
| `Azure Monitor / Alerts Resource Monitored at 15 Minute Frequency` | 10-01 のみ 0.0054（発火試験で dimension `ca-felisaichatbot-dev-ops` の時系列ができた分）。10-02 以降は無し |
| `Log Analytics / Analytics Logs Data Ingestion` | 10-01: 0.0102 GB / 10-02: 0.0094 GB / 10-03（部分）: 0.0034 GB、いずれも cost 0（workspace 全体。無料枠内）。Key Vault 分は下の KQL で分離する |
| KQL: `AuditEvent` の日次課金バイト数 | 09-28（chat API キーの参照開始）以降は 0.087〜0.099 MB / 日、行数 94〜107。10-01（発火試験）だけ 0.23 MB / 256 行。`Usage` テーブルの `AzureDiagnostics` 日次値（0.0875〜0.105 MB）と一致 |
| KQL: 直近 7 日の操作内訳 | `SecretGet` 650（同期）、`Authentication` 56、`VaultGet` 24（Terraform の data source の refresh）、`SecretList*` 22、`SecretSet` 5、`SecretUpdate` 4、`SecretDelete` 2、`SecretPurge` 2 |

事前確認からの見込み（実測で置き換える）: Key Vault 操作は平常日 約 100 操作 / 日（2 app × 48 回 / 日の同期 ≈ 96 + 人の操作）→ 月 約 3,000 操作 ≈ **0.01 USD / 月**。
`AuditEvent` は 約 0.1 MB / 日 → 月 約 3 MB ≈ 0.01 USD（無料枠 5 GB の内側なので実請求 0）。log search alert は **0.5 USD / 月**（固定）。合計 **約 0.52 USD / 月**（発火なし）。
Easy Auth secret の参照が加わった 10-03 以降は同期が 3 secret 分（frontend に 2、serving に 1）になるため、操作数は 約 150 / 日 に増える見込み。

## 4. 結果（計測期間 2026-10-03 06:30Z 〜 2026-10-10 06:30Z。数値は確定後に記入）

### 4-1. 日ごとの値

| 日 (UTC) | Key Vault 操作数（`Operations` × 10,000） | 同期 `SecretGet` 行数 | 人の操作数（`SecretGet` 以外） | `AuditEvent` 課金 MB | log search alert（ルール・月の按分） | `Alerts Resource Monitored`（発火分） | 備考 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-03（部分日・参考） |  |  |  |  |  |  | PR 3 の切替作業 06:21〜06:40Z |
| 2026-10-04 |  |  |  |  |  |  |  |
| 2026-10-05 |  |  |  |  |  |  |  |
| 2026-10-06 |  |  |  |  |  |  |  |
| 2026-10-07 |  |  |  |  |  |  |  |
| 2026-10-08 |  |  |  |  |  |  |  |
| 2026-10-09 |  |  |  |  |  |  |  |
| 2026-10-10 |  |  |  |  |  |  |  |
| 7 日合計（10-04〜10-10） |  |  |  |  |  |  |  |
| 1 日平均 |  |  |  |  |  |  |  |

### 4-2. 月額の見積もり（30 日換算。USD。JPY は `costInBillingCurrency` の合計を参考に併記）

| 費用 | 7 日実測 | 月換算（× 30 / 7） | 単価 | 月額 (USD) | 備考 |
| --- | --- | --- | --- | --- | --- |
| Key Vault 操作 |  操作 |  操作 | 0.03 USD / 10K |  |  |
| `AuditEvent` 取り込み |  MB |  MB | 3.34 USD / GB |  | 無料枠 5 GB / 月の内側なら実請求 0 |
| log search alert（発火なし） | — | 1 ルール | 0.5 USD / 月 | 0.50 |  |
| 発火 1 回あたりの増分 | — | 1 監視リソース・月 | 0.05 USD / 月 | 0.05 |  |
| **合計（発火なし）** |  |  |  |  |  |

### 4-3. 読み取りの日程

| 日 | 読むもの | 理由 |
| --- | --- | --- |
| 2026-10-07 | 10-04〜10-06 の 3 日分（中間） | 反映の遅れ（最長 72 時間）を見込み、10-04 分が確定した頃。取れ方と遅れの実測を記録する |
| 2026-10-13 以降 | 10-04〜10-10 の 7 日分（最終） | 10-10 分の確定（最長 72 時間後 = 10-13 00:00Z）。これで 4-1 / 4-2 を埋め、台帳 §A と ADR-0032「影響」を更新して `Closes #286` |

## 関連

- [observations.md](./observations.md) — PR 1〜3 の実施記録
- [ADR-0032](../../adr/0032-key-vault-references-for-container-apps-secrets.md) — 「影響」の課金項
- [azure-resource-inventory.md §A](../../operations/azure-resource-inventory.md) — Key Vault 行の費用欄
- [Issue #286](https://github.com/kmryst/felis-ai-chatbot/issues/286)
