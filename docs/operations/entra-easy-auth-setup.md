# Entra ID 側の Easy Auth 準備手順（app registration・app role・割当・テストユーザー）

[ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) 決定 4 / 5 の Entra ID 側
作業の正本。これらは **Terraform 管理外**であり、CI 用 service principal（RG スコープの
Contributor）の権限外のため、**tenant 管理権限を持つユーザー（owner のローカル az）で実行する**
（ADR-0012 の権限境界）。作成したオブジェクトは
[azure-resource-inventory.md](./azure-resource-inventory.md) §B に台帳として記録する。

> client secret は画面に echo せず、発行コマンドの出力を Key Vault `kv-felisaichatbot-dev` の secret
> `easy-auth-client-secret` へ直接パイプする（§1。[ADR-0032](../adr/0032-key-vault-references-for-container-apps-secrets.md) 決定 2）。
> ファイル・tfvars・シェル履歴に残さない。テストユーザーのパスワードは保存しない（§4）。

## 1. app registration（application object）

redirect URI は frontend の FQDN から組み立てる（FQDN は `<APP名>.<CAE 既定ドメイン>` で
決定的なため、frontend 作成前でも登録できる）。

```bash
front_fqdn="ca-felisaichatbot-dev-front.<CAE 既定ドメイン>"   # 例: ....japaneast.azurecontainerapps.io

# app role は allowedMemberTypes = ["User", "Application"] で定義する（ADR-0027 決定 4。
# ["Application"] のみでは人間ユーザーを割当不能）。id は任意の新規 UUID
app_id=$(az ad app create \
  --display-name "felis-ai-chatbot-dev-easyauth" \
  --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "https://${front_fqdn}/.auth/login/aad/callback" \
  --enable-id-token-issuance true \
  --app-roles '[{
    "allowedMemberTypes": ["User", "Application"],
    "description": "felis AI chatbot の利用者（Easy Auth の割当対象）",
    "displayName": "Chat User",
    "id": "'"$(uuidgen)"'",
    "isEnabled": true,
    "value": "Chat.Use"
  }]' \
  --query appId -o tsv)

# client secret: 発行した値を画面・ファイル・履歴に出さず、そのまま Key Vault の secret へパイプする
# （ADR-0032 決定 2。`--append` 必須 = §6-2。実行者には Key Vault Secrets Officer が要る = 台帳 §B #15）。
# `tr -d '\n'` は -o tsv の末尾改行を落とす（改行込みで保存すると認可コードの交換が失敗する）
az ad app credential reset --id "$app_id" --append --display-name "easyauth-$(date -u +%Y%m)" --years 1 \
  --query password -o tsv | tr -d '\n' \
  | az keyvault secret set --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret --file /dev/stdin --output none
# 確認（値は出さない）: 資格情報の本数と失効日、Key Vault 側の有効状態と長さ（40 文字）
az ad app credential list --id "$app_id" --query "[].{displayName:displayName,keyId:keyId,endDateTime:endDateTime}" -o table
az keyvault secret show --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret --query "attributes.enabled" -o tsv
az keyvault secret show --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret --query value -o tsv | tr -d '\n' | wc -c
```

- `easy_auth_client_id`（= `$app_id`）を `terraform/ephemeral/terraform.tfvars` に書く（ADR-0030 決定 3）。
  client secret は Terraform の変数ではない（旧変数 `easy_auth_client_secret` は 2026-10-03 に廃止）。
  frontend の secret `microsoft-provider-authentication-secret` が Key Vault 参照で読み、ephemeral 層の
  precondition は Key Vault に `easy-auth-client-secret` が存在することを plan 時に検査する
- **ローカルの環境変数ファイル（`.env`）には置かない。** 以前は `TF_VAR_easy_auth_client_id` /
  `TF_VAR_easy_auth_client_secret` を export する方式で、ADR-0030 決定 3 で tfvars へ一本化し、
  ADR-0032 で client secret を Key Vault へ移した。環境変数側に残っていれば消す

## 2. enterprise application（service principal）側

到達制御として実際に効くのは role の値ではなく **`appRoleAssignmentRequired = true`** である
（ADR-0027 決定 4。Easy Auth は role claim を検証しない）。

```bash
sp_obj=$(az ad sp create --id "$app_id" --query id -o tsv)
az ad sp update --id "$app_id" --set appRoleAssignmentRequired=true

# OIDC の delegated scope（openid profile email）への管理者同意。テナントがユーザー同意を
# 許可していない場合、これが無いと割当済みユーザーでも AADSTS90094（Need admin approval）で
# 止まる（2026-09-01 実測）。app registration に requiredResourceAccess が無いため
# `az ad app permission admin-consent` は空振りし、oauth2PermissionGrants を直接作成する
graph_sp=$(az ad sp show --id 00000003-0000-0000-c000-000000000000 --query id -o tsv)
az rest --method POST --url https://graph.microsoft.com/v1.0/oauth2PermissionGrants \
  --body '{"clientId":"'"$sp_obj"'","consentType":"AllPrincipals","resourceId":"'"$graph_sp"'","scope":"openid profile email User.Read"}'
```

