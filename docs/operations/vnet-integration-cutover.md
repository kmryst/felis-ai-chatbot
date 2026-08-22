# VNet 統合カットオーバー手順（public access → private access。ADR-0018）

[ADR-0018](../adr/0018-postgresql-private-access-and-vnet-integration.md) の移行を実行する手順の正本。
**PostgreSQL はネットワーク方式を変えられないため再作成になる**（テーブル 0 件・バックアップ Full 1 件のみの
状態で実施する前提。データ引き継ぎはしない）。時刻・出力はすべて実行時に記録し、証跡は
`docs/verification/` 配下に残す。

> 実行前提: すべての apply / destroy は Azure への書き込みであり、CLAUDE.md の禁止事項に従い
> **ユーザーの明示承認を得てから**実行する。本書は手順の正本であって実行許可ではない。

## 0. 事前確認（読み取りのみ）

```bash
# ephemeral 層が destroy 済みであること（Azure に残るのは PostgreSQL / マネージド ID / Log Analytics の 3 件）
az resource list -g rg-felisaichatbot-dev-tf -o table

# 捨ててよい状態の確認: テーブル 0 件・バックアップ履歴（earliestRestoreDate）を記録
az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --query "{state: state, earliestRestoreDate: backup.earliestRestoreDate}" -o json
```

- `terraform/persistent/terraform.tfvars` から `firewall_allowed_client_ips` の行を削除する
  （変数自体が削除されたため。残すと undeclared variable の警告が出る）

### 0-1. リソースプロバイダー登録（apply より前に必須。Azure への書き込み = 要ユーザー承認）

このサブスクリプションでは `Microsoft.Network`（VNet の作成に必要）と `Microsoft.ContainerService`
（CAE の custom VNet 構成に必要。出典: [Integrate a virtual network with an Azure Container Apps
environment](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom) に
"Register the `Microsoft.ContainerService` provider" と明記）が **NotRegistered** であり
（2026-08-22 読み取り実測）、登録しないまま §1 の apply を実行すると
`409 MissingSubscriptionRegistration` で失敗する（Day 3 に別 namespace で実際に踏んだエラー。
[walking-skeleton/observations.md](../verification/walking-skeleton/observations.md)）。

```bash
# 現状確認（読み取りのみ）
az provider show -n Microsoft.Network --query registrationState -o tsv
az provider show -n Microsoft.ContainerService --query registrationState -o tsv

# NotRegistered の場合のみ登録する（サブスクリプション単位の書き込み操作。ローカルの Owner で実行）
az provider register --namespace Microsoft.Network --wait
az provider register --namespace Microsoft.ContainerService --wait

# 両方 Registered になったことを確認してから §1 へ進む
az provider show -n Microsoft.Network --query registrationState -o tsv
az provider show -n Microsoft.ContainerService --query registrationState -o tsv
```

- **Terraform の自動登録（provider の `resource_provider_registrations` 等）には任せない**。
  プロバイダー登録はサブスクリプション単位の操作で、CI の service principal（RG スコープの
  Contributor）には実行権限がない（`/register/action` はサブスクリプションスコープ。Day 3 の 409 と
  Owner 手動登録の実測記録は上記 observations.md）。Terraform に任せると「ローカル（Owner）では通るが
  CI では落ちる」構成になり、CI 経由デプロイ（Issue #82）で必ず踏む。手動登録を前提作業として固定する
- 登録済み・未登録の全 namespace の一覧は
  [azure-resource-inventory.md](./azure-resource-inventory.md) の「リソースプロバイダー登録」節が正本

### 0-2. 必須変数の export（最初の plan より前。値を画面に出さない）

Terraform は `.env` を自動では読まない。`terraform.tfvars` にも secret は書かない方針のため、
必要な値を **`TF_VAR_*` 環境変数**として export してから plan / apply に入る。§2 の ACR-only apply も
必須変数 `container_image` が未指定だと入力プロンプトで停止し、full apply は `database_url` が空だと
ops リソースの precondition で失敗する。

