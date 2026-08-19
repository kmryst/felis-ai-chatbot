# felis-ai-chatbot Day 3〜5 実行計画書（PostgreSQL Backup / PITR / Maintenance / HA / Monitoring）

本書は Day 3〜5 で実行する手順と判断基準の正本です。[bootstrap.md](./bootstrap.md)（Day 0）と同じ作法で、各 Day に「検証」（これが通れば次へ）と「teardown / stop」を置きます。

本書内の Azure の仕様・数値は、2026-08-19 に Microsoft Learn の公式ドキュメントを実際に読んで確認したものです（§2 に出典 URL 一覧）。**出典を添えられない数値は本書には書いていません。** ドキュメントで確定できなかった項目は「未実測。Day N で測る」と明示しています（§2-2）。

---

## 0. この計画の立て付け（全判断がここに従属する）

**成果物は「Azure 上の AI チャットボット」ではない。** 面談で「実務で DB のバックアップ、メンテナンスやったことありますか？」と訊かれて答えられなかった。その質問に「これが答えです」と出せる実物と記録を作ることが、このプロジェクトの唯一の目的である。

### 0-1. 表現ルール（成果物すべてに適用）

- **「実務でやった」とは書かない。** 実務ではなく個人開発である。正しい立て付けは「実務では担当していない。訊かれて答えられなかったので、自分で構築して一通り設計・実行した。これがその記録」。この誠実さ自体が回答の強みなので、曖昧にしない。
- 経験の有無を訊く質問への勝負どころは**追い質問**である。「リストアは試しましたか？」「保持期間はどう決めましたか？」「メンテナンス中に止まりましたか？」で詰まると最初の回答まで疑われる。だから実測値と記録が要る。

### 0-2. 追い質問と、それに答える実測の対応

| 想定される追い質問 | 答えになる実測・記録 | どこで作るか |
| --- | --- | --- |
| リストアは試しましたか？ | PITR ドリルの RTO / RPO 実測とタイムライン | Day 4（`docs/verification/restore-drill/`） |
| 保持期間はどう決めましたか？ | 7日（既定）採用の根拠と、geo 冗長を無効にした判断の記録 | Day 3（ADR） |
| メンテナンス中に止まりましたか？ | 計画フェイルオーバーの実測ダウンタイム（HA では計画メンテがこの切替で処理される） | Day 5（`docs/verification/failover-drill/`） |
| vacuum は見ていますか？ | autovacuum 発火・bloat・長時間トランザクション阻害の観測記録 | Day 4（`docs/verification/vacuum-maintenance/`） |
| 監視は何を見ていますか？ | 指標・アラートと閾値の根拠 | Day 5（時間不足なら削る。§1-2） |

### 0-3. 作業量の原則

技術的に立派でも作業量が増える設計は減点。残り3日。網羅性・学術的厳密さは評価軸ではない。迷ったら「追い質問に実測で答えられるか」だけで判断する。

---

## 1. 全体構成（決定済み。変えない）

| Day | 構成 | 内容 |
| --- | --- | --- |
| 3 | Burstable B1ms | Flexible Server 構築 + walking skeleton + `SELECT 1` 疎通。STOP 時のバックアップ課金の観測開始。HA 有効化リスクの前倒し検証 |
| 4 | Burstable B1ms | **PITR ドリル（最優先）**。壊す → 特定時刻に復旧 → RTO / RPO 計測。後半に PostgreSQL 側メンテナンス（autovacuum / bloat） |
| 5 | **General Purpose + ゾーン冗長 HA** | 階層変更（ダウンタイム実測）→ HA 有効化 → 計画 / 強制フェイルオーバー → 計測 → destroy |

### 1-1. この順序の理由

**時間が足りなくなったら HA を捨てて PITR を守るため。** 名指しで訊かれたのは「バックアップ」であり、これを落とすわけにはいかない。PITR ドリルを Day 4 に置き、HA を Day 5 に隔離することで、Day 4 までの遅延が本命成果物を侵食しない。また HA（GP ×2台分）は Day 5 に数時間だけ立てるため、課金は月額レートではなく実稼働時間分に収まる。

PostgreSQL 自体を Day 3 前半に作るのは、PITR の復元可能範囲（バックアップの蓄積）を Day 4 までに稼ぐため（[bootstrap.md](./bootstrap.md) 「Day 3 の方針」で確定済み）。

### 1-2. 時間が足りないときに削る順序（この順で削る）

1. **Monitoring のアラート実装**（§7 の指標表と閾値根拠はドキュメントとして残す。作るのを省く）。Monitoring は面談で名指しされていない。
2. **強制フェイルオーバー**（計画フェイルオーバーの実測のみで代表させる。「メンテナンス中に止まりましたか？」への回答は計画フェイルオーバー側で成立する）。
3. **HA 全体**（Day 5 を「階層変更ダウンタイム実測 + PostgreSQL 側メンテの深掘り」に縮退させる）。
4. **削らないもの**: Day 4 の PITR ドリルと Backup 設計根拠（成果物 1・2）、および PostgreSQL 側メンテナンス（成果物 4）。「DB のメンテナンス」で経験者が想起するのは autovacuum / bloat の側であり、Azure の設定画面の話だけでは「クラウドの設定はできるが DB は分かっていない」と見られる。

### 1-3. HA をやる理由（当初「訊かれていないから不要」としたが撤回済み）

