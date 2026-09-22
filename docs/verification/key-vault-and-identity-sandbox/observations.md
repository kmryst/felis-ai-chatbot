# Key Vault 参照 / managed identity 検証環境（kv-sandbox）実測記録

- 対象 Issue: #287（Refs #286 / #280）
- 実施日: 2026-09-22（UTC 06:53 〜 08:5x。8 項目すべて同日に完了）　実施者: kmryst
- 検証環境: resource group `rg-kvsandbox-7x8cht`（japaneast）。
  Container Apps 環境だけは新規作成できず、既存の環境を参照した（後述）。
  felis 本体の Terraform state・コード・リソース設定には一切書き込んでいない
- 秘密値・トークンは書かない。長さ（`len`）または sha256 の先頭 8 桁で代用する
- 「事実」は実行結果そのもの、「推測」は実行結果から導いた解釈。本文中で区別して書く

## 結果一覧

| # | 項目 | 判定 | 根拠の要点 |
| --- | --- | --- | --- |
| 1 | Key Vault 参照 secret で Easy Auth サインイン | **可** | sidecar の `POST .../oauth2/v2.0/token` が `Completed with 200`。`LoginComplete` / `Authenticated: true`。サインイン後は `/` が HTTP 200（未サインインは 401） |
| 2 | ローテーション追従（環境変数 / Easy Auth sidecar） | **可（両方とも自動追従）** | 2-a: t0 から 19 分 01 秒で環境変数が新値に。2-b: t0 から 7 分 28 秒で platform が同期し、サインインが回復。いずれも `RevisionRestartWithNewSecrets` による再起動を伴い、新 revision は作られない |
| 3 | ロール剥奪の反映時間 | **可（21 秒以内）** | t0 = 2026-09-22T08:17:49Z → t0 + 21 秒の probe 行で `kv_http` が 200 → 403。`token_exp` は同一値のまま。二次観測: 08:43:53 の定期同期が `SyncingSecretFromAzureKeyVaultForContainerAppFailed` で失敗するが、アプリは旧値を保持して稼働を続ける |
| 4 | `identitySettings.lifecycle = "None"` | **可** | azapi で in-place 更新（17 秒、replace 無し）。revision 再起動後に identity A は HTTP 400、B は 200。platform 側の Key Vault 参照は再起動後も解決 |
| 5 | 複数 user-assigned identity で `client_id` 省略 | **可（公式どおり）** | `client_id` 省略で HTTP 400 `Unable to load the proper Managed Identity.`。A / B を明示すれば 200 |
| 6 | `terraform state pull` に秘密値が残らない | **可（azurerm / azapi 両方）** | 解決済みの値の grep が 0 件。state には `keyVaultUrl` / `value_wo_version` / secret の URL だけが残る |
| 7 | Key Vault 削除 → 同名再作成 → purge | **可**（ただし CLI の挙動に注意） | ARM API は `ConflictError` で拒否。`az keyvault create` は同名を通す（soft-delete から回復していた）。purge は subscription Owner で通り、purge 後の同名作成は成功 |
| 8 | `az keyvault secret set` に必要なロール | **仮説どおり** | subscription Owner のみでは `Forbidden`（`secrets/setSecret/action`）。`Key Vault Secrets Officer` を vault スコープで付与後、84 秒以内に成功 |

## Container Apps 環境の上限と、既存環境への相乗り

### 事実

サンドボックス専用の Container Apps 環境（CAE）を新規作成しようとしたが、
**subscription のクォータ上、追加の Container Apps 環境を作成できなかった。**
japaneast / japanwest / eastus の 3 リージョンで試し、いずれも HTTP 409 で拒否された。

| 試行 | 時刻 (UTC) | CAE の region | HTTP | エラーコード |
| --- | --- | --- | --- | --- |
| 1 回目 | 06:56 頃 | japaneast | 409 | `MaxNumberOfRegionalEnvironmentsInSubExceeded` |
| 2 回目 | 07:1x | japanwest | 409 | `MaxNumberOfGlobalEnvironmentsInSubExceeded` |
| 3 回目 | 07:33:42 → 07:33:46 | japanwest | 409 | `MaxNumberOfGlobalEnvironmentsInSubExceeded` |
| 4 回目 | 07:33:53 → 07:34:00 | eastus | 409 | `MaxNumberOfGlobalEnvironmentsInSubExceeded` |

メッセージ（原文 / 日本語訳。subscription ID は伏せる）:

> `The subscription '...' cannot have more than 1 Container App Environments in Japan East.`
> この subscription は Japan East において Container App Environment を 1 つより多く持つことはできない。

以下は 2 つ目のメッセージ。

> `The subscription '...' cannot have more than 1 Container App Environments.`
> この subscription は Container App Environment を 1 つより多く持つことはできない。

### 構造的な知見（#286 / #280 の作業計画に効く）

**Container Apps 環境の上限は 2 段ある。**

1. **リージョン単位の上限**: `Microsoft.App/locations/<region>/usages` の `ManagedEnvironmentCount` として露出する。
   超過すると `MaxNumberOfRegionalEnvironmentsInSubExceeded`
2. **subscription 全体スコープの上限**: 超過すると `MaxNumberOfGlobalEnvironmentsInSubExceeded`

**2 は `Microsoft.App/locations/<region>/usages`（api-version `2024-03-01`）にも `Microsoft.Quota`（api-version `2023-02-01`）にも
項目として存在しない。** 実測で確認したクォータ API の返り値:

| region | `ManagedEnvironmentCount`（usages） | `ExpressEnvironmentCount` |
| --- | --- | --- |
| japaneast | 1 / 1（使用中） | 0 / 450 |
| japanwest | **0 / 1** | 0 / 450 |
| eastus | **0 / 1** | 0 / 450 |
| westus | 0 / 1 | 0 / 450 |

`Microsoft.Quota` も `ManagedEnvironmentCount`（`limitType: Independent`）しか返さず、
**subscription 全体スコープの上限に対応する quota 名は存在しない**。
`Microsoft.App/usages`（location 無しの subscription スコープ）は `InvalidResourceType` で、そもそも存在しない。
`Microsoft.Quota` 経由の引き上げ要求も `provisioningState: Failed` で拒否された（API では上げられない）。

つまり **「usages を見て別リージョンが空いている」ことを根拠に環境を追加できると判断してはいけない。**
2 段目の上限はエラーコードでしか区別できず、実際に作成を試みるまで分からない。

### 採った回避策: 既存 Container Apps 環境への相乗り

検証用の Container App 2 つは **resource group `rg-kvsandbox-7x8cht` に作り**、
`managedEnvironmentId` として felis の既存環境 `cae-felisaichatbot-dev` の resource ID を参照した。
環境そのものは `data` source（読み取り専用）で参照し、設定は一切変更していない。

- サンドボックスのアプリ名は `ca-kvsbx-` で始める（`ca-kvsbx-7x8cht` / `ca-kvsbx-probe-7x8cht`）。
  felis の命名（`felisaichatbot` を含む名前）は作成も変更もしていない
- `terraform plan` の変更対象は 3 件とも `ca-kvsbx-` で、`felisaichatbot` を含む文字列は
  `managedEnvironmentId` / `container_app_environment_id` の**参照値としてのみ**現れた
- 環境が Consumption ワークロードプロファイルかつ VNet 統合のため、アプリ側に
  `workloadProfileName = "Consumption"` の明示が要る（新規の Consumption 専用環境では不要だった項目）

### 相乗りによる副作用（設定変更ではないが記録する）