```bash
# 1) 使うイメージタグは「実際に ACR へ push 済みの SHA」= .env の DEPLOY_SHA が正本。
#    HEAD から再計算しない（理由は本節末尾の注意）。DEPLOY_SHA は §2 で push に成功した
#    ときだけ書き戻す。初回（まだ一度も push していない）は未設定のままでよく、§2 の
#    push 後に書き戻してから本節を再実行する

# 2) .env から secret と DEPLOY_SHA を読み込む（値を画面に echo しない）。
#    .env に TF_VAR_database_url が無ければ、TF_VAR_administrator_password と同じ作法で
#    追記してから実行する（値の形式は terraform/ephemeral/variables.tf の database_url を参照）
set -a; source .env; set +a

# 3) serving / ops 両イメージ参照（DEPLOY_SHA 未設定なら :? で即失敗する。
#    初回で §2 の push がまだなら、この 2 行を飛ばして §2 へ進む）
export TF_VAR_container_image="felisaichatbotacrdev.azurecr.io/backend:sha-${DEPLOY_SHA:?DEPLOY_SHA が .env に無い（§2 の push 後に書き戻す）}"
export TF_VAR_ops_container_image="felisaichatbotacrdev.azurecr.io/backend-ops:sha-${DEPLOY_SHA:?}"

# 4) 設定の有無だけ確認する（値は表示しない）
env | grep -o '^TF_VAR_[A-Za-z_]*' | sort
# → TF_VAR_administrator_password / TF_VAR_container_image /
#   TF_VAR_database_url / TF_VAR_ops_container_image の 4 つに加え、
#   /chat 保護（#107）導入後は TF_VAR_chat_api_key / TF_VAR_chat_disabled が並ぶこと
```

- **この環境変数は §1〜§4 の apply / destroy 全体で維持する**（同じシェルで通しで実行する。
  シェルを開き直したら本節を再実行する）
- **注意（タグを HEAD から再計算してはいけない理由）**: 以前の手順は 1) で
  `git rev-parse --short HEAD` を実行していたが、push は §2 の一度だけなのに対し HEAD は
  実測記録のコミット等で進むため、あとから本節を再実行する Day 4 の apply（計画書 §4-3 の 8 /
  §4-5）が **push していないタグ**を参照し、新 revision が `ErrImagePull` で起動しなくなる。
  また `git rev-parse --short HEAD` は**作業ツリーが dirty でも同じ値を返す**ため、
  タグがビルド内容を同定しない（未コミットの変更込みでビルドしても同じタグになる）。
  push した時点の SHA を `.env` の `DEPLOY_SHA` に固定し、build / push したときだけ更新する
- `TF_VAR_database_url` のホスト部は §1 の apply 後に新 FQDN へ更新が必要になる（§1 参照。
  更新したら `.env` を編集して本節の 2) を再実行する）

## 1. persistent 層の再作成（PostgreSQL が作り直される）

```bash
# plan で「pgsql が destroy → create（replace）される」「firewall rule が destroy される」
# 「VNet / subnet ×2 / private DNS zone / VNet link が add される」
# 「geo_redundant_backup_enabled が false → true になる（replace 要因のひとつ。ADR-0019）」
# ことを確認してから apply する
terraform -chdir=terraform/persistent plan
terraform -chdir=terraform/persistent apply
```

- 依存順序はコードが持っている: VNet → サブネット / private DNS zone → **VNet link → PostgreSQL**
  （link 完成前のサーバー作成は失敗し得るため `depends_on` で明示済み）
- **B1ms × private access は「明文の禁止がない」根拠のみで未確定**（ADR-0018）。ここで失敗したら
  その時点のエラーを記録し、GP 最小 SKU での作成可否を切り分ける
