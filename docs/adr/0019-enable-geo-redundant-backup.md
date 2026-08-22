# ADR-0019: geo 冗長バックアップを有効化する（ADR-0011 の geo 冗長部分のみを supersede）

## ステータス

Accepted

（[ADR-0011](./0011-backup-retention-and-geo-redundancy.md) の決定のうち **`geo_redundant_backup_enabled = false` のみ**を supersede する。保持 7 日の決定と、その根拠（検証 3 日 < 窓 7 日）は引き続き有効）

## 日付

2026-08-22

## 決定内容

- `terraform/persistent/` の PostgreSQL Flexible Server（`pgsql-felisaichatbot-dev`）で **`geo_redundant_backup_enabled = true`** にする
- 実機への反映は VNet 統合カットオーバー（[ADR-0018](./0018-postgresql-private-access-and-vnet-integration.md) / [vnet-integration-cutover.md](../operations/vnet-integration-cutover.md)）の apply で行う。本 ADR の時点では Azure への書き込みは行っていない
- geo リストアのドリルは Day 3〜5 のスコープに**入れない**（判断根拠は「影響」の節）

## 背景

### なぜ今か

geo 冗長バックアップは**サーバー作成時にしか設定できず、作成後は変更できない**（"You can configure geo-redundant storage for backup only during server creation. After a server is provisioned, you can't change the backup storage redundancy option." 出典: <https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore> ）。azurerm 5.1.0 の実装でも本属性は **ForceNew**（変更 = サーバー再作成。確認記録は「影響」の節）。

そして cutover（Issue #81 / ADR-0018）で PostgreSQL をこれから再作成する。つまり、この判断を追加コストなしで確定できる機会は今しかない。

### ADR-0011 の判断を覆す理由（前提の変化）

ADR-0011 は geo 冗長を無効と決めた。却下理由は 4 点で、そのうち **(b) だけが前提の変化で崩れた**。

| ADR-0011 の却下理由 | 現在の評価 |
| --- | --- |
| (a) 有効化は作成時のみで後から変更不可（不可逆） | **cutover で再作成するため、今なら追加コストなしで決められる**（不可逆性はむしろ今決める理由になった） |
| (b) 有効時はバックアップストレージ消費が 2 倍で課金 | **崩れた。** 12 か月無料枠にバックアップ 32 GB が含まれると判明し（ADR-0017）、実測の Backup Storage Used は 2,861,497 バイト（約 2.7 MiB。[restore-drill/observations.md](../verification/restore-drill/observations.md)）。課金式は「(2 × ローカルバックアップサイズ − プロビジョン済みストレージ) × GB/月単価」（出典: 上記 concepts-backup-restore）で、2 × 約 2.7 MiB は無料枠 32 GB に対して桁が 4 つ下。実コストはゼロ |
| (c) geo リストアは PITR 不可・RPO 最大 1 時間で、本命の PITR ドリルには寄与しない | **変わらず正しい**（下記「geo リストアの制約」） |
| (d) リージョン災害対策は本プロジェクトの要件にない | **変わらず正しい** |

つまり「当初の判断が間違っていた」のではない。**(b) の消滅で有効化のコストがゼロになり、選択の天秤が変わった**。(c)(d) が正しい以上、geo 冗長は本命成果物（PITR ドリル）に寄与しないが、コストゼロで不可逆な選択肢を確保できるなら、放棄する理由がない。

## geo リストアの制約（有効化しても変わらない事実）

出典はすべて <https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore>（2026-08-22 確認）。

- **PITR 不可（最新復元のみ）**: "You can restore only to the last available backup data that's available at the paired region. Currently, PITR of geo-redundant backups isn't available."
- **RPO は最大 1 時間**: バックアップデータはペアリージョンへ非同期複製され、"you can expect up to one hour of RPO when you restore."
- **復元先は geo ペアリージョン**（japaneast のペアは japanwest。出典: <https://learn.microsoft.com/en-us/azure/reliability/cross-region-replication-azure> ）
- **private access のサーバーは別 VNet へのみ geo リストア可**（VNet はリージョンを跨げないため）: "If you configure your source server with a private access virtual network, you can only restore to a different virtual network, because virtual networks can't span regions." つまり本構成（ADR-0018）で geo リストアするには、ペアリージョン側に VNet / 委任サブネット / private DNS zone を先に用意する必要がある
- **サーバー作成後 1 時間はレプリケーション待ちが必要**: "After you create a server, wait at least one hour before initiating a geo-restore." cutover での再作成直後の 1 時間は geo リストアできない

## 検討した選択肢

### 1. geo 冗長の設定値

- **(a) 有効化（採択）**: 上記のとおり実コストゼロ・不可逆・今が最後の機会
- (b) 無効のまま（ADR-0011 を維持）: 却下。維持する根拠だった (b) 2 倍課金が消えており、「後から必要になったらサーバー再作成」という不可逆コストだけが残る

### 2. 判断の記録方式（ADR の扱い）

- **(a) 新 ADR で ADR-0011 の geo 冗長部分のみを supersede + ADR-0011 冒頭に注記（採択）**: [ADR-0016](./0016-log-analytics-workspace-in-persistent-layer.md) が ADR-0015 の一部（Log Analytics の配置）だけを supersede した先例と同じ方式。本件は**記録済みの決定の反転**であり、反転の経緯（前提の変化）自体が成果物になるため、独立した ADR として残す
- (b) ADR-0011 本文の書き換え: 却下。ADR は判断当時の記録であり、当時正しかった判断（(c)(d) は今も正しい）を書き換えると「無効と決めた根拠」の記録が消える
- (c) ADR-0011 への追記節: 却下。[ADR-0018](./0018-postgresql-private-access-and-vnet-integration.md) の追記は**自身の決定を同方向に補強**する用途（ステータス Accepted のまま）だった。決定の反転を追記で表すと、ステータスと本文（無効の採択理由）が現行の設計値と食い違ったまま残る