## 3. 割当（ADR-0027 決定 5 の 3 者）

割当は (i) intended user（project owner）、(ii) 非管理者テストユーザー、(iii) synthetic 用
service principal。(iii) は synthetic transaction SLI の作業単位（execution plan §1 の 6）で
service principal を作成した時点で追加する（それまでは 2 者。割当一覧を検証記録に含める）。

```bash
role_id=$(az ad app show --id "$app_id" --query "appRoles[?value=='Chat.Use'].id" -o tsv)

assign() {  # $1 = principal object id
  az rest --method POST \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/${sp_obj}/appRoleAssignedTo" \
    --body '{"principalId":"'"$1"'","resourceId":"'"$sp_obj"'","appRoleId":"'"$role_id"'"}'
}

assign "$(az ad signed-in-user show --query id -o tsv)"   # owner
assign "<テストユーザーの object id>"                       # §4 で作成後に実行

# 割当一覧（検証記録に含める）
az rest --url "https://graph.microsoft.com/v1.0/servicePrincipals/${sp_obj}/appRoleAssignedTo" \
  --query "value[].{principal:principalDisplayName,type:principalType}" -o table
```

## 4. テストユーザー（非管理者）2 名

成功試験の証跡は**管理者ロールを持たない専用テストユーザー**のブラウザ実測に限定する
（owner の成功は補助記録）。未割当ユーザーのサインインが `AADSTS50105` で拒否されることを
対で記録するため、割当あり / なしの 2 名を作る。

```bash
domain=$(az rest --url "https://graph.microsoft.com/v1.0/domains" \
  --query "value[?isDefault].id" -o tsv)

# パスワードは生成して画面に出さない。保存もしない（実測者が入力できる経路 = mode 600 の一時ファイル等で渡し、
# 実測後に消す）。テストユーザーはチャット実測の完了後にユーザーごと削除する（下記）
az ad user create --display-name "felis test user (assigned)" \
  --user-principal-name "felis-test@${domain}" \
  --password "<generated>" --force-change-password-next-sign-in false
az ad user create --display-name "felis test user (unassigned)" \
  --user-principal-name "felis-test-unassigned@${domain}" \
  --password "<generated>" --force-change-password-next-sign-in false
```

- 割当ありユーザーの object id を §3 の `assign` に渡す。割当なしユーザーには何もしない
- どちらにも管理者ロールを付与しない（作成直後の既定のまま）
- **削除のタイミング**: 未割当ユーザーの `AADSTS50105` と、割当ありユーザーの **`chat_disabled = false` 後のチャット疎通**
  （vnet-integration-cutover.md §7-4 / §7-5）まで両方の証跡を取ってから 2 名とも削除する（§5 のコマンド）。
  `AADSTS50105` の証跡を取った直後に削除するとチャット実測のために作り直しになる（2026-09-19 に実際に起きた =
  [subscription-migration/observations.md §6-3](../verification/subscription-migration/observations.md)）。
  削除すればパスワードのローテーションは不要
- **初回サインインで MFA 登録が必須**: Entra ID のセキュリティの既定値により、新規ユーザーは初回サインインで
  Microsoft Authenticator（または TOTP アプリ）の登録を求められる。実測者は認証アプリを用意しておく。
  未割当ユーザーは password 通過直後に認可で拒否されるため MFA 登録には進まない（2026-09-19 実測）
- **ブラウザの注意**: Chrome のシークレットウィンドウは**ウィンドウ間でセッションを共有する**。2 人目の実測前に
  シークレットウィンドウを**すべて閉じて**からやり直す（閉じないと 1 人目のセッションが流用され、
  どのアカウントの結果か確定できなくなる）

## 5. 後片付け（プロジェクト終了時）

```bash
az ad user delete --id "felis-test@${domain}"
az ad user delete --id "felis-test-unassigned@${domain}"
az ad app delete --id "$app_id"   # service principal も同時に消える
```

## 6. クライアントシークレットを失ったときの復旧

Entra ID はクライアントシークレットの値を保持せず、発行時に一度だけ返す
（Microsoft Graph `application: addPassword`: "There is no way to retrieve this password in the future."
= このパスワードを後から取得する方法は無い。出典:
<https://learn.microsoft.com/en-us/graph/api/application-addpassword?view=graph-rest-1.0> ）。
値の正本は Key Vault の secret `easy-auth-client-secret` で、Terraform state や tfvars には無い（ADR-0032）。

### 6-1. Key Vault から読む（先に試す経路）