- 再作成後のサーバーは geo 冗長バックアップ有効（ADR-0019）。**作成後 1 時間はペアリージョンへの
  レプリケーション待ちのため geo リストアできない**（"After you create a server, wait at least one hour
  before initiating a geo-restore." 出典:
  <https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore> ）。
  Day 4 の PITR ドリルには影響しない（PITR と geo リストアは別経路）
- apply 後、新しい接続先 FQDN を取得する（private DNS zone 配下の名前に変わる）:

```bash
terraform -chdir=terraform/persistent output server_fqdn
```

- `.env` / CI secret の `TF_VAR_database_url` のホスト部をこの FQDN に更新する（`sslmode=require` は維持）。
  更新後に §0-2 の 2)（`set -a; source .env; set +a`）を再実行して export を反映する。
  **作業端末からこの FQDN へは到達できなくなるのが正常**（psql 検証は §3 の ops 経由で行う）

## 2. ephemeral 層の apply（2 段階。egress IP 依存の旧 2 段階とは別物）

旧構成の「firewall rule の for_each が outbound IP に依存するための 2 段階 apply」は廃止された。
残るのは「ACR にイメージが無いと Container App / Job が作れない」というイメージ押し込みの段階のみ。

変数はすべて §0-2 で export 済みの `TF_VAR_*` から渡る（コマンドラインに `-var` で secret を
並べない）。`TF_VAR_database_url` が §1 の新 FQDN へ更新済みであることを先に確認する。

```bash
# 第 1 段: ACR だけ先に作る（-target でも container_image は必須変数のため、
# TF_VAR_container_image が無いと入力プロンプトで停止する。初回で §0-2 の 3) を飛ばした
# 場合は、実在しない暫定値で export してよい — この段は ACR しか作らず、イメージは参照されない）
# export TF_VAR_container_image="felisaichatbotacrdev.azurecr.io/backend:sha-bootstrap"   # 初回のみ
# export TF_VAR_ops_container_image="felisaichatbotacrdev.azurecr.io/backend-ops:sha-bootstrap"
terraform -chdir=terraform/ephemeral apply -target=azurerm_container_registry.main

# イメージ投入（serving と ops の 2 本）。push するタグはここで確定する。
# git rev-parse --short HEAD は作業ツリーが dirty でも同じ値を返す（= タグがビルド内容を
# 同定しない）ため、先に作業ツリーが clean であることを確認する
git status --short          # 出力が空（clean）であることを確認してから進む
NEW_SHA=$(git rev-parse --short HEAD)
az acr login --name felisaichatbotacrdev
docker build -t felisaichatbotacrdev.azurecr.io/backend:sha-$NEW_SHA backend/
docker build --target ops -t felisaichatbotacrdev.azurecr.io/backend-ops:sha-$NEW_SHA backend/
docker push felisaichatbotacrdev.azurecr.io/backend:sha-$NEW_SHA
docker push felisaichatbotacrdev.azurecr.io/backend-ops:sha-$NEW_SHA

# 2 本とも push に成功したら、.env の DEPLOY_SHA を $NEW_SHA へ書き戻す（無ければ追記。
# .env はコミットしない）。以後の apply（Day 4 の向け替え / 戻しを含む）はこの push 済み
# タグを使い、HEAD が進んでも影響を受けない。書き戻したら §0-2 の 2)〜4) を再実行して
# TF_VAR_container_image / TF_VAR_ops_container_image を反映する

# 第 2 段: 残り全部（CAE + app + ops app + migration Job）。
# container_image / ops_container_image / database_url は TF_VAR_* から渡る（§0-2）
terraform -chdir=terraform/ephemeral apply
```

- CAE は workload profiles + custom VNet になったため作成時間が伸びる可能性がある（実測して記録）
- apply 後の検証: `curl -i https://$(terraform -chdir=terraform/ephemeral output -raw container_app_fqdn)/readyz`
  が 200 / `db: "ok"` を返すこと（= VNet 内経路での `SELECT 1` 開通）

## 3. ops 結線（マイグレーションと psql 経路の確認）

