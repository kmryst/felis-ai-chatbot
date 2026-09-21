# Entra ID 側の Easy Auth 準備手順（app registration・app role・割当・テストユーザー）

[ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) 決定 4 / 5 の Entra ID 側
作業の正本。これらは **Terraform 管理外**であり、CI 用 service principal（RG スコープの
Contributor）の権限外のため、**tenant 管理権限を持つユーザー（owner のローカル az）で実行する**
（ADR-0012 の権限境界）。作成したオブジェクトは
[azure-resource-inventory.md](./azure-resource-inventory.md) §B に台帳として記録する。

> client secret は画面に echo せず、`terraform/ephemeral/terraform.tfvars`（gitignore 済み・コミット禁止）
> にのみ保存する。テストユーザーのパスワードは保存しない（§4）。

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

# client secret（値は表示せず terraform/ephemeral/terraform.tfvars の easy_auth_client_secret へ保存する）
az ad app credential reset --id "$app_id" --append --display-name easyauth --years 1 \
  --query password -o tsv > /dev/null   # 実際は値を安全に terraform.tfvars へ書き込むこと（画面に出さない）
```

- `easy_auth_client_id`（= `$app_id`）と `easy_auth_client_secret` を `terraform/ephemeral/terraform.tfvars` に
  書く（ADR-0030 決定 3: 秘密値は層ごとの tfvars で渡し、`TF_VAR_*` の export と混在させない）
- **ローカルの環境変数ファイル（`.env`）には置かない。** 以前は `TF_VAR_easy_auth_client_id` /
  `TF_VAR_easy_auth_client_secret` を export する方式で、ADR-0030 決定 3 で tfvars へ一本化した。
  両方に持つと、どちらの値が apply に効いたのか追えず、ローテーション（§7）で古い値が残る。
  これらを読むのは ephemeral 層の Terraform だけなので、環境変数側に残っていれば消す

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
`terraform/ephemeral/terraform.tfvars` を失ってもシークレット自体は失効していないので、
**再発行の前に Terraform state を確認する**。

### 6-1. state から取り出す（先に試す経路）

ephemeral 層の state には frontend Container App の secret
`microsoft-provider-authentication-secret` として平文で入っている（ADR-0031「影響」の
「state に残る秘密値」）。**2026-09-21 に取り出せることを確認済み**（値は取り出さず、
存在と長さだけを確認した）。

```bash
terraform -chdir=terraform/ephemeral state pull \
  | jq -r '.resources[]
           | select(.type=="azurerm_container_app" and .name=="front")
           | .instances[].attributes.secret[]
           | select(.name=="microsoft-provider-authentication-secret") | .value' \
  | wc -c          # まず長さだけ確認する（値を画面に出さない）
```

- 値を戻すときも画面とシェル履歴に出さない。上記の `| wc -c` を
  `> terraform/ephemeral/secret.tmp` 等（mode 600・書き戻し後に削除）に替えて
  `terraform.tfvars` の `easy_auth_client_secret` へ貼り、一時ファイルを消す
- frontend Container App を destroy 済みで state に `azurerm_container_app.front` が無い場合、
  この経路は使えない（§6-2 へ）

### 6-2. 再発行する（state から取れない場合のみ）

**`--append` を必ず付ける。** `az ad app credential reset` は既定で既存の資格情報を消す
（公式: "By default, this command clears all passwords and keys, and let graph service generate
a password credential." = 既定ではすべてのパスワードとキーを削除し、Graph サービスに
パスワード資格情報を生成させる。出典:
<https://learn.microsoft.com/en-us/cli/azure/ad/app/credential?view=azure-cli-latest> ）。
`--append` 無しで実行すると**現行のシークレットがその場で無効になり、新しい値で
ephemeral 層を apply し直すまで frontend のサインインが失敗する**。

```bash
app_id=$(az ad app list --display-name felis-ai-chatbot-dev-easyauth --query "[0].appId" -o tsv)

# 追加発行（既存は消さない）。値は画面に出さず terraform.tfvars へ書き込む
az ad app credential reset --id "$app_id" --append \
  --display-name "easyauth-$(date -u +%Y%m)" --years 1 --query password -o tsv > /dev/null
```

- 書き戻したら §7 の手順 3 以降（plan → apply → サインイン実測 → 旧 keyId の削除）を行う
- 値を失った古い資格情報は、新しい値で apply して疎通を確認したあとに
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

2026-09-21 時点: `easyauth` 1 本のみ、2026-09-19 発行 / **2027-09-19 失効**
（[azure-resource-inventory.md](./azure-resource-inventory.md) §12）。
**失効したまま放置した場合の挙動は未検証**のため、失効の 1 か月前までに入れ替える。

### 7-2. 入れ替えの順序

1. 新しいシークレットを**追加**発行する（§6-2 のコマンド。`--append` 必須。
   `--display-name` は `easyauth-<YYYYMM>` のように発行月で区別する）
2. `terraform/ephemeral/terraform.tfvars` の `easy_auth_client_secret` を新しい値に差し替える。
   編集前のコピーを `backup-before-*.tfvars`（gitignore 済み・Terraform は自動読込しない）に残す
   （[entra-auth-cutover.md](./entra-auth-cutover.md) §6）
3. `terraform -chdir=terraform/ephemeral plan` が frontend Container App の in-place update
   （secret + authConfigs）だけで、destroy / replacement を含まないことを確認してから apply する
4. 割当済みユーザーのブラウザで frontend にサインインできることを実測する
   （新旧どちらの値でも Entra は検証するため、この時点では旧シークレットも生きている）
5. 旧シークレットを削除する: `az ad app credential delete --id "$app_id" --key-id <旧 keyId>`
6. §7-1 を再実行して新しい 1 本だけになっていることを確認し、台帳 §12 の失効日を更新する

## 関連

- [ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) 決定 4 / 5
- [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — 権限境界
- [ADR-0030](../adr/0030-subscription-migration-and-02-suffix-naming.md) 決定 3 — 秘密値は層ごとの `terraform.tfvars` で渡す
- [ADR-0031](../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md) — 残す秘密値と 1 年ごとのローテーション（§6 / §7）
- [vnet-integration-cutover.md §7](./vnet-integration-cutover.md) — この手順の成果物
  （client id / secret）を使う bootstrap
