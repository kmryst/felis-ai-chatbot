# ADR-0018: PostgreSQL を private access（VNet 統合）で確定し、運用経路を VNet 内の ops コンテナに一本化する

## ステータス

Accepted

## 日付

2026-08-22

## 決定内容

Day 3 の暫定構成「public access + サーバーレベル firewall rule」（[day3-5-execution-plan.md §3-1](../operations/day3-5-execution-plan.md)）を廃し、ネットワーク境界を次のとおり確定する。

| 項目 | 決定 |
| --- | --- |
| PostgreSQL | **private access で再作成**（`public_network_access_enabled = false`。委任サブネット + private DNS zone）。firewall rule と `firewall_allowed_client_ips` 変数は削除 |
| VNet | `vnet-felisaichatbot-dev`（`10.10.0.0/24`）。**persistent 層** |
| サブネット | `snet-felisaichatbot-dev-aca` **`10.10.0.0/26`**（`Microsoft.App/environments` 委任）/ `snet-felisaichatbot-dev-pgsql` **`10.10.0.64/27`**（`Microsoft.DBforPostgreSQL/flexibleServers` 委任）。どちらも persistent 層（当初 /27・/28 → 追記 2026-08-22 で拡大） |
| private DNS zone | `felisaichatbot-dev.private.postgres.database.azure.com` + VNet link。persistent 層 |
| CAE | **workload profiles 環境（Consumption プロファイルのみ）+ custom VNet + External ingress**。ephemeral 層のまま |
| 運用経路 | backend Dockerfile に **ops ターゲット**（runtime + postgresql-client + `migrations/` + `alembic.ini`）を追加し、**ops Container App**（ingress なし・min_replicas 0）と **Manual トリガーの Container Apps Job**（`alembic upgrade head`）を ephemeral 層に置く |

移行手順（destroy → persistent apply → ephemeral apply → ops 結線）は [vnet-integration-cutover.md](../operations/vnet-integration-cutover.md) が正本。

## 背景

- 現状の制御はサーバーレベル firewall のみで、許可対象は作業端末 IP と Container Apps egress IP の 2 件。**egress IP は静的保証がなく実測でも変化した**（[walking-skeleton/observations.md](../verification/walking-skeleton/observations.md)。ADR-0015 選択肢 4-(a) のリスク受容が実際に発現）。IP ベースの許可は本質的な制御になっていない
- DB を公開エンドポイントに置かない、はネットワーク設計の原則であり、Day 3 の「VNet 統合は検証目的に寄与しない」という判断は walking skeleton 開通までの暫定だった（Issue #81）。本 ADR はその暫定を確定構成に引き上げる

### なぜ今やるか

- **ネットワーク方式（public / private access）は作成時にしか決められない**。変更はサーバーの再作成で、PITR も public / private を跨げない（出典: <https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private> / Issue #81 記載の Backup and restore ドキュメント）
- 現サーバーは**テーブル 0 件・バックアップは Full 1 件（2026-08-21T05:59:00Z）のみ**。失うデータ・引き継ぐバックアップ履歴が実質なく、再作成のコストが最小なのは今しかない。Day 4 の PITR ドリル本番に入ってからでは、ドリルの前提（バックアップチェーン）ごと作り直しになる

## 検討した選択肢

### 1. CAE のネットワーク形態

- **(a) workload profiles 環境（Consumption プロファイルのみ）+ custom VNet + External（採択）**:
  サブネット最小 **/27**・`Microsoft.App/environments` への委任必須（インフラ用 12 IP 予約）。
  Consumption プロファイルだけ使う限りプラン管理の固定費はない（"You aren't billed any plan
  management charges unless you use a Dedicated workload profile in your environment."
  出典: <https://learn.microsoft.com/en-us/azure/container-apps/billing> ）。External なら VNet 統合後も
  `/readyz` を外部から叩く検証経路を維持できる
- (b) Consumption-only 環境のまま VNet 統合: 可能だが公式が **legacy** と表記し、サブネットは最小 **/23**・
  UDR / NAT Gateway 非対応・サブネット委任不可（出典: <https://learn.microsoft.com/en-us/azure/container-apps/networking> ）。
  これから作る構成を legacy 経路に載せる理由がない。却下
- なお **CAE のネットワーク種別は作成後に変更不可・サブネットサイズも変更不可**（同 networking 出典）。
  CAE は毎日 destroy / 再作成する ephemeral 層のため、この制約は本プロジェクトでは運用上の障害にならない

### 2. VNet / サブネット / private DNS zone の置き場所