```bash
# 3-1. Alembic マイグレーション（Manual Job を起動して完了を待つ）
az containerapp job start -g rg-felisaichatbot-dev-tf -n caj-felisaichatbot-dev-migrate
az containerapp job execution list -g rg-felisaichatbot-dev-tf -n caj-felisaichatbot-dev-migrate -o table
# → Status: Succeeded を確認。失敗時はログを見る（Log Analytics: ContainerAppConsoleLogs_CL）

# 3-2. psql 対話経路（ops コンテナ）
# ops は min_replicas = 1 の常駐構成（2026-08-22 是正。ADR-0015 追記）。exec は Running
# レプリカに直接つながる（実測）ため、min-replicas の一時変更は不要
az containerapp replica list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops -o table  # Running 1 本を確認
az containerapp exec  -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --command bash
#   コンテナ内で: psql "$DATABASE_URL" -c 'SELECT 1;' / \dt でマイグレーション結果を確認
```

- **旧手順（使うたびに min-replicas を 1 に上げ、終わったら 0 に戻す）の訂正（2026-08-22）**:
  この操作は目的（常駐課金を残さない）を**達成していなかった**。ingress なしの ops には
  スケールインを駆動する仕組みが無く、min-replicas を 0 に戻してもレプリカ 1 が常駐し続ける
  （Replicas メトリクスで実測。[observations.md](../verification/vnet-cutover/observations.md)
  の「G4 の訂正」節が正本）。さらに 0 宣言は idle 課金の適格条件（"Configured with a minimum
  replica count greater than zero"。出典:
  <https://learn.microsoft.com/en-us/azure/container-apps/billing> ）を外すため、常駐レプリカが
  **active 単価で課金される**構成だった。宣言を実態に合わせた min_replicas = 1 へ是正済み

- **`az containerapp exec` の非対話実行の癖（2026-08-22 実測）**: `--command` の文字列は
  コンテナ内シェルを介さず実行されるため **`$DATABASE_URL` 等は展開されない**（psql が
  ローカルソケットへ向かう）。`--command 'sh -c "…"'` の入れ子引用は az 側の分割で壊れる
  （Syntax error を実測）。スクリプトから叩く場合は `--command bash` で対話セッションを張り、
  **接続確立（約 10 秒）を待ってから標準入力にコマンドを流し込む**（pty が必要なら `script -qec` を使う）

### 3-3. revision 名衝突の意図的実測（Azure への書き込み = 要ユーザー承認）

> **2026-08-22 実施済み**。結果は
> [vnet-cutover/observations.md](../verification/vnet-cutover/observations.md) の
> 「revision 名衝突の意図的実測」節が正本: **PATCH は ARM に HTTP 202 で受理された後、
> revision provisioning が `revision with suffix probe1 already exists`
> （`ContainerAppOperationError`）で明示的に失敗**（判定表 1 行目）。既存 revision は無変更。
> 本節の手順は再実施できるよう残すが、判定表の「未実測」前提は解消済み。

ADR-0018 追記 #98 は「過去に使った revision suffix を再指定したとき、ARM API がエラーを返すのか
黙って既存 revision を参照するのかは公式に記載がなく**未実測**」とした。Day 4 の本番（DSN の
往復 apply）で初めて踏むのではなく、**ここ（ステップ C。§3-2 の psql 疎通成功の直後）で意図的に
衝突させて実測し、証跡を残す**。「未実測の前提を実測に変えた」記録自体が本プロジェクトの成果物である。
本節のコマンドはすべて Azure への書き込みを含むため、冒頭の但し書きどおり
**ユーザーの明示承認を得てから**実行する。結果はすべて
[vnet-cutover/observations.md](../verification/vnet-cutover/observations.md) の
「revision 名衝突の意図的実測」欄に記録する。

**対象は ops（`ca-felisaichatbot-dev-ops`）のみ**。ingress が無くトラフィックが乗らないため、
壊れても外部影響がない。serving（`ca-felisaichatbot-dev`）では行わない。