サンドボックスのアプリのコンソールログは、参照した Container Apps 環境のログ出力先の
Log Analytics workspace に入る。サンドボックス用に作った `log-kvsandbox-7x8cht` は**使われなかった**。
取り込み量は probe アプリが毎分 1 行、メインアプリが起動時に十数行で、30 分あたり計 265 行（実測）。
RG を削除した時点でログの追加は止まり、既存の行は workspace の保持期間で消える。

**項目 2 / 3 の観測はこの workspace に対して行った**（読み取りのみ）。
相乗りする場合、観測先が自分の workspace ではなくなる点に注意する。

### felis 側への影響（作業前後の比較）

| 確認 | 結果 |
| --- | --- |
| `az containerapp env show` の JSON 全体（07:41 取得 / 07:44 取得） | **完全一致**（Python の辞書比較で `True`） |
| felis frontend `/readyz`（07:42:10Z / 07:44:07Z / 07:58:13Z） | いずれも **HTTP 200** |
| felis の Container App 3 件（`ca-felisaichatbot-dev` / `-front` / `-ops`） | `provisioningState: Succeeded` のまま。変更操作は行っていない |
| felis の Terraform / リポジトリ | `terraform apply` を felis のディレクトリで実行していない。変更したのは本記録ファイルのみ |

## 環境（時系列）

| 時刻 (UTC) | 操作 | 結果 |
| --- | --- | --- |
| 06:53:53 | `az provider register -n Microsoft.KeyVault` | 06:55:10 に `Registered`（約 77 秒） |
| 06:55:36 | phase 1 apply | RG / identity ×2 / Log Analytics / Key Vault / ロール割当は作成成功。CAE のみ 409 |
| 07:07:37 | Entra app registration 作成、service principal 作成 | 成功。client secret（`easyauth-v1`、`len=40`）を Key Vault `easyauth-client-secret` に投入 |
| 07:07:49 | `create_probe_secret = true` で apply | `azurerm_key_vault_secret.probe[0]` 作成成功（`value_wo`、バージョン 1） |
| 07:33 〜 07:34 | CAE 作成を japanwest / eastus で再試行 | いずれも 409。新規作成を断念 |
| 07:41 | 既存 Container Apps 環境の設定を取得（比較用ベースライン） | `az containerapp env show` の JSON を保存 |
| 07:43:04 | app registration に redirect URI を設定 | `https://ca-kvsbx-7x8cht.<既定ドメイン>/.auth/login/aad/callback` |
| 07:43:40 → 07:44:00 | phase 2 apply（既存環境を参照する形に修正後） | **20 秒で成功**。`azapi_resource.app` 16 秒 / `azurerm_container_app.probe` 17 秒 / `authConfigs` 1 秒 |
| 07:44:07 | 既存 Container Apps 環境の設定を再取得して比較 | **差分なし** |
| 07:44:15 | サンドボックスアプリの secret 解決を確認 | `keyVaultUrl` 参照、`--show-values` で `len=40` |
| 07:53:18 → 07:53:36 | `tools` コンテナの起動コマンドを identity 観測スクリプトに変更 | 新 revision `ca-kvsbx-7x8cht--0000001` |
| 07:54:48 → 07:55:06 | 項目 2-a: `probe_secret_wo_version` 1 → 2 で apply | Key Vault に新バージョン（07:54:50 作成）。**t0（2-a）= 07:55:06Z** |
| 07:55:37 → 07:55:57 | 項目 4: `identity_a_lifecycle = "None"` で apply | azapi の **in-place 更新 17 秒**。replace ではない |
| 07:57:00 | 項目 4: revision を再起動 | `Restart succeeded` |
| 07:58:13 | 再起動後の secret 解決と felis の `/readyz` | `len=40` / felis `/readyz` は HTTP 200 |

Terraform 側で手直しした点（この検証用 Terraform はコミットしない）:

- `azurerm_container_app_environment` の新規作成をやめ、`data "azurerm_container_app_environment"` による**読み取り参照**に置き換えた
- azapi のアプリに `workloadProfileName = "Consumption"`、azurerm の probe アプリに `workload_profile_name = "Consumption"` を追加した
  （参照先の環境がワークロードプロファイル構成のため）
- azurerm 5.1.0 の `azurerm_container_app_environment` は `logs_destination = "log-analytics"` を明示しないと
  `log_analytics_workspace_id` を受け付けない（エラー: `` `log_analytics_workspace_id` can only be set when `logs_destination` is set to `log-analytics` or `""` ``）。
  felis 本体で CAE を azurerm 5.x に上げる際に同じ指摘を受ける可能性がある（推測）

### azapi 2.12.0 の差分が消えない問題（#286 / #280 で必ず踏む）

**事実**: `identitySettings[].identity` に user-assigned identity の resource ID を書くと、
ARM は `/subscriptions/.../resourcegroups/...`（`resourcegroups` が小文字 g）で返すのに対し、
Terraform の設定値は `resourceGroups`（大文字 G）のため、apply 後も毎回 in-place update の差分が出続ける。

**対処（実測で確認）**: `azapi_resource` に `ignore_casing = true` を付けると差分が消えた
（付ける前: `Plan: 0 to add, 1 to change` が繰り返し出る。付けた後: `terraform plan -detailed-exitcode` が 0）。

## 項目 1: Key Vault 参照 secret を `clientSecretSettingName` に指定した Easy Auth

### 判定: 可

**Easy Auth の auth sidecar は、Key Vault 参照で解決された secret を使って認可コードの交換に成功した。**

Easy Auth の client secret は認可コードの交換時に使われるため、`/.auth/login/aad` へのリダイレクトだけでは可否が分からない。
ブラウザでサインインを完了させ、sidecar（コンテナ名 `http-auth`、`ModuleRuntimeVersion: 1.14.0.0`）のログで
トークンエンドポイントへの POST の結果を確認した。

### 事前確認（事実）

| 確認 | 時刻 (UTC) | 結果 |
| --- | --- | --- |
| `secrets[]` が Key Vault 参照として登録されている | 07:44:15 | `name=microsoft-provider-authentication-secret` / `keyVaultUrl=.../secrets/easyauth-client-secret` / `identity=<identity A>`（`value` は無し） |
| platform が Key Vault 参照を解決できている | 07:44:15 | `az containerapp secret list --show-values` で **`len=40`** |
| authConfigs の設定 | 07:44 | `clientSecretSettingName=microsoft-provider-authentication-secret` / `platform.enabled=true` |
| auth sidecar の起動 | 07:44 | replica のコンテナは `web` / `tools` / **`http-auth`** の 3 本とも `Running` |
| `/.auth/login/aad` の応答 | 07:54 | HTTP 302。`response_type=code+id_token` / `response_mode=form_post`。**hybrid flow なので code 交換で client secret を使う** |
| Key Vault の値が Entra で有効か | 07:50:39 | Key Vault から取り出した値で `client_credentials` のトークン要求 → **発行成功**。値そのものは正しい |
| 未サインインでの `/` | 07:44〜07:54 | HTTP 401 |

### サインインの実測（事実）

| 時刻 (UTC) | 観測 |
| --- | --- |
| 08:05:36 / 08:05:43 | sidecar が `POST .../oauth2/v2.0/token` を実行し、ログに **`Completed with 200`**（所要 535 ms / 316 ms）。`/.auth/login/aad/callback` は HTTP 302 |
| 08:05:43 | `TaskName: LoginComplete` / `Authenticated: true` / `ClientId` は app registration の appId |
| 08:05:43 | ブラウザは `/.auth/login/done`（「You have successfully signed in」）に到達 |
| 08:05:59 | サインイン済みで `/` が **HTTP 200**（quickstart のページが描画される。未サインイン時は 401 だった） |