- **(a) persistent 層（採択）**: PostgreSQL の委任サブネットと private DNS zone はサーバーが生きている限り
  手放せず、寿命が PostgreSQL（persistent）と一致する。CAE 用サブネットも「毎日 CAE に貸すだけの土地」であり、
  CAE の destroy で消える必要がない
- (b) ephemeral 層: 毎日の destroy が PostgreSQL の委任サブネット削除を試みて必ず失敗する。却下

### 3. private access 化後の運用経路（psql / alembic をどこから打つか）

- **(a) ops コンテナ経路（採択）**: backend イメージの ops ターゲット + ingress なし・min_replicas 0 の
  ops Container App（`az containerapp exec` 用）+ Manual トリガーの Container Apps Job（`alembic upgrade head`）。
  「**本番 DB へは VNet 内の運用コンテナ経由でのみ接続し、手元から直接繋がない**」という運用を構成そのもので
  強制する。追加固定費ゼロ（min 0 / Manual Job は待機中課金なし）
- (b) Bastion + VM: 常設 VM とBastion の時間課金・パッチ運用が増える。5 日間プロジェクトの運用経路として過大。却下
- (c) P2S VPN: VPN Gateway の常時課金と証明書配布の運用が増える。作業端末を VNet に入れる発想自体が
  「手元から直接繋がない」原則と逆行する。却下
- (d) serving イメージに psql を同梱: 運用ツールが攻撃面ごと本番 serving コンテナに常駐する。
  serving と ops の分離（最小イメージ原則）を壊す。却下（Dockerfile の ops ターゲット分離が代替）

### 4. egress の静的化（NAT Gateway）

- **不要と判断**: egress IP を DB の firewall に登録する構成自体が消えるため、「egress IP を固定したい」動機が消滅する。
  外向き通信（Azure OpenAI）は CAE の managed public IP 経由で到達でき、宛先はどの IP から来ても受ける。
  NAT Gateway は課金と設定を増やすだけ。却下

## 採択理由

- **原則への回帰**: DB を公開エンドポイントに置かず、到達経路をネットワークで閉じる。IP 許可リストの
  「本質的でない制御 + 変動 IP への追随」という既知の弱点（ADR-0015 選択肢 4-(a) のリスク受容）ごと撤去できる
- **タイミング**: 再作成コストが最小の今（テーブル 0 件・バックアップ 1 件）に確定させ、Day 4 の PITR ドリルを
  確定構成の上で実施する
- **コスト（Retail Prices API 実測。japaneast）**: custom VNet では CAE の managed resources
  （Standard Load Balancer + Standard static public IP）が課金対象になる（既定ネットワークでは無料。
  出典: <https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks> ）。
  単価は private DNS zone 0.5 USD/zone/月・Standard Public IP 0.005 USD/時・Standard LB（Included Rules）
  0.025 USD/時。24 時間換算で**常設分（private DNS zone）約 0.02 USD、CAE 稼働中の追加分を含めて約 0.84 USD**。
  CAE は毎日 destroy する運用のため managed resources 分も夜間は止まり、Day 3〜5 総額見込みを崩さない。
  VNet / サブネット / サブネット委任そのものは無料
- **2 段階 apply の解消**: firewall rule の for_each が `outbound_ip_addresses`（apply 後確定値）に依存する
  制約が消え、「Invalid for_each argument」を回避するための 2 段階 apply（ADR-0015 の 7）が不要になる。
  残るのは「ACR にイメージを入れてから Container App / Job を作る」というイメージ押し込みの段階のみ
  （`terraform/ephemeral/main.tf` 冒頭コメント）

## 影響

- `terraform/persistent/`: VNet / サブネット 2 / private DNS zone / VNet link を追加。PostgreSQL に
  `delegated_subnet_id` / `private_dns_zone_id` / `public_network_access_enabled = false` を設定
  （**ForceNew。サーバー再作成**）。firewall rule リソースと `firewall_allowed_client_ips` 変数を削除。
  依存順序は「VNet link 完成 → サーバー作成」を `depends_on` で明示（サーバーは zone id しか参照せず
  暗黙依存が作れない）
- `terraform/ephemeral/`: CAE に `infrastructure_subnet_id`（data source 参照）+ `workload_profile`（Consumption）を
  追加、`internal_load_balancer_enabled = false`（External 維持）。egress firewall rule / PostgreSQL data source /
  `postgres_server_name` 変数 / `container_app_outbound_ips` output を削除。ops Container App と
  migration Job（`ops_container_image` が空なら作らない）を追加