```bash
# 前提: §3-2 の psql 疎通が成功済みで、min_replicas は 0 に戻してあること

# 0) 基準状態を記録する（revision の一覧・active/inactive・replicas）。
#    既定の revision list は inactive を表示しない（2026-08-22 実測: deprovision 完了後の
#    revision は一覧から消える）。非アクティブ側を見るときは必ず --all を付ける
az containerapp revision list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --all -o table

# 1) suffix probe1 で新 revision を作る。env の追加（--set-env-vars）は template の変化 =
#    revision-scope の変更なので、suffix 指定と合わせて新 revision が作られる想定
az containerapp update -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops \
  --revision-suffix probe1 --set-env-vars REVISION_COLLISION_PROBE=1
echo "exit=$?"
az containerapp revision list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --all -o table
# → probe1 側の revision の実名をここで控える（suffix と実名の区切り文字も実出力で確認して記録する）

# 1-b) ガード: 既存 env が生き残ったことの実測確認（確認できるまで 2) へ進まない）。
#    --set-env-vars のヘルプは "Existing environment variables are not modified." と言うが、
#    それはヘルプの記述であってまだ実挙動ではない。本節の前提（ドキュメントと実挙動が
#    食い違った前例がある）は --set-env-vars 自身にも適用する。万一 secretref の env が
#    落ちていると ops の DB 接続が壊れ、しかも気づかず 3) に進むと「壊れたアプリで衝突を測る」
#    ことになり、provision 失敗など衝突と無関係な理由のエラーと区別できなくなる
az containerapp revision show -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops \
  --revision <REV_PROBE1> --query "properties.template.containers[0].env"
# → 確認して記録すること（クエリのパスは想定であり、実行時に実出力で確かめて必要なら直す）:
#   - DATABASE_URL（secretRef が database-url を指す形）と DSN_REVISION_MARKER と
#     REVISION_COLLISION_PROBE=1 の 3 つが並んでいること
#   - secret の値そのものは絶対に出力しない。secretRef は参照名しか出ないはずだが、
#     まず上記クエリの実出力で形式を確認し、値が展開される形のクエリは使わないこと
# → DATABASE_URL / DSN_REVISION_MARKER のどちらかが消えていた場合は**ここで中止**し、
#   2) 3) に進まない。ヘルプの記述と実挙動が食い違ったこと自体が記録に値する発見なので、
#   observations.md に記録してから「後始末とゲート」（terraform apply で収束 →
#   plan -detailed-exitcode exit 0）へ飛ぶ

# 2) suffix probe2 でもう 1 回。Single revision モードで probe1 をアクティブから外すための
#    中間ステップ。これが無いと「非アクティブな既存 revision との名前衝突」のテストにならない
#    （アクティブな revision と同名にするのとは別の話）
az containerapp update -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops \
  --revision-suffix probe2 --set-env-vars REVISION_COLLISION_PROBE=2
echo "exit=$?"
az containerapp revision list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --all -o table
# → probe1 が非アクティブ側に落ち、probe2 がアクティブであることを確認して記録

# 3) 本番: probe1 を再指定する（= 非アクティブな既存 revision と同名）。
#    env 値を 3 に変えて「同名だが内容は新しい」状態を作り、あとで新旧を識別できるようにする
az containerapp update -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops \
  --revision-suffix probe1 --set-env-vars REVISION_COLLISION_PROBE=3
rc=$?; echo "exit=$rc"    # ← これが測りたい値。exit code と、エラーならエラー全文を必ず記録する
az containerapp revision list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --all -o table
```

**3) の結果の記録（ここを曖昧にすると測った意味がない）**:

- exit code。エラーなら**エラー全文**（メッセージとエラーコード）。さらに `--debug` を付けて
  再実行し、stderr のログから **ARM への PUT/PATCH リクエストが実際に発行されたか**（= CLI 側の
  バリデーションで ARM に到達する前に弾かれたのではないか）と HTTP ステータス・ARM エラーコードを
  切り分けて記録する