原文と日本語訳（sidecar のログ）:

> `Completed with 200. Partial response if failure: .` / `ActionTaken: HttpRequest POST` / `Location: https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token`
> 200 で完了した（失敗時はここに部分レスポンスが入る）。実行した操作は POST、宛先はトークンエンドポイント。

**この 200 が判定の根拠**である。client secret が誤っていればここが 401 / `AADSTS7000215` になる
（実際、項目 2-b でローテーション直後に同じ箇所が 401 になった。下記「項目 2-b」）。

### 判定が Key Vault 参照によるものであることの確定（事実）

| 確認 | 結果 |
| --- | --- |
| 成功時点（08:05:43 / 08:15:30）の `secrets[]` | **Key Vault 参照のみ**（`name` + `keyVaultUrl` + `identity`）。`value` フィールドを持つ secret は **0 件** |
| revision | 一貫して `ca-kvsbx-7x8cht--0000001`（07:53:28 作成）。成功と失敗で revision は変わっていない |
| 08:06:25 〜 08:15:30 のアクティビティログ | このアプリへの **`write` 操作は 1 件も無い**（`listSecrets` の読み取りのみ） |
| 値方式への切り替え（対照実験） | **行っていない**。Key Vault 参照のまま最初から最後まで通した |

途中（08:07 〜 08:11）に出た `AADSTS7000215` は、**項目 2-b のために 08:06:25 に client secret をローテーションし、
旧資格情報を app registration から削除したことによる**ものであり、Key Vault 参照方式の失敗ではない。
platform が新バージョンを取り込んだ 08:13:53 以降、設定を一切変えずにサインインが回復している。

### 付随して分かったこと

- **`/.auth/me` は Container Apps の auth sidecar では 404 を返す**（サインイン済みでも 404、未サインインでは 401）。
  sidecar のアクセスログにも `GET /.auth/me - 404 19 text/plain` と出る（事実）。
  App Service の Easy Auth と同じつもりで `/.auth/me` を疎通確認に使うと誤判定する。
  認証済みかどうかは `/` のステータス（401 か 200 か）と sidecar のログで判定する
- `curl` で `/` を叩くと `Accept: text/html` を付けても 302 ではなく 401 が返る（事実）。
  ログインへのリダイレクトはブラウザからの要求でのみ観測できた
- 偽の認可コードで `/.auth/login/aad/callback` に POST すると HTTP 400 で、code 交換まで到達しない（事実）。
  自動判定には使えない

### 「値方式の secret が残っていない」ことの確認（判定の前提）

`Microsoft.App/containerApps@2025-07-01` の GET で `configuration.secrets` を直接見た結果（08:08 取得）:

- **secret は 1 件のみ**。`name=microsoft-provider-authentication-secret` / `keyVaultUrl` / `identity` の 3 フィールドだけで、
  **`value` フィールドを持つ secret は 1 件も無い**
- `az containerapp secret list --show-values` で解決後の長さは 40
- したがって、sidecar が使えた client secret は **Key Vault 参照経由で解決されたもの以外にあり得ない**

### secret 取得に関するログ（事実）

- `ContainerAppSystemLogs_CL` に `Reason_s = SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` /
  `Sync with secrets from Azure Key Vault was successful for container app ca-kvsbx-7x8cht` が記録される
  （日本語訳: 「この container app について Azure Key Vault からの secret 同期に成功した」）。
  アプリの作成・更新のたびに出る。**Key Vault 参照の解決は platform（Container Apps 側）が行い、sidecar は行わない**
- sidecar の設定ログ（`TaskName: TraceConfigurationSetting` / `SettingName: WEBSITE_AUTH_V2_CONFIG_JSON`）では、
  `clientSecretSettingName` が **`WEBSITE_AUTH_CLIENT_SECRET_SETTING_NAME`** という固定の番兵名に書き換わっている。
  つまり platform が Container Apps の secret を sidecar の環境変数に流し込み、sidecar は固定名でそれを読む。
  Key Vault 参照か値方式かは sidecar からは区別できない（推測だが、この設定ログと上の同期イベントから整合的）
- `unauthenticatedClientAction` は sidecar の内部表現で **`0`**（= `RedirectToLoginPage`）

### Key Vault の監査ログ（確認済み・記録）

この検証環境の Key Vault `kv-sbx-7x8cht` には **診断設定が 0 件**（`az monitor diagnostic-settings list` が空）。
したがって `AuditEvent`（`SecretGet` など）は記録されておらず、
**「Easy Auth 起因の `SecretGet` があったか」を Key Vault 側のログから確認することはできない。**
代わりに Container Apps 側の `ContainerAppSystemLogs_CL` の
`SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` を同期の証跡として使った。

felis への含意: #286 で Key Vault を本番に入れるなら、
**診断設定で `AuditEvent` を Log Analytics に送る設定を最初から入れる**（誰の identity がいつ secret を読んだかの証跡になる）。

### `unauthenticatedClientAction` と匿名アクセス（事実）

| 設定 | 値 |
| --- | --- |
| `platform.enabled` | `true` |
| `globalValidation.unauthenticatedClientAction` | `RedirectToLoginPage`（sidecar 内部表現は `0`） |
| `globalValidation.redirectToProvider` | `azureactivedirectory` |

この設定で、**未サインインの `curl` は `/` も `/.auth/me` も HTTP 401**（08:08:15 実測）。
`RedirectToLoginPage` でもブラウザ以外の要求には 302 ではなく 401 が返る。
サインイン済みのブラウザでは `/` が 200 になり、quickstart のページが表示される。
「ルートページが見える」のは**認証を通過した後**の状態であって、匿名到達ではない。

### 実施方法の注記

サインインは Playwright の永続ブラウザプロファイルに残っていた Entra のセッションで無音で完了した。
**エージェントは資格情報（メールアドレス・パスワード）を入力していない。**

## 項目 5: 複数 user-assigned identity で `client_id` を省略した場合の挙動（#280）

メインアプリには identity A と B の 2 つが付いており、system-assigned identity は**無い**。
`tools` コンテナの起動時に IMDS（`IDENTITY_ENDPOINT`）へ 3 通りの要求を出し、標準出力に記録した（07:53:45Z）。

| 要求 | HTTP | 本文 / 結果 |
| --- | --- | --- |
| `client_id` 省略 | **400** | `{"statusCode": 400, "message": "Unable to load the proper Managed Identity.", "correlationId": "..."}` |
| `client_id=<identity A>` | 200 | `client_id` が A、`access_token` の長さ 2116 |
| `client_id=<identity B>` | 200 | `client_id` が B、`access_token` の長さ 2048 |
| A のトークンで Key Vault GET secret | **200** | `Key Vault Secrets User` を持っている |
| B のトークンで Key Vault GET secret | **403** | `error.code = Forbidden`（ロール無し） |

原文と日本語訳:

> `Unable to load the proper Managed Identity.`
> 適切な managed identity を読み込めない。

判定: **公式どおり（可）。** 公式の記述
"If all ID parameters (`client_id`, `principal_id`, `object_id`, and `mi_res_id`) are omitted, the system-assigned identity is used."
（ID パラメーターをすべて省略すると system-assigned identity が使われる）/
"the token service will attempt to obtain a token for a system-assigned identity, which may or may not exist"
（トークンサービスは system-assigned identity のトークンを取りに行くが、それは存在するとは限らない）
のとおり、system-assigned identity が無い状態で省略すると失敗する。先頭の user-assigned identity への fallback は**起きない**（事実）。

