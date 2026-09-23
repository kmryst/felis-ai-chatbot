# ADR-0032: Container Apps の secret を Azure Key Vault 参照にし、残る秘密値を tfvars と Terraform state から外す

## ステータス

Proposed

（Issue #286 の PR 1 で起票。chat API キー（PR 2）と Easy Auth クライアントシークレット（PR 3）の切り替えを
実測で確認した時点で Accepted にする）

## 日付

2026-09-23

## 決定内容

1. **Easy Auth のクライアントシークレットと chat API キーを Azure Key Vault（Standard、Azure RBAC 権限モデル）に置き、
   Container Apps の secret をバージョン無しの Key Vault 参照（`key_vault_secret_id` + `identity`）にする。**
   参照の解決には既存の user-assigned managed identity `id-felisaichatbot-dev` を使う
   （identity の用途別分割は [Issue #280](https://github.com/kmryst/felis-ai-chatbot/issues/280) で扱い、本 ADR の後に行う）。
2. **値の投入経路を秘密値ごとに分ける。**
   - Easy Auth クライアントシークレット: 人が Entra で `--append` 発行した値を、画面・ファイル・シェル履歴に出さずに
     `az keyvault secret set` で投入する。Terraform は値に触れない（`terraform.tfvars` の `easy_auth_client_secret` を廃止する）
   - chat API キー: persistent 層の ephemeral resource `random_password` で生成し、`azurerm_key_vault_secret` の
     write-only argument `value_wo` / `value_wo_version` で書く。値は state にも plan にも残らない
3. **ローテーションは Key Vault の新バージョン作成だけで行う。** Container Apps は 30 分以内に新バージョンを取り込み、
   revision を再起動する（`RevisionRestartWithNewSecrets`。新しい revision は作られない）。
   chat API キーの `CHAT_API_KEY_CONFIG_CHECKSUM`（[ADR-0027](0027-frontend-azure-deployment-and-public-surface.md)「付随する決定」）は不要になるので廃止する
4. **ロール割当は Terraform に含めない。** identity に `Key Vault Secrets User`、所有者アカウントに
   `Key Vault Secrets Officer` を、いずれも Key Vault スコープで手動作成し、台帳 §B で管理する
   （[ADR-0012](0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) の権限境界。AcrPull・`Cognitive Services OpenAI User` と同じ扱い）
5. **Key Vault 参照の同期失敗を log search alert で検知する。** `ContainerAppSystemLogs_CL` の
   `Reason_s == "SyncingSecretFromAzureKeyVaultForContainerAppFailed"` を 15 分ごと・ウィンドウ 1 時間で評価し、
   既存の Action Group へ通知する。あわせて Key Vault の `AuditEvent` を diagnostic setting で Log Analytics に送る
6. **Key Vault は persistent 層に置く。soft-delete の保持は 7 日、purge protection は無効。**
   provider の `features.key_vault` で destroy 時の purge を有効にし、soft-delete 中の同名リソースの回復は無効にする
7. **ネットワーク制限（firewall / private endpoint）は付けない。** public endpoint + Entra 認証 + RBAC で始める
8. **権限境界への影響を受け入れる。** 将来 CI 用 service principal を作る場合、persistent 層の
   `azurerm_key_vault_secret` を refresh するために Key Vault の data plane の読み取り権限が要る
   （ロール割当は決定 4 のとおり手動で与える）

## 背景

- [ADR-0031](0031-entra-managed-identity-auth-and-remaining-secrets.md) で DB と Azure OpenAI の認証を managed identity の
  Microsoft Entra 認証へ移し、残す秘密値を Easy Auth のクライアントシークレットと chat API キーの 2 つに限定した。
  このとき「Container Apps の `secret` ブロックに write-only 版が無い」ことを理由に、2 つの値が Terraform state に平文で残ることを受け入れた
- 「残す」ことと「平文で持つ」ことは別の問題である。Container Apps の secret は Key Vault を参照でき、
  公式ドキュメントも本番環境では値を直接指定せず Key Vault 参照を使うよう勧めている
  > "Avoid specifying the value of a secret directly in a production environment. Instead, use a reference to a secret stored in Azure Key Vault"
  > （本番環境では secret の値を直接指定せず、Azure Key Vault に保存した secret への参照を使うこと）
  > 出典: <https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets>
- 2026-09-22 に検証環境で次のことを実測した（[docs/verification/key-vault-and-identity-sandbox/observations.md](../verification/key-vault-and-identity-sandbox/observations.md)）
  - Easy Auth の `clientSecretSettingName` に Key Vault 参照の secret を指定してサインインできる
  - Key Vault の新バージョンは、環境変数経由で 19 分 01 秒、Easy Auth sidecar で 7 分 28 秒で取り込まれた。いずれも revision の再起動を伴い、新しい revision は作られない
  - identity のロールを外すと、アプリは解決済みの値で動き続け、30 分ごとの同期だけが `SyncingSecretFromAzureKeyVaultForContainerAppFailed`（403 `ForbiddenByRbac`）で失敗する
  - `value_wo` と Key Vault 参照は、どちらも値を state に残さない
  - `az keyvault secret set` には `Key Vault Secrets Officer` が要り、subscription の Owner では実行できない
  - soft-delete 中の同名 Key Vault は ARM の PUT では作れない（`ConflictError`）が、`az keyvault create` は同名を通す（soft-delete からの回復と推測）
- Easy Auth のクライアントシークレットを federated identity credential で置き換える方法は、Container Apps では現状使えない
  （secret 名が小文字に強制されるため。<https://github.com/microsoft/azure-container-apps/issues/1693>）。
  Easy Auth のシークレットは当面残り、1 年ごとにローテーションする

## 検討した選択肢

### 秘密値の保管場所

- **A. Azure Key Vault に置き、Container Apps の secret を Key Vault 参照にする（採択）**: tfvars と state から値が消える。
  ローテーションが Key Vault の新バージョン作成だけで済み、Terraform apply が要らない。Key Vault の操作数課金と、ロール割当・監視の運用が増える
- B. 現状維持（値方式の secret。state に平文）: 運用は増えないが、state に到達できる主体に値が見える。
  tfstate の Storage Account は blob のバージョニングが有効で、過去の state にも値が残り続ける
- C. 値方式の secret のまま、state の到達面だけを絞る（Issue #87）: 値は state に残る。B の緩和であって解消ではない
- D. ADR-0031 の選択肢 B（Key Vault への集約）をそのまま却下したままにする: ADR-0031 は Entra 認証と比べて劣後させたのであり、
  Entra 認証に移せない 2 つの値に対しては、Key Vault が state から値を外す唯一の手段である

### 値の投入経路

- **A. Easy Auth は人が投入、chat API キーは Terraform の write-only argument（採択）**: Easy Auth は Entra での発行が人の操作であり、
  Terraform を経由させると値が tfvars に戻る。chat API キーは人が値を扱わずに生成でき、`value_wo_version` でローテーションを表せる
- B. 両方とも人が投入する: chat API キーの生成を人に戻すことになり、ADR-0031 決定 4（人が扱う秘密値から外す）に逆行する
- C. 両方とも Terraform の `value`（write-only でない）で書く: 値が state に平文で残り、本 ADR の目的に反する

### Key Vault の配置と削除保護

- **A. persistent 層、soft-delete 保持 7 日、purge protection 無効、destroy で purge（採択）**: soft-delete は無効化できず、
  soft-delete 中は同名で作り直せないため、destroy と再作成を前提にする ephemeral 層（ADR-0015）には置けない。
  purge protection を有効にすると保持期間が過ぎるまで同名で作り直せず、revive runbook（destroy 後に apply だけで戻す）が成立しない。
  誤って削除しても、Easy Auth のシークレットは Entra で再発行、chat API キーは Terraform で再生成できる
- B. purge protection を有効にする: 誤削除から値を守れるが、失う値はいずれも作り直せる。名前が最長 90 日ロックされる不利益の方が大きい
- C. soft-delete 中の同名 Key Vault を自動で回復する（provider の `recover_soft_deleted_key_vaults = true`）: 古い値や設定を黙って持ち込む。
  作り直しは purge を挟んだ新規作成に限る

### 同期失敗の検知

- **A. `ContainerAppSystemLogs_CL` の log search alert（採択）**: 同期失敗はアプリの挙動に現れない（実測）。
  Container Apps が記録する同期失敗イベントを直接見るのが唯一の直接的な信号である
- B. アプリの死活監視（`/readyz`）に任せる: 解決済みの値で動き続けるため、次の再起動かローテーションまで検知できない
- C. Key Vault の `ServiceApiResult`（403）のメトリクスアラート: 他の主体の 403 も拾い、どの Container App の同期かが分からない

### ネットワーク制限

- **A. 付けない（採択）**: Azure Container Apps は Key Vault firewall の trusted services に含まれず、有効化には
  Container Apps 環境のサブネットからの VNet ルール（service endpoint）か private endpoint が要る
  （<https://learn.microsoft.com/en-us/azure/key-vault/general/overview-vnet-service-endpoints#trusted-services>）。
  [ADR-0018](0018-postgresql-private-access-and-vnet-integration.md) と同じ判断軸で別 Issue として検討する
- B. private endpoint を付ける: private DNS zone と endpoint の追加で構成と課金が増える。本 ADR の目的（state からの除去）と独立

## 採択理由

- 残す 2 つの秘密値を、廃止せずに tfvars と Terraform state から外せる。state に到達できる主体に値が見えなくなる
- 実測で、Easy Auth を含めて技術的な障害が無いことを確認できた（分割の必要が無い）
- ローテーションが Terraform apply を要しない操作になり、1 年ごとの Easy Auth のローテーションで tfvars を編集しなくて済む
- 失敗の仕方（アプリは動き続け、同期だけが失敗する）が実測で分かっており、それに合った監視を最初から入れられる

## 影響

- **Terraform（persistent 層）**: `azurerm_key_vault.main`、`azurerm_monitor_diagnostic_setting.key_vault`、
  `azurerm_monitor_scheduled_query_rules_alert_v2.kv_secret_sync_failed`、`azurerm_key_vault_secret.chat_api_key`、
  ephemeral resource `random_password.chat_api_key`、変数 `key_vault_name` / `chat_api_key_version`。provider に `hashicorp/random 3.9.1` と `features.key_vault` を追加
- **Terraform（ephemeral 層。PR 2 / PR 3）**: `data "azurerm_key_vault"` で参照し、serving と frontend の secret を Key Vault 参照にする。
  `random_password.chat_api_key`、変数 `chat_api_key_rotation` / `easy_auth_client_secret`、output `chat_api_key`、
  env `CHAT_API_KEY_CONFIG_CHECKSUM` を削除する。frontend の precondition は Key Vault の secret の存在確認（値を state に読まない方法）に置き換える
- **Terraform 管理外（台帳 §B）**: Key Vault スコープのロール割当 2 件
- **初回作成の順序**: Key Vault 本体を `-target` で先に作る → ロール割当 2 件を手動で作る（反映は実測 84 秒以内）→ 全体を apply する。
  `Key Vault Secrets Officer` が付く前に `azurerm_key_vault_secret` を作ると 403 で失敗する
- **運用**: ローテーション中はアプリの revision が再起動される（瞬断がある）。Easy Auth の旧資格情報は、
  新バージョンの同期とサインインを確認してから Entra から削除する（順序を逆にすると同期までサインインできない）
- **rollback**: Key Vault 参照から直接値へは az CLI で戻す。直接値が入っている間は ephemeral 層で Terraform を実行しない
  （値方式の secret の値が state に書かれるため）。手順は PR 2 / PR 3 の手順書に置く
- **課金**: Key Vault Standard の操作数、log search alert 1 件、`AuditEvent` の取り込み。7 日間の実測から月額を推定して記録する（PR 4）
- **過去の state**: tfstate の blob バージョニングにより、過去のバージョンには切り替え前の値が残る。
  切り替え時に chat API キーは新しい値に置き換わり、Easy Auth の旧資格情報は Entra から削除するため、残った値は使えない値になる

## 関連

- [Issue #286](https://github.com/kmryst/felis-ai-chatbot/issues/286) — 本 ADR の作業 Issue
- [Issue #287](https://github.com/kmryst/felis-ai-chatbot/issues/287) / [docs/verification/key-vault-and-identity-sandbox/observations.md](../verification/key-vault-and-identity-sandbox/observations.md) — 事前の実測
- [Issue #280](https://github.com/kmryst/felis-ai-chatbot/issues/280) — identity の用途別分割（本 ADR の後に行う）
- [ADR-0012](0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — ロール割当を Terraform に含めない理由
- [ADR-0013](0013-azure-resource-naming-convention.md) — Key Vault 名 `kv-felisaichatbot-dev`
- [ADR-0015](0015-ephemeral-layer-acr-container-apps-design.md) — 層の分離、data source 参照
- [ADR-0027](0027-frontend-azure-deployment-and-public-surface.md) — Easy Auth / BFF / chat API キーと checksum
- [ADR-0030](0030-subscription-migration-and-02-suffix-naming.md) — 決定 3（秘密値は層ごとの tfvars で渡す）の適用範囲が狭まる
- [ADR-0031](0031-entra-managed-identity-auth-and-remaining-secrets.md) — 残す秘密値の決定。本 ADR が「state に残る秘密値」を解消する
- [docs/verification/key-vault-secret-references/observations.md](../verification/key-vault-secret-references/observations.md) — 本 ADR の実施記録
- [azure-resource-inventory.md](../operations/azure-resource-inventory.md) — §A の Key Vault、§B のロール割当
