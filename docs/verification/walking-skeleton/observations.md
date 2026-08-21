# walking skeleton 経路開通の実測記録（Day 3）

[day3-5-execution-plan.md](../../operations/day3-5-execution-plan.md) §3-2 の walking skeleton のうち、
**hello-world 段階（ACR pull → Container Apps 起動 → 外部 ingress 応答 → egress IP の firewall 登録）**の実測記録。
時刻はすべて UTC。コマンドと生の出力をそのまま残す。

## 実測できたこと / できていないこと（正直な線引き）

- **実証できた**: ACR（マネージド ID + AcrPull）からの pull → Container Apps 起動（revision Healthy）→ 外部 ingress の HTTP 200 応答、および Container Apps の egress IP が PostgreSQL firewall rule に登録された**設定状態**
- **実証できていない**: 「Container Apps から PostgreSQL へ `SELECT 1` が通ること」。hello-world イメージは DB に接続しないため、この構成では確認できない。`/readyz`（`SELECT 1`）の実測は backend イメージへの差し替え（bootstrap.md「Day 3 の方針」方針1 の 2 段階目。backend の Dockerfile は未作成）が前提であり、**本記録をもって §3-5 の 1 点目を達成扱いにしない**

## 前提

- main = `2ad1bc1`（ephemeral 層の Terraform 構成マージ済み）。persistent 層は apply 済み（`pgsql-felisaichatbot-dev` state Ready。[restore-drill/observations.md](../restore-drill/observations.md)）
- マネージド ID `id-felisaichatbot-dev` + AcrPull（RG スコープ）は手動作成済み（[管理外リソース台帳](../../operations/azure-resource-inventory.md) #8 / #9）
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
<WORKSTATION_IP>  allow-workstation        rg-felisaichatbot-dev-tf  <WORKSTATION_IP>
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

---

## backend 段階 + Log Analytics 層移設の実測記録（2026-08-21 追記）

hello-world 段階（上記）に続く **backend 段階**（backend イメージへの差し替え → `/readyz` の外部実測）と、
**ADR-0016 の移設実操作（destroy → apply → apply）** の記録。時刻はすべて UTC。

### 前提

- main = `7c81be0`（ADR-0016/0017 と Terraform 両層のコード変更 #78、backend Dockerfile #77 マージ済み）
- 移設手順の正本は [ADR-0016](../../adr/0016-log-analytics-workspace-in-persistent-layer.md)。実操作は本記録が初回

### タイムライン（2026-08-21）

| 操作 | 結果 / 所要 |
| --- | --- |
| `terraform -chdir=terraform/ephemeral destroy` | **5 destroyed / 8m05s**（うち CAE 削除 7m31s。旧 Log Analytics は features の `permanently_delete_on_destroy = true` により完全削除） |
| `terraform -chdir=terraform/persistent plan` | **1 to add, 0 to change, 0 to destroy**（追加は Log Analytics のみ。PostgreSQL に差分なしを確認してから apply） |
| `terraform -chdir=terraform/persistent apply` | **1 added / 51s**（workspace 作成 48s。名前 conflict なし = 完全削除が効き、ADR-0016 のフォールバック手順は不要だった） |
| ephemeral 第1段 `apply -target=ACR,CAE` | **2 added / 1m02s** |
| `docker build`（backend、タグ `sha-7c81be0`） | 2.8s（ローカルキャッシュ利用） |
| `az acr login` + `docker push` | 2.9s |
| 第2段 `apply -target=azurerm_container_app.main` | **1 added / 41s**（Container App 本体 36s） |
| 第3段 `apply`（全体） | **1 added / 1m17s**（firewall rule 作成 1m07s） |
| `/readyz` へ外部から `curl -i`（07:58:21Z） | **HTTP/2 200**・本文 `{"status":"ok","db":"ok"}`（下記） |
| `terraform plan -detailed-exitcode`（ephemeral 全体） | **exitcode 0（差分ゼロ）** |

### デプロイした backend イメージ

| 項目 | 値 |
| --- | --- |
| イメージ | `felisaichatbotacrdev.azurecr.io/backend:sha-7c81be0`（ビルド時点の main = `7c81be0` の short SHA 由来の不変タグ。ADR-0015） |
| digest | `sha256:33a771f6a31393ca62fd51f5cea240a30cde11a02388c12a790e6dc494a2c0be` |
| `container_target_port` | 8000（uvicorn。hello-world 段階の 80 から変更） |

Container App に渡した環境変数（値は記載しない）:

- `DATABASE_URL`（Container App の secret 経由。Azure PostgreSQL への libpq DSN、DB は既定の `postgres`、`sslmode=require`）

`LLM_PROVIDER` は**未設定（= 既定の `stub`）のまま**とした。判断根拠:

- Day 3 のゴールは `/readyz` の 200（= DB への `SELECT 1`）であり、`/readyz` の実装（`app/main.py` / `app/db.py`）は LLM を一切使わない
- `app/config.py` は `LLM_PROVIDER=azure-openai` のときだけ `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` を必須にする（ADR-0004 のスタブ既定）。stub のままなら必須環境変数は `DATABASE_URL` のみで、API キーを Container Apps へ渡す経路（secret 追加）を今日は作らずに済む
- 実 LLM の結線検証は `/chat` の検証であり Day 3 のスコープ外

マイグレーション / データ投入は**実施していない**。判断根拠: `/readyz` は `SELECT 1` のみでテーブルを参照しない（`app/db.py` 実読で確認）。Alembic 適用・seed 投入は Day 4 のドリル準備で別途行う（計画書 §3-5 の 2 点目は本日時点で未達のまま）。

### 検証の生出力（2026-08-21）

#### 1. `/readyz` の外部実測（07:58:21Z）