felis への含意（#280）: user-assigned identity を複数付けるアプリでは **`AZURE_CLIENT_ID` を必ず明示する**。
省略時の挙動は fallback ではなく HTTP 400 の失敗なので、起動時に必ず露見する（サイレントに別 identity を使う事故は起きない）。

## 項目 2: Key Vault secret のローテーション追従（#286）

公式:

> "When newer versions become available, the app automatically retrieves the latest version within 30 minutes. Any active revisions that reference the secret in an environment variable is automatically restarted to pick up the new value."
> 新しいバージョンが利用可能になると、app は 30 分以内に自動で最新を取得する。その secret を環境変数で参照するアクティブな revision は、新しい値を取り込むために自動で再起動される。

環境変数経由（probe アプリ）と Easy Auth sidecar 経由（メインアプリ）の 2 本を同じ時間帯に走らせて測った。

### 2-a: 環境変数（probe アプリ `ca-kvsbx-probe-7x8cht`）

| 時刻 (UTC) | 事象 |
| --- | --- |
| 07:54:50 | Key Vault `probe-secret` に新バージョンを作成（`value_wo_version` 1 → 2） |
| **07:55:06** | **t0**（`terraform apply` 完了） |
| 07:55:15 | probe の**直接読み取り**（identity A のトークンで Key Vault GET）の `kv_hash` が**即座に**新値へ。環境変数 `env_hash` は旧値のまま |
| 08:13:53 | `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` と **`RevisionRestartWithNewSecrets`**: `Revision ca-kvsbx-probe-7x8cht--72bgdyd was successfully restarted to apply new updated secret.`（「更新された secret を適用するために revision を再起動した」） |
| 08:13:54 | `Revision ... updated. No new revision was provisioned.`（**新しい revision は作られない**）。replica が作り直される |
| **08:14:07** | 再起動後の最初の probe 行で **`env_hash` が新値**に変わる |

**追従時間: t0 から 19 分 01 秒**（Key Vault のバージョン作成 07:54:50 起点なら 19 分 17 秒）。公式の「30 分以内」の範囲内。

判定: **公式どおり（可）。**

- 環境変数は**自動で再起動**して新しい値を取り込む。**新 revision は作られない**（`revision list` は 1 件のまま）
- `value_wo_version` を増やすだけで追従するので、felis の `CHAT_API_KEY_CONFIG_CHECKSUM` 方式（checksum を変えて新 revision を作る）は不要になる
- 一方で**再起動は起きる**ので、「無停止でローテーションできる」わけではない（min replicas 1 の構成では瞬断がある）

### 2-b: Easy Auth sidecar（メインアプリ `ca-kvsbx-7x8cht`）

| 時刻 (UTC) | 事象 |
| --- | --- |
| 08:05:36 / 08:05:43 | ローテーション前のサインイン。sidecar のトークン POST が **`Completed with 200`**（項目 1 の判定根拠） |
| 08:06:24 | 新しい client secret（`easyauth-v2`）を発行し、Key Vault `easyauth-client-secret` に**新バージョン**として投入（`len=40`） |
| **08:06:25** | **t0** |
| 08:06:27 | app registration から旧資格情報 `easyauth-v1` を削除（以後、旧値では必ず失敗する） |
| 08:06:47 | アプリ側の解決済み secret の hash は**旧値のまま**（Key Vault 最新版の hash と不一致） |
| 08:07:13 / 08:07:14 | サインイン試行 → sidecar のトークン POST が **401 `AADSTS7000215: Invalid client secret provided`** |
| 08:09:59 / 08:10:00 / 08:11:49 / 08:11:50 | 同じく **`AADSTS7000215`**（別ウィンドウからの試行を含む） |
| 08:13:53 | `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded` と **`RevisionRestartWithNewSecrets`**: `Revision ca-kvsbx-7x8cht--0000001 was successfully restarted to apply new updated secret.` |
| 08:14:17 | アプリ側の解決済み secret の hash が Key Vault 最新版と**一致** |
| **08:15:30** | サインイン試行 → sidecar のトークン POST が **`Completed with 200`**。`/.auth/login/done` に到達 |

**追従時間: t0 から 7 分 28 秒で platform が新バージョンを取り込み（08:13:53）、以後サインインが回復した。**
最初に成功を確認したのは 08:15:30（= t0 + 9 分 05 秒）だが、これは試行のタイミングであって回復時刻ではない。
**回復は 08:13:53 時点**と読むのが妥当（推測。08:13:53 〜 08:15:30 の間に試行していないため）。

判定: **可。sidecar は自動で追従する。手動の revision 再起動は不要だった。**

### 2-a と 2-b をまとめて分かったこと（重要）

- **platform の Key Vault 同期は 2 つのアプリで同時刻（08:13:53）に起きた。**
  取り込みは app ごとの個別タイマーではなく、platform 側の周期処理に見える（推測）。
  したがって「t0 からの経過時間」は**最大 30 分・平均 15 分程度のばらつきを持つ**と考えるべきで、
  2-a の 19 分と 2-b の 7 分の差は追従方式の差ではなく、同じ周期に対する t0 の位置の差である（推測）
- **`RevisionRestartWithNewSecrets` はメインアプリでも起きた。**
  メインアプリはこの secret を環境変数では参照しておらず、`authConfigs` の `clientSecretSettingName` からのみ参照している。
  それでも revision は再起動された。
  公式の「環境変数で参照する revision は再起動される」より**広い範囲で再起動が起きる**（事実）。
  #286 では「Key Vault 参照 secret のローテーション = アプリの再起動」と見積もること
- 再起動されても**新しい revision は作られない**（両アプリとも `Revision ... updated. No new revision was provisioned.`）。
  Terraform の state にも差分は出ない
- probe アプリが identity A のトークンで Key Vault を**直接読んだ**値は、バージョン作成の**数秒後**には新しくなっていた（07:55:15）。
  遅延は Key Vault 側ではなく Container Apps の secret 同期側にある（事実）
- ローテーション中の失敗は `AADSTS7000215: Invalid client secret provided` として sidecar のログに残る。
  **旧バージョンの資格情報を Entra から消すのは、platform の同期が終わってからにする**（felis 手順書に反映する）

## 項目 4: `identitySettings.lifecycle = "None"`（#280 / #286）

### 判定: 可

| 時刻 (UTC) | 操作 | 観測 |
| --- | --- | --- |
| 07:55:37 → 07:55:57 | `identity_a_lifecycle` を `All` → `None` にして apply | `azapi_resource.app[0]` の **in-place 更新（17 秒）**。replace ではない |
| 07:55:57 | `az containerapp show --query properties.configuration.identitySettings` | A が `lifecycle: None`、B が `All` |
| 07:56 | `az containerapp revision list` | **新しい revision は作られない**（`ca-kvsbx-7x8cht--0000001` のまま。`identitySettings` は `configuration` 配下のため revision スコープではない） |
| 07:56 | 再起動前の `tools` コンテナの観測 | A も B も **HTTP 200 のまま**（設定は入っているが稼働中の replica には効いていない） |
| 07:57:00 | `az containerapp revision restart` | `Restart succeeded` |
| 07:57:17 | 再起動後の `tools` コンテナの観測 | A: **HTTP 400** `{"statusCode": 400, "message": "No User Assigned or Delegated Managed Identity found for specified ClientId/ResourceId/PrincipalId."}` / B: HTTP 200 |
| 07:58:13 | 再起動後の platform 側 Key Vault 参照 | `az containerapp secret list --show-values` が **`len=40`**。`/.auth/login/aad` も HTTP 302 |