- SRE として冗長構成を扱えないのは穴である。
- **HA 構成では計画メンテナンスがフェイルオーバー（standby 先行適用 → 昇格）で処理される**（§2-1 No.12）。つまり計画フェイルオーバーを実測すれば、「メンテナンス中に止まりましたか？」に実測ダウンタイムで答えられるようになる。月次の実メンテナンスに Day 5 中に遭遇することは期待できないため、この代理実測が現実的な唯一の手段である（この立て付け自体を証跡に正直に書く）。

---

## 2. 公式ドキュメントで確認済みの事実（本書の根拠）

以下はすべて 2026-08-19 に Microsoft Learn を実際に読んで確認した。番号は本文から `§2-1 No.x` で参照する。

### 2-1. 確認済み

| No | 項目 | 確認できた内容 | 出典 |
| --- | --- | --- | --- |
| 1 | バックアップ保持期間 | 既定 7 日、7〜35 日で設定可。作成後の変更可・オンライン操作 | [Backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) / [Scaling resources](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-scaling-resources)（"Backup retention period changes are an online operation"） |
| 2 | バックアップ方式と取得間隔 | スナップショットは日次（初回フル、以降差分）+ WAL の連続アーカイブ。WAL アーカイブ由来の遅延 RPO は最大 5 分程度（"the delay RPO can be up to five minutes"） | [Backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) |
| 3 | PITR の時刻粒度 | 保持期間内の**任意の時刻**を指定可（Custom restore point）。復旧は新サーバー作成方式で、既存サーバーは上書きされない | [Backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) |
| 4 | PITR の所要時間 | 「数分〜数時間」とのみ記載（"usually takes from few minutes up to a few hours"）。具体値なし → **Day 4 で実測**（§2-2 No.1） | [Backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) |
| 5 | geo 冗長バックアップの有効化タイミング | **サーバー作成時のみ。作成後は変更不可**（"You can configure geo-redundant storage for backup only during server creation"）。有効時はバックアップサイズが 2 倍で課金 | [Backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) |
| 6 | **STOPPED 時のバックアップと課金** | **停止中は新規バックアップは取得されない**（"No new backups are performed for stopped servers"）。停止時点の保持分は保持され、**プロビジョン済みストレージとバックアップストレージの課金は継続**（"While your server instance is stopped, no new backups are performed. You pay for provisioned storage and backup storage"） | [Backup and restore FAQ](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) |
| 7 | バックアップストレージ無料枠 | プロビジョン済みストレージの 100% まで無料。超過分が GB/月課金 | [Backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) |
| 8 | 停止サーバーの自動再起動 | 停止後 **7 日で自動的に起動する** | [Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits)（Stop/start operations） |
| 9 | 階層変更（Burstable→GP） | 可能（"Scale the compute tier up or down between Burstable, General Purpose, and Memory Optimized"）。**再起動を伴う**。near-zero downtime scaling（10〜30 秒）は存在するが、**Burstable の 1〜2 vCore が絡むスケーリングは対象外**（"Near-zero doesn't work if you scale the compute of your server from or to a compute size of 1 or 2 vCores of the Burstable tier"）。通常スケーリングは 2〜10 分（"this process takes anywhere from 2 to 10 minutes with regular scaling"）→ B1ms からの変更は通常経路。**実ダウンタイムは Day 5 で実測** | [Scaling resources](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-scaling-resources) |
| 10 | HA の階層要件 | **Burstable は HA 非対応**。ゾーン冗長 / 同一ゾーンとも General Purpose か Memory Optimized が必要 | [Reliability in Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql) / [Configure high availability](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-configure-high-availability) |
| 11 | **既存サーバーへの後からの HA 有効化** | **可能**（"You can enable high availability on an existing Azure Database for PostgreSQL flexible server at any time"）。有効化・無効化は**オンライン操作**（"Enabling or disabling high availability is an online operation. This operation doesn't affect your application connectivity and operations"）。CLI 引数は No.25（現環境での実測）に従う | [Configure high availability](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-configure-high-availability) |
| 12 | HA と計画メンテナンス | HA 有効時、メンテナンスは **standby に先に適用 → standby を昇格 → 旧 primary に適用**のローリング方式（"minor version upgrades happen on the standby replica first. To reduce downtime, the standby is promoted to primary"）。非 HA サーバーは「メンテナンス中に短時間のダウンタイム」 | [Reliability in Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql)（Resilience to service maintenance） |
| 13 | ゾーン障害時（≒強制）フェイルオーバー時間 | ゾーン冗長 HA のフェイルオーバーは通常 **60〜120 秒**（"Failover typically completes within 60-120 seconds"）。計画フェイルオーバーは「最小のダウンタイム」とのみ記載で数値なし → **Day 5 で実測** | [Reliability in Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql) |
| 14 | フェイルオーバーのテスト方法 | 強制: `az postgres flexible-server restart --failover Forced` / 計画: `--failover Planned`。**連続実行は不可で 15〜20 分空ける**（"Wait for at least 15 to 20 minutes between failovers"）。「Portal 表示の所要時間より実ダウンタイムは短いことがあり、アプリ視点で測れ」と明記（"You should measure the downtime from the application's perspective"） | [Configure high availability](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-configure-high-availability) |
| 15 | HA の課金 | standby は **primary と同額**で課金（"a standby server is created and it's billed at the same rate as the primary server"）。バックアップは HA でも 1 セットのみで二重課金なし | [Reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql) / [Backup FAQ](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) |
| 16 | メンテナンスウィンドウ | カスタム（曜日 + 1 時間枠）または system-managed（23:00〜7:00 の 1 時間枠）。**5 日前に通知**。通常の間隔は **30 日以上**（≒月次）。Burstable はメンテナンスの reschedule 非対応 | [Planned maintenance](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-maintenance) |
| 17 | 停止中サーバーとメンテナンス | 停止中はメンテナンスは適用されず、**再起動時に適用**される。適用時は再起動が 5〜8 分程度延びる | [Planned maintenance](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-maintenance) |
| 18 | マイナーバージョン更新 | 計画メンテナンスの一部として自動適用（"The service includes security updates, software updates, and minor version upgrades as part of planned maintenance"） | [Reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql) |
| 19 | SLA | ゾーン冗長 HA 99.99% / 同一ゾーン HA 99.95% / 非 HA 99.9% | [Reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql) |
| 20 | autovacuum の既定発火条件 | VACUUM: 変更行が「テーブル行数 × 0.2 + 50」超 / ANALYZE: 「× 0.1 + 50」超（PG13+ の insert 経由は「× 0.2 + 1000」）。監視 SQL（`pg_stat_all_tables` の `n_dead_tup` 等）、長時間トランザクション検出 SQL、bloat 用メトリック `bloat_percent`（`metrics.autovacuum_diagnostics = ON` で有効化、動的パラメータで再起動不要）が公式に提供されている | [Autovacuum tuning](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-autovacuum-tuning) |
| 21 | ストレージ監視の閾値 | 使用率 95%（または残 5 GiB 未満）で**自動的に read-only 化**。「80% 超でのアラート設定」が公式に例示されている（"you can set an alert if the storage percentage exceeds 80% usage"） | [Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) |
| 22 | B1ms の接続数上限 | max 50 / ユーザー接続 35（15 は予約） | [Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) |
| 23 | Burstable の監視推奨 | **CPU Credits Remaining** を監視し低クレジットでアラートせよと明記。クレジット枯渇時は baseline に制限され深刻な性能劣化 | [Compute options](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-compute) |
| 24 | japaneast の HA / geo バックアップ対応 | `ZoneRedundantHa: Enabled` / `geoBackupSupported: Enabled`（Day 0 に `az postgres flexible-server list-skus -l japaneast` で実測済み） | CLI 実測（bootstrap 時） |
| 25 | **HA 有効化 / 無効化の CLI 引数（現環境実測）** | az CLI **2.89.1** の `az postgres flexible-server update --help` / `create --help` を実測した結果、`--high-availability` は**存在しない**（grep 0 件）。現行引数は `--zonal-resiliency`（"Enable or disable high availability feature. Allowed values: Disabled, Enabled"）+ `--standby-zone` / `--allow-same-zone`。`--high-availability` は CLI 2.87.0 で削除済み。公式 How-to ページは新旧引数が混在しており（`--high-availability` / `--zonal-resiliency` / `--zone-resiliency` の 3 表記）、本書は実測で受理を確認した `--zonal-resiliency` のみを使う。`restart --failover Forced / Planned`（No.14）は 2.89.1 に存在することを同時に確認済み | CLI 実測（2026-08-19、az 2.89.1 の `--help`） / [Azure CLI release notes](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes-cli) |
| 26 | public access の既定接続可否 | firewall rule を作成するまで**すべての接続が拒否**される（"By default, the firewall blocks all access to the server"）。許可はサーバーレベル firewall rule に発信元 IP 範囲を登録する方式。**反映まで最大 5 分**（"Changes to the firewall configuration ... can take up to five minutes"） | [Firewall rules](https://learn.microsoft.com/en-us/azure/postgresql/security/security-firewall-rules) |
| 27 | 拡張機能の事前許可 | `CREATE EXTENSION` の前にサーバーパラメータ `azure.extensions` への **allowlist 追加が必須**。CLI は `az postgres flexible-server parameter set --name azure.extensions --value "<ext>,<ext>"`。PG17 での提供バージョン: `vector` 0.8.2 / `pgstattuple` 1.5（いずれも `shared_preload_libraries` 不要） | [Allow extensions](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions) / [Extensions list](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions) |
| 28 | 計画フェイルオーバーの断の順序 | 公式の手順表で、**書き込みブロック（Step 3 "Application writes are blocked when the standby server is close to the primary LSN"）が standby 昇格（Step 4）・DNS 切替（Step 5）より先に発生**する。アプリのダウンタイムは Step 3〜5（"Application downtime starts at step 3 and can resume operation after step 5"）。つまり読み取りの成否だけを見る probe では書き込み断の開始を見逃す | [High availability concepts](https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability)（Planned failover の手順表） |

### 2-2. 出典が取れず「未実測」とする項目（Day 3〜5 で測る）

| No | 項目 | ドキュメントの状況 | いつ測るか |
| --- | --- | --- | --- |
| 1 | PITR の RTO（restore 発行 → 接続可能まで） | 「数分〜数時間」とのみ記載 | Day 4 |
| 2 | PITR の実 RPO（復旧点にどこまで直前のデータが残るか） | WAL 遅延「最大 5 分程度」の一般論のみ | Day 4 |
| 3 | 停止中の `earliestRestoreDate` の動き（復元可能範囲が停止でどう狭まる / 進むか） | 明記なし | Day 3 停止前 → Day 4 起動後の差分で実測 |
| 4 | 階層変更（B1ms→GP）の実ダウンタイム | 「通常スケーリング 2〜10 分」の幅のみ | Day 5（1 秒間隔の疎通ループで実測） |
| 5 | HA 有効化（standby 構築）の所要時間と、その間のアプリ影響 | 「オンライン操作」とのみ記載。所要時間の数値なし | Day 3（リスク潰し時）+ Day 5 |
| 6 | 計画フェイルオーバーの実ダウンタイム | 「least downtime」とのみ記載 | Day 5 |
| 7 | 強制フェイルオーバーの実ダウンタイム（アプリ視点） | 「60〜120 秒」はゾーン障害時の一般値。アプリ視点で測れと明記 | Day 5 |
| 8 | B1ms / GP 最小 SKU の japaneast 実単価 | 料金は [Pricing ページ](https://azure.microsoft.com/pricing/details/postgresql/flexible-server/) と Portal 見積で都度確認する。本書には転記しない（改定で古くなるため） | Day 3 作成時に Portal 見積を証跡に記録 |
| 9 | FreeTrial クォータでの GP + HA（vCore ×2）の可否 | ドキュメントでは判定不能（サブスクリプション依存） | **Day 3 の終わりに前倒しで実地検証**（§3-4） |

---

## 3. Day 3: Burstable 構築 + walking skeleton + 課金観測開始

前提: [bootstrap.md](./bootstrap.md) フェーズC（§3 名前空き確認 / §11 OIDC / §12 tfstate Storage。計 1.75h）を Day 3 の最初に実施する。

### 3-1. PostgreSQL Flexible Server の設計値（Terraform `terraform/persistent/`）

トレードオフを伴う判断は着手時に ADR として記録する（保持期間・geo 冗長の判断で 1 本）。

| 項目 | 値 | 根拠 |
| --- | --- | --- |
| 名前 | `felisaichatbot-pg-dev` | bootstrap §3 で空き確認済みの予定名 |
| リージョン | japaneast | Day 0 決定（アプリ・DB 同一リージョン原則） |
| SKU | `B_Standard_B1ms`（1 vCore / 2 GiB） | Day 3〜4 の検証には最小で足りる。HA が必要になる Day 5 に GP へ変更（§2-1 No.9 で変更可能と確認済み） |
| ストレージ | 32 GiB（最小） | データは数百 MB 規模。バックアップ無料枠も 32 GiB になる（§2-1 No.7） |
| PostgreSQL バージョン | ローカル（Docker の PostgreSQL 17）と揃える。作成前に `az postgres flexible-server list-skus -l japaneast` の `supportedServerVersions` で提供を確認 | ローカルとの差異をなくす |
| バックアップ保持期間 | **7 日（既定のまま）** | 検証期間は 3 日で、復旧ウィンドウ 7 日で十分に覆う。延長はバックアップストレージ消費（=無料枠超過リスク）を増やすだけで、このプロジェクトでは得るものがない（§2-1 No.1）。「既定だから」ではなく「要件（3 日）< 窓（7 日）だから」と ADR に書く |
| geo 冗長バックアップ | **無効** | (a) 有効化は作成時のみで後から変更不可（§2-1 No.5）なので今決める必要がある。(b) 有効時はバックアップサイズ 2 倍課金。(c) geo リストアは PITR 不可・RPO 最大 1 時間で、本プロジェクトの本命である PITR ドリルには寄与しない。(d) リージョン災害対策は本プロジェクトの要件にない。「無効にした」という判断と根拠を残すこと自体が成果物 1 になる |
| HA | 無効（Day 5 に有効化） | Burstable は HA 非対応（§2-1 No.10） |
| ネットワーク | **public access + サーバーレベル firewall rule**。許可対象は (a) 作業端末のグローバル IP（`curl -s ifconfig.me` で当日確認）、(b) Container Apps の egress IP（apply 後に判明するため Terraform で参照して許可） | firewall rule を作るまで全接続拒否（§2-1 No.26）。これがないと `/readyz`（アプリ→DB）も Day 4〜5 の `psql`（作業端末→DB）も開始できない。VNet 統合は本プロジェクトの検証目的に寄与せず作業量だけ増えるため採らない |
| `azure.extensions` | **`VECTOR,PGSTATTUPLE`**（Terraform のサーバーパラメータで設定） | `CREATE EXTENSION` は事前 allowlist 必須（§2-1 No.27）。`vector` は既存 migration `backend/migrations/versions/0001_initial_schema.py` が `CREATE EXTENSION IF NOT EXISTS vector` を実行するため Alembic 適用の前提。`pgstattuple` は Day 4 の bloat 実測（§4-6）で使う。PG17 で両方提供済み（§2-1 No.27） |
| メンテナンスウィンドウ | カスタム: 水曜 17:00 UTC 開始（木曜 02:00 JST） | 検証作業（日中〜夜）と重ならない深夜帯。カスタム設定の実物を持つこと自体が成果物 3 の一部。ただし実メンテは月次（§2-1 No.16）で Day 3〜5 中の遭遇は期待しない、と証跡に正直に書く |

`.mise.toml` への `terraform = "1.14.8"` 追加と、Terraform を使う workflow の pin を**同じ PR で**揃える（bootstrap §7 の予告どおり。勝手に下げない）。

### 3-2. walking skeleton（bootstrap「Day 3 の方針」確定済み）

1. hello world コンテナを ACR に push し、Container Apps にデプロイ（`terraform/ephemeral/`）
2. アプリから PostgreSQL へ `SELECT 1`（backend の `/readyz` がそのまま使える）
3. GitHub Actions からの OIDC 認証 → Terraform apply → イメージ push → デプロイまでを一度通す

### 3-3. バックアップ観測の開始（Day 4 の宿題の仕込み）

サーバー作成直後と停止直前に以下を記録する（読み取り系）。

```bash
az postgres flexible-server show -g rg-felisaichatbot-dev -n felisaichatbot-pg-dev \
  --query "{state: state, earliestRestoreDate: backup.earliestRestoreDate, retention: backup.backupRetentionDays, geo: backup.geoRedundantBackup}" -o json
# Backup Storage Used メトリック（直近1時間）
az monitor metrics list \
  --resource "$(az postgres flexible-server show -g rg-felisaichatbot-dev -n felisaichatbot-pg-dev --query id -o tsv)" \
  --metric backup_storage_used --interval PT1H -o table
```

- 記録先: `docs/verification/restore-drill/observations.md`（時刻は UTC で記録）
- ドキュメント上は「停止中は新規バックアップなし・保持分課金は継続」（§2-1 No.6）。**これが実地でどう見えるか**（`earliestRestoreDate` の動き、Backup Storage Used の推移）を Day 4 起動後の同じコマンドとの差分で確かめる（§2-2 No.3）。

### 3-4. HA 有効化リスクの前倒し検証（Day 3 の終わり・タイムボックス 45 分）

後から HA を有効化できること自体はドキュメントで確認済み（§2-1 No.11）。残るリスクは **FreeTrial のクォータ / リージョン容量**（§2-2 No.9）で、これは実際に叩くまで分からない。Day 5 の朝に発覚すると最終日が崩れるため、Day 3 の終わりに潰す。

1. GP 最小 SKU へスケール: `az postgres flexible-server update -g rg-felisaichatbot-dev -n felisaichatbot-pg-dev --tier GeneralPurpose --sku-name Standard_D2ds_v5`（SKU 名は当日 `list-skus` の実物で確定）
2. HA 有効化を発行: `az postgres flexible-server update ... --zonal-resiliency Enabled`（引数は 2.89.1 で実測確認済み。`--high-availability` は現環境に存在しない。§2-1 No.25）
   - クォータ / 容量系のエラーは同期的に返る（[Configure HA](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-configure-high-availability) にエラー応答の実例が列挙されている）。**エラーなく受理されデプロイが始まれば合格**とする
3. `highAvailability.state` が `Healthy` になったら所要時間を記録（§2-2 No.5 の1回目の実測）→ HA 無効化（`--zonal-resiliency Disabled`。§2-1 No.25）→ B1ms へ戻す
4. タイムボックス超過時: Healthy 待ちの間に §3-5 の teardown 以外を進め、無効化と B1ms 戻しだけ就寝前に必ず行う（GP×2 台を夜間放置しない）
5. **クォータ等で失敗した場合**: Day 5 を「GP サーバー新規作成（HA 有効で作成。10〜15 分）+ アプリ向け替え」に差し替えると**この時点で決めて**本書に追記する。Day 5 当日に迷わない

### 3-5. 検証（これが通れば Day 4 へ）

- CI（GitHub Actions）経由で Container Apps がデプロイされ、`/readyz` が 200 を返す（= Azure 上の PostgreSQL へ `SELECT 1` が通っている = Container Apps からの接続経路が開通している）
- 作業端末から `psql` で接続でき、Alembic migration（`CREATE EXTENSION IF NOT EXISTS vector` を含む）が適用済み（= firewall と `azure.extensions` の設定が効いている。§3-1）。ここが通らないと Day 4 の `psql` 作業・pgstattuple・seed 投入がすべて開始できない
- `az postgres flexible-server show` で `backup.backupRetentionDays: 7` / geo 冗長無効 / `earliestRestoreDate` の値が記録済み
- §3-4 の結果（HA 可否）が確定し、Day 5 の経路（変更 or 新規作成）が決まっている

### 3-6. teardown / stop（Day 3 終了時）

```bash
# Container Apps（ephemeral）は destroy（時間課金を止める）
terraform -chdir=terraform/ephemeral destroy
# PostgreSQL は削除せず stop（バックアップ蓄積と課金観測のため。§2-1 No.6/8）
az postgres flexible-server stop -g rg-felisaichatbot-dev -n felisaichatbot-pg-dev
az resource list -g rg-felisaichatbot-dev -o table   # 消し忘れ・残存の目視確認
```

- ローカルは `docker compose down`。**`-v` を付けない**（ローカル DB のデータ・検証素材が消える）。

---

## 4. Day 4: PITR ドリル（最優先）+ PostgreSQL 側メンテナンス

### 4-1. 朝: 起動と停止中挙動の実測

```bash
az postgres flexible-server start -g rg-felisaichatbot-dev -n felisaichatbot-pg-dev
```

- 起動所要時間を記録（保留メンテナンスが適用されると 5〜8 分延びる仕様。§2-1 No.17。適用有無も記録）
- §3-3 と同じコマンドで `earliestRestoreDate` / Backup Storage Used を取り、停止前との差分を `observations.md` に記録（§2-2 No.3 の答え）

### 4-2. ドリル準備: 復旧点を判定できるデータを作る

- seed データ（気象庁データ）を投入した上で、**1 分おきにタイムスタンプ行を insert するマーカーテーブル**を 30 分以上回す。これが RPO 判定の物差しになる（「復旧後に残っている最後のマーカー」と復旧目標時刻の差が実測 RPO）
- WAL バックアップを確実に発生させるため、マーカー稼働中は他の書き込みも通常どおり行う

### 4-3. ドリル本番（すべての時刻を UTC で記録）

1. `T0`: 正常状態を記録（各テーブルの行数・マーカー最新時刻）
2. `T1`: 破壊を実行（例: `DROP TABLE documents;`）。実行時刻を記録
3. 復旧目標時刻 `T_target = T1 の 1 分前` を決める
4. 復元を発行し、発行時刻を記録:

   ```bash
   az postgres flexible-server restore \
     -g rg-felisaichatbot-dev \
     --name felisaichatbot-pg-dev-restored \
     --source-server felisaichatbot-pg-dev \
     --restore-time "<T_target (ISO8601 UTC)>"
   ```

5. **RTO 実測**: restore 発行 → 復元サーバーへ `psql` で `SELECT 1` が通るまでの経過時間（1 分間隔でポーリングし、`state` 遷移もログする）
6. **RPO 実測（実損失）**: `T1 −（復元サーバーに残っている最新マーカー時刻）`。RPO は「障害時点（T1）からどれだけのデータが失われたか」なので、意図的に 1 分手前を指定した分も含めて T1 起点で計算する（RPO の定義: [Business continuity concepts](https://learn.microsoft.com/en-us/azure/reliability/concept-business-continuity-high-availability-disaster-recovery)）。破壊したテーブルが `T_target` 時点の内容で存在することを行数で確認
7. **復元点精度（RPO とは別に記録）**: `T_target −（復元サーバーの最新マーカー時刻）`。指定した時刻をどこまで正確に再現できたかの値であり、RPO と混ぜない。マーカーは 1 分間隔のため、両値とも最大 1 分の標本化誤差を含む（この注記ごと証跡に書く）
8. アプリの向け替え: 接続文字列を復元サーバーに変えて `/readyz` → `/chat` を確認（「復旧した」の判定はアプリが動くことまで）
9. 注意（§2-1 No.3 と [Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) の restore 節より）: 復元は**新サーバー作成**であり、ファイアウォール規則は引き継がれない。復元後に接続規則を再設定する手順まで込みで計測する

### 4-4. ドリル証跡（`docs/verification/restore-drill/`）

`2026-08-XX-pitr-drill.md` に以下を残す: タイムライン表（T0 / T1 / T_target / restore 発行 / 接続回復 / アプリ回復）、実行コマンド全文と出力、**RTO / RPO（実損失）の実測値と復元点精度**（§4-3 の 5〜7）、引っかかった点、次にやるなら変える点。

### 4-5. ドリル後始末

- 元サーバー `felisaichatbot-pg-dev` を正として継続する（破壊したテーブルは Alembic + seed スクリプトで再構築できることを確認済みのうえで破壊対象に選ぶ）
- 復元サーバー `felisaichatbot-pg-dev-restored` は証跡取得後に**削除**（放置課金の芽を残さない）

### 4-6. 午後: PostgreSQL 側メンテナンス（成果物 4。落とさない）

観測はローカル Docker ではなく **Azure 上のサーバーで**行う（サーバーパラメータとメトリックも成果物のため）。証跡は `docs/verification/vacuum-maintenance/`。

1. `metrics.autovacuum_diagnostics = ON` を設定（動的パラメータ・再起動不要。§2-1 No.20）
2. **autovacuum 発火の実測**: 行数 N のテーブルに「0.2 × N + 50」を超える UPDATE を流し、[公式の監視 SQL](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-autovacuum-tuning)（`pg_stat_all_tables` の `n_dead_tup` / `last_autovacuum` / `dead_pct`）で発火前後を記録
3. **bloat 計測**: `CREATE EXTENSION pgstattuple;`（利用可否は `SHOW azure.extensions` で確認）でテーブル / インデックスの実 bloat を、`bloat_percent` メトリックで推定値を、それぞれ記録して突き合わせる
4. **ANALYZE と統計情報**: `ANALYZE` 前後で `EXPLAIN` の推定行数がどう変わるかを 1 例記録
5. **長時間トランザクションの vacuum 阻害**: セッション A で `BEGIN ISOLATION LEVEL REPEATABLE READ; SELECT count(*) FROM <対象テーブル>;` を実行して放置 → セッション B の UPDATE + COMMIT で dead tuples を作る → autovacuum / `VACUUM (VERBOSE)` が回っても dead tuples が「dead but not yet removable」で回収されないことを観測 → セッション A の `COMMIT` 後に回収されることを観測。阻害中は `pg_stat_activity` のセッション A の **`backend_xmin` の age** も記録する（読み取りのみのトランザクションは `backend_xid` を持たないため、`backend_xmin` 側を見る）
   - 手順の根拠（ローカル Docker の PostgreSQL 17.11 で 2026-08-19 に実測確認済み）: Read Committed では `BEGIN;` のみ・`SELECT` 実行後のアイドル、いずれも `backend_xid` / `backend_xmin` が NULL のままで dead tuples は全量回収され（1000/1000 removed）、阻害を**再現できない**。REPEATABLE READ + `SELECT` のみが `backend_xmin` を保持し「0 removed / 1000 dead but not yet removable」を再現した。仕様上も、スナップショットは最初のクエリで取得され（[Transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html)）、Read Committed はステートメント単位でスナップショットを取り直す。検出 SQL の `backend_xmin` / `backend_xid` は [pg_stat_activity](https://www.postgresql.org/docs/17/monitoring-stats.html) 参照

### 4-7. 検証（これが通れば Day 5 へ）

- RTO / RPO の実測値が記録され、復元サーバーが削除済み
- autovacuum 発火・bloat・長時間トランザクション阻害の 3 点の観測記録がある

### 4-8. teardown / stop（Day 4 終了時）

- 復元サーバー削除済みの再確認（`az postgres flexible-server list -g rg-felisaichatbot-dev -o table`）
- Container Apps を立てた場合は destroy、PostgreSQL は stop（Day 3 と同じ）
- ローカルは `docker compose down`（`-v` なし）

---

## 5. Day 5: General Purpose + ゾーン冗長 HA（フェイルオーバー実測）→ 全消し

計測の共通道具として、別端末で 1 秒間隔の疎通ループを**読み取り・書き込みの 2 本**回し続ける。計画フェイルオーバーは書き込みブロックが DNS 切替より先に始まる（§2-1 No.28）ため、読み取りだけでは断の開始を見逃す。また `connect_timeout` 未指定の接続は**無期限に待つ**（"Zero, negative, or not specified means wait indefinitely"。[libpq](https://www.postgresql.org/docs/17/libpq-connect.html)）ため、障害中の 1 試行がハングするとその間の計測が空白になる。タイムアウトを明示し、**各試行の開始時刻・終了時刻・終了コード**を残す:

```bash
export PGCONNECT_TIMEOUT=3   # libpq が読む接続タイムアウト（未指定は無期限待機）
# 事前に 1 回だけ: psql "$DATABASE_URL" -c 'CREATE TABLE IF NOT EXISTS failover_probe (ts timestamptz);'

# 読み取り probe
while true; do
  s=$(date -u +%FT%T.%3NZ)
  out=$(timeout 5 psql "$DATABASE_URL" -qtAc 'SELECT 1' 2>&1); rc=$?
  echo "$s $(date -u +%FT%T.%3NZ) rc=$rc ${out:0:40}"
  sleep 1
done | tee read-probe.log

# 書き込み probe（別端末。COMMIT まで成功して初めて rc=0 になる）
while true; do
  s=$(date -u +%FT%T.%3NZ)
  out=$(timeout 5 psql "$DATABASE_URL" -qtAc "INSERT INTO failover_probe VALUES (now()) RETURNING 1" 2>&1); rc=$?
  echo "$s $(date -u +%FT%T.%3NZ) rc=$rc ${out:0:40}"
  sleep 1
done | tee write-probe.log
```

- ダウンタイムはログから読み取り断・書き込み断を**別々に**算出する: 断の下限 =「最後に成功した試行の終了時刻 → 最初に復帰した試行の開始時刻」、上限 =「最後に成功した試行の開始時刻 → 最初に復帰した試行の終了時刻」。試行間隔（1 秒）+ タイムアウト分の幅がある値として証跡に書く
- `timeout 5` は接続後のクエリ側ハング（TCP 切断が伝わらないケース）の保険。probe の追加コストは書き込み 1 行 / 秒で、実行時間は増やさない

### 5-1. 階層変更（Burstable → General Purpose）ダウンタイム実測

1. サーバー起動 → 疎通ループ開始
2. `az postgres flexible-server update --tier GeneralPurpose --sku-name <Day 3 で確定した SKU>`
3. ループのログから断の実測値を記録（ドキュメント上の目安は通常スケーリング 2〜10 分。§2-1 No.9）

### 5-2. HA 有効化（§3-4 で確定した経路で）

- 経路 A（既存サーバーへ有効化）: `az postgres flexible-server update --zonal-resiliency Enabled`（§2-1 No.25）。オンライン操作でアプリ断がないこと（§2-1 No.11）を疎通ループで裏取りし、`Healthy` までの所要時間を記録
- 経路 B（Day 3 で不可と判明した場合）: HA 有効の GP サーバーを新規作成（10〜15 分）→ seed 再投入 → アプリ向け替え

### 5-3. フェイルオーバー実測（成果物 3 の中核）

1. **計画フェイルオーバー**: `az postgres flexible-server restart -g rg-felisaichatbot-dev -n felisaichatbot-pg-dev --failover Planned` → 疎通ループで実測。**この値が「メンテナンス中に止まりましたか？」への回答**になる（HA では計画メンテがこの standby 切替で処理される。§2-1 No.12。実メンテの実測ではなく代理実測である旨も証跡に書く）
2. **15〜20 分待つ**（§2-1 No.14 の明記事項。守らないと標的の standby が未確立）
3. **強制フェイルオーバー**: `--failover Forced` → 実測（ドキュメント目安 60〜120 秒との差を記録）
4. 証跡: `docs/verification/failover-drill/` にタイムライン・probe ログ抜粋・実測値・zone の入れ替わり（`show` の `availabilityZone` / `standbyAvailabilityZone`）を記録
5. HA 構成の判断（なぜゾーン冗長か・SLA 差・コスト）を ADR に 1 本記録

### 5-4. Monitoring 仕上げ（時間が足りなければここを削る。§1-2）

§7 の指標表のうち、最低限 storage 80% と CPU 系の 2 本のアラートルールを作り、1 本は実際に発火させて（閾値を一時的に下げる等）通知経路を確認する。残りは表と根拠の記載のみでも成果物として成立させる。

### 5-5. 検証（これが通れば destroy へ）

- 階層変更 / HA 有効化 / 計画・強制フェイルオーバーの 4 つの実測値が記録されている
- 証跡 3 ディレクトリ（restore-drill / vacuum-maintenance / failover-drill）がコミットされている

### 5-6. teardown（Day 5 終了時 = 検証完了後に全 destroy）

```bash
terraform -chdir=terraform/ephemeral destroy
terraform -chdir=terraform/persistent destroy   # PostgreSQL 含む。証跡コミット済みを確認してから
az resource list -g rg-felisaichatbot-dev -o table   # 残存ゼロ確認（Azure OpenAI は面談デモ用に残すなら明示的に残す）
```

- HA は destroy 前に無効化する必要はない（サーバーごと消える）。destroy が何かで失敗した場合のみ、時間課金の大きい順（HA 無効化 → GP サーバー stop）に手で止血する

---

## 6. 成果物 5 点と作業の対応

| # | 成果物 | 中身 | 作る日 |
| --- | --- | --- | --- |
| 1 | Backup | 保持 7 日・日次スナップショット + WAL・geo 冗長無効の**根拠**（§3-1 の表 + ADR） | Day 3 |
| 2 | PITR ドリル | 破壊 → 特定時刻へ復旧。**RTO / RPO 実測** → `docs/verification/restore-drill/` | Day 4 |
| 3 | Maintenance（Azure 側） | メンテナンスウィンドウ設定・マイナー更新の仕組み・**階層変更ダウンタイム実測**・**STOPPED 時のバックアップ挙動の実測**（ドキュメント確認済み事項の実地裏取り） | Day 3〜5 |
| 4 | Maintenance（PostgreSQL 側） | autovacuum 発火実測・bloat 計測・ANALYZE・長時間トランザクション阻害の観測 → `docs/verification/vacuum-maintenance/` | Day 4 |
| 5 | Monitoring | 指標・アラートと**閾値の根拠**（§7）。時間不足なら実装を削り表を残す | Day 5 |

---

## 7. Monitoring: 指標と閾値の根拠（成果物 5 の設計）

| 指標 | 閾値 | 根拠 |
| --- | --- | --- |
| `storage_percent` | > 80% | 公式が 80% でのアラートを例示（§2-1 No.21）。95% で自動 read-only 化という実害が閾値の意味を与える |
| CPU Credits Remaining（Burstable 期間中） | 低下傾向で警告 | 公式推奨（§2-1 No.23）。枯渇で baseline 制限。**具体の閾値は Day 3〜4 の実測レンジを見て決め、根拠を証跡に書く（未実測のまま数字を置かない）** |
| `cpu_percent`（GP 変更後） | 未定 | 出典のある既定値がないため、Day 5 の負荷実測レンジから決める。決めた根拠を証跡に書く |
| active connections | > 30 | B1ms のユーザー接続上限 35（§2-1 No.22）の手前。上限到達は `FATAL: sorry, too many clients already` の実害 |
| Backup Storage Used | > 32 GiB | 無料枠 = プロビジョン済みストレージ 100%（§2-1 No.7）。超過分から課金が始まる |
| `bloat_percent` / `n_dead_tup` | 未定 | メトリックは公式提供（§2-1 No.20）。閾値はワークロード依存のため Day 4 の観測値から決める |

---

## 8. コスト見張り

- **クレジット残の確認**: FreeTrial の残クレジットは Azure Portal（Subscription → 残高、または Cost Management）で確認する。CLI の `az consumption usage list` は補助として使えるが、FreeTrial サブスクリプションでの網羅性・即時性は未検証（この確認自体を Day 3 に 1 度行い、以後の見張り手段を確定する）
- **毎日の終業チェック**（§3-6 / §4-8 / §5-6 の teardown と同時に）:

  ```bash
  az postgres flexible-server list -g rg-felisaichatbot-dev --query "[].{name:name, state:state, sku:sku.name}" -o table
  az resource list -g rg-felisaichatbot-dev -o table
  ```

- **停止中も課金は残る**: stop で止まるのはコンピュート課金のみ。ストレージ + バックアップストレージは継続（§2-1 No.6）。7 日で自動再起動する（§2-1 No.8）ため「stop したから放置してよい」は成立しない
- **プロジェクト完了後の全消し**（クレジット失効 2026-09-18 より前に必ず実施）:

  ```bash
  az group delete -n rg-felisaichatbot-dev --yes        # アプリ・DB・Azure OpenAI すべて
  az group delete -n felisaichatbot-rg-tfstate --yes    # tfstate Storage（bootstrap §12）
  ```

  実行前に、証跡（`docs/verification/`）がすべてコミット済みであることを確認する。

---

## 9. Day 3〜5 でやらないこと（スコープクリープ防止）

- geo リストア・読み取りレプリカ・長期保持（Azure Backup / LTR）の実施（根拠の議論は §3-1 で済ませており、実物は作らない）
- Memory Optimized 階層・pgBouncer・カスタムメンテナンス自動化などの検証
- アプリ機能の追加開発（walking skeleton の先のアプリ改善は本プロジェクトの目的ではない）
- 本書に書いた設計値の再議論（ADR 化は実施時に行うが、方向は本書で確定）

## 10. 参照する既存資産（読み取りのみ）

| 参照先 | 使う場面 |
| --- | --- |
| `terraform-hannibal/docs/operations/rollback-plan.md` | Day 4: restore 手順の構造（切り分け → 初動 → 復旧）の手本 |
| `terraform-hannibal/terraform/modules/rds/main.tf:1-58` | Day 3: retention / maintenance window の環境別出し分けの手本（Azure へ 1:1 対応） |
| `ticket-c2c-platform/docs/architecture/production-readiness.md`（M-17 / M-18 / L-32） | Day 4 着手時: DB backup / PITR runbook 要件リスト |
| `ticket-c2c-platform/docs/runbooks/alarm-aurora.md` | Day 5: アラート初動 Runbook の書式 |