- 成功（exit 0）の場合は、probe1 という名前の revision が**新しい内容で存在する**のか、
  **古い内容のまま再アクティブ化されただけ**なのかを区別する:

```bash
# 1) で控えた probe1 の実名を <REV_PROBE1> に入れる
az containerapp revision show -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops \
  --revision <REV_PROBE1> \
  --query "{active: properties.active, createdTime: properties.createdTime, env: properties.template.containers[0].env}"
# → REVISION_COLLISION_PROBE が 3 なら「同名で新しい内容」、1 のままなら「古い内容の再利用」。
#   createdTime が 1) の時刻のままか 3) の時刻に変わったかも突き合わせる。
#   なお revision は本来 "Immutable: Once established, a revision remains unchangeable."
#   （出典: https://learn.microsoft.com/en-us/azure/container-apps/revisions ）とされており、
#   「同名で新しい内容」が観測された場合はこの記述との食い違いとして特記する
```

**判定表（結果に応じた Day 4 への含意。どちらに転んでも本 PR の変更で回避済みであることの確認）**:

| 3) の結果 | 旧方式（`revision_suffix` = DSN ハッシュ固定）への含意 | 現方式（suffix 未指定・Azure が一意生成 + `DSN_REVISION_MARKER`）での扱い |
| --- | --- | --- |
| エラーが返る | Day 4 の戻し apply（§4-5）が同じ衝突でブロックされていたことの実証になる | suffix を指定しないため衝突自体が発生しない |
| 黙認され、古い内容のまま | 「元サーバーに戻したつもりで復元先を見続ける」= RTO / RPO の計測値が偽になっていたことの実証になる | 同上 |
| 黙認され、同名で新しい内容になる | 動作はするが revision 履歴の同一名が別内容を指し、immutable の公式記述と食い違う（履歴の信頼性が失われる） | 同上 |

**`--set-env-vars` を選んだ根拠（`az containerapp update --help` の実出力。2026-08-22 取得）**:

> `--set-env-vars` : Add or update environment variable(s) in container. **Existing environment
> variables are not modified.** Space-separated values in 'key=value' format.

既存の env（secret 参照の `DATABASE_URL` と `DSN_REVISION_MARKER`）を**消さずに**追加できる。
対して `--replace-env-vars` は同ヘルプで
"Replace environment variable(s) in container. **Other existing environment variables are
removed.**" とされており、これを使うと ops の DB 接続が壊れるため**使わない**。
公式 Web ドキュメントではなく手元の CLI ヘルプ実出力を根拠とする
（ドキュメントと CLI 実挙動が食い違った前例があるため。ADR-0018 追記 #96 ほか）。

**コスト影響**:

- probe で revision が最大 3 本増えるが、非アクティブ revision に課金は無い
  （"Container Apps doesn't charge for inactive revisions."
  出典: <https://learn.microsoft.com/en-us/azure/container-apps/revisions> ）
- ops は min_replicas = 1 の常駐構成（2026-08-22 是正。実施当時は 0 宣言だったが 1 レプリカが
  常駐し active 単価で課金されていた — 経緯は observations.md「G4 の訂正」節）。probe 中も
  レプリカ 1 が維持され、その稼働分の課金が発生する。各ステップの revision list で
  `Replicas` 列も記録しておく

**後始末とゲート（すべて Azure への書き込み = 要ユーザー承認）**:

```bash
# probe で入れた template の変更（REVISION_COLLISION_PROBE / suffix 指定）をコード定義へ収束させる。
# まず plan が probe の差分を検出することを確認してから apply する
terraform -chdir=terraform/ephemeral plan -detailed-exitcode; echo "exit=$?"   # exit 2 想定
terraform -chdir=terraform/ephemeral apply

# 2026-08-22 実測: provider の refresh は env 差分を拾い、plan は exit 2（ops の in-place
# update = probe env の削除のみ）を返した。ただし config が suffix 未指定のため、probe 用
# suffix の残存自体は drift として検出されない（新 revision は apply 時に自動生成名で作られる）。
# 万一 plan が差分を検出しない場合の代替経路（今回は不要だった）:
#   az containerapp update -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops \
#     --remove-env-vars REVISION_COLLISION_PROBE
#   （--remove-env-vars: "Remove environment variable(s) from container. Space-separated
#     environment variable names." 同ヘルプ実出力）

# ゲート: ステップ A / Day 4 / Day 5 と同じ。az で直接触った後にコードと実体が乖離して
# いないことを担保する。exit 0 になるまで §4 以降へ進まない
terraform -chdir=terraform/ephemeral plan -detailed-exitcode; echo "exit=$?"   # exit 0 を確認

# psql 疎通が probe 前と同じく取れることを §3-2 と同じ手順で再確認する
```

## 4. 終業時の扱い（「毎日 destroy」を改める。ADR-0018 追記 2026-08-22）

**ephemeral 層はカットオーバー後、Day 5 の最終 teardown（計画書 §5-6）まで destroy しない。**
private access 化後は ops Container App / migration Job が**唯一の DB アクセス経路**であり、
夜間に ephemeral を destroy すると翌朝の Day 4 PITR ドリル（seed 投入・破壊・復元確認）も
Day 5 の疎通 probe も開始できないため（判断根拠は ADR-0018 追記と計画書 §3-6）。

```bash
# 終業時は destroy せず、状態確認とコスト見張り（計画書 §8）のみ行う
az resource list -g rg-felisaichatbot-dev-tf -o table
az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev --query state -o tsv
```

- 残すことによる追加コストは ACR 0.1666 USD/日 + custom VNet の CAE managed resources を含めて
  約 0.84 USD/日（いずれも Retail Prices API 実測単価。ADR-0018）。ドリル前の朝に不確実な
  再構築作業（apply + イメージ push）を積むより安い、という判断（ADR-0018 追記）
- 夜間のコンピュート課金（2026-08-22 是正）: **serving は** min_replicas 0 + ingress の暗黙
  HTTP スケールルールで Replicas 0 まで縮退し課金ゼロ（実測）。**ops は** min_replicas 1 の
  常駐で、公式の idle 適格条件（min > 0 / 最小数で稼働 / 全コンテナ起動済み / HTTP 処理なし /
  0.01 vCPU 未満 / 1,000 bytes/s 未満）を満たすことを実測済み — ただし **idle 単価が請求に
  実際に適用されたかは課金データでは未確認**（詳細は ADR-0015 追記と observations.md）

## 5. 巻き戻し（万一 private access で B1ms が作れない場合）

- persistent の apply が失敗した時点では旧サーバーは既に destroy 済み（データは捨ててよい前提で開始している）
- 切り分け: SKU を GP 最小に変えて再 apply → 通れば B1ms × private の制約が確定（ADR-0018 に追記して記録）
- GP でも通らない場合はエラーを記録した上で、コードを revert して public access 構成で作り直す
  （main へ revert PR。暫定構成の継続を Issue で追跡する）

## 6. ステップ B/C の失敗時対応（2026-08-22 の実走を踏まえて追記）

§5 は persistent 層の apply 失敗（B1ms × private access が作れない場合）しかカバーしていない、
という外部レビュー指摘への追記。**2026-08-22 の実走ではステップ B/C は全ゲート合格で完走**しており、
以下のうち「実測」と書いた項目だけが実際に踏んだ経路である。**踏んでいない失敗経路は「未踏」と明記
する。未踏の経路について具体的な復旧コマンドを想像で並べることはしない**（間違った手順書は無いより悪い）。

### 原則（実測で裏付けあり）

- **destroy で消しにいかない**。ephemeral 層は「`terraform plan` を読む → apply で収束」が
  そのまま復旧経路になる（実測: §3-3 の probe で az により template を書き換えた後、
  plan exit 2 → apply（in-place 18 秒）→ plan exit 0 に収束し、psql 疎通も回復した）。
  中途半端な状態で止まったら、まず `plan -detailed-exitcode` で「コードとの乖離」を測る