原文と日本語訳:

> `No User Assigned or Delegated Managed Identity found for specified ClientId/ResourceId/PrincipalId.`
> 指定された ClientId / ResourceId / PrincipalId に対応する user-assigned identity も delegated managed identity も見つからない。

felis への含意:

- `lifecycle = "None"` はコンテナから identity を見えなくするが、**platform 側の用途（Key Vault 参照・ACR pull）には引き続き使える**（実測）。
  frontend 用 identity のようにアプリコードがトークンを取らない identity に適用できる
- **設定変更だけでは効かない。revision の再起動（または新 revision）が要る**（実測）。
  逆に言えば、`identitySettings` の変更は無停止では反映されない
- azurerm 5.1.0 には対応ブロックが無く、azapi で書くしかない。書く場合は `ignore_casing = true` を併記する（前述）

## 項目 3: ロール剥奪が効くまでの時間（#280）

### 判定: 可。剥奪は 21 秒以内に効いた

公式の注意（原文と日本語訳）:

> "The back-end services for managed identities maintain a cache per resource URI for around 24 hours. If you update the access policy of a particular target resource and immediately retrieve a token for that resource, you may continue to get a cached token with outdated permissions until that token expires."
> managed identity のバックエンドはリソース URI ごとに約 24 時間キャッシュを持つ。対象リソースのアクセスポリシーを更新した直後にトークンを取ると、期限が切れるまで古い権限のキャッシュ済みトークンを受け取り続けることがある。

**実測では、トークンは確かにキャッシュされたままだったが、Key Vault 側が即座に拒否した。**

### 測定条件

| 項目 | 値 |
| --- | --- |
| **t0（剥奪時刻、UTC）** | **2026-09-22T08:17:49Z** |
| 剥奪内容 | identity A（`id-kvsandbox-a-7x8cht`）の **`Key Vault Secrets User`**（スコープ: Key Vault `kv-sbx-7x8cht`）を削除。`terraform apply`（`grant_identity_a_secrets_user = false`）で destroy 1 件のみ、所要 2 秒 |
| 剥奪後の確認 | vault スコープのロール割当は実行アカウントの `Key Vault Secrets Officer` 1 件のみに |
| ポーリング | probe アプリ（`ca-kvsbx-probe-7x8cht`）が 60 秒ごとに `kv_http` と `token_exp` を stdout に記録 |
| 打ち切り条件 | t0 + 24 時間（一次結果は t0 + 21 秒で出たため、残りは二次観測のみ） |

### 結果（事実）

| probe の時刻 (UTC) | `token_exp` | `kv_http` |
| --- | --- | --- |
| 08:17:09（t0 の 40 秒前） | 1790151246 | **200** |
| **08:18:10（t0 の 21 秒後）** | **1790151246**（同じ） | **403** |
| 08:19:11 | 1790151246（同じ） | 403 |

**反映時間: t0 から 21 秒以内**（probe の間隔が 60 秒なので「21 秒以内」としか言えない。下限は 0 秒）。

**`token_exp` は 200 の区間と 403 の区間で同一値**（`1790151246`。集計クエリでも
`token_exp=1790151246` が `kv_http=200`（08:14:09〜08:17:11）と `kv_http=403`（08:18:12〜）の両方にまたがることを確認）。
つまり **managed identity のトークンは更新されておらず、同じトークンで Key Vault が 403 を返すようになった。**

判定: **Key Vault の RBAC は data plane で要求ごとに評価されるため、ロール剥奪はほぼ即座に効く。**
公式が警告する「約 24 時間のトークンキャッシュ」は**トークンの発行側**の話であり、
**リソース側の認可には影響しない**（少なくとも Key Vault では）。

### 二次観測の結果（同日 08:43:53 に確定。当初「翌日」としていたが前倒しで採れた）

**判定: (a) Container Apps は既に解決済みの旧値を保持し続ける。同期は失敗するが、アプリは停止しない。**

剥奪（t0 = 08:17:49Z）の後、**08:43:53Z** に platform の定期同期が走り、両アプリで失敗した。

| 時刻 (UTC) | アプリ | `Reason_s` |
| --- | --- | --- |
| 08:13:53 | `ca-kvsbx-7x8cht` / `ca-kvsbx-probe-7x8cht` | `SyncingSecretFromAzureKeyVaultForContainerAppSucceeded`（剥奪前） |
| **08:43:53** | **両方** | **`SyncingSecretFromAzureKeyVaultForContainerAppFailed`** |

**定期同期の間隔は 08:13:53 → 08:43:53 でちょうど 30 分**（事実）。公式の「30 分以内」と整合する。

失敗ログの本文（原文。subscription ID・テナント ID・principal ID は伏せる）:

```text
Failed to sync secret 'microsoft-provider-authentication-secret' from Azure Key Vault
'https://<vault>.vault.azure.net/secrets/easyauth-client-secret' for ContainerApp 'ca-kvsbx-7x8cht'.
Ensure the managed identity '<identity A の resource ID>' has the correct access policies or
RBAC role assignments on the Key Vault.
Error: GET request to Azure Key Vault ... returned error status: 403.
body: {"error":{"code":"Forbidden","message":"Caller is not authorized to perform action on resource. ...
Action: 'Microsoft.KeyVault/vaults/secrets/getSecret/action' ... Assignment: (not found) ...",
"innererror":{"code":"ForbiddenByRbac"}}}
```

日本語訳（要点）:

> ContainerApp `ca-kvsbx-7x8cht` の secret `microsoft-provider-authentication-secret` を Azure Key Vault から同期できなかった。
> managed identity が Key Vault に対して適切なアクセスポリシーまたは RBAC ロール割当を持っているか確認せよ。
> Key Vault への GET が 403 を返した。呼び出し元は操作を許可されていない。
> アクション: `Microsoft.KeyVault/vaults/secrets/getSecret/action`。割当: 見つからない。

### 同期失敗後のアプリの状態（08:45:52 実測）

| 確認 | 結果 |
| --- | --- |
| 両アプリの `provisioningState` / `runningStatus` | `Succeeded` / **`Running`**（停止していない） |
| replica の `createdTime` | 両方とも **08:13:5x のまま**。**同期失敗では再起動されない**（成功時の `RevisionRestartWithNewSecrets` は出ない） |
| `az containerapp secret list --show-values` | **`len=40`**。解決済みの値を保持している |
| Easy Auth `/.auth/login/aad` | **HTTP 302**。sidecar は動き続けている |
| probe の直接読み取り | `kv_http=403` が継続。`token_exp` は t0 前から一貫して同一値 |

### felis への含意（追加）

- **ロールを外しても、アプリはすぐには壊れない。** 既に解決済みの値を保持したまま動き続け、
  30 分ごとの同期が静かに失敗する。**気づくには `SyncingSecretFromAzureKeyVaultForContainerAppFailed` を監視する必要がある**
  （`ContainerAppSystemLogs_CL` の `Reason_s`）。#286 のアラート設計に入れる
- 壊れるのは次に**新しい値が必要になったとき**（ローテーション）か、**replica が作り直されたとき**（推測。本作業では未検証）。
  スケールアウトやノード入れ替えで初めて落ちる可能性がある