## 採択理由

- **コストの前提が崩れた**: 12 か月無料枠（「750 hours of Flexible Server—Burstable B1MS Instance, 32 GB storage, and 32 GB backup storage」出典: <https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account> ）+ 実測約 2.7 MiB により、2 倍消費でも課金ゼロ
- **不可逆な選択肢の確保**: 作成時のみ設定可という制約は変わらないので、コストゼロの今、有効側に倒しておけば将来の DR 要件変化に再作成なしで対応できる。逆（有効 → 無効）は復元時に選べる（geo リストア中に geo 冗長を外せる。出典: 上記 concepts-backup-restore）ため、有効側に倒すほうが可逆性が高い
- **本命成果物への影響ゼロ**: (c) のとおり geo リストアは PITR ドリルとは別物であり、Day 4 のドリル設計（ADR-0011 / 計画書 §4）は一切変わらない
- **面接での効き方**: 「バックアップはどうしていましたか」への追い質問「リージョンごと落ちたらどうしますか」に対し、「geo 冗長も有効。ただし geo リストアは PITR 不可・RPO 最大 1 時間なので、通常の復旧（PITR）とは別物として扱う」と**制約込みで**答えられる

## 影響

- `terraform/persistent/main.tf`: `geo_redundant_backup_enabled = true`（コメントに理由と出典を記載）
- **ForceNew の確認記録**（2026-08-22）: `terraform providers schema -json` の出力には ForceNew（replace 要否）の情報が**含まれない**（属性の type / optional のみ）ため、azurerm **v5.1.0 のプロバイダー実装**で確認した。`internal/services/postgres/postgresql_flexible_server_resource.go` L275-280 に `"geo_redundant_backup_enabled": { ... ForceNew: true }` が明記されている。cutover ではどのみち private access 化（ADR-0018）で replace されるため、本変更が追加の再作成を引き起こすことはない
- cutover の plan で確認する差分に「`geo_redundant_backup_enabled: false → true`（replace 要因のひとつ）」が加わる（[vnet-integration-cutover.md](../operations/vnet-integration-cutover.md) §1）
- 再作成直後の 1 時間は geo リストア不可（上記制約。運用上の待ち時間として cutover 手順に注記）
- **geo リストアのドリルは実施しない**（Day 5 の「時間が余ればやること」にも入れない）。理由: (1) private access のため、ペアリージョン（japanwest）側に VNet / 委任サブネット / private DNS zone と検証用の接続経路を新設する必要があり「時間が余れば」の作業量ではない。(2) PITR 不可のため本命成果物（追い質問に実測で答える。計画書 §0-3）に寄与しない。(3) Day 5 は最繁忙日で、時間不足時に削る対象（Monitoring。計画書 §1-2）が既に決まっており、それより劣後する任意項目を足すのはスコープクリープ（計画書 §9 の趣旨）になる。「有効化したが、リージョン災害の復旧演習までは要件にないため実施していない」という線引き自体を記録として残す
- ドキュメント更新（本 ADR と同一 PR）: [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §0-2 / §3-1 / §3-5 / §6 / §9、[vnet-integration-cutover.md](../operations/vnet-integration-cutover.md) §1、[azure-resource-inventory.md](../operations/azure-resource-inventory.md) §A、[production-readiness.md](../production-readiness.md)、ADR-0011 冒頭注記、ADR-0018 関連節、ADR README 一覧

## 数値の出典

- geo 冗長は作成時のみ設定可・課金式「(2 × ローカルバックアップサイズ − プロビジョン済みストレージ) × GB/月単価」・geo リストアは PITR 不可（最新復元のみ）・RPO 最大 1 時間・作成後 1 時間の待ち・private access は別 VNet へのみ復元・無料バックアップ枠 = プロビジョン済みストレージの 100%: [Backup and restore in Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore)（2026-08-22 に確認）
- 12 か月無料枠にバックアップ 32 GB が含まれる: <https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account>（ADR-0017 / [azure-resource-inventory.md](../operations/azure-resource-inventory.md)「12か月無料枠」節）
- Backup Storage Used 実測 2,861,497 バイト（約 2.7 MiB。2026-08-21）: [restore-drill/observations.md](../verification/restore-drill/observations.md)
- ForceNew: [terraform-provider-azurerm v5.1.0 `postgresql_flexible_server_resource.go` L275-280](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.1.0/internal/services/postgres/postgresql_flexible_server_resource.go#L275-L280)（2026-08-22 に確認）
- japaneast の geo バックアップ対応（`geoBackupSupported: Enabled`）: Day 0 の `az postgres flexible-server list-skus -l japaneast` 実測（計画書 §2-1 No.24）

## 関連

- [ADR-0011](./0011-backup-retention-and-geo-redundancy.md) — geo 冗長無効の決定を本 ADR が supersede（保持 7 日は有効なまま）
- [ADR-0017](./0017-no-nightly-stop-for-postgresql.md) — 12 か月無料枠の判明（本 ADR の前提変化の出どころ）
- [ADR-0018](./0018-postgresql-private-access-and-vnet-integration.md) — 再作成のタイミングを与えた cutover。geo リストア時の VNet 制約もこの構成に由来
- [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §3-1 / [vnet-integration-cutover.md](../operations/vnet-integration-cutover.md)
- Issue: #92
