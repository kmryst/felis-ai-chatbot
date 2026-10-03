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

- 値が要る操作は `az keyvault secret show ... --query value -o tsv | tr -d '\n'` の出力をパイプで直接使い、画面・ファイル・履歴に残さない。
  ただし §8 の rollback は Key Vault が読めない状況を前提にするため、この値ではなく Entra で新しく発行した値を使う
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

1. **変更前の replica 名を記録する**（切替完了の判定に使う）:
   `az containerapp replica list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-front --revision "$(az containerapp show -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-front --query properties.latestReadyRevisionName -o tsv)" --query "[].{name:name,created:properties.createdTime,state:properties.runningState}" -o table`
2. 新しいシークレットを**追加**発行し、そのまま Key Vault に新バージョンとして投入する（§6-2 のパイプ。
   `--append` 必須。`--display-name` は `easyauth-<YYYYMM>` のように発行月で区別する）。投入時刻を控える
3. 同期を待つ: `ContainerAppSystemLogs_CL | where ContainerAppName_s == "ca-felisaichatbot-dev-front" and Reason_s in ("SyncingSecretFromAzureKeyVaultForContainerAppSucceeded", "RevisionRestartWithNewSecrets")`
   に投入時刻より後の行が出るまで（最長 30 分 + 取り込み遅延）。待てない場合は Key Vault 参照を設定し直すと
   直後に同期が走る（`az containerapp secret set ... "microsoft-provider-authentication-secret=keyvaultref:<URL>,identityref:<identity の resource ID>"`
   は secret 名が CLI の 20 文字制限に当たるので使えない。§8 の `az rest` PATCH で同じ `keyVaultUrl` + `identity` を書き直す）
4. platform 側の値が新バージョンと一致することを確認する（`az containerapp secret list --show-values` の該当 value と
   Key Vault 最新版を sha256 で比較。値は画面に出さない）
5. **replica の切替が終わったことを確認する**: 手順 1 と同じ `az containerapp replica list` で、
   (a) 手順 1 で記録した replica が一覧からすべて消えている（または `runningState` が `Running` でない）、
   (b) それ以外の replica がすべて `Running`、の両方。
   「同期より後に作られた replica」を条件にしてはいけない: 2026-10-03 の切替では新 replica の作成（06:30:32）が同期 `Succeeded`
   のログ（06:30:33 / 34）より先で、その条件では完了と判定できなかった。同期から旧 container の停止（06:30:57）までは数十秒ずれ、
   旧 replica が動いている間は旧い値でサインインが成立し続けるので、ここを飛ばすと手順 6 の確認が旧い値の成功を拾う
6. 割当済みユーザーのブラウザで **`https://<frontend FQDN>/.auth/logout` を開いてから** サインインし直す
   （既存のセッション cookie が残っていると client secret を使う認可コードの交換を通らず、確認にならない）。
   sidecar（コンテナ `http-auth`）のログで `oauth2/v2.0/token` の POST が `Completed with 200`、
   `AADSTS7000215` が無いことを確認する。新旧どちらの資格情報も Entra では有効なので、
   **旧シークレットは手順 4 / 5 / 6 がすべて満たされるまで削除しない**（先に削除すると、同期か replica の切替が終わるまでサインインが失敗する）
7. 旧シークレットを削除する: `az ad app credential delete --id "$app_id" --key-id <旧 keyId>`。
   削除後にもう一度 `/.auth/logout` → サインインで確認する
8. §7-1 を再実行して新しい 1 本だけになっていることを確認し、台帳 §12 の失効日を更新する。
   Key Vault の旧バージョンは参照されないまま残る（削除してもよい）

## 8. Key Vault 参照から直接値へ戻す（rollback）

Key Vault 参照の解決が壊れた（同期が `Failed` し続ける、ロール割当を失った、Key Vault 自体の障害等）ときの最後の手段。
Container Apps は解決済みの値で動き続けるので、サインインが止まるのは次のローテーションか replica の作り直しが起きたときで、
それまでは原因の解消（ロール割当の再作成 = 台帳 §B #15、secret の再有効化）を先に試す。

- chat API キーで使った `az containerapp secret set --secrets "<name>=<値>"` は、secret 名 `microsoft-provider-authentication-secret`
  （40 文字）が CLI の **key 20 文字制限**（`az containerapp secret set --help`）に当たるため使えない。ARM に直接 PATCH する
