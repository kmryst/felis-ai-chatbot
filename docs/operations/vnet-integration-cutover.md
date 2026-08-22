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

## 1. persistent 層の再作成（PostgreSQL が作り直される）

```bash
# plan で「pgsql が destroy → create（replace）される」「firewall rule が destroy される」
# 「VNet / subnet ×2 / private DNS zone / VNet link が add される」ことを確認してから apply する
terraform -chdir=terraform/persistent plan
terraform -chdir=terraform/persistent apply
```

- 依存順序はコードが持っている: VNet → サブネット / private DNS zone → **VNet link → PostgreSQL**
  （link 完成前のサーバー作成は失敗し得るため `depends_on` で明示済み）
- **B1ms × private access は「明文の禁止がない」根拠のみで未確定**（ADR-0018）。ここで失敗したら
  その時点のエラーを記録し、GP 最小 SKU での作成可否を切り分ける
- apply 後、新しい接続先 FQDN を取得する（private DNS zone 配下の名前に変わる）:

```bash
terraform -chdir=terraform/persistent output server_fqdn
```

- `.env` / CI secret の `TF_VAR_database_url` のホスト部をこの FQDN に更新する（`sslmode=require` は維持）。
  **作業端末からこの FQDN へは到達できなくなるのが正常**（psql 検証は §3 の ops 経由で行う）

## 2. ephemeral 層の apply（2 段階。egress IP 依存の旧 2 段階とは別物）

旧構成の「firewall rule の for_each が outbound IP に依存するための 2 段階 apply」は廃止された。
残るのは「ACR にイメージが無いと Container App / Job が作れない」というイメージ押し込みの段階のみ。

```bash
# 第 1 段: ACR だけ先に作る
terraform -chdir=terraform/ephemeral apply -target=azurerm_container_registry.main

# イメージ投入（serving と ops の 2 本。タグは main の short SHA）
SHA=$(git rev-parse --short HEAD)
az acr login --name felisaichatbotacrdev
docker build -t felisaichatbotacrdev.azurecr.io/backend:sha-$SHA backend/
docker build --target ops -t felisaichatbotacrdev.azurecr.io/backend-ops:sha-$SHA backend/
docker push felisaichatbotacrdev.azurecr.io/backend:sha-$SHA
docker push felisaichatbotacrdev.azurecr.io/backend-ops:sha-$SHA

# 第 2 段: 残り全部（CAE + app + ops app + migration Job）
terraform -chdir=terraform/ephemeral apply \
  -var "container_image=felisaichatbotacrdev.azurecr.io/backend:sha-$SHA" \
  -var "ops_container_image=felisaichatbotacrdev.azurecr.io/backend-ops:sha-$SHA"
# database_url は TF_VAR_database_url 環境変数で渡す（§1 で更新した新 FQDN のもの）
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
# min_replicas 0 のため、まずレプリカを起こす（未実測: exec に稼働レプリカが必要という理解。ADR-0018）
az containerapp update -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --min-replicas 1
az containerapp exec  -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --command bash
#   コンテナ内で: psql "$DATABASE_URL" -c 'SELECT 1;' / \dt でマイグレーション結果を確認
# 使い終わったら必ず 0 へ戻す（常駐課金を残さない）
az containerapp update -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --min-replicas 0
```

## 4. 終業 teardown（従来どおり）

```bash
terraform -chdir=terraform/ephemeral destroy
az resource list -g rg-felisaichatbot-dev-tf -o table
# → 残るのは pgsql / id / log + vnet / subnets / private DNS zone（persistent 層。ADR-0018）
```

## 5. 巻き戻し（万一 private access で B1ms が作れない場合）

- persistent の apply が失敗した時点では旧サーバーは既に destroy 済み（データは捨ててよい前提で開始している）
- 切り分け: SKU を GP 最小に変えて再 apply → 通れば B1ms × private の制約が確定（ADR-0018 に追記して記録）
- GP でも通らない場合はエラーを記録した上で、コードを revert して public access 構成で作り直す
  （main へ revert PR。暫定構成の継続を Issue で追跡する）

## PITR ドリル（Day 4）への影響

復元コマンドが private 前提になる（計画書 §4-3 の改訂を参照）:

```bash
az postgres flexible-server restore \
  -g rg-felisaichatbot-dev-tf \
  --name pgsql-felisaichatbot-dev-restored \
  --source-server pgsql-felisaichatbot-dev \
  --restore-time "<T_target (ISO8601 UTC)>" \
  --vnet vnet-felisaichatbot-dev \
  --subnet snet-felisaichatbot-dev-pgsql \
  --private-dns-zone felisaichatbot-dev.private.postgres.database.azure.com
```

- 復元サーバーは**同じ VNet に入る**（public へは復元できない。ADR-0018 の出典参照）。
  接続検証（`SELECT 1` / マーカー行数）は ops コンテナから行う
- `/28`（16 アドレス、Azure 予約 5 を除き実質 11）に一時的に 2 台目のサーバーが入る。
  委任サブネットの空きが足りない場合は `--subnet` にアドレス追加が要るため、失敗したらまず空きを疑う
