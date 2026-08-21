# walking skeleton 経路開通の実測記録（Day 3）

[day3-5-execution-plan.md](../../operations/day3-5-execution-plan.md) §3-2 の walking skeleton のうち、
**hello-world 段階（ACR pull → Container Apps 起動 → 外部 ingress 応答 → egress IP の firewall 登録）**の実測記録。
時刻はすべて UTC。コマンドと生の出力をそのまま残す。

## 実測できたこと / できていないこと（正直な線引き）

- **実証できた**: ACR（マネージド ID + AcrPull）からの pull → Container Apps 起動（revision Healthy）→ 外部 ingress の HTTP 200 応答、および Container Apps の egress IP が PostgreSQL firewall rule に登録された**設定状態**
- **実証できていない**: 「Container Apps から PostgreSQL へ `SELECT 1` が通ること」。hello-world イメージは DB に接続しないため、この構成では確認できない。`/readyz`（`SELECT 1`）の実測は backend イメージへの差し替え（bootstrap.md「Day 3 の方針」方針1 の 2 段階目。backend の Dockerfile は未作成）が前提であり、**本記録をもって §3-5 の 1 点目を達成扱いにしない**

## 前提

- main = `2ad1bc1`（ephemeral 層の Terraform 構成マージ済み）。persistent 層は apply 済み（`pgsql-felisaichatbot-dev` state Ready。[restore-drill/observations.md](../restore-drill/observations.md)）
- マネージド ID `id-felisaichatbot-dev` + AcrPull（RG スコープ）は手動作成済み（[管理外リソース台帳](../../operations/terraform-unmanaged-resources.md) #8 / #9）
- apply は ADR-0015「7. Terraform 上の実装形」の段階 apply。ACR が空のままでは Container App がイメージを pull できないため、実際には `-target` を 2 回に分け、間に `az acr import` を挟んだ（下記タイムライン）

## タイムライン（2026-08-21）

| 時刻 (UTC) | 操作 | 結果 / 所要 |
| --- | --- | --- |
| 06:44 | 第1段 `terraform apply -target=ACR/LAW/CAE`（1回目） | **失敗**: `409 MissingSubscriptionRegistration`（下記「つまずき」） |
| 06:44〜06:46 | `az provider register`（`Microsoft.ContainerRegistry` / `Microsoft.OperationalInsights` / `Microsoft.App`） | 3 件とも約 1 分で Registered |
| 06:46 | 第1段 apply（再実行） | **3 added / 1m50s**（ACR 18s・Log Analytics 45s・CAE 55s） |
| 06:48 | `az acr import`（hello-world イメージ取り込み） | 12s |
| 06:48 | 第2段 `terraform apply -target=azurerm_container_app.main` | **1 added / 44s**（Container App 本体 36s） |
| 06:49 | 第3段 `terraform apply`（全体） | **1 added / 1m17s**（firewall rule。うち作成 1m6s） |
| 06:49 | `terraform plan -detailed-exitcode` | **exitcode 0（差分ゼロ）** |
| 06:49:33 | ingress URL へ `curl -i` | **HTTP/2 200**（応答 0.044s） |
| 06:50:26 | クレジット残の再取得（§8 の手順） | estimatedBalance USD 199.99（apply 前と同値。下記） |

## つまずき: リソースプロバイダー未登録（初回 apply 前提の実測知見）

第1段 apply の 1 回目は次のエラーで失敗した（抜粋）。

```text
Error: creating Registry ... unexpected status 409 (409 Conflict) with error:
MissingSubscriptionRegistration: The subscription is not registered to use
namespace 'Microsoft.ContainerRegistry'.
```

- このサブスクリプションでは `Microsoft.ContainerRegistry` / `Microsoft.OperationalInsights` / `Microsoft.App` がいずれも `NotRegistered` だった（persistent 層で使う `Microsoft.DBforPostgreSQL` は bootstrap 時点で登録済みだったため Day 3 朝の apply では踏まなかった）
- `az provider register -n <ns>` ×3 を実行し、約 1 分（15 秒間隔ポーリング 5 回目）で 3 件とも `Registered` になった。登録はサブスクリプションレベルの設定変更であり、リソースではないため管理外台帳の対象には追加しない
- CI（service principal）からの初 apply でも同じ 409 を踏み得る点に注意。RG スコープ Contributor はプロバイダー登録権限（`/register/action` はサブスクリプションスコープ）を持たないため、**未登録 namespace が必要になったら Owner が手動で登録するのが本リポジトリの運用**になる

## ACR に投入したイメージ

| 項目 | 値 |
| --- | --- |
| 取り込み元 | `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest` |
| 取り込み先 | `felisaichatbotacrdev.azurecr.io/containerapps-helloworld:mcr-7ab96989` |
| 取り込みコマンド | `az acr import --name felisaichatbotacrdev --source mcr.microsoft.com/azuredocs/containerapps-helloworld:latest --image containerapps-helloworld:mcr-7ab96989` |
| 取り込み元 manifest list digest | `sha256:7ab9698944af677cf77ae67d0a5c54595609e93adeb42babc154b9380a565539`（2026-08-21 に MCR の manifest HEAD で実測） |
| ACR 上の digest | `sha256:e9b3e7c34664c7cffd7144864b0e4eec369bfde80068f9095dc63b37058bec48`（`az acr repository show` 実測。import はプラットフォーム個別 manifest を取り込むため取り込み元 list digest とは一致しない） |

選定理由:

- Day 3 の検証は ingress への HTTP 応答確認を含むため、**HTTP を返す最小イメージ**が必要（`hello-world` 公式イメージはテキスト出力のみで listen しない）。`containerapps-helloworld` は Container Apps クイックスタートの公式サンプルで、port 80 で HTTP を返す
- MCR 側のタグは `latest` のみ（tags/list API で実測）。ADR-0015 のタグ方針（`latest` 禁止・不変タグ）に合わせ、import 時に**取り込み元 digest の先頭 8 hex 由来の不変タグ `mcr-7ab96989`** を付けた。git commit SHA 由来でないのは、このイメージがリポジトリのコードからビルドされたものではないため（backend 差し替え時から SHA タグ運用に入る）
- `container_target_port` は 80 で上書きした（変数既定値 8000 は backend/uvicorn 用）

## 検証の生出力（2026-08-21）

### 1. ingress URL への HTTP アクセス（06:49:33Z）

```console
$ curl -si https://ca-felisaichatbot-dev--25pggev.gentlesand-0e73dc70.japaneast.azurecontainerapps.io/ | head -6
HTTP/2 200
date: Fri, 21 Aug 2026 06:49:33 GMT
content-type: text/html; charset=utf-8

<!DOCTYPE html>
<html lang=en>
```

（本文は Azure Container Apps の Welcome ページ。所要 0.044s = 検証作業中のためレプリカが温まっていた状態）

### 2. revision の状態（= ACR pull 成功の判定）

```console
$ az containerapp revision list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev \
    --query '[].{name:name,active:properties.active,state:properties.runningState,health:properties.healthState,replicas:properties.replicas}' -o table
Name                            Active    State              Health    Replicas
------------------------------  --------  -----------------  --------  ----------
ca-felisaichatbot-dev--25pggev  True      RunningAtMaxScale  Healthy   1
```

pull 失敗なら revision が Failed / ImagePullBackOff 相当になるため、Healthy + HTTP 200 をもって
「マネージド ID `id-felisaichatbot-dev` + AcrPull（RG スコープ）による ACR pull の成功」と判定する。

### 3. egress IP と PostgreSQL firewall rule

```console
$ terraform -chdir=terraform/ephemeral output container_app_outbound_ips
tolist([
  "20.18.200.55",
])

$ az postgres flexible-server firewall-rule list -g rg-felisaichatbot-dev-tf -s pgsql-felisaichatbot-dev -o table
EndIpAddress    Name                     ResourceGroup             StartIpAddress
--------------  -----------------------  ------------------------  ----------------
20.18.200.55    aca-egress-20-18-200-55  rg-felisaichatbot-dev-tf  20.18.200.55
147.192.0.45    allow-workstation        rg-felisaichatbot-dev-tf  147.192.0.45
```

- `outbound_ip_addresses` は 1 件だった（複数 IP を想定した for_each 設計だが、Consumption 環境の実測は 1 件）
- この IP は静的保証がない（ADR-0015 選択肢 4-(a) の既知の不確実性）。rule は毎朝の apply でその時点の実 IP から作り直す

### 4. RG 内リソース一覧（apply 後）

```console
$ az resource list -g rg-felisaichatbot-dev-tf -o table
Name                      ResourceGroup             Location    Type                                              Status
------------------------  ------------------------  ----------  ------------------------------------------------  ---------
pgsql-felisaichatbot-dev  rg-felisaichatbot-dev-tf  japaneast   Microsoft.DBforPostgreSQL/flexibleServers         Succeeded
id-felisaichatbot-dev     rg-felisaichatbot-dev-tf  japaneast   Microsoft.ManagedIdentity/userAssignedIdentities  Succeeded
felisaichatbotacrdev      rg-felisaichatbot-dev-tf  japaneast   Microsoft.ContainerRegistry/registries            Succeeded
log-felisaichatbot-dev    rg-felisaichatbot-dev-tf  japaneast   Microsoft.OperationalInsights/workspaces          Succeeded
cae-felisaichatbot-dev    rg-felisaichatbot-dev-tf  japaneast   Microsoft.App/managedEnvironments                 Succeeded
ca-felisaichatbot-dev     rg-felisaichatbot-dev-tf  japaneast   Microsoft.App/containerApps                       Succeeded
```

（firewall rule はサーバーの子リソースのためこの一覧には出ない。3. の firewall-rule list が実測）

### 5. クレジット残（§8 の手順で再取得。06:50:26Z）

```json
{
  "current":   { "currency": "USD", "value": 200.0 },
  "estimated": { "currency": "USD", "value": 199.99 }
}
```

- apply 前（2026-08-21T06:00Z 頃）の実測も estimatedBalance USD 199.99 であり、**差分なし**。ephemeral 層の稼働は数分のため課金反映が追いついていない（反映遅延）。差分は当日 teardown 時・翌日の §8 チェックで再測する

## Day 3 のゴール判定（提案）

計画書 §3-5 の 1 点目「`/readyz` が 200（= `SELECT 1` 開通）」は**未達**。本記録で達成したのは
その前段の「デプロイ経路の開通」（bootstrap.md 方針1 が hello-world 段階に割り当てた検証範囲そのもの）である。

- **達成扱いにしてよいと考えるもの**: ACR pull 認証（ADR-0015 選択肢 6-(b) の実地検証）/ ingress 公開 / egress IP→firewall の Terraform 結線 / 段階 apply 手順の確立 / 全体 plan 差分ゼロ
- **次のタスク（これが通って初めて §3-5 の 1 点目が達成）**: backend の Dockerfile 作成 → SHA タグで ACR へ push → `container_image` / `container_target_port`（8000）/ `database_url` を差し替えて apply → `https://<FQDN>/readyz` の 200 を実測。CI（OIDC）経由のデプロイ整備（§3-2 の 3 点目）も未着手