- **復旧に使う値は Key Vault から取らない。** Key Vault が読めない状況がこの手順の前提であり、障害後に Key Vault へ読みに行く設計では
  戻せない（PR 2 の chat API キーの rollback も、Key Vault を読まずに事前確保した値で戻した）。Easy Auth のクライアントシークレットは
  Entra で `--append` 発行すれば Key Vault に依存せずに有効な値が手に入るので、**復旧用のシークレットを新しく発行してそのまま PATCH に渡す**
- 値の取得が失敗したときに空の値で PATCH しないよう、`set -euo pipefail` と長さの検査を PATCH の実行条件にする。
  秘密値の入った一時ファイルは `mktemp` で作り、スクリプト全体を subshell `( ... )` に入れて `EXIT` の trap で削除する
  （対話シェルに貼り付けても subshell の終了時に動く。`INT` / `TERM` は `exit 130` で明示的に終了させ、中断後に処理が続かないようにする。
  Bash の trap の仕様: <https://www.gnu.org/s/bash/manual/bash.html#Bourne-Shell-Builtins>。`az rest --body` は `@{file}` のみで標準入力は使えない。
  外部コマンドをスタブにした模擬実行（2026-10-03）: 正常終了 / PATCH 失敗 / 発行中の `SIGINT` / PATCH 中の `SIGINT` / 対話シェルへの貼り付け、の
  いずれも一時ファイルが残らなかった。発行中に中断すると PATCH は呼ばれず、PATCH 中に中断すると実行中の PATCH は完了するがその後の処理は続かない）

```bash
# 全体を subshell に入れる: 対話シェルに貼り付けても、subshell の終了時に EXIT の trap が動いて一時ファイルが消える
(
set -euo pipefail
BODY=""
trap 'if [ -n "$BODY" ]; then shred -u "$BODY" 2>/dev/null || rm -f "$BODY"; fi' EXIT
trap 'exit 130' INT TERM   # 中断時は明示的に終了する（EXIT の trap が走り、以後の処理は続かない）
RG=rg-felisaichatbot-dev-tf
APP_ID=$(az ad app list --display-name felis-ai-chatbot-dev-easyauth --query "[0].appId" -o tsv)
FRONT_RES=$(az containerapp show -g $RG -n ca-felisaichatbot-dev-front --query id -o tsv)
IDENTITY_ID=$(az containerapp show -g $RG -n ca-felisaichatbot-dev --query "properties.configuration.registries[0].identity" -o tsv)
REV=$(az containerapp show -g $RG -n ca-felisaichatbot-dev-front --query properties.latestReadyRevisionName -o tsv)
umask 077

# 0. 変更前の replica 名を記録する（§7-2 手順 1。Key Vault 参照へ戻すときの切替完了の判定に使う）
echo "replicas before:"; az containerapp replica list -g $RG -n ca-felisaichatbot-dev-front --revision "$REV" \
  --query "[].{name:name,created:properties.createdTime,state:properties.runningState}" -o table
# 1. 復旧用のシークレットを Entra で追加発行し、値をシェル変数に受ける（画面に出さない。Key Vault を経由しない）
EASY_AUTH_ROLLBACK_SECRET=$(az ad app credential reset --id "$APP_ID" --append \
  --display-name "easyauth-rollback-$(date -u +%Y%m%dT%H%M)" --years 1 --query password -o tsv | tr -d '\n')
# 2. 取得の検査（空・短すぎる値では止める。これまでの実測はいずれも 40 文字）
[ "${#EASY_AUTH_ROLLBACK_SECRET}" -ge 32 ] || { echo "secret length ${#EASY_AUTH_ROLLBACK_SECRET} < 32: abort" >&2; exit 1; }
echo "secret length: ${#EASY_AUTH_ROLLBACK_SECRET}"
# 3. PATCH body（secrets 配列は丸ごと置き換わるので chat-api-key の Key Vault 参照も一緒に書く）。
#    一時ファイルは mktemp（mode 600）。値は環境変数経由で jq に渡し、プロセス引数に出さない
BODY=$(mktemp)
export EASY_AUTH_ROLLBACK_SECRET
jq -n --arg id "$IDENTITY_ID" '{properties:{configuration:{secrets:[
    {name:"chat-api-key", keyVaultUrl:"https://kv-felisaichatbot-dev.vault.azure.net/secrets/chat-api-key", identity:$id},
    {name:"microsoft-provider-authentication-secret", value:env.EASY_AUTH_ROLLBACK_SECRET}]}}}' > "$BODY"
unset EASY_AUTH_ROLLBACK_SECRET
# 4. 生成物の検査: 値が空でないこと（長さだけを見る）。失敗時は EXIT の trap が一時ファイルを消す
[ "$(jq -r '.properties.configuration.secrets[] | select(.name=="microsoft-provider-authentication-secret") | .value | length' "$BODY")" -ge 32 ] \
  || { echo "rollback body has empty value: abort" >&2; exit 1; }
# 5. PATCH（成功・失敗・中断のいずれでも、subshell を抜けるときに EXIT の trap が一時ファイルを shred する）
az rest --method patch --url "https://management.azure.com${FRONT_RES}?api-version=2025-07-01" \
  --body @"$BODY" --output none
az containerapp show -g $RG -n ca-felisaichatbot-dev-front \
  --query "properties.configuration.secrets[].{name:name,kv:keyVaultUrl}" -o json   # Easy Auth の secret は kv が null になる
)
```