```console
$ curl -si https://ca-felisaichatbot-dev--ent1yog.gentleforest-75fced2c.japaneast.azurecontainerapps.io/readyz
HTTP/2 200
date: Fri, 21 Aug 2026 07:58:21 GMT
server: uvicorn
content-length: 25
content-type: application/json
x-request-id: e423b82b-553f-46c9-97b9-11ed97d95f61

{"status":"ok","db":"ok"}
```

（time_total 0.102s。`db: "ok"` は `app/db.py` の `check_database_ready` が Azure PostgreSQL へ psycopg で接続し
`SELECT 1` を実行できた場合にのみ返る。DB へ到達できない場合は 503 `{"status":"unavailable","db":"unreachable"}` になる実装）

#### 2. revision の状態（= ACR pull 成功の判定。hello-world 段階と同じ判定基準）

```console
$ az containerapp revision list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev \
    --query '[].{name:name,active:properties.active,state:properties.runningState,health:properties.healthState,replicas:properties.replicas}' -o table
Name                            Active    State              Health    Replicas
------------------------------  --------  -----------------  --------  ----------
ca-felisaichatbot-dev--ent1yog  True      RunningAtMaxScale  Healthy   1
```

#### 3. egress IP と PostgreSQL firewall rule（IP は前回から変わった）

```console
$ az postgres flexible-server firewall-rule list -g rg-felisaichatbot-dev-tf -s pgsql-felisaichatbot-dev -o table
EndIpAddress    Name                      ResourceGroup             StartIpAddress
--------------  ------------------------  ------------------------  ----------------
74.176.38.216   aca-egress-74-176-38-216  rg-felisaichatbot-dev-tf  74.176.38.216
<WORKSTATION_IP>  allow-workstation         rg-felisaichatbot-dev-tf  <WORKSTATION_IP>
```

- egress IP は hello-world 段階の `20.18.200.55` から `74.176.38.216` に**変わった**（「Outbound IPs might change over time」の実例。ADR-0015 選択肢 4-(a) の既知の不確実性が destroy / 再作成で実際に発現）。旧 IP の rule は層の destroy で消え、新 IP の rule が第3段 apply で作られた。設計どおり「毎回その時点の実 IP で作り直す」が機能している

#### 4. Log Analytics 移設の成立

```console
$ az monitor log-analytics workspace show -g rg-felisaichatbot-dev-tf -n log-felisaichatbot-dev \
    --query '{name:name,state:provisioningState,sku:sku.name,retention:retentionInDays,quota:workspaceCapping.dailyQuotaGb,created:createdDate}' -o json
{
  "created": "2026-08-21T07:53:43.2230554Z",
  "name": "log-felisaichatbot-dev",
  "quota": 1.0,
  "retention": 30,
  "sku": "PerGB2018",
  "state": "Succeeded"
}
```

- `created` が移設当日の persistent apply 時刻 = 新規作成された workspace であることの証拠（設定値 PerGB2018 / 30 日 / 1 GB は ADR-0016 どおり据え置き）
- state の所属（`terraform state list` 実測）: `azurerm_log_analytics_workspace.main` は **persistent 層の state のみ**にあり、ephemeral 層の state は `data.azurerm_log_analytics_workspace.main`（読み取り参照）のみ。**以後 ephemeral の destroy で workspace は消えない**
- ephemeral destroy（上記タイムライン 1 行目）の後も workspace を作り直せた（= 旧 workspace の完全削除で名前が即時解放された）ことが、移設手順の soft delete 対処の実測になっている

#### 5. PostgreSQL が無傷であることの確認（destroy / stop を行っていない）

```console
$ az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
    --query '{state:state,earliestRestore:backup.earliestRestoreDate,retention:backup.backupRetentionDays}' -o json
{
  "earliestRestore": "2026-08-21T05:59:00.967587+00:00",
  "retention": 7,
  "state": "Ready"
}
```

（state Ready・`earliestRestoreDate` が保持されており、バックアップチェーンは継続。Day 4 の PITR ドリルの前提を壊していない）

#### 6. クレジット残（§8 の手順で再取得）

```json
{
  "current":   { "currency": "USD", "value": 200.0 },
  "estimated": { "currency": "USD", "value": 199.99 }
}
```

（hello-world 段階の実測と同値。当日分の課金反映遅延は前回と同様）

### provider features の整理（移設完了に伴う同日変更）

- `terraform/persistent/provider.tf` に `log_analytics_workspace { permanently_delete_on_destroy = true }` を**追加**（revive runbook の成立要件。経緯は ADR-0016 追記）
- `terraform/ephemeral/provider.tf` から同ブロックを**削除**（移設のためだけに必要だった設定で、完了後は無効果。ADR-0016 追記）
- どちらも変更後に `terraform plan -detailed-exitcode` を実測し **exitcode 0（差分ゼロ）** = features 変更は既存リソースに影響しないことを確認済み

### Day 3 のゴール判定

計画書 §3-5 の 1 点目「`/readyz` が 200（= Azure 上の PostgreSQL へ `SELECT 1` が通り、Container Apps からの接続経路が開通している）」は、
上記 1.（HTTP 200 + `db: "ok"`）と 2.（revision Healthy = ACR pull 成功）をもって**達成**と判定する。

- hello-world 段階で「実証できていない」と明記した「Container Apps から PostgreSQL へ `SELECT 1` が通ること」が、本記録で実証された
- 未達のまま残るもの（正直な線引き）: §3-2 の 3 点目「CI（GitHub Actions）経由のデプロイ」（本記録のデプロイはローカル実行。CI 経由は未整備）、§3-5 の 2 点目「psql 接続 + Alembic 適用」（Day 4 準備で実施）