```bash
az keyvault secret show --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret --query "attributes.enabled" -o tsv
az keyvault secret list-versions --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret \
  --query "[].{created:attributes.created,enabled:attributes.enabled}" -o table
```

- 値が要る操作（§8 の直接値への rollback など）は `az keyvault secret show ... --query value -o tsv | tr -d '\n'` の
  出力をパイプで直接使い、画面・ファイル・履歴に残さない
- Key Vault ごと失った（destroy して soft-delete 保持 7 日も過ぎた）場合のみ §6-2 で再発行する。
  2026-10-03 以前の ephemeral 層の state バージョンには旧資格情報の値が平文で残っているが、その資格情報は
  同日に Entra から削除済みで使えない

### 6-2. 再発行する（Key Vault から取れない場合のみ）

**`--append` を必ず付ける。** `az ad app credential reset` は既定で既存の資格情報を消す
（公式: "By default, this command clears all passwords and keys, and let graph service generate
a password credential." = 既定ではすべてのパスワードとキーを削除し、Graph サービスに
パスワード資格情報を生成させる。出典:
<https://learn.microsoft.com/en-us/cli/azure/ad/app/credential?view=azure-cli-latest> ）。
`--append` 無しで実行すると**現行のシークレットがその場で無効になり、Key Vault に新しい値を
投入して Container Apps が同期するまで（最長 30 分）frontend のサインインが失敗する**。

```bash
app_id=$(az ad app list --display-name felis-ai-chatbot-dev-easyauth --query "[0].appId" -o tsv)

# 追加発行（既存は消さない）→ Key Vault に新バージョンとして投入（§1 と同じパイプ。値は画面に出さない）
az ad app credential reset --id "$app_id" --append --display-name "easyauth-$(date -u +%Y%m)" --years 1 \
  --query password -o tsv | tr -d '\n' \
  | az keyvault secret set --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret --file /dev/stdin --output none
```

- 投入したら §7 の手順 3 以降（同期の確認 → サインイン実測 → 旧 keyId の削除）を行う
- 値を失った古い資格情報は、新しい値での同期とサインインを確認したあとに
  `az ad app credential delete --id "$app_id" --key-id <古い keyId>` で削除する

## 7. クライアントシークレットのローテーション（1 年ごと）

[ADR-0031](../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md) 決定で
**Easy Auth のクライアントシークレットは残し、1 年ごとにローテーションする**と決めている。
1 つの app registration は複数のクライアントシークレット（`passwordCredentials`）を持てるため、
**重なり期間を作れば認証を止めずに入れ替えられる**（Graph `addPassword` は既存を消さずに追加する。
az CLI では `--append`）。

### 7-1. 期限の確認

```bash
app_id=$(az ad app list --display-name felis-ai-chatbot-dev-easyauth --query "[0].appId" -o tsv)
az ad app credential list --id "$app_id" \
  --query "[].{displayName:displayName,keyId:keyId,startDateTime:startDateTime,endDateTime:endDateTime}" -o table
```

2026-10-03 時点: `easyauth-202610` 1 本のみ、2026-10-03 発行 / **2027-10-03 失効**
（[azure-resource-inventory.md](./azure-resource-inventory.md) §12。Key Vault 参照への切替時に発行し、
旧 `easyauth`（2026-09-19 発行）は同日に削除した）。
**失効したまま放置した場合の挙動は未検証**のため、失効の 1 か月前までに入れ替える。

### 7-2. 入れ替えの順序（Terraform の apply は要らない）

Container Apps の secret はバージョン無しの Key Vault 参照なので、Key Vault に新バージョンを投入すれば
platform が 30 分周期の定期同期で取り込み、frontend の replica を再起動する（`RevisionRestartWithNewSecrets`。
新しい revision は作られない。authConfigs からしか参照していなくても再起動は起きる = 2026-09-22 実測）。
再起動中は `/readyz` が数十秒落ちるので、`gh variable set PROBE_ENABLED --body false` で外形監視を止めてから行い、
確認後に `true` へ戻す。

1. 新しいシークレットを**追加**発行し、そのまま Key Vault に新バージョンとして投入する（§6-2 のパイプ。
   `--append` 必須。`--display-name` は `easyauth-<YYYYMM>` のように発行月で区別する）。投入時刻を控える
2. 同期を待つ: `ContainerAppSystemLogs_CL | where ContainerAppName_s == "ca-felisaichatbot-dev-front" and Reason_s in ("SyncingSecretFromAzureKeyVaultForContainerAppSucceeded", "RevisionRestartWithNewSecrets")`
   に投入時刻より後の行が出るまで（最長 30 分 + 取り込み遅延）。待てない場合は Key Vault 参照を設定し直すと
   直後に同期が走る（`az containerapp secret set ... "microsoft-provider-authentication-secret=keyvaultref:<URL>,identityref:<identity の resource ID>"`
   は secret 名が CLI の 20 文字制限に当たるので使えない。§8 の `az rest` PATCH で同じ `keyVaultUrl` + `identity` を書き直す）