- 確認: §7-2 の手順 6 と同じ（`/.auth/logout` → サインイン → sidecar の token POST 200）。新しいシークレットは Entra で即時に有効
- 直接値が入っている間は **ephemeral 層で Terraform を実行しない**（plan も不可。値方式の secret の値が state に書かれる）
- `chat-api-key` の Key Vault 参照は PATCH の body に残す。Key Vault 自体の障害中にこの PATCH が `chat-api-key` の参照の検証で拒否されるかは**未検証**
  （拒否された場合、chat API キーの値は Key Vault にしか無いので直接値にはできない。Container Apps が保持している値で動き続けるのを待つ）
- **Key Vault 参照へ戻す（障害の解消後）**: §6-2 のパイプで**もう 1 本**発行して Key Vault に新バージョンとして投入 → 同じ PATCH で
  `microsoft-provider-authentication-secret` を `{name, keyVaultUrl: "https://kv-felisaichatbot-dev.vault.azure.net/secrets/easy-auth-client-secret", identity: $id}`
  にする（値は書かない。`IDENTITY_ID` は上のとおり `registries[0].identity` から取る。`az identity show --query id` は `resourcegroups` 小文字を返し、
  Terraform の表記と食い違って次の plan が差分になる = 2026-09-28 実測）→ **復旧用の資格情報を削除する前に §7-2 の手順 3 〜 6 を順に満たす**:
  同期 `Succeeded` → platform 側の値の sha256 が Key Vault の最新値と一致 → スクリプト冒頭で記録した replica が一覧から消え（または `Running` でなくなり）、
  それ以外の replica がすべて `Running`（同期から旧 container の停止まで数十秒ずれる。2026-10-03 実測は 06:30:33 → 06:30:57。この間は旧 replica が復旧用の値で
  サインインを通すため、ここで消すと旧 replica でのサインインが失敗する。「同期より後に作られた replica」は条件にしない = §7-2 手順 5）
  → `/.auth/logout` からサインインし直して sidecar の token POST 200 →
  そのうえで `az ad app credential delete` で復旧用の `easyauth-rollback-*` と、それ以前の資格情報を削除し、§7-1 で 1 本だけになっていることを確認 →
  削除後にもう一度 `/.auth/logout` → サインイン → `terraform -chdir=terraform/ephemeral plan -detailed-exitcode` が exit 0
- この手順は**未検証**（2026-10-03 の切替では rollback 演習を省いた）。Key Vault 参照 → 直接値 → Key Vault 参照の往復自体は
  chat API キーで実測済み（[key-vault-secret-references/observations.md](../verification/key-vault-secret-references/observations.md)）

## 関連

- [ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) 決定 4 / 5
- [ADR-0012](../adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — 権限境界
- [ADR-0030](../adr/0030-subscription-migration-and-02-suffix-naming.md) 決定 3 — 秘密値は層ごとの `terraform.tfvars` で渡す
- [ADR-0031](../adr/0031-entra-managed-identity-auth-and-remaining-secrets.md) — 残す秘密値と 1 年ごとのローテーション（§6 / §7）
- [vnet-integration-cutover.md §7](./vnet-integration-cutover.md) — この手順の成果物
  （client id / secret）を使う bootstrap