- **一過性の ARM エラーはリトライしてから疑う**（実測: `az containerapp revision list` が
  1 回だけ `InternalServerError` を返し、10 秒後のリトライで成功。再発なし）
- 症状の確定を構成変更より先に行う: revision の `runningState` / `runningStateDetails`、
  Log Analytics の `ContainerAppSystemLogs_CL` / `ContainerAppConsoleLogs_CL`。
  **推測で NAT Gateway 追加等の構成変更をしない**（コストと設計に影響。判断を仰ぐ）

### 個別の失敗モード

| 失敗モード | 状態 | 対応 |
| --- | --- | --- |
| revision suffix の名前衝突 | **実測**（§3-3 で意図的に再現） | ARM が `ContainerAppOperationError` で拒否し、**既存 revision は無変更**のまま。suffix 指定をやめて apply し直す（現行コードは suffix 未指定なので通常運用では発生しない） |
| az で直接触った後の drift | **実測**（§3-3 の後始末） | `plan` を読んで `apply` で収束 → `plan -detailed-exitcode` exit 0 を確認 |
| イメージ push 前に apply が走り `ErrImagePull` | **未踏**（G1 ゲート = push 直後のタグ実在・ダイジェスト一致確認で予防し、発生しなかった） | 症状確定（`runningStateDetails`）→ 正しいタグを push → 同じ参照で apply。詳細手順は実際に踏んだときに記録する |
| CAE 作成失敗・タイムアウト | **未踏**（実測は 3 分 07 秒で成功） | 状態を記録して報告。CAE は作り直し以外の復旧手段が乏しい想定だが、**未踏のため断定しない** |
| 委任サブネットから ACR に到達できない | **未踏**（実測で到達できることが確定済み。NSG / UDR / NAT Gateway なしの素の委任サブネットで pull 成功） | 発生し得るのは構成を変えた場合。症状確定 → 変更差分の特定から |

## PITR ドリル（Day 4）への影響

復元コマンドが private 前提になる（計画書 §4-3 の改訂を参照）:

```bash
# --no-wait で非同期にし、RTO はポーリングで計測する（同期 restore だと CLI が完了まで
# ブロックし、1 分間隔の計測が成立しない。計測手順の正本は計画書 §4-3）
az postgres flexible-server restore \
  -g rg-felisaichatbot-dev-tf \
  --name pgsql-felisaichatbot-dev-restored \
  --source-server pgsql-felisaichatbot-dev \
  --restore-time "<T_target (ISO8601 UTC)>" \
  --no-wait \
  --vnet vnet-felisaichatbot-dev \
  --subnet snet-felisaichatbot-dev-pgsql \
  --private-dns-zone felisaichatbot-dev.private.postgres.database.azure.com
```

- 復元サーバーは**同じ VNet に入る**（public へは復元できない。ADR-0018 の出典参照）。
  接続検証（`SELECT 1` / マーカー行数）は ops コンテナから、**復元先の FQDN を指す専用 DSN** で行う
  （元サーバーの `DATABASE_URL` と混ぜない。手順は計画書 §4-3）
- アプリ・ops を復元先へ向け替えるときは `TF_VAR_database_url` を更新して ephemeral 層を apply する。
  secret の更新は既存 revision に自動反映されないが、template 内の非 secret 環境変数
  `DSN_REVISION_MARKER`（DSN ハッシュ）が変わるため apply が必ず新 revision を作る
  （コードで担保。`terraform/ephemeral/main.tf` / ADR-0018 追記 #98）
- 委任サブネットは `/27`（32 アドレス、Azure 予約 5 を除き実質 27。ADR-0018 追記）で、
  復元中の 2 台同居 + Day 5 の HA standby を見込んでも余白がある。それでも復元が失敗したら
  まずサブネットの空きを疑う