3. platform 側の値が新バージョンと一致することを確認する（`az containerapp secret list --show-values` の該当 value と
   Key Vault 最新版を sha256 で比較。値は画面に出さない）
4. 割当済みユーザーのブラウザで **`https://<frontend FQDN>/.auth/logout` を開いてから** サインインし直す
   （既存のセッション cookie が残っていると client secret を使う認可コードの交換を通らず、確認にならない）。
   sidecar（コンテナ `http-auth`）のログで `oauth2/v2.0/token` の POST が `Completed with 200`、
   `AADSTS7000215` が無いことを確認する。新旧どちらの資格情報も Entra では有効なので、
   **旧シークレットは手順 2 の同期が確認できるまで削除しない**（先に削除すると同期までサインインが失敗する）
5. 旧シークレットを削除する: `az ad app credential delete --id "$app_id" --key-id <旧 keyId>`。
   削除後にもう一度 `/.auth/logout` → サインインで確認する
6. §7-1 を再実行して新しい 1 本だけになっていることを確認し、台帳 §12 の失効日を更新する。
   Key Vault の旧バージョンは参照されないまま残る（削除してもよい）

## 8. Key Vault 参照から直接値へ戻す（rollback）

Key Vault 参照の解決が壊れた（同期が `Failed` し続ける、ロール割当を失った等）ときの最後の手段。
chat API キーで使った `az containerapp secret set --secrets "<name>=<値>"` は、secret 名 `microsoft-provider-authentication-secret`
（40 文字）が CLI の **key 20 文字制限**（`az containerapp secret set --help`）に当たるため使えない。ARM に直接 PATCH する。

```bash
RG=rg-felisaichatbot-dev-tf
APP_ID_RES=$(az containerapp show -g $RG -n ca-felisaichatbot-dev-front --query id -o tsv)
IDENTITY_ID=$(az containerapp show -g $RG -n ca-felisaichatbot-dev --query "properties.configuration.registries[0].identity" -o tsv)
umask 077
# PATCH は secrets 配列を丸ごと置き換えるので、chat-api-key の Key Vault 参照も一緒に書く。値はパイプで埋め、ファイルは mode 600
az keyvault secret show --vault-name kv-felisaichatbot-dev -n easy-auth-client-secret --query value -o tsv | tr -d '\n' \
  | jq -Rs --arg id "$IDENTITY_ID" '{properties:{configuration:{secrets:[
      {name:"chat-api-key", keyVaultUrl:"https://kv-felisaichatbot-dev.vault.azure.net/secrets/chat-api-key", identity:$id},
      {name:"microsoft-provider-authentication-secret", value:.}]}}}' > /tmp/front-secrets-rollback.json
az rest --method patch --url "https://management.azure.com${APP_ID_RES}?api-version=2025-07-01" \
  --body @/tmp/front-secrets-rollback.json --output none
shred -u /tmp/front-secrets-rollback.json
```

- 直接値が入っている間は **ephemeral 層で Terraform を実行しない**（plan も不可。値方式の secret の値が state に書かれる）
- Key Vault 参照へ戻すときは同じ PATCH で `microsoft-provider-authentication-secret` を
  `{name, keyVaultUrl: ".../secrets/easy-auth-client-secret", identity: $id}` にする（値は書かない）。
  `IDENTITY_ID` は上のとおり `registries[0].identity` から取る（`az identity show --query id` は `resourcegroups` 小文字を返し、
  Terraform の表記と食い違って次の plan が差分になる = 2026-09-28 実測）
- 旧資格情報が Entra に残っている間（切替直後）は、Terraform の変更を一時的に戻して旧値で apply する方が単純だった
  （2026-10-03 の切替時の計画）。旧資格情報の削除後はこの §8 だけが戻し方になる
- この手順は**未検証**（2026-10-03 の切替では rollback 演習を省いた）。Key Vault 参照 → 直接値 → Key Vault 参照の往復自体は
  chat API キーで実測済み（[key-vault-secret-references/observations.md](../verification/key-vault-secret-references/observations.md)）

## 関連

- [ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) 決定 4 / 5
- [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — 権限境界
- [ADR-0030](../adr/0030-subscription-migration-and-02-suffix-naming.md) 決定 3 — 秘密値は層ごとの `terraform.tfvars` で渡す
- [ADR-0031](../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md) — 残す秘密値と 1 年ごとのローテーション（§6 / §7）
- [vnet-integration-cutover.md §7](./vnet-integration-cutover.md) — この手順の成果物
  （client id / secret）を使う bootstrap
