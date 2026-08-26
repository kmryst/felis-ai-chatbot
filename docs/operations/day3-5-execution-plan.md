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
| 保持期間はどう決めましたか？ | 7日（既定）採用の根拠と、geo 冗長の判断の記録（当初無効 → 無料枠の判明で前提が変わり有効化。ADR-0011 / ADR-0019） | Day 3（ADR） |
| メンテナンス中に止まりましたか？ | 計画フェイルオーバーの実測ダウンタイム（HA では計画メンテがこの切替で処理される） | Day 5（`docs/verification/failover-drill/`） |
| vacuum は見ていますか？ | autovacuum 発火・bloat・長時間トランザクション阻害の観測記録 | Day 4（`docs/verification/vacuum-maintenance/`） |
| 監視は何を見ていますか？ | 指標・アラートと閾値の根拠 | Day 5（時間不足なら削る。§1-2） |

### 0-3. 作業量の原則

技術的に立派でも作業量が増える設計は減点。残り3日。網羅性・学術的厳密さは評価軸ではない。迷ったら「追い質問に実測で答えられるか」だけで判断する。

---

## 1. 全体構成（決定済み。変えない）

| Day | 構成 | 内容 |
| --- | --- | --- |
| 3 | Burstable B1ms | Flexible Server 構築 + walking skeleton + `SELECT 1` 疎通。バックアップ観測開始（サーバーは stop しない。ADR-0017）。HA 有効化リスクの前倒し検証 |
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
| 20 | autovacuum の既定発火条件 | **3 つの条件は別物で、比較する対象が違う**（「変更行」と一括りにしない）。VACUUM: **前回 VACUUM 以降の dead tuple 数**（`n_dead_tup`）が `reltuples × 0.2 + 50` 超 / insert-vacuum（PG13+）: **前回 VACUUM 以降に INSERT した行数**（`n_ins_since_vacuum`）が `reltuples × 0.2 + 1000` 超 / ANALYZE: **前回 ANALYZE 以降の INSERT + UPDATE + DELETE の合計**（`n_mod_since_analyze`）が `reltuples × 0.1 + 50` 超。`reltuples` は `pg_class.reltuples` で、**VACUUM だけでなく ANALYZE でも更新される**（発火予測への影響は [credit-window-execution-plan.md](./credit-window-execution-plan.md) §5-4）。監視 SQL（`pg_stat_all_tables` の `n_dead_tup` 等）、長時間トランザクション検出 SQL、bloat 用メトリック `bloat_percent`（`metrics.autovacuum_diagnostics = ON` で有効化、動的パラメータで再起動不要）が公式に提供されている | [Autovacuum tuning](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-autovacuum-tuning) |
| 21 | ストレージ監視の閾値 | 使用率 95%（または残 5 GiB 未満）で**自動的に read-only 化**。「80% 超でのアラート設定」が公式に例示されている（"you can set an alert if the storage percentage exceeds 80% usage"） | [Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) |
| 22 | B1ms の接続数上限 | max 50 / ユーザー接続 35（15 は予約） | [Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) |
| 23 | Burstable の監視推奨 | **CPU Credits Remaining** を監視し低クレジットでアラートせよと明記。クレジット枯渇時は baseline に制限され深刻な性能劣化 | [Compute options](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-compute) |
| 24 | japaneast の HA / geo バックアップ対応 | `ZoneRedundantHa: Enabled` / `geoBackupSupported: Enabled`（Day 0 に `az postgres flexible-server list-skus -l japaneast` で実測済み） | CLI 実測（bootstrap 時） |
| 25 | **HA 有効化 / 無効化の CLI 引数（現環境実測）** | az CLI **2.89.1** の `az postgres flexible-server update --help` / `create --help` を実測した結果、`--high-availability` は**存在しない**（grep 0 件）。現行引数は `--zonal-resiliency`（"Enable or disable high availability feature. Allowed values: Disabled, Enabled"）+ `--standby-zone` / `--allow-same-zone`。`--high-availability` は CLI 2.87.0 で削除済み。公式 How-to ページは新旧引数が混在しており（`--high-availability` / `--zonal-resiliency` / `--zone-resiliency` の 3 表記）、本書は実測で受理を確認した `--zonal-resiliency` のみを使う。`restart --failover Forced / Planned`（No.14）は 2.89.1 に存在することを同時に確認済み | CLI 実測（2026-08-19、az 2.89.1 の `--help`） / [Azure CLI release notes](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes-cli) |
| 26 | public access の既定接続可否 | firewall rule を作成するまで**すべての接続が拒否**される（"By default, the firewall blocks all access to the server"）。許可はサーバーレベル firewall rule に発信元 IP 範囲を登録する方式。**反映まで最大 5 分**（"Changes to the firewall configuration ... can take up to five minutes"） | [Firewall rules](https://learn.microsoft.com/en-us/azure/postgresql/security/security-firewall-rules) |
| 27 | 拡張機能の事前許可 | `CREATE EXTENSION` の前にサーバーパラメータ `azure.extensions` への **allowlist 追加が必須**。CLI は `az postgres flexible-server parameter set --name azure.extensions --value "<ext>,<ext>"`。PG17 での提供バージョン: `vector` 0.8.2 / `pgstattuple` 1.5（いずれも `shared_preload_libraries` 不要） | [Allow extensions](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions) / [Extensions list](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions) |
| 28 | 計画フェイルオーバーの断の順序 | 公式の手順表で、**書き込みブロック（Step 3 "Application writes are blocked when the standby server is close to the primary LSN"）が standby 昇格（Step 4）・DNS 切替（Step 5）より先に発生**する。アプリのダウンタイムは Step 3〜5（"Application downtime starts at step 3 and can resume operation after step 5"）。つまり読み取りの成否だけを見る probe では書き込み断の開始を見逃す | [High availability concepts](https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability)（Planned failover の手順表） |
| 29 | **委任サブネットの `Microsoft.Storage` service endpoint** | 委任サブネットに最初のサーバーがプロビジョンされた時点で、Azure が `Microsoft.Storage` の service endpoint を**自動付与する**。用途は **WAL ファイルを Azure Storage へアップロードする通信の経路確保**（"This configuration ensures reliable routing of traffic to the Azure Storage accounts used for uploading Write-Ahead Log (WAL) files"）。**削除すると接続性を損ない得る**（"Removing this endpoint may disrupt connectivity and can lead to unintended consequences for core service operations"）。Terraform 側は `azurerm_subnet` に明記しておかないと毎回この endpoint を削除する plan を出し続ける（2026-08-22 実測・対応済み） | [Private access (VNet integration)](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private) |
| 30 | **revision suffix の名前衝突は ARM がエラーで拒否する** | 非アクティブな既存 revision と同名の suffix を指定した update は、PATCH が HTTP 202 で受理された後に revision provisioning が `revision with suffix probe1 already exists.`（`ContainerAppOperationError`）で失敗する。既存 revision は無変更。**公式ドキュメントに衝突時挙動の記載はなく、2026-08-22 の意図的衝突実測（vnet-integration-cutover.md §3-3）で確定した事実**。旧 revision_suffix 固定方式（PR #99 で廃止）なら Day 4 の戻し apply がこのエラーでブロックされていた | [実測記録](../verification/vnet-cutover/observations.md)（公式記載なしのため実測が正本） |
| 31 | **既定の `az containerapp revision list` は非アクティブ revision を表示しない** | deprovision 完了後の revision は既定の一覧から消え、`--all`（ヘルプ実出力: "Show inactive revisions."）を付けたときのみ Active=False / Stopped として見える（2026-08-22 実測）。非アクティブ側の確認・衝突調査では `--all` 必須 | `az containerapp revision list --help` 実出力 + [実測記録](../verification/vnet-cutover/observations.md) |

### 2-2. 出典が取れず「未実測」とする項目（Day 3〜5 で測る）

| No | 項目 | ドキュメントの状況 | いつ測るか |
| --- | --- | --- | --- |
| 1 | PITR の RTO（restore 発行 → 接続可能まで） | 「数分〜数時間」とのみ記載 | Day 4 |
| 2 | PITR の実 RPO（障害時点 `T1` からどれだけ直前のデータが失われるか。§4-3 の 6。指定時刻をどこまで正確に再現できたかの**復元点精度**は §4-3 の 7 で別に測る） | WAL 遅延「最大 5 分程度」の一般論のみ | Day 4 |
| 3 | 停止中の `earliestRestoreDate` の動き（復元可能範囲が停止でどう狭まる / 進むか） | 明記なし | **取りやめ**（夜間 stop の廃止により停止状態が発生しない。ADR-0017。代わりに連続稼働中の日次推移を §3-3 で記録） |
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

トレードオフを伴う判断は着手時に ADR として記録する（保持期間・geo 冗長の判断で 1 本 = ADR-0011。geo 冗長はその後、前提の変化により ADR-0019 で有効へ変更した）。

| 項目 | 値 | 根拠 |
| --- | --- | --- |
| 名前 | `pgsql-felisaichatbot-dev` | 命名規則は ADR-0013（CAF 略語準拠）。bootstrap §3 で空き確認済みの予定名（改名後の 2026-08-20 再確認で nameAvailable: true） |
| resource group | `rg-felisaichatbot-dev-tf`（bootstrap §11-3 で手動作成。Terraform 管理にしない） | Terraform 管理外の Azure OpenAI が同居する `rg-felisaichatbot-dev` から分離し、CI 用 service principal の Contributor スコープを Terraform 管理リソースに限定する（ADR-0012）。既存リソースは移動しない |
| リージョン | japaneast | Day 0 決定（アプリ・DB 同一リージョン原則） |
| SKU | `B_Standard_B1ms`（1 vCore / 2 GiB） | Day 3〜4 の検証には最小で足りる。HA が必要になる Day 5 に GP へ変更（§2-1 No.9 で変更可能と確認済み） |
| ストレージ | 32 GiB（最小） | データは数百 MB 規模。バックアップ無料枠も 32 GiB になる（§2-1 No.7） |
| PostgreSQL バージョン | ローカル（Docker の PostgreSQL 17）と揃える。作成前に `az postgres flexible-server list-skus -l japaneast` の `supportedServerVersions` で提供を確認 | ローカルとの差異をなくす |
| バックアップ保持期間 | **7 日（既定のまま）** | 検証期間は 3 日で、復旧ウィンドウ 7 日で十分に覆う。延長はバックアップストレージ消費（=無料枠超過リスク）を増やすだけで、このプロジェクトでは得るものがない（§2-1 No.1）。「既定だから」ではなく「要件（3 日）< 窓（7 日）だから」と ADR に書く |
| geo 冗長バックアップ | **有効**（**2026-08-22 改訂。ADR-0019**。当初は無効 = ADR-0011） | 有効化は作成時のみで後から変更不可（§2-1 No.5）であり、cutover（ADR-0018）の再作成が最後の設定機会。当初の却下理由のうち「バックアップサイズ 2 倍課金」は 12 か月無料枠（バックアップ 32 GB）の判明と実測約 2.7 MiB で崩れ、有効化の実コストがゼロになった。geo リストアは PITR 不可・RPO 最大 1 時間で PITR ドリルとは別物、リージョン災害対策が要件外である点は不変（ADR-0019）。判断の反転の経緯を記録すること自体が成果物 1 になる |
| HA | 無効（Day 5 に有効化） | Burstable は HA 非対応（§2-1 No.10） |
| ネットワーク | **private access（VNet 統合）**: 委任サブネット `snet-felisaichatbot-dev-pgsql`（/28）+ private DNS zone。`public_network_access_enabled = false`・firewall rule なし（**2026-08-22 改訂。ADR-0018**） | 当初の「public access + firewall rule」は walking skeleton 開通までの暫定構成（Issue #81）。egress IP の変動が実測で確認され（[walking-skeleton/observations.md](../verification/walking-skeleton/observations.md)）、IP 許可は本質的な制御にならないため、テーブル 0 件・バックアップ 1 件の再作成コスト最小のうちに private access へ確定した。`psql` / Alembic は VNet 内の ops コンテナ経由（[vnet-integration-cutover.md](./vnet-integration-cutover.md)） |
| `azure.extensions` | **`VECTOR,PGSTATTUPLE`**（Terraform のサーバーパラメータで設定） | `CREATE EXTENSION` は事前 allowlist 必須（§2-1 No.27）。`vector` は既存 migration `backend/migrations/versions/0001_initial_schema.py` が `CREATE EXTENSION IF NOT EXISTS vector` を実行するため Alembic 適用の前提。`pgstattuple` は Day 4 の bloat 実測（§4-6）で使う。PG17 で両方提供済み（§2-1 No.27） |
| メンテナンスウィンドウ | カスタム: 水曜 17:00 UTC 開始（木曜 02:00 JST） | 検証作業（日中〜夜）と重ならない深夜帯。カスタム設定の実物を持つこと自体が成果物 3 の一部。ただし実メンテは月次（§2-1 No.16）で Day 3〜5 中の遭遇は期待しない、と証跡に正直に書く |

`.mise.toml` への `terraform = "1.14.8"` 追加と、Terraform を使う workflow の pin を**同じ PR で**揃える（bootstrap §7 の予告どおり。勝手に下げない）。

### 3-2. walking skeleton（bootstrap「Day 3 の方針」確定済み）

1. hello world コンテナを ACR に push し、Container Apps にデプロイ（`terraform/ephemeral/`）
2. アプリから PostgreSQL へ `SELECT 1`（backend の `/readyz` がそのまま使える）
3. GitHub Actions からの OIDC 認証 → Terraform apply → イメージ push → デプロイまでを一度通す

### 3-3. バックアップ観測の開始（Day 4 の宿題の仕込み）

サーバー作成直後と毎日の終業時に以下を記録する（読み取り系）。

```bash
az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --query "{state: state, earliestRestoreDate: backup.earliestRestoreDate, retention: backup.backupRetentionDays, geo: backup.geoRedundantBackup}" -o json
# Backup Storage Used メトリック（直近1時間）
az monitor metrics list \
  --resource "$(az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev --query id -o tsv)" \
  --metric backup_storage_used --interval PT1H -o table
```

- 記録先: `docs/verification/restore-drill/observations.md`（時刻は UTC で記録）
- 「停止中は新規バックアップなし」（§2-1 No.6）は、夜間 stop を廃止した根拠のひとつ（ADR-0017）。stop しないため §2-2 No.3 の停止中差分の実測は取りやめ、代わりに**連続稼働中**の `earliestRestoreDate` / Backup Storage Used の日次推移を記録する（バックアップ蓄積が計画どおり進んでいることの確認）。

### 3-4. HA 有効化リスクの前倒し検証（Day 3 の終わり・タイムボックス 45 分）

後から HA を有効化できること自体はドキュメントで確認済み（§2-1 No.11）。残るリスクは **FreeTrial のクォータ / リージョン容量**（§2-2 No.9）で、これは実際に叩くまで分からない。Day 5 の朝に発覚すると最終日が崩れるため、Day 3 の終わりに潰す。

1. GP 最小 SKU へスケール: `az postgres flexible-server update -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev --tier GeneralPurpose --sku-name Standard_D2ds_v5`（SKU 名は当日 `list-skus` の実物で確定）
2. HA 有効化を発行: `az postgres flexible-server update ... --zonal-resiliency Enabled`（引数は 2.89.1 で実測確認済み。`--high-availability` は現環境に存在しない。§2-1 No.25）
   - クォータ / 容量系のエラーは同期的に返る（[Configure HA](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-configure-high-availability) にエラー応答の実例が列挙されている）。**エラーなく受理されデプロイが始まれば合格**とする
3. `highAvailability.state` が `Healthy` になったら所要時間を記録（§2-2 No.5 の1回目の実測）→ HA 無効化（`--zonal-resiliency Disabled`。§2-1 No.25）→ B1ms へ戻す
4. タイムボックス超過時: Healthy 待ちの間に §3-5 の teardown 以外を進め、無効化と B1ms 戻しだけ就寝前に必ず行う（GP×2 台を夜間放置しない）
5. **クォータ等で失敗した場合**: Day 5 を「GP サーバー新規作成（HA 有効で作成。10〜15 分）+ アプリ向け替え」に差し替えると**この時点で決めて**本書に追記する。Day 5 当日に迷わない

### 3-5. 検証（これが通れば Day 4 へ）

- CI（GitHub Actions）経由で Container Apps がデプロイされ、`/readyz` が 200 を返す（= Azure 上の PostgreSQL へ `SELECT 1` が通っている = Container Apps からの接続経路が開通している）
- `psql` で接続でき、Alembic migration（`CREATE EXTENSION IF NOT EXISTS vector` を含む）が適用済み（= `azure.extensions` の設定が効いている。§3-1）。**private access 化（ADR-0018）後の psql / alembic は作業端末からではなく VNet 内の ops コンテナ / migration Job から行う**（[vnet-integration-cutover.md](./vnet-integration-cutover.md) §3）。ここが通らないと Day 4 の `psql` 作業・pgstattuple・seed 投入がすべて開始できない
- `az postgres flexible-server show` で `backup.backupRetentionDays: 7` / geo 冗長有効（cutover 後の再作成サーバー。ADR-0019。cutover 前の旧サーバーの記録は Disabled で正しい） / `earliestRestoreDate` の値が記録済み
- §3-4 の結果（HA 可否）が確定し、Day 5 の経路（変更 or 新規作成）が決まっている

### 3-6. teardown / stop（Day 3 終了時）

```bash
# ephemeral（ACR / CAE / Container Apps）は destroy しない（下記。ADR-0018 追記 2026-08-22。
# 当初の「毎日 destroy」から改訂。最終 destroy は §5-6 のみ）
# PostgreSQL は stop しない（下記。ADR-0017）。稼働状態と残存リソースの確認だけ行う
az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev --query state -o tsv   # Ready のはず
az resource list -g rg-felisaichatbot-dev-tf -o table   # 消し忘れ・残存の目視確認
```

- **ephemeral 層は夜間 destroy しない**（ADR-0018 追記 2026-08-22。当初の「終業時に destroy」から改訂）。理由:
  - private access 化（ADR-0018）後、ops Container App / migration Job が**唯一の DB アクセス経路**になる。
    夜に destroy すると、翌朝の Day 4 ドリル（seed 投入・破壊・復元確認）も Day 5 の疎通 probe も
    VNet 内から打つ手段がなく開始できない
  - 残すことによる追加コストは ACR 0.1666 USD/日 + custom VNet の CAE managed resources 込みで
    約 0.84 USD/日（Retail Prices API 実測単価。ADR-0018）。Container App はスケールゼロ
    （min_replicas 0）のため夜間のコンピュート課金はない
  - 対案（毎朝 ACR 再 push を含む 2 段階 apply で作り直す）は、ドリル本番の前に apply + イメージ push
    という不確実な作業を毎朝積むことになり却下（判断の記録は ADR-0018 追記）

- **PostgreSQL は夜間 stop しない**（ADR-0017。当初の「終業時に stop」から改訂）。理由:
  - B1ms 1 台の常時稼働は 24 時間 × 31 日 = 744 時間 < **750 時間の 12 か月無料枠**（「750 hours of Flexible Server—Burstable B1MS Instance, 32 GB storage, and 32 GB backup storage」。出典: <https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account> ）に収まり、$200 クレジット期間中も適用される（「As long as you have unexpired credit or you use only free services within the limits, you're not charged.」出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account> ）。stop の根拠だったコスト削減が消えた
  - **停止中は新規バックアップが取得されない**（§2-1 No.6）。主成果物である Backup / PITR の材料（WAL・スナップショットの蓄積）を減らす運用は本末転倒
  - 停止後 **7 日で自動起動する**（§2-1 No.8）ため、stop 前提の運用はもともと「放置してよい」状態を作れない
  - 無料枠の詳細・750 時間の管理・未確定事項は [azure-resource-inventory.md](./azure-resource-inventory.md) の「12か月無料枠」節が正本
- ローカルは `docker compose down`。**`-v` を付けない**（ローカル DB のデータ・検証素材が消える）。

---

> **【superseded 2026-08-22。#103】本節（Day 4）と §5（Day 5）は
> [credit-window-execution-plan.md](./credit-window-execution-plan.md) に置き換えられた**
> （方針転換は [ADR-0020](../adr/0020-credit-window-resource-strategy.md)）。
> ただし §4-3（PITR ドリル手順）・§4-6（合成メンテナンステスト）・§5 の計測手法は
> 新計画から**手順の正本として参照され続ける**。§2-1 / §2-2 の事実台帳も有効。

## 4. Day 4: PITR ドリル（最優先）+ PostgreSQL 側メンテナンス

### 4-1. 朝: 状態確認（stop 運用は廃止。ADR-0017）

サーバーは夜間も稼働継続している（§3-6）。起動操作は不要で、状態確認から始める。

> **【ドリル前のゲート】`terraform apply` の前に、必ず `plan` が差分ゼロであることを確認する。**
>
> ```bash
> terraform -chdir=terraform/persistent plan -detailed-exitcode   # exit 0 以外なら apply しない
> ```
>
> exit 0 以外（= 差分あり）なら、**差分の中身を読むまで apply しない**。Azure 側が自動で付ける設定を
> Terraform が「コードにないから消す」と判断しているケースがあり、実例として **PostgreSQL 委任サブネットの
> `Microsoft.Storage` service endpoint（WAL アーカイブ経路。§2-1 No.29）を外す plan** が実際に出た
> （[vnet-cutover/observations.md](../verification/vnet-cutover/observations.md) ステップ A-2。対応済み）。
> 中身を見ずに apply すると、**本命成果物である Backup / PITR の経路をドリルの最中に壊せてしまう**。
> ephemeral 層（DSN 向け替えの再 apply。§4-3 の 8 / §4-5）でも同じゲートを踏む。

- ステップ C の revision 名衝突の意図的実測（[vnet-integration-cutover.md](./vnet-integration-cutover.md) §3-3）が完了し、結果が [vnet-cutover/observations.md](../verification/vnet-cutover/observations.md) に記録済みであることを確認する（**2026-08-22 実施済み**: 衝突は ARM がエラーで拒否・既存 revision 無変更 = §2-1 No.30。現行コードは suffix 未指定のため Day 4 の往復 apply では衝突自体が発生しない）
- `az postgres flexible-server show` で `state: Ready` を確認する（Ready でなければ §2-1 No.8 の自動再起動等の想定外イベントを疑い、Activity Log を確認して記録する）
- §3-3 と同じコマンドで `earliestRestoreDate` / Backup Storage Used を取り、前日終業時からの推移を `observations.md` に記録（連続稼働中のバックアップ蓄積の実測。PITR ドリルの復元可能範囲の確認を兼ねる）

### 4-2. ドリル準備: 復旧点を判定できるデータを作る

- seed データ（気象庁データ）を投入した上で、**1 分おきにタイムスタンプ行を insert するマーカーテーブル**を 30 分以上回す。これが RPO 判定の物差しになる（実測 RPO は `T1 −「復旧後に残っている最後のマーカー」`。復旧目標時刻 `T_target` と最後のマーカーの差は**復元点精度**であり、RPO とは別物として記録する。式と標本化誤差の注記は §4-3 の 6〜7）
- WAL バックアップを確実に発生させるため、マーカー稼働中は他の書き込みも通常どおり行う

### 4-3. ドリル本番（すべての時刻を UTC で記録）

1. `T0`: 正常状態を記録（各テーブルの行数・マーカー最新時刻）
2. `T1`: 破壊を実行（例: `DROP TABLE documents;`）。実行時刻を記録
3. 復旧目標時刻 `T_target = T1 の 1 分前` を決める
4. 復元を **`--no-wait` で非同期発行**し、発行時刻を記録する（同期実行だと CLI が完了までブロックし、1 分間隔の計測が成立しない）:

   ```bash
   # private access のサーバーは同一 or 別 VNet へのみ復元できる（public とは跨げない）。
   # 復元サーバーは同じ VNet に入れる（--vnet / --subnet / --private-dns-zone。ADR-0018）
   az postgres flexible-server restore \
     -g rg-felisaichatbot-dev-tf \
     --name pgsql-felisaichatbot-dev-restored \
     --source-server pgsql-felisaichatbot-dev \
     --restore-time "<T_target (ISO8601 UTC)>" \
     --no-wait \
     --vnet vnet-felisaichatbot-dev \
     --subnet snet-felisaichatbot-dev-pgsql \
     --private-dns-zone felisaichatbot-dev.private.postgres.database.azure.com

   # 作業端末側: プロビジョニング状態を 1 分間隔でポーリングし、state 遷移を時刻つきで記録する
   while true; do
     echo "$(date -u +%FT%T.%3NZ) state=$(az postgres flexible-server show \
       -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-restored \
       --query state -o tsv 2>&1)"
     sleep 60
   done | tee restore-state.log
   ```

5. **RTO 実測**: restore 発行 → 復元サーバーへ `psql` で `SELECT 1` が通るまでの経過時間。**psql は VNet 内の ops コンテナ（`az containerapp exec`）から打つ**（private access のため作業端末から届かない。ADR-0018 / [vnet-integration-cutover.md](./vnet-integration-cutover.md) §3-2）。接続試行は**復元先の FQDN を指す専用 DSN** に対して行い、元サーバーの `DATABASE_URL` と明確に分ける（元サーバーは生きているので、元サーバーへの接続成功を拾うと RTO が偽になる）:

   ```bash
   # 作業端末側: 復元先の実 FQDN を取得する（private DNS zone 配下の名前）
   az postgres flexible-server show -g rg-felisaichatbot-dev-tf \
     -n pgsql-felisaichatbot-dev-restored --query fullyQualifiedDomainName -o tsv

   # 以下は ops コンテナ内（az containerapp exec）で実行する。
   # 元 DSN のホスト部だけを復元先 FQDN に置換して専用 DSN を作る（値を画面に出さない）
   RESTORED_HOST="<↑で取得した FQDN>"
   SRC_HOST="$(printf '%s' "$DATABASE_URL" | sed -E 's#^.*@([^/:?]+).*$#\1#')"
   RESTORED_DATABASE_URL="${DATABASE_URL/"$SRC_HOST"/"$RESTORED_HOST"}"

   # 接続タイムアウトを明示する（未指定は無期限待機。§5 の probe と同じ作法・同じ出典 libpq）。
   # 各試行の開始時刻・終了時刻・終了コードを記録する
   export PGCONNECT_TIMEOUT=3
   while true; do
     st=$(date -u +%FT%T.%3NZ)
     out=$(timeout 5 psql "$RESTORED_DATABASE_URL" -qtAc 'SELECT 1' 2>&1); rc=$?
     echo "$st $(date -u +%FT%T.%3NZ) rc=$rc ${out:0:40}"
     [ "$rc" -eq 0 ] && break
     sleep 60
   done
   # 出力（各行 = 1 試行）はターミナルログごと証跡（§4-4）に残す
   ```

6. **RPO 実測（実損失）**: `T1 −（復元サーバーに残っている最新マーカー時刻）`。RPO は「障害時点（T1）からどれだけのデータが失われたか」なので、意図的に 1 分手前を指定した分も含めて T1 起点で計算する（RPO の定義: [Business continuity concepts](https://learn.microsoft.com/en-us/azure/reliability/concept-business-continuity-high-availability-disaster-recovery)）。破壊したテーブルが `T_target` 時点の内容で存在することを行数で確認
7. **復元点精度（RPO とは別に記録）**: `T_target −（復元サーバーの最新マーカー時刻）`。指定した時刻をどこまで正確に再現できたかの値であり、RPO と混ぜない。マーカーは 1 分間隔のため、両値とも最大 1 分の標本化誤差を含む（この注記ごと証跡に書く）
8. アプリの向け替え: `.env` の `TF_VAR_database_url` のホスト部を復元先 FQDN に変えて export し直し（[vnet-integration-cutover.md](./vnet-integration-cutover.md) §0-2）、`terraform -chdir=terraform/ephemeral apply` する。**Container Apps の secret 更新は既存 revision に自動反映されない**（"An updated or deleted secret doesn't automatically affect existing revisions in your app"。出典: <https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets> ）が、template 内の非 secret 環境変数 `DSN_REVISION_MARKER`（DSN ハッシュ。`terraform/ephemeral/main.tf`）が revision-scope の変更であるため、DSN が変わる apply は serving / ops とも必ず新 revision を作る（コードで担保。ADR-0018 追記 #98。イメージタグは `.env` の `DEPLOY_SHA` = ステップ B で push 済みの SHA のまま変えない — [vnet-integration-cutover.md](./vnet-integration-cutover.md) §0-2 の注意のとおり、HEAD から再計算すると未 push タグで `ErrImagePull` になる）。**新 revision が稼働してから** `/readyz` → `/chat` を確認し、その成功時刻をアプリ回復時刻として記録する（古い revision の応答を拾うと元サーバーへの接続成功を誤計測する）。migration Job は revision を持たず実行ごとに secret を読み直す想定（**未実測のまま**。cutover ステップ B/C では secret の更新が発生しなかったため測れず、この Day 4 の向け替え後の Job 実行が初の実測になる）
9. 注意（§2-1 No.3 と [Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) の restore 節より）: 復元は**新サーバー作成**である。private access（ADR-0018）では firewall 規則は存在せず、代わりに (a) 復元サーバーが同一 VNet・委任サブネットに入ること、(b) private DNS zone に復元サーバーの名前が登録され ops コンテナから解決できること、を接続回復の確認手順に含めて計測する。委任サブネットは /27（32 − Azure 予約 5 = 実質 27 アドレス。ADR-0018 追記）で、復元中は一時的に 2 台が同居する（[vnet-integration-cutover.md](./vnet-integration-cutover.md) 末尾の注意）

### 4-4. ドリル証跡（`docs/verification/restore-drill/`）

`2026-08-XX-pitr-drill.md` に以下を残す: タイムライン表（T0 / T1 / T_target / restore 発行 / 接続回復 / アプリ回復）、実行コマンド全文と出力、**RTO / RPO（実損失）の実測値と復元点精度**（§4-3 の 5〜7）、引っかかった点、次にやるなら変える点。

### 4-5. ドリル後始末

- 元サーバー `pgsql-felisaichatbot-dev` を正として継続する（破壊したテーブルは Alembic + seed スクリプトで再構築できることを確認済みのうえで破壊対象に選ぶ）
- アプリ・ops の DSN を元サーバーへ戻す: `TF_VAR_database_url` を元の FQDN に戻して ephemeral 層を再 apply（§4-3 の 8 と同じ経路。`DSN_REVISION_MARKER` の値が戻ることも revision-scope の変更のため、戻しの apply でも Azure が一意な名前の新 revision を作る。ADR-0018 追記 #98）
- 復元サーバー `pgsql-felisaichatbot-dev-restored` は証跡取得後に**削除**（放置課金の芽を残さない）

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

- 復元サーバー削除済みの再確認（`az postgres flexible-server list -g rg-felisaichatbot-dev-tf -o table`）
- **ephemeral 層は destroy しない**（§3-6 と同じ。Day 5 の疎通 probe / psql も ops コンテナ経由のため、消すと翌朝また開始できない。最終 destroy は §5-6 のみ）。**PostgreSQL は stop しない**（ADR-0017）
- ops コンテナの `min_replicas` を 0 に戻したか確認する（exec のために 1 へ上げたままだと常駐課金が残る。[vnet-integration-cutover.md](./vnet-integration-cutover.md) §3-2）
- ローカルは `docker compose down`（`-v` なし）

---

> **【superseded 2026-08-22。#103】§4 冒頭の注記のとおり。実行順・時期は
> [credit-window-execution-plan.md](./credit-window-execution-plan.md) §6 が正本**（本節の計測手法は有効）。

## 5. Day 5: General Purpose + ゾーン冗長 HA（フェイルオーバー実測）→ destroy

計測の共通道具として、1 秒間隔の疎通ループを**読み取り・書き込みの 2 本**回し続ける。private access（ADR-0018）のため、この 2 本は作業端末からではなく **ops コンテナ内の 2 つの exec セッション**（`az containerapp exec` を 2 端末から張る。psql / bash / timeout は ops イメージに同梱）で実行する。計画フェイルオーバーは書き込みブロックが DNS 切替より先に始まる（§2-1 No.28）ため、読み取りだけでは断の開始を見逃す。また `connect_timeout` 未指定の接続は**無期限に待つ**（"Zero, negative, or not specified means wait indefinitely"。[libpq](https://www.postgresql.org/docs/17/libpq-connect.html)）ため、障害中の 1 試行がハングするとその間の計測が空白になる。タイムアウトを明示し、**各試行の開始時刻・終了時刻・終了コード**を残す:

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

- ダウンタイムはログから読み取り断・書き込み断を**別々に**算出する。`read-probe.log` / `write-probe.log` それぞれについて、各行の開始時刻・終了時刻・`rc` から次の 2 値を求めて証跡に書く:
  - **下限** = `max(0, 最後に失敗した試行の開始時刻 − 最初に失敗した試行の終了時刻)`。失敗した試行（`rc≠0`）は「その試行区間内のどこかの瞬間にダウンしていた」ことしか証明しないため、確実にダウンしていたと言えるのはこの区間まで
  - **上限** =「最後に成功した試行の終了時刻 → 最初に復帰した試行の開始時刻」。断はこの区間の内側で始まり内側で終わる
  - この上下限は**断が 1 回の連続した区間である**という仮定に依存する。失敗行の並びの途中に成功行が挟まる（断続的に切れる）場合は成立しないため、その場合は連続した失敗のかたまりごとに算出し、ログ全体を証跡に残す。両値とも試行間隔（1 秒）+ タイムアウト分の幅を含む値として書く
- `timeout 5` は接続後のクエリ側ハング（TCP 切断が伝わらないケース）の保険。probe の追加コストは書き込み 1 行 / 秒で、実行時間は増やさない

> **【ゲート再掲】Day 5 の各 apply の前にも `plan -detailed-exitcode` が exit 0 であることを確認する**
> （§4-1 のゲートと同じ。差分があれば中身を読むまで apply しない）。Day 5 は階層変更・HA 有効化と
> インフラ変更が続くため、意図しない差分が紛れ込んだまま apply されるリスクが最も高い。

### 5-1. 階層変更（Burstable → General Purpose）ダウンタイム実測

1. サーバー起動 → 疎通ループ開始
2. `az postgres flexible-server update --tier GeneralPurpose --sku-name <Day 3 で確定した SKU>`
3. ループのログから断の実測値を記録（ドキュメント上の目安は通常スケーリング 2〜10 分。§2-1 No.9）

### 5-2. HA 有効化（§3-4 で確定した経路で）

- 経路 A（既存サーバーへ有効化）: `az postgres flexible-server update --zonal-resiliency Enabled`（§2-1 No.25）。オンライン操作でアプリ断がないこと（§2-1 No.11）を疎通ループで裏取りし、`Healthy` までの所要時間を記録
- 経路 B（Day 3 で不可と判明した場合）: HA 有効の GP サーバーを新規作成（10〜15 分）→ seed 再投入 → アプリ向け替え

### 5-3. フェイルオーバー実測（成果物 3 の中核）

1. **計画フェイルオーバー**: `az postgres flexible-server restart -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev --failover Planned` → 疎通ループで実測。**この値が「メンテナンス中に止まりましたか？」への回答**になる（HA では計画メンテがこの standby 切替で処理される。§2-1 No.12。実メンテの実測ではなく代理実測である旨も証跡に書く）
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
terraform -chdir=terraform/ephemeral destroy    # ephemeral の destroy はここが唯一（§3-6。ADR-0018 追記）
terraform -chdir=terraform/persistent destroy   # PostgreSQL 含む。証跡コミット済みを確認してから
az resource list -g rg-felisaichatbot-dev-tf -o table   # 残存ゼロ確認（マネージド ID は管理外のため残るのが正常。Azure OpenAI は別 RG rg-felisaichatbot-dev で意図して残す。§8 の後片付け参照）
```

- HA は destroy 前に無効化する必要はない（サーバーごと消える）。destroy が何かで失敗した場合のみ、時間課金の大きい順（HA 無効化 → GP サーバー stop）に手で止血する

---

## 6. 成果物 5 点と作業の対応

| # | 成果物 | 中身 | 作る日 |
| --- | --- | --- | --- |
| 1 | Backup | 保持 7 日・日次スナップショット + WAL・geo 冗長の判断（無効 → 前提変化で有効化）の**根拠**（§3-1 の表 + ADR-0011 / ADR-0019） | Day 3 |
| 2 | PITR ドリル | 破壊 → 特定時刻へ復旧。**RTO / RPO 実測** → `docs/verification/restore-drill/` | Day 4 |
| 3 | Maintenance（Azure 側） | メンテナンスウィンドウ設定・マイナー更新の仕組み・**階層変更ダウンタイム実測**・**夜間 stop を廃止した判断の記録**（「停止中は新規バックアップなし」（§2-1 No.6）を根拠に運用を変えた。ADR-0017） | Day 3〜5 |
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
| Backup Storage Used（ローカル） | > 16 GiB | 無料枠 = プロビジョン済みストレージ 100% = 32 GiB（§2-1 No.7）。**geo 冗長を有効化した（[ADR-0019](../adr/0019-enable-geo-redundant-backup.md)）ため課金式は 「(2 × ローカルバックアップサイズ − プロビジョン済みストレージ) × GB/月単価」**となり、課金開始点はローカル 16 GiB（2 × 16 − 32 = 0）。ADR-0019 適用前の閾値 32 GiB は本行で訂正済み |
| `bloat_percent` / `n_dead_tup` | 未定 | メトリックは公式提供（§2-1 No.20）。閾値はワークロード依存のため Day 4 の観測値から決める |

---

## 8. コスト見張り

- **全リソースの一覧（管理区分・寿命・課金）・12か月無料枠・プロジェクト終了時の後片付け・再現手順（revive runbook）の正本は [azure-resource-inventory.md](./azure-resource-inventory.md)**。本節は Day 3〜5 の毎日の見張り手順のみを持つ
- **宿題（2026-08-23 頃）**: PostgreSQL 無料枠 **750 時間の消費状況を初回確認**する（手段は台帳の「750 時間の消費状況の確認手段」節。課金データの反映に 1〜2 日程度かかるため、常時稼働開始（8/21）から 2 日後の 8/23 頃に見る）
- **クレジット残の確認**（Day 3 に実測して確立した手段。2026-08-21）: CLI では Microsoft.Consumption の credits/balanceSummary API を billing profile 経由で叩く。以下をそのまま実行する（billing account / profile 名は ARM の識別子だが、public リポジトリにはハードコードせず毎回 CLI で取得する）:

  ```bash
  BA=$(az billing account list --query "[0].name" -o tsv)
  BP=$(az billing profile list --account-name "$BA" --query "[0].name" -o tsv)
  az rest --method get --url "https://management.azure.com/providers/Microsoft.Billing/billingAccounts/$BA/billingProfiles/$BP/providers/Microsoft.Consumption/credits/balanceSummary?api-version=2023-05-01" \
    --query "properties.balanceSummary.{current: currentBalance, estimated: estimatedBalance}" -o json
  ```

  2026-08-21T06:00Z 頃の実測: currentBalance USD 200.00 / estimatedBalance USD 199.99（約 32,775 円。失効 2026-09-18 は同 API 群の lots に記載）。`az consumption usage list` も動くが PretaxCost が None で残高の見張りには使えなかった。Azure Portal（Cost Management）は併用可
- **毎日の終業チェック**（§3-6 / §4-8 / §5-6 の teardown と同時に）:

  ```bash
  az postgres flexible-server list -g rg-felisaichatbot-dev-tf --query "[].{name:name, state:state, sku:sku.name}" -o table
  az resource list -g rg-felisaichatbot-dev-tf -o table
  ```

- **PostgreSQL は stop しない**（§3-6 / ADR-0017）。stop で止まるのはコンピュート課金のみで、ストレージ + バックアップストレージは停止中も課金が継続し（§2-1 No.6）、B1ms 1 台の常時稼働は無料枠内のため、stop に得がない。7 日で自動再起動する仕様（§2-1 No.8）もあり、stop 前提の運用はもともと「放置してよい」状態を作れなかった
- **プロジェクト完了後の後片付け**: 正本は [azure-resource-inventory.md](./azure-resource-inventory.md) の「プロジェクト終了時の後片付け」節（**`terraform destroy` 2 本で済み、`az group delete` は使わない**。当初の「3 RG 全消し」から改訂）。**従量課金へアップグレードしない場合はクレジット失効 2026-09-18 より前に必ず実施**する（アップグレードの判断期限も同日。台帳の「従量課金へのアップグレード」節）

---

## 9. Day 3〜5 でやらないこと（スコープクリープ防止）

- geo リストア・読み取りレプリカ・長期保持（Azure Backup / LTR）の実施（根拠の議論は §3-1 で済ませており、実物は作らない）。geo 冗長バックアップを有効化（ADR-0019）した後も、geo リストアのドリルは「時間が余ればやること」にも**入れない**: private access（ADR-0018）ではペアリージョン側に VNet 一式と接続経路の新設が要り「時間が余れば」の作業量ではなく、PITR 不可のため本命成果物にも寄与しない（判断の記録は ADR-0019）
- Memory Optimized 階層・pgBouncer・カスタムメンテナンス自動化などの検証
- アプリ機能の追加開発（walking skeleton の先のアプリ改善は本プロジェクトの目的ではない）
- 本書に書いた設計値の再議論（ADR 化は実施時に行うが、方向は本書で確定）

上記を含む「本番運用の水準に対して足りていないもの」の横断一覧（理由 1 行と追跡先つき）は
[production-readiness.md](../production-readiness.md) が正本。本書はやらない判断の根拠（各節）を持ち、
差分の一覧は持たない（役割分担は同書冒頭の表を参照）。

## 10. 参照する既存資産（読み取りのみ）

| 参照先 | 使う場面 |
| --- | --- |
| `terraform-hannibal/docs/operations/rollback-plan.md` | Day 4: restore 手順の構造（切り分け → 初動 → 復旧）の手本 |
| `terraform-hannibal/terraform/modules/rds/main.tf:1-58` | Day 3: retention / maintenance window の環境別出し分けの手本（Azure へ 1:1 対応） |
| `ticket-c2c-platform/docs/architecture/production-readiness.md`（M-17 / M-18 / L-32） | Day 4 着手時: DB backup / PITR runbook 要件リスト |
| `ticket-c2c-platform/docs/runbooks/alarm-aurora.md` | Day 5: アラート初動 Runbook の書式 |