- したがって「ロールを外してもアプリが動いているから問題ない」という確認は**無効**。
  Key Vault への直接アクセスと同期ログの両方で確認する

### felis への含意（#280）

- **旧 identity からロールを外したら、その効果は数十秒で現れる。** 待ち時間を長く見積もる必要はない
- 逆に言えば、**切り戻しの猶予も無い。** 移行時は「新 identity にロールを付けて動作確認 → 旧 identity から外す」の順を守る
  （ロール付与側の反映は項目 8 で 84 秒以下だった。剥奪より遅い）
- **既に解決済みの Container Apps secret は剥奪後も残る**（実測）。
  「ロールを外したのにアプリが動き続ける」のは正常で、次の同期・再起動まで露見しない。
  剥奪の検証は**アプリの挙動ではなく Key Vault への直接アクセスで行う**こと

## 項目 6: `terraform state pull` に秘密値が残らないこと（azurerm / azapi 両方）

| 確認 | 結果 |
| --- | --- |
| (a) Key Vault から取り出した client secret の値が state にある件数 | **0** |
| (b) `value_wo` に渡した値（`probe-v...`）の grep 件数 | **0** |
| (b) `azurerm_key_vault_secret` の属性 | `value` = 空文字、`value_wo` = `null`、`value_wo_version` = `1`（当時） |
| (c) 参照 URL（`secrets/easyauth-client-secret` / `secrets/probe-secret`）の出現数 | **8**（すべて URL。値ではない） |
| azapi の `body.properties.configuration.secrets[]` | `name` / `keyVaultUrl` / `identity` の 3 つだけ。**`value` は無い** |
| azapi の `sensitive_body` | 未設定（`false`）。Key Vault 参照を使う限り不要 |
| `azurerm_container_app.probe` の `secret` ブロック | `key_vault_secret_id` / `identity` / `name` と、`value` は**空文字** |

判定: **可（azurerm / azapi 両方）。** Key Vault 参照を使う限り、解決後の値は state に入らない。
state に残るのは secret の URL・identity の resource ID・`value_wo_version` の数値だけで、いずれも秘密ではない。

## 項目 8: `az keyvault secret set` に必要なロール

前提（事実）: 実行アカウントは subscription スコープの Owner のみ。vault は `enableRbacAuthorization: true`、`softDeleteRetentionInDays: 7`、purge protection 無し。

| 時刻 (UTC) | 操作 | 観測 |
| --- | --- | --- |
| 07:01:01 | Owner のみで `az keyvault secret set --name smoke` | `Code: Forbidden` / `Caller is not authorized to perform action on resource.` / `Action: 'Microsoft.KeyVault/vaults/secrets/setSecret/action'` / `Assignment: (not found)` |
| 07:01:03 | `Key Vault Secrets Officer` を自分（User）に vault スコープで付与 | 作成成功 |
| 07:02:27 | 再試行（30 秒間隔ループの 1 回目） | 成功。付与から 84 秒。それより前は試行していないので、反映所要は「84 秒以下」とだけ言える |

判定: **仮説どおり。** subscription Owner は control plane のみで、RBAC 権限モデルの vault の data plane 操作（`setSecret`）はできない。
`Key Vault Secrets Officer` を vault スコープで付ければよい。反映待ちは 1〜2 分見ておけば足りる（実測 84 秒以下）。

felis への含意: #286 で Key Vault を作る Terraform には、実行アカウントへの `Key Vault Secrets Officer` 割当を
Key Vault と同じ apply に含め、secret 投入は別の apply（またはロール反映を待ってから）にする。

## 項目 7: Key Vault 削除 → 同名再作成 → purge

Terraform 管理外の vault `kv-sbx7-7x8cht` で実施（3 回繰り返して再現性を確認）。

| 時刻 (UTC) | 操作 | 観測 |
| --- | --- | --- |
| 07:05:26 | `az keyvault create` → `az keyvault delete` | `list-deleted` に載る。`deletionDate 07:05:27`、`scheduledPurgeDate 2026-09-29T07:05:27`（保持 7 日） |
| 07:05:35 | 同名で ARM `PUT`（`createMode` 省略、api-version `2023-07-01`） | **409 `ConflictError`**: `A vault with the same name already exists in deleted state. You need to either recover or purge existing key vault.` |
| 07:05:36 | 同名で ARM `PUT`（`createMode: "default"` 明示） | 同じ `ConflictError` |
| 07:15:43〜45 | 同名で ARM `PUT`（api-version `2023-07-01` / `2024-11-01` / `2025-05-01`、`createMode` 省略） | すべて同じ `ConflictError`（api-version 非依存） |
| 07:05:36 | 同名で **`az keyvault create`**（az 2.89.1） | **成功**（`PUT` が 200）。直後に `list-deleted` が空になり、`az keyvault show` は `provisioningState: Succeeded`、`createMode: null` |
| 07:06:12 → 07:06:31 | `delete` → `az keyvault purge`（subscription Owner のまま） | **成功**。`Key Vault Purge Operator` は不要だった。`list-deleted` が空 |
| 07:07:07 | purge 後に同名で ARM `PUT` | 成功（`provisioningState: RegisteringDns`）。名前は即日回収できる |

事実と推測の区別:

- 事実: ARM API を直接叩くと、soft-delete 中の同名 vault は `createMode` に関係なく `ConflictError` で作れない。公式どおり
  （"You can't reuse the name of a key vault that was soft-deleted, until the retention period expires"＝soft-delete された key vault の名前は保持期間が過ぎるまで再利用できない）。
- 事実: `az keyvault create` は同じ状況で成功し、その直後に deleted 一覧から消える。
- 推測: az CLI 2.89.1 の `keyvault create` は deleted vault を検出して `createMode: recover` 相当の要求を送っている。
  `--debug` では要求本文が表示されず、CLI ソース（`keyvault/custom.py`）でも `create_vault` 内に該当分岐を見つけられなかったため、確証は無い。
- 事実: purge は subscription Owner で通る（公式の "only the subscription owner or a user with the Key Vault Purge Operator Azure RBAC role can purge a key vault" と整合）。

判定: **可。** purge protection を付けなければ `delete → purge` で即日に名前を回収できる。

felis への含意:

- `az keyvault create` で「同名再作成できた」ように見えても、それは新規作成ではなく旧 vault の回復である可能性が高い（推測）。
  #286 の手順で「作り直し」をする場合は、`az keyvault purge` を挟んでから作る。
- azurerm provider は `features { key_vault { recover_soft_deleted_key_vaults } }` でこの挙動を明示的に選べる。
  本検証の provider 設定は `recover_soft_deleted_key_vaults = false`、`purge_soft_delete_on_destroy = true`。

## 動作した ARM ペイロード（#286 の実装で流用する形）

以下は **実際に `Microsoft.App/containerApps@2025-07-01` に PUT して成功したペイロード**の抜粋
（`terraform apply` が 07:43:40 → 07:44:00 で成功。`az containerapp secret list --show-values` で解決を確認済み）。

`configuration.secrets[]`（Key Vault 参照。`value` を書かない）:

```json
{
  "name": "microsoft-provider-authentication-secret",
  "keyVaultUrl": "https://<vault>.vault.azure.net/secrets/easyauth-client-secret",
  "identity": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ManagedIdentity/userAssignedIdentities/<identity>"
}
```

