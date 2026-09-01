# Entra ID 側の Easy Auth 準備手順（app registration・app role・割当・テストユーザー）

[ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) 決定 4 / 5 の Entra ID 側
作業の正本。これらは **Terraform 管理外**であり、CI 用 service principal（RG スコープの
Contributor）の権限外のため、**tenant 管理権限を持つユーザー（owner のローカル az）で実行する**
（ADR-0012 の権限境界）。作成したオブジェクトは
[azure-resource-inventory.md](./azure-resource-inventory.md) §B に台帳として記録する。

> secret（client secret・テストユーザーのパスワード）は画面に echo せず、`.env`
> （コミット禁止）にのみ保存する。

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

# client secret（値は表示せず .env の TF_VAR_easy_auth_client_secret へ保存する）
az ad app credential reset --id "$app_id" --append --display-name easyauth --years 1 \
  --query password -o tsv > /dev/null   # 実際は値を安全に .env へ書き込むこと
```

- `TF_VAR_easy_auth_client_id`（= `$app_id`）と `TF_VAR_easy_auth_client_secret` を `.env` に
  保存し、`set -a; source .env; set +a` で export する

## 2. enterprise application（service principal）側

到達制御として実際に効くのは role の値ではなく **`appRoleAssignmentRequired = true`** である
（ADR-0027 決定 4。Easy Auth は role claim を検証しない）。

```bash
sp_obj=$(az ad sp create --id "$app_id" --query id -o tsv)
az ad sp update --id "$app_id" --set appRoleAssignmentRequired=true
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

# パスワードは生成して .env に保存し、画面に出さない
az ad user create --display-name "felis test user (assigned)" \
  --user-principal-name "felis-test@${domain}" \
  --password "<generated>" --force-change-password-next-sign-in false
az ad user create --display-name "felis test user (unassigned)" \
  --user-principal-name "felis-test-unassigned@${domain}" \
  --password "<generated>" --force-change-password-next-sign-in false
```

- 割当ありユーザーの object id を §3 の `assign` に渡す。割当なしユーザーには何もしない
- どちらにも管理者ロールを付与しない（作成直後の既定のまま）
- ブラウザ実測にパスワードを入力した場合は、実測完了後に
  `az ad user update --id <upn> --password <新値>` でローテーションする

## 5. 後片付け（プロジェクト終了時）

```bash
az ad user delete --id "felis-test@${domain}"
az ad user delete --id "felis-test-unassigned@${domain}"
az ad app delete --id "$app_id"   # service principal も同時に消える
```

## 関連

- [ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) 決定 4 / 5
- [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — 権限境界
- [vnet-integration-cutover.md §7](./vnet-integration-cutover.md) — この手順の成果物
  （client id / secret）を使う bootstrap