- `backend/Dockerfile`: ops ターゲット追加（実測: serving 298 MB / ops 379 MB。ops で
  `psql (PostgreSQL) 17.11` / `alembic 1.19.1` の動作確認済み・2026-08-22 ローカル実測）
- **ADR-0015 の部分的変更**: 選択肢 4-(a)（egress IP を firewall rule で許可 + IP 変動のリスク受容）と
  7 の 2 段階 apply は本 ADR により**不要化**。ADR-0015 の他の決定（SKU / スケールゼロ / タグ方針 /
  ACR pull 認証）は引き続き有効のため、ADR 全体の supersede はせず、ADR-0015 冒頭に注記を追加する
  （ADR-0016 が取った方式と同じ）
- DATABASE_URL のホスト部が private DNS zone 配下の FQDN に変わる（再作成後に
  `terraform -chdir=terraform/persistent output server_fqdn` で取得し直す）
- ドキュメント: [azure-resource-inventory.md](../operations/azure-resource-inventory.md) §A /
  [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §3-1・§4（PITR ドリルの private 前提化）/
  [vnet-integration-cutover.md](../operations/vnet-integration-cutover.md)（新設）/ ADR-0013 規則表（`vnet` / `snet` / `caj` /
  private DNS zone の行を追加）

### PITR ドリルへの影響（Day 4 の前提変更）

- **private access のサーバーは同一 or 別 VNet へのみ復元でき、public とは跨げない。復元サーバーは同じ VNet に入る**
  （"The system restores database servers in virtual networks into the same virtual networks"。
  出典: <https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private> ）
- `az postgres flexible-server restore` には `--vnet` / `--subnet` / `--private-dns-zone` 引数がある。
  復元検証（`SELECT 1` / 行数確認）は作業端末からではなく ops コンテナ（`az containerapp exec`）から行う
  （改訂後の計画書 §4-3）

## 未確定として残るもの（apply / 実測で判明する類のリスク）

- **B1ms × private access の可否は「明文の禁止がない」という根拠のみ**。Burstable の制約列挙
  （PgBouncer 不可・オンデマンドバックアップ不可）にネットワーク方式の記載はないが、「可能」と明記した
  一次情報も見つかっていない。persistent apply で判明する（失敗した場合は GP 最小 SKU での作成を検討）
- **12 か月無料枠（750 時間 B1ms）がネットワーク方式で変わるかは確定できなかった**。影響ありという根拠は
  見つかっていないが、「変わらない」と断定しない。8/23 頃の無料枠消費の初回確認（計画書 §8 の宿題）で観測する
- **`az containerapp exec` の稼働レプリカ要件**: min_replicas 0 の ops コンテナに exec するには
  レプリカを起こす操作（`az containerapp update --min-replicas 1` 等）が先に要るはず、という理解で
  運用手順を書いたが、実測はまだ（cutover 手順書に検証ステップとして記載）
- **workload profiles 環境の managed resources 用 RG**（`ME_` プレフィックスの自動作成 RG）が
  CI 用 SP の権限スコープ外に作られる際の挙動は未実測。当面の apply はローカル（Owner）実行のため
  ブロッカーにはならない

## 追記（2026-08-22。#84: 外部レビュー指摘の反映と CIDR 拡大）

apply 前の外部レビューを受けて、本 ADR の決定を 4 点補強する。ステータスは Accepted のまま。

### 1. サブネットを最小要件より大きく取り直す（/27→/26・/28→/27）

**サブネットのサイズは CAE / PostgreSQL の作成後に変更できない**（CAE: 本文の networking 出典。
PostgreSQL: 委任サブネットはサーバーが生きている限り手放せず、変更 = persistent 層の作り直し）。
当初の割り当ては最小要件ちょうどで、「変更できない値を最小要件ぴったりで作る」設計だった。

| | 当初 | 拡大後 | 実質利用可能数 |
| --- | --- | --- | --- |
| VNet | `10.10.0.0/24` | 据え置き | — |
| `snet-...-aca` | `10.10.0.0/27`（32） | **`10.10.0.0/26`（64）** | 15 → **47**（Azure 予約 5 + CAE インフラ予約 12 を控除） |
| `snet-...-pgsql` | `10.10.0.32/28`（16） | **`10.10.0.64/27`（32）** | 11 → **27**（Azure 予約 5 を控除） |

- 根拠: `/27` は workload profiles 環境の最小要件ちょうど（本文の networking 出典）で、Day 4 は
  ops コンテナと backend が同時に動く。`snet-pgsql` には本体に加えて **Day 4 の PITR 復元先サーバー・
  Day 5 の HA standby** が入る。Azure はサブネットごとに 5 IP（先頭 4 + 末尾 1）を予約する
  （出典: <https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-faq> ）
- コスト: プライベート IP アドレス・VNet・サブネットに課金はなく（本文「採択理由」の無料根拠と同じ）、
  拡大の追加費用はゼロ。`/24` 内で `.0〜.63` / `.64〜.95` と重複せず、160 アドレスの余白も残る

### 2. リソースプロバイダー登録は手動側の前提作業として固定する

`Microsoft.Network` / `Microsoft.ContainerService` が NotRegistered のままで（2026-08-22 読み取り実測）、
このまま apply すると `409 MissingSubscriptionRegistration` で失敗する（`Microsoft.ContainerService` は
CAE の custom VNet 構成の前提。出典: <https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom> ）。
**Terraform の自動登録には任せない**: 登録はサブスクリプション単位で、CI の service principal
（RG スコープ Contributor）には権限がなく、自動登録に任せると「ローカルでは通るが CI では落ちる」
（Day 3 の 409 実測: `docs/verification/walking-skeleton/observations.md`）。手順は
[vnet-integration-cutover.md](../operations/vnet-integration-cutover.md) §0-1、namespace の一覧は
[azure-resource-inventory.md](../operations/azure-resource-inventory.md) の「リソースプロバイダー登録」節が正本。

### 3. secret 更新の revision 反映をコードで担保する（`revision_suffix`）

Container Apps は **secret を更新しても既存 revision に反映しない**（"An updated or deleted secret
doesn't automatically affect existing revisions in your app"。secret の変更だけでは新 revision も
作られない。出典: <https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets> ）。
Day 4 で DSN を復元先へ向け替えた後、古い revision が元サーバーを見続けるとアプリ回復時刻の計測が偽になる。

- 対応: serving / ops 両 Container App の template に **`revision_suffix` = DSN の sha256 先頭 8 桁**を
  設定（`terraform/ephemeral/main.tf`）。`database_url` が変わる apply では template が必ず変化し、
  新 revision の作成が Terraform のコードで保証される。手順書の「restart を忘れない」運用への依存をなくす
- `revision_suffix` が azurerm **5.1.0** の `azurerm_container_app` template に存在することは
  `terraform providers schema -json` で確認済み（2026-08-22）。Container Apps **Job** の template には
  revision の概念自体がなく suffix も存在しない（同確認）。Job の新 execution が更新後の secret を
  読むことは**未実測**（cutover 実測時に確認する）
- suffix は不可逆な truncated hash で、revision 名として公開されても DSN・パスワードは復元できない

### 4. ephemeral 層の夜間 destroy をやめる（destroy は Day 5 の最終 teardown のみ）

private access 化後は ops コンテナ / migration Job が**唯一の DB アクセス経路**になり、夜間に
ephemeral を destroy すると翌朝の Day 4 ドリルも Day 5 の疎通 probe も開始できない。選択肢は
(a) destroy を後ろへ移す / (b) 毎朝 ACR 再 push 込みの 2 段階 apply で作り直す、の 2 つで **(a) を採択**:

- (b) はドリル本番の前に毎朝 apply + イメージ push という不確実な作業を積む（VNet 統合 CAE の
  作成時間は未実測で延びる可能性あり）。計測が主目的の日の冒頭に置くべきでない
- (a) の追加コストは ACR 0.1666 USD/日 + custom VNet の CAE managed resources 込みで約 0.84 USD/日
  （本文「採択理由」の Retail Prices API 実測単価）。Container App はスケールゼロで夜間の
  コンピュート課金はない。Day 5 の probe も ops 経由のため、整合的に「destroy は Day 5 §5-6 の
  最終 teardown のみ」とする（[day3-5-execution-plan.md](../operations/day3-5-execution-plan.md)
  §3-6 / §4-8 / §5-6 を改訂）

## 関連

- [ADR-0011](./0011-backup-retention-and-geo-redundancy.md) — 再作成でも保持 7 日の決定は不変（geo 冗長は本 ADR 起案時は無効のままの予定だったが、その後 [ADR-0019](./0019-enable-geo-redundant-backup.md) が本 ADR の再作成タイミングを利用して有効へ変更した）
- [ADR-0013](./0013-azure-resource-naming-convention.md) — 本 ADR で `vnet` / `snet` / `caj` / private DNS zone の行を追加
- [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) — 選択肢 4-(a) と 7 の 2 段階 apply を本 ADR が不要化（他は有効）
- [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §3-1 / §4
- [vnet-integration-cutover.md](../operations/vnet-integration-cutover.md) — 移行手順の正本
- Issue: #81