- `keyVaultUrl` は**バージョン無し**にすると最新バージョンに追従する（項目 2 の前提）
- `identity` は Key Vault 参照を解決する user-assigned identity の resource ID。`Key Vault Secrets User` が要る
- secret 名は小文字のみ（Kubernetes RFC 1123）。Easy Auth の既定名 `microsoft-provider-authentication-secret` はこれを満たす

`configuration.identitySettings[]`（項目 4。azurerm 5.1.0 には対応ブロックが無い）:

```json
[
  { "identity": "<identity A の resource ID>", "lifecycle": "None" },
  { "identity": "<identity B の resource ID>", "lifecycle": "All" }
]
```

`configuration` の残り（既存環境に相乗りする場合に必要だった項目）:

```json
{
  "managedEnvironmentId": "<既存の Container Apps 環境の resource ID>",
  "workloadProfileName": "Consumption"
}
```

`authConfigs/current`（`Microsoft.App/containerApps/authConfigs@2025-07-01`。作成 1 秒で成功）:

```json
{
  "properties": {
    "platform": { "enabled": true },
    "globalValidation": {
      "unauthenticatedClientAction": "RedirectToLoginPage",
      "redirectToProvider": "azureactivedirectory"
    },
    "identityProviders": {
      "azureActiveDirectory": {
        "registration": {
          "openIdIssuer": "https://login.microsoftonline.com/<tenant>/v2.0",
          "clientId": "<appId>",
          "clientSecretSettingName": "microsoft-provider-authentication-secret"
        }
      }
    }
  }
}
```

環境変数から secret を参照する形（chat API キー用。Easy Auth を介さない経路。probe アプリで実測）:

```json
{
  "template": {
    "containers": [
      { "env": [ { "name": "CHAT_API_KEY", "secretRef": "chat-api-key" } ] }
    ]
  }
}
```

## 調査で判明した制約: Easy Auth の federated identity credential 化は Container Apps では現状できない

出典: `microsoft/azure-container-apps` Issue #1693 "Feature Request: Container Apps to support FIC (Federated Identity Credentials)"
（open、2026-04-13 起票、<https://github.com/microsoft/azure-container-apps/issues/1693>）

起票者の説明（原文）:

> "the feature requires setting `clientSecretSettingName` to the sentinel value `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` and creating an application setting with that exact name. On App Service, application settings support uppercase names, so this works. On Container Apps, the equivalent mechanism maps `clientSecretSettingName` to a Container Apps secret, which enforces lowercase naming (Kubernetes RFC 1123 convention). This creates an unsolvable conflict: using the lowercase name deploys successfully but the auth sidecar doesn't recognize it as the FIC sentinel and treats the managed identity client ID as a literal client secret (failing with AADSTS7000215: Invalid client secret provided), while using the uppercase name fails deployment validation."

日本語訳:

> この機能は `clientSecretSettingName` に番兵値 `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` を設定し、その名前どおりの application setting を作ることを要求する。App Service の application setting は大文字の名前を許すので動く。Container Apps では同じ仕組みが `clientSecretSettingName` を Container Apps の secret に対応付けるが、secret 名は小文字に強制される（Kubernetes RFC 1123 の規約）。これは解決不能な衝突を生む。小文字の名前ならデプロイは通るが auth sidecar が FIC の番兵値と認識せず、managed identity の client ID をそのまま client secret として扱う（`AADSTS7000215: Invalid client secret provided` で失敗）。大文字の名前ではデプロイ時の検証で弾かれる。

Microsoft 側（simonjj、2026-04-16）の返答（原文）:

> "You've identified the core issue correctly — the FIC sentinel value (`OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID`) requires uppercase, but Container Apps secrets enforce lowercase per Kubernetes RFC 1123. This is a real gap between the shared auth sidecar and the Container Apps secret plumbing."

日本語訳:

> 核心を正しく指摘している。FIC の番兵値（`OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID`）は大文字を要求するが、Container Apps の secret は Kubernetes RFC 1123 に従って小文字を強制する。共有されている auth sidecar と Container Apps の secret の配管の間にある実際のギャップだ。

felis への含意: ADR-0031 が「将来の候補」とした Easy Auth の FIC 化は、この Issue が解決されるまで Container Apps では選べない。
Easy Auth の client secret は当面 Key Vault に置いてローテーションする前提で #286 を進める。

## 後片付け（2026-09-22 実施）

項目 3 の二次観測が同日 08:43:53 に確定したため、当初「翌日」としていた後片付けを同日に実施した。

| 時刻 (UTC) | 操作 | 結果 |
| --- | --- | --- |
| 08:46:44 → 08:47:48 | `az group delete -n rg-kvsandbox-7x8cht --yes` | 成功（64 秒）。Container App 2 つ / Key Vault / identity ×2 / Log Analytics / ロール割当が削除 |
| 08:47:51 | `az keyvault list-deleted` | `kv-sbx-7x8cht`（japaneast）が soft-delete 状態で 1 件 |
| 08:47:51 → 08:48:21 | `az keyvault purge -n kv-sbx-7x8cht -l japaneast` | 成功（30 秒） |
| 08:48:33 | `az ad app delete --id <appId>` | 成功。service principal も同時に削除 |

削除前に対象名を確認した（`az resource list -g rg-kvsandbox-7x8cht`）。
RG の中身は 6 件で、**`felisaichatbot` を含む名前は 0 件**。タグは `purpose=kv-sandbox` / `delete_after=2026-09-25`。

### 消し残しの確認（すべて読み取り。08:48:33 実行）

| 確認コマンド | 期待 | 結果 |
| --- | --- | --- |
| `az group list` で `rg-kvsandbox*` / `ME_cae-kvsandbox*` | 0 件 | **0 件** |
| `az resource list --tag purpose=kv-sandbox` | 0 件 | **0 件** |
| `az keyvault list-deleted` | 0 件 | **0 件** |
| `az ad app list --display-name kvsandbox-easyauth-7x8cht` | 0 件 | **0 件** |
| `az role assignment list --all` で scope に `kvsandbox` を含むもの | 0 件 | **0 件** |

ローカルの Terraform state（`terraform.tfstate` / `*.tfplan`）も削除した。秘密値は含まれていなかった（項目 6 で確認済み）。

`Microsoft.KeyVault` / `Microsoft.Quota` のリソースプロバイダー登録は**残した**（登録自体に課金は無く、#286 で再び必要になる）。

### 後片付け後の felis 側の確認（08:48:53、すべて読み取り）

| 確認 | 結果 |
| --- | --- |
| `az group list` の `felisaichatbot` 系 RG | **4 件**（`ME_cae-...` を含む）。作業前と同じ |
| 相乗りした Container Apps 環境の設定 JSON | **作業前のベースラインと完全一致**（後片付け後も差分なし） |
| felis の Container App 3 件 | `provisioningState: Succeeded`。`latestRevisionName` も作業前と同じ |
| felis frontend `/readyz` | **HTTP 200** |

**Container App を削除しても、参照していた Container Apps 環境には一切影響しなかった**（実測）。
環境は `data` source で読んだだけで Terraform の管理対象ではなく、`terraform destroy` の対象にもならない。

## 費用（実測）

- `usageDetails`（resource group 名に `kvsandbox` を含む行、直近 3 日、`metric=actualcost`）: **0 行 / 0 USD**（08:48 時点）
- 課金の反映には 1〜2 日の遅延があるため、**2026-09-24 に同じクエリで再確認する**
- 稼働実績: Container App 2 つが 07:43:52 〜 08:47:48 の **約 64 分**（メインアプリ 0.5 vCPU / 1 GiB、probe アプリ 0.25 vCPU / 0.5 GiB、いずれも min=max=1）。
  手順書 §1 の単価（active 0.000024 USD/vCPU 秒・0.000003 USD/GiB 秒）で全量 active 換算しても **0.1 USD 未満**（推測）
- Key Vault は操作数のみ（vault の作成・削除・purge を計 4 サイクル、secret 操作 20 件程度）。0.01 USD 未満（推測）
- Log Analytics への取り込みはサンドボックス側の workspace では 0。相乗り先 workspace への取り込みは約 1 時間分で数 MB
- **手順書 §1 の見積もり 3〜5 USD に対し、実績は 0.2 USD 未満の見込み**（推測。確定は 2026-09-24 の再確認）

## 中止条件の該当

- 参照した Container Apps 環境の設定に**差分は出ていない**（作業前・apply 直後・作業後・**後片付け後**の 4 回比較でいずれも完全一致）
- felis frontend `/readyz` は作業前・phase 2 apply 直後・項目 4 の再起動後・**後片付け後**のいずれも **HTTP 200**
- `terraform plan` に `felisaichatbot` を含む名前の**作成・変更・削除は 1 件も無い**
  （出現するのは `managedEnvironmentId` / `container_app_environment_id` の参照値のみ。変更対象 3 件はすべて `ca-kvsbx-`）
- 費用は累計 5 USD 未満（実測 0 USD、確定は 2026-09-24 の再確認）。想定外のメーターなし
- 手順書 §10 の A〜I にはいずれも該当していない
- 項目 1 は対話サインインを要したが、Playwright の永続プロファイルに残っていた Entra セッションで完了した。エージェントは資格情報を入力していない

## #286 を分割する必要があるかの判断

### 結論: 技術的には分割不要。ただし段階を分けて進めることを推奨する

**分割が必須になる理由は無くなった。** 項目 1 で、Easy Auth の `clientSecretSettingName` に
Key Vault 参照 secret を指定してサインインが通ることを実測した（sidecar のトークン POST が 200）。
「chat API キーだけ Key Vault 参照にして Easy Auth は現状維持」という分割は、**技術的な制約からは要らない**。

### それでも段階を分ける理由（判断。根拠は下記の実測）

1. **ローテーション時にアプリの revision が再起動される**（項目 2）。
   しかも環境変数で参照していないメインアプリでも起きた。
   chat API キーと Easy Auth の client secret を同じ Container App の secret に同居させると、
   **どちらをローテーションしても両方が巻き添えで再起動する**
2. **ローテーション中は最大 30 分、旧値が使われ続ける**（項目 2。実測 7 分 28 秒 〜 19 分 01 秒）。
   Easy Auth の場合、この間に旧資格情報を Entra から消すと `AADSTS7000215` でサインインできなくなる。
   chat API キーより運用手順が繊細で、手順書の記述量が増える
3. Easy Auth 側には **FIC 化できない別の制約**がある（後述の Issue #1693）。
   将来 FIC に移す前提で設計すると手戻りするため、Easy Auth 側は「当面 Key Vault + 手動ローテーション」と
   割り切った設計判断を先に決めたい

### 提案

- **先行**: chat API キーの Key Vault 参照化（`secrets[].keyVaultUrl` + `env.secretRef`）。項目 2-a の追従時間と再起動の挙動は実測済み
- **後続**: Easy Auth client secret の Key Vault 参照化。実装自体は可能なので、
  ローテーション手順（新バージョン投入 → platform の同期を確認 → 旧資格情報を削除）を手順書に書くことがセットになる
- 分割するかどうかは Issue の粒度の話であり、**技術的なブロック要因は無い**

## felis への持ち帰り（Issue #286 / #280 に書くこと）

### #286（Container Apps secret の Key Vault 参照化）

- Key Vault を作る apply に、実行アカウントへの `Key Vault Secrets Officer` 割当を含める。secret 投入はその後（反映は実測 84 秒以下）
- 作り直し時は `az keyvault purge` を挟む。`az keyvault create` の同名成功は新規作成ではなく回復である可能性が高い（推測）
- `azurerm_key_vault_secret` は `value_wo` / `value_wo_version` で state に値が残らない（実測）。
  azapi の `secrets[].keyVaultUrl` も同じく値が state に入らない（実測）
- `secrets[].keyVaultUrl` をバージョン無しで書くと最新バージョンに追従する。参照用 identity に `Key Vault Secrets User` が要る
- **Easy Auth の `clientSecretSettingName` に Key Vault 参照 secret を指定してサインインできる**（実測）。
  `secrets[]` には `value` を持つ secret を 1 件も置かずに通った
- **Key Vault 参照 secret の新バージョンは、最大 30 分で自動的に取り込まれる。取り込み時に revision が再起動される**（実測）。
  環境変数で参照していないアプリ（authConfigs からのみ参照）でも再起動が起きた
- ローテーション手順は「Key Vault に新バージョンを投入 → platform の同期（`SyncingSecretFromAzureKeyVaultForContainerAppSucceeded`）を確認 → 旧資格情報を Entra から削除」の順にする。
  順序を逆にすると同期までの間 `AADSTS7000215` でサインインできない（実測）
- **`/.auth/me` は Container Apps では 404 を返す。** 疎通確認に使わない
- #286 の分割は技術的には不要（判断の詳細は「#286 を分割する必要があるかの判断」）

### #280（managed identity の用途分割）

- user-assigned identity を複数付けるアプリでは **`AZURE_CLIENT_ID` を必ず明示する**。
  省略すると HTTP 400 `Unable to load the proper Managed Identity.` で失敗する（実測）。先頭 identity への fallback は起きない
- `identitySettings.lifecycle = "None"` はコンテナから identity を隠すが、platform 側の Key Vault 参照は引き続き動く（実測）。
  frontend 用 identity に適用できる
- `identitySettings` の変更は **revision の再起動（または新 revision）が要る**。設定を入れただけでは稼働中の replica に効かない（実測）
- **ロール剥奪は 21 秒以内に効く**（実測）。公式が警告する「約 24 時間のトークンキャッシュ」は
  トークン発行側の話で、Key Vault の data plane 認可には影響しない。移行は「新 identity に付与 → 動作確認 → 旧 identity から剥奪」の順で
- ただし **既に解決済みの Container Apps secret は剥奪後も保持される**。剥奪の検証はアプリの挙動ではなく Key Vault への直接アクセスで行う
- azapi で `identitySettings` を書くときは **`ignore_casing = true`** を併記する。
  ARM が `resourcegroups`（小文字 g）で返すため、無いと差分が消えない（実測）

### 共通（作業計画に効く）

- **Container Apps 環境の上限は 2 段ある。** リージョン単位（`ManagedEnvironmentCount`）と subscription 全体スコープで、
  **後者はどのクォータ API にも項目として存在せず**、エラーコード
  （`MaxNumberOfRegionalEnvironmentsInSubExceeded` / `MaxNumberOfGlobalEnvironmentsInSubExceeded`）でしか区別できない。
  usages を読んで「別リージョンが空いている」と判断して計画を立ててはいけない
- 追加の環境が作れない場合、**検証用の Container App を既存環境に相乗りさせる**ことはできる。
  `managedEnvironmentId` に既存環境の resource ID を書くだけでよく、環境側の設定は変更されない（実測。作業前後の JSON が完全一致）。
  ただし (1) 別 resource group のアプリでもコンソールログは環境側のログ出力先に入る、
  (2) 環境がワークロードプロファイル構成なら `workloadProfileName` の明示が要る、の 2 点に注意する
