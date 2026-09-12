# PITR ドリル 3 回目（状態検証）実測記録（Issue #237）

Issue [#237](https://github.com/kmryst/felis-ai-chatbot/issues/237) の PITR ドリル 3 回目（前半 = 状態検証）の実測記録。時刻はすべて UTC。
1〜2 回目の記録は [pitr-drill.md](./pitr-drill.md)、時刻指標の名前（`restore_request_accepted_at` など）の定義は同ファイルの「用語」節が正本。
実測値は **RPO / RTO とは呼ばない**（[restore-drill-recovery-objectives.md](../../operations/restore-drill-recovery-objectives.md) §6-1）。

## 目的と #230 との関係

1〜2 回目（[#230](https://github.com/kmryst/felis-ai-chatbot/issues/230)）は 4 テーブルのヒープ行 digest とセンチネルで「復元指定時刻どおりに復元された」ことを見たが、
digest はヒープ行のテキスト化しか見ておらず、**HNSW インデックス・identity / sequence の現在値・サーバーパラメータと拡張の許可リスト・ロール / 所有者 / 権限・統計カウンタ・タイムライン・スキーマ定義・Alembic リビジョン・アプリと同一ユーザーでの接続**を素通りしていた。
本ドリルはこれらを復元先で実測し、「復元はできたがアプリ（RAG）が動かない」を見逃す穴を埋める回である。
時点の正当性（元サーバーへの UPDATE を伴う直接測定）は後半のドリル（時点証明）で別途行う。

- 復元方式: latest restore point（`--restore-time` 省略）。復元指定時刻の精度を測る回ではない
- 元サーバー `pgsql-felisaichatbot-dev` への書き込みは **`DROP TABLE obs.pitr_sentinel` の 1 回のみ**（#230 からの持ち越し）。それ以外は SELECT と `pg_dump --schema-only`
- 復元先: `pgsql-felisaichatbot-dev-r3a-0912`（一時リソースのため Issue の手順どおりの名前を使った。同 VNet・委任サブネット `snet-felisaichatbot-dev-pgsql`・private DNS zone `felisaichatbot-dev.private.postgres.database.azure.com`）
- 実行経路: `az containerapp exec` → `ca-felisaichatbot-dev-ops`（revision `--0000006`、replica `…-7bd5cd7f86-9smb6`）→ `psql` 17.11 / `pg_dump` 17.11
- run は 1 回で完結した（**中断なし**。Issue の規則 2 の意味での不成立 run は発生していない）

## 結果の要約

| 項目 | 結果 |
| --- | --- |
| `restore_request_accepted_at`（Activity Log `Accepted`） | 2026-09-12T06:53:50.6267783Z |
| `server_ready_observed_at`（`state=Ready` 初観測、30 s ポーリング） | 07:02:48.101Z（**− accepted = 8 min 57.474 s**） |
| `first_connection_succeeded_at`（最初の `SELECT 1` 成功） | 07:03:41.980Z（− accepted = 9 min 51.353 s。**上限値・欠測扱い**。後述「知見 1」） |
| `validation_completed_at`（v1 digest 4/4 一致の `clock_timestamp()`） | 07:04:18.401Z（**− accepted = 10 min 27.774 s**） |
| Activity Log `Succeeded` − accepted | 9 min 10.804 s |
| 復元点精度（記録のみ） | 復元先の `max(obs.heartbeat.ts)` = 06:53:17.725188 → accepted の 32.902 s 前（heartbeat 1 分粒度の標本化誤差を含む） |
| データ（v1 / v2 digest、embedding NULL） | 全一致 / 0 |
| HNSW | Index Scan 使用、`self_top1 = 38`、hnsw digest = exact digest = baseline、`indisvalid = t` |
| identity / sequence | 6 本すべて `nextval > max(id)`、`INSERT obs.heartbeat` 成功（id 28822 > 28788） |
| 統計カウンタ | 12 テーブルすべて 0、`pg_stats` の documents 行数 5 |
| timeline | 3 → 4 |
| ext / roles digest、`alembic_version`、slots | 一致 / `0004` / 0 |
| owner / grants digest、`pg_dump -s` md5 | baseline（sentinel DROP **前**）とは不一致、DROP **後**の元サーバーとは一致（差分は sentinel の 3 オブジェクトのみ。後述「知見 3」） |
| 名前付き 18 パラメータ | 17 項目一致、`server_version` のみ 17.10 → 17.11。`azure.extensions` は一致（`VECTOR,PGSTATTUPLE`） |
| 拡張（測定） | `DROP EXTENSION pgstattuple` → `CREATE EXTENSION pgstattuple` とも成功（許可リストは引き継がれている） |
| アプリ DSN | 認証成功、RAG top-1 `id = 1 = min(id)`、properties 53 行 |
| Azure 側 | sku / storage / retention / HA / tags は一致。**`geoRedundantBackup` / `maintenanceWindow` / `availabilityZone` / `minorVersion` は不一致**（知見 5） |
| 後始末 | 復元先削除済み（`list` に不在）、元サーバー v1 digest 4/4 一致、`obs.pitr_sentinel` 不在、`CanNotDelete` ロック健在 |
| `az containerapp exec` | **9 回 / 37 分で 429 なし** |

## 開始前ゲート（2026-09-12T06:25:31.699Z）

| 項目 | 結果 | 出力 |
| --- | --- | --- |
| 元サーバーの `CanNotDelete` ロック | pass | `lock-pgsql-source-cannotdelete`（Level=CanNotDelete）1 件 |
| `az postgres flexible-server list` | pass | `pgsql-felisaichatbot-dev` 1 台のみ（前回の復元先は残っていない） |
| seed / embed Job の Running execution | pass | `caj-felisaichatbot-dev-seed running=0` / `caj-felisaichatbot-dev-embed running=0`（最終実行は 2026-09-01 の Succeeded） |
| 元サーバー | Ready / PostgreSQL 17（minorVersion 10）/ Standard_B1ms / 32 GiB P4 / `geoRedundantBackup: Enabled` / retention 7 / HA NotEnabled / maintenanceWindow custom（dayOfWeek 3, 17:00）/ tags `{}` / availabilityZone 1 | |
| `earliestRestoreDate` | `2026-09-05T07:28:18.423447+00:00` | `backup list` の最古 Full `backup_639241900974234471` の completedTime と一致（1〜2 回目の「鋸歯状」知見と整合） |
| ops コンテナ | Running、`minReplicas = 1` / `maxReplicas = 1`、replica 1 | |
| 委任サブネット / private DNS zone | `10.10.0.64/27`、zone の A レコードは元サーバー分 1 件（`bf4b8e9cdc10 → 10.10.0.71`） | |

## baseline（元サーバー、SELECT + `pg_dump -s` + sentinel DROP のみ）

取得 2026-09-12T06:34:56Z（exec #1）と 06:42:21Z（exec #3。exec #2 は知見 2 のとおりページャで停止したため再実行）。
`inet_server_addr() = 10.10.0.71`、`current_user = felisadmin`、`pg_is_in_recovery() = f`、`pg_postmaster_start_time() = 2026-08-28 10:19:08.93395+00`。

### v1 digest（#230 手順 0 の固定値と照合）と v2 digest（本ドリルで初回固定）

| table | n | v1 digest | 固定値との照合 | v2 digest（baseline digest v2） |
| --- | --- | --- | --- | --- |
| documents | 38 | `e7deb2d1473bd7a5ce66540c4c7c78d4` | 一致 | `1d0014e847b184b97fbdbd2537305bdd` |
| object_properties | 53 | `f3cf355b403988282a33bf62c4ad4f17` | 一致 | `bde0f2ef22f753561b7a5e8b7358af14` |
| objects | 15 | `4244aa6dffd5e181ad46930d3bedaa5d` | 一致 | `781a485282ef00bd693587c71b0618a1` |
| sources | 13 | `ae32dbe92dabb4e4ec9de08481280d4e` | 一致 | `217fa7bad6369c45620faf50668cdcdc` |

- v1 照合時刻（`clock_timestamp()`）: 2026-09-12 06:34:57.239906+00。`documents WHERE embedding IS NULL` = 0
- 固定値との比較はシェル側で `cmp`（psql `-At` 出力 vs 期待値ファイル）。exec #3 の冒頭で再照合し 4/4 一致（06:42:22.067Z）

### HNSW

```text
           relname            | indisvalid | indisready | bytes
------------------------------+------------+------------+--------
 documents_embedding_hnsw_idx | t          | t          | 319488
 documents_pkey               | t          | t          |  16384
 documents_source_id_idx      | t          | t          |  16384

 Nested Loop
   ->  Seq Scan on documents d
   ->  Aggregate
         ->  Limit
               ->  Index Scan using documents_embedding_hnsw_idx on documents
                     Order By: (embedding <=> d.embedding)

 q  | self_top1 |           hnsw_digest
----+-----------+----------------------------------
 38 |        38 | 0fcddefe7e63cc159a1384f3f21f8665
```

- `exact_digest`（`enable_indexscan = off`）= `0fcddefe7e63cc159a1384f3f21f8665`（hnsw digest と一致）
- **LATERAL 形のクエリでプランナが HNSW の Index Scan を選んだ**（Issue の未確認事項が解消。`\gset` の fallback は不要）

### sequence / max(id)、パラメータ、digest 群

| sequence | `last_value` | 表 | `max(id)` |
| --- | --- | --- | --- |
| public.documents_id_seq | 38 | documents | 38 |
| public.object_properties_id_seq | 159 | object_properties | 53 |
| public.objects_id_seq | 45 | objects | 15 |
| public.sources_id_seq | 39 | sources | 13 |
| obs.marker_id_seq | 28777 | obs.heartbeat | 28777 |
| obs.phase_log_id_seq | 1 | obs.phase_log | 1 |

（06:42 時点。06:35 時点の heartbeat は 28769 で、元サーバーでは heartbeat が約 1 行 / 分で増え続けている）

名前付き 18 パラメータ（`pg_settings.setting` / `source`）:

| name | setting | source |
| --- | --- | --- |
| archive_mode | always | configuration file |
| archive_timeout | 300 | configuration file |
| autovacuum | on | default |
| azure.extensions | VECTOR,PGSTATTUPLE | configuration file |
| checkpoint_timeout | 600 | configuration file |
| DateStyle | ISO, MDY | （全量ダンプから。知見 8） |
| extra_float_digits | 3 | session |
| hnsw.ef_search | 40 | default |
| IntervalStyle | postgres | （全量ダンプから） |
| maintenance_work_mem | 99328 | configuration file |
| max_connections | 50 | configuration file |
| max_wal_size | 2048 | configuration file |
| server_version | 17.10 | default |
| shared_buffers | 32768 | configuration file |
| shared_preload_libraries | pg_cron,pg_stat_statements,azure,pg_qs,pgaadauth,pgms_stats,pgms_wait_sampling,pg_availability | configuration file |
| TimeZone | UTC | （全量ダンプから） |
| wal_level | replica | default |
| work_mem | 4096 | default |

| 項目 | baseline 値 |
| --- | --- |
| `pg_extension` digest | `54224058264ec72ccea9ac82685113b2` |
| `pg_roles` digest | `d89a434e94db3fab8e114e7dbbd9f62e` |
| 所有者 digest（public / obs の r・S・i） | `ab77be24bc33f98c673ddc0542793ae9`（sentinel DROP 前）/ `d6251c956104fbe84c38a58cd3148ea8`（DROP 後、07:05:12Z 再取得） |
| `role_table_grants` digest | `809d89ebe390b7ca573271d8a021c398`（DROP 前）/ `474e1bcb36eeb6d475cc35147950bbfa`（DROP 後） |
| `pg_dump --schema-only` md5（`\restrict` / `\unrestrict` 行除外） | `1bf71b2d036a34099f6399c306f1ebc1`（DROP 前、1,126 行）/ `7ec66320f8e5d32cf0af042a1d9fcd7f`（DROP 後） |
| `pg_control_checkpoint()` | timeline_id **3**、checkpoint_lsn 17/B1001B88 |
| `pg_replication_slots` | 0 |
| `alembic_version.version_num` | `0004` |
| `documents` の所有者 | felisadmin |
| `pg_settings` 全量 | 440 行（md5 `9f4ed8bbdf981bedb46af173c6d56083`。復元先との diff は後述） |

`pg_dump` 17.11 の出力には `\restrict <token>` / `\unrestrict <token>` 行が**存在した**（Issue の未確認事項が解消。トークンは実行ごとに変わるので除外が必要）。

### `obs.pitr_sentinel` の記録と DROP（#230 からの持ち越し）

DROP 直前 2026-09-12 06:42:23.801921+00（`inet_server_addr() = 10.10.0.71` を同時に確認）:

```text
 id |                                          note                                           |              ts
----+-----------------------------------------------------------------------------------------+-------------------------------
 S1 | PITR drill S1: before restore-time #1 (fast restore)                                    | 2026-09-04 13:36:31.223339+00
 S2 | PITR drill S2: after custom restore-time 2026-09-04T13:50:00Z, before fast restore-time | 2026-09-04 14:04:30.993218+00
 S3 | PITR drill S3: after restore-time of fast restore                                       | 2026-09-05 07:28:52.69699+00
(3 rows)
DROP TABLE
 should_be_null |          after_drop
----------------+-------------------------------
                | 2026-09-12 06:42:23.835462+00
```

3 行は当時の id `S1` / `S2` / `S3` のまま（証跡上の呼称は `sentinel-2026-09-04T13:36:31Z` / `sentinel-2026-09-04T14:04:31Z` / `sentinel-2026-09-05T07:28:52Z`。[pitr-drill.md](./pitr-drill.md) の用語節）。作り直していない。

## 復元の実行と時刻

```console
$ az postgres flexible-server show ... --query "{earliestRestoreDate:backup.earliestRestoreDate,state:state}"   # 06:53:44.814Z
{ "earliestRestoreDate": "2026-09-05T07:28:18.423447+00:00", "state": "Ready" }
t0-cli-before=2026-09-12T06:53:45.547Z
$ az postgres flexible-server restore -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-r3a-0912 --source-server pgsql-felisaichatbot-dev --no-wait --yes \
    --vnet vnet-felisaichatbot-dev --subnet snet-felisaichatbot-dev-pgsql --private-dns-zone felisaichatbot-dev.private.postgres.database.azure.com -o json
restore_cli_rc=0 t0-cli-after=2026-09-12T06:53:48.799Z
```

（生出力のラベル `t0-cli-*` は当時のシェル変数名。`--no-wait` のため本文は空）

| 事象 | 時刻 (UTC) | 備考 |
| --- | --- | --- |
| CLI 送信直前（`t0-cli-before`） | 06:53:45.547 | 参考値。`Accepted` より 5.080 s 早い |
| Activity Log `write` `Started` | 06:53:49.6111296 | `Accepted` の 1.016 s 前 |
| **`restore_request_accepted_at`** = Activity Log `write` `Accepted` | **06:53:50.6267783** | correlationId `c485ca4a-2cae-4342-8fee-a21d20f68ac5` |
| `state`: `ResourceNotFound` → `Provisioning` | 06:53:58.013 → 06:54:31.243 | 30 s ポーリング |
| **`server_ready_observed_at`** | **07:02:48.101** | 直前の 07:02:14.907 は `Provisioning` |
| 復元先 `pg_postmaster_start_time()` | 07:02:45.075165 | `Ready` 観測の 3 s 前 |
| Activity Log `write` `Succeeded` | 07:03:01.430623 | `Ready` 観測の 13.3 s 後 |
| 誤ホストの疎通ポーリング停止 | 07:03:35.927 | 知見 1 |
| **`first_connection_succeeded_at`** | **07:03:41.980**（正しいホストでの try=1、試行開始 07:03:41.764） | **上限値**。真の初回成功時刻は取れていない |
| verify 開始（exec） | 07:04:17.761 | |
| **`validation_completed_at`**（v1 digest 4/4 一致の `clock_timestamp()`） | **07:04:18.401280** | 統計カウンタ取得の直後、v2 / HNSW より前 |

| 区間 | 値 | 備考 |
| --- | --- | --- |
| `server_ready_observed_at − restore_request_accepted_at` | **8 min 57.474 s** | 30 s ポーリングを含む上限値。1 回目 8 min 12.499 s（60 s ポーリング）/ 2 回目 6 min 6.051 s（30 s） |
| 実測復元所要区間 `restore_to_first_connection_duration` | 9 min 51.353 s | **欠測扱い**（知見 1）。1 回目 6 min 51.155 s / 2 回目 5 min 42.130 s と比較しない |
| `validation_completed_at − restore_request_accepted_at` | **10 min 27.774 s** | 1 回目の verify2 − accepted = 8 min 31.255 s、2 回目の verify − accepted = 6 min 24.497 s に相当 |
| Activity Log `Succeeded` − `restore_request_accepted_at` | 9 min 10.804 s | 1 回目 9 min 6.539 s / 2 回目 7 min 9.751 s |

## 復元先での検証（`state=Ready` 観測後、07:04:17〜07:04:44Z）

復元先: `inet_server_addr() = 10.10.0.68`、`pg_is_in_recovery() = f`、`current_user = felisadmin`、`current_database = postgres`。
書き込みを伴う節（nextval / INSERT / DROP-CREATE EXTENSION）の直前に `inet_server_addr()` を出力し、元サーバーの 10.10.0.71 でないことを確認してから進めた（3 回とも 10.10.0.68）。

### 判定（Issue #237 受け入れ条件と 1 対 1）

| 項目 | 復元先の値 | 合否 |
| --- | --- | --- |
| v1 digest 4 表 | documents 38 / `e7deb2d1…`、object_properties 53 / `f3cf355b…`、objects 15 / `4244aa6d…`、sources 13 / `ae32dbe9…` | **合格**（固定値と 4/4） |
| v2 digest 4 表 | `1d0014e8…` / `bde0f2ef…` / `781a4852…` / `217fa7ba…` | **合格**（baseline digest v2 と 4/4） |
| `documents WHERE embedding IS NULL` | 0 | 合格 |
| EXPLAIN | `Index Scan using documents_embedding_hnsw_idx`（baseline と同一プラン） | 合格 |
| `self_top1` / hnsw digest / exact digest | 38 / `0fcddefe7e63cc159a1384f3f21f8665` / 同値 | **合格**（baseline と一致、hnsw = exact） |
| `indisvalid` | t（`indisready` t、319,488 bytes） | 合格 |
| sequence 6 本（`max(id)` → `nextval`） | documents 38→39、object_properties 53→160、objects 15→46、sources 13→40、obs.heartbeat 28788→28821、obs.phase_log 1→2 | **合格**（すべて `nextval > max(id)`） |
| `INSERT INTO obs.heartbeat DEFAULT VALUES RETURNING id` | 28822（INSERT 前の `max(id)` 28788 より大きい） | 合格 |
| `pg_stat_user_tables`（書き込み試験より前。v1 照合より**前**に取得） | public 5 表・obs 7 表の 12 表すべて `n_tup_ins` / `n_tup_upd` / `seq_scan` / `idx_scan` = 0、`last_autovacuum` NULL | **合格** |
| `pg_stats` の documents 行数 | 5 | 合格（> 0） |
| `pg_control_checkpoint().timeline_id` | **4**（checkpoint_lsn 17/B7000080） | **合格**（baseline 3 より大きい） |
| `pg_extension` digest | `54224058264ec72ccea9ac82685113b2` | 合格（一致） |
| `pg_roles` digest | `d89a434e94db3fab8e114e7dbbd9f62e` | 合格（一致） |
| 所有者 digest | `d6251c956104fbe84c38a58cd3148ea8` | baseline（DROP 前 `ab77be24…`）とは**不一致**、DROP 後の元サーバーと**一致**（知見 3） |
| `role_table_grants` digest | `474e1bcb36eeb6d475cc35147950bbfa` | 同上（DROP 前 `809d89eb…` とは不一致、DROP 後と一致） |
| `pg_dump -s` md5 | `93d2f91bc5a366f986d69aae3e6fdca7`（1,105 行） | baseline（DROP 前、1,126 行）とは**不一致**。コンテナ内 `diff` で差分は `obs.pitr_sentinel` の CREATE TABLE / OWNER / PRIMARY KEY（21 行）と `\restrict` トークン、`Dumped from database version 17.10` → `17.11` のコメント行のみ。DROP 後の元サーバーとの diff は `\restrict` トークンと version コメントのみ（知見 3） |
| `alembic_version` / `pg_replication_slots` | `0004` / 0 | 合格 |
| 名前付き 18 パラメータ | 18 行取得（`lower(name) IN (...)`）。**17 項目が baseline と一致**。`server_version` のみ 17.10 → **17.11**（知見 4） | 記録（合否にしない） |
| `azure.extensions` | `VECTOR,PGSTATTUPLE`（`pg_settings` / `SHOW` / `az … parameter show`（user-override）とも元と**一致**） | 記録 |
| `pg_settings` 全量 diff | 4 件: `output_plugin_libraries`（復元先のみ `pgoutput, test_decoding, pglogical_output, wal2json, pg_squeeze`）、`primary_slot_name`（元 `azure_standby_b58f4eb0c18a` → 空）、`restore_command`（元 `BlobLogDownloadHA.sh %f %p` → 空）、`server_version` / `server_version_num`（17.10 / 170010 → 17.11 / 170011）。復元先 437 行、元 436 行 | 記録 |
| `SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector` | 0.00853986601633272 | 記録（成功） |
| `pgstattuple('obs.counter')` | tuple_count 1 | 記録（成功） |
| `DROP EXTENSION pgstattuple; CREATE EXTENSION pgstattuple;` | 両方 rc=0（`pg_extension`: azure 1.1 / pgaadauth 1.11 / pgstattuple 1.5 / plpgsql 1.0 / vector 0.8.2） | 記録（**許可リストは引き継がれている**） |
| アプリと同一ユーザーの DSN（ops の `DATABASE_URL` のホスト部のみ置換） | `felisadmin@postgres` で認証成功 | **合格** |
| RAG 実 SQL top-5 | id 1（similarity 1）, 2（0.6243498697140684）, 6（0.5710689185869163）, 3（0.5435823850864488）, 4（0.5303207380680578）。`min(id)` = 1 | **合格**（top-1 = `min(id)`） |
| `object_properties` レンダリング行数 | 53 | 合格 |
| `pg_is_in_recovery()` / `pg_postmaster_start_time()` / `inet_server_addr()` | f / 2026-09-12 07:02:45.075165+00 / 10.10.0.68 | 記録 |
| 復元先の heartbeat | 28,737 行、`max(id)` 28788、`max(ts)` 2026-09-12 06:53:17.725188+00（`n_tup_ins = 0` のまま = pg_cron による書き込みは復元先で起きていない） | 記録 |

`obs.marker_id_seq` の `last_value` は復元先で 28820（`max(id)` 28788 より 32 先行。元サーバーでは 06:42 時点で `max(id)` と同値だった）。sequence のキャッシュ / WAL 先行書き込みの性質どおりで、identity 衝突は起きない側のずれである。

### Azure 側の比較（`az postgres flexible-server show`、07:04:34Z）

| 項目 | 元 `pgsql-felisaichatbot-dev` | 復元先 `pgsql-felisaichatbot-dev-r3a-0912` | 一致 |
| --- | --- | --- | --- |
| sku | Standard_B1ms / Burstable | 同 | 一致 |
| storage | 32 GiB / P4 / Premium_LRS / iops 120 / autoGrow Disabled | 同 | 一致 |
| backup.backupRetentionDays | 7 | 7 | 一致 |
| **backup.geoRedundantBackup** | **Enabled** | **Disabled** | **不一致** |
| backup.earliestRestoreDate | 2026-09-05T07:28:18.423447 | 2026-09-12T07:04:34.360418（復元先の初回スナップショット） | （比較対象外） |
| highAvailability | Disabled / NotEnabled | 同 | 一致 |
| **maintenanceWindow** | **customWindow Enabled, dayOfWeek 3, 17:00** | **customWindow Disabled, dayOfWeek 0, 00:00** | **不一致** |
| tags | `{}` | `{}` | 一致 |
| **availabilityZone** | **1** | **2** | **不一致** |
| version / **minorVersion** | 17 / **10** | 17 / **11** | **不一致**（minor） |
| `azure.extensions`（`parameter show`） | VECTOR,PGSTATTUPLE（user-override） | 同 | 一致 |
| fullyQualifiedDomainName | `pgsql-felisaichatbot-dev.postgres.database.azure.com` | `pgsql-felisaichatbot-dev-r3a-0912.postgres.database.azure.com` | （知見 1） |

## 削除と Activity Log

### 復元先の削除（fail-closed）

```console
gate_at=2026-09-12T07:08:17.924Z
locks=lock-pgsql-source-cannotdelete
RST_ID=/subscriptions/e503b2a6-d4d8-4954-82aa-4f64d36651f5/resourceGroups/rg-felisaichatbot-dev-tf/providers/Microsoft.DBforPostgreSQL/flexibleServers/pgsql-felisaichatbot-dev-r3a-0912
fail_closed_checks=3/3 passed
delete_start=2026-09-12T07:08:20.398Z
delete_rc=0 delete_end=2026-09-12T07:09:43.030Z
```

- 3 条件（`CanNotDelete` ロック存在 / `RST_ID != SRC_ID` / `RST_ID` に `r3a-0912` を含む）をすべて満たしてから `az postgres flexible-server delete --ids "$RST_ID" --yes` を実行した。**`--ids` は使える**（未確認事項が解消）
- 削除後の `az postgres flexible-server list`: `pgsql-felisaichatbot-dev` のみ（Ready）。private DNS zone の A レコードも元サーバー分 1 件に戻った（`d88d28145a39 → 10.10.0.68` は消えた）
- 復元先が課金対象だった区間: `Accepted` 06:53:50 〜 `delete Succeeded` 07:09:56 の**約 16 分**（Standard_B1ms 0.026 USD/時 → 約 0.007 USD）

### Activity Log（取得 07:14:28Z、`resourceId` に `pgsql-felisaichatbot-dev-r3a-0912` を含むもの。`flexibleServers/read` 行は省略）

```console
Ts                            Sub                   Op                                                Status     Corr
----------------------------  --------------------  ------------------------------------------------  ---------  ------------------------------------
2026-09-12T07:09:56.7311063Z  2026-09-12T07:12:14Z  Microsoft.DBforPostgreSQL/flexibleServers/delete  Succeeded  a1aba70c-6788-46cd-9dd6-98b2248df6de
2026-09-12T07:08:21.7431972Z  2026-09-12T07:09:56Z  Microsoft.DBforPostgreSQL/flexibleServers/delete  Accepted   a1aba70c-6788-46cd-9dd6-98b2248df6de
2026-09-12T07:08:21.5400663Z  2026-09-12T07:09:56Z  Microsoft.DBforPostgreSQL/flexibleServers/delete  Started    a1aba70c-6788-46cd-9dd6-98b2248df6de
2026-09-12T07:03:01.430623Z   2026-09-12T07:06:00Z  Microsoft.DBforPostgreSQL/flexibleServers/write   Succeeded  c485ca4a-2cae-4342-8fee-a21d20f68ac5
2026-09-12T06:53:50.6267783Z  2026-09-12T06:54:32Z  Microsoft.DBforPostgreSQL/flexibleServers/write   Accepted   c485ca4a-2cae-4342-8fee-a21d20f68ac5
2026-09-12T06:53:49.6111296Z  2026-09-12T06:54:32Z  Microsoft.DBforPostgreSQL/flexibleServers/write   Started    c485ca4a-2cae-4342-8fee-a21d20f68ac5
```

- 07:05:12Z の先行取得では `write` の `Started` / `Accepted` までしか取り込まれておらず、`Succeeded` は 07:06 以降、`delete Succeeded` は 07:12 以降に出現した（取り込み遅延 42 s 〜 3 min 55 s）。`restore_request_accepted_at` の値は両取得で同一
- 削除の所要（`delete Started` → `Succeeded`）: 1 min 35.191 s

### 元サーバーの不変性（07:11:39Z、exec #9）

`inet_server_addr() = 10.10.0.71`、`to_regclass('obs.pitr_sentinel')` = NULL、`pg_is_in_recovery() = f`、v1 digest 4 表とも固定値と一致（`documents|38|e7deb2d1473bd7a5ce66540c4c7c78d4` ほか）。
`CanNotDelete` ロックは削除前後とも存在。本ドリル全体を通じて元サーバーへの書き込みは 06:42:23Z の `DROP TABLE obs.pitr_sentinel` のみ。

## 知見

### 1. `first_connection_succeeded_at` は上限値であり、1〜2 回目と比較できない（欠測）

Issue #237 §6 の疎通ポーリングはホストを `<name>.felisaichatbot-dev.private.postgres.database.azure.com` としていたが、この名前は**存在しない**。
private DNS zone の A レコードはハッシュ名（本回は `d88d28145a39 → 10.10.0.68`。元サーバーは `bf4b8e9cdc10 → 10.10.0.71`）で、正しいホストは `az postgres flexible-server show` の
`fullyQualifiedDomainName` = `pgsql-felisaichatbot-dev-r3a-0912.postgres.database.azure.com`（zone のハッシュ名へ CNAME）である。
誤ホストのポーリングは `Ready` 観測後も `could not translate host name` のまま（try=39 まで）だったため 07:03:35Z に止め、正しいホストで再送したところ try=1 で成功した。
記録された `first_connection_succeeded_at`（07:03:41.980）は `server_ready_observed_at`（07:02:48.101）より後で、真の初回接続可能時刻を含んでいない。
**本回の実測復元所要区間は欠測として扱い**、代替として `server_ready_observed_at − restore_request_accepted_at` = **8 min 57.474 s** を 1 回目 8 min 12.499 s / 2 回目 6 min 6.051 s と並べる（いずれもポーリング間隔ぶんの上限値）。
手順の `RHOST` は `show --query fullyQualifiedDomainName` の値を使う形に直すべきである。

### 2. `az containerapp exec` は TTY があるため psql のページャが起動して固まる

exec セッションには TTY があり、psql は出力がスクリーン高を超えると `more` を起動してキー入力を待つ（`--More--`）。
baseline の exec #2 は 18 パラメータ表の途中でこれに掛かり、6 分間出力が止まった（ローカル側の `script` のログも 4,096 バイトで止まり、原因の切り分けにも時間を要した）。
ローカル側を kill するとコンテナ側のプロセスも SIGHUP で終了し、DROP には到達していなかったことを再実行時の `to_regclass` で確認した。
**psql を exec で使うときは `-P pager=off`（および `export PAGER=cat`）が必須**。1〜2 回目の知見 3（`--command` の制約 / TTY / 2 KB / 429）に無かった項目である。
併せて、`script` は `-f`（flush）を付けると途中経過をログで追える。

### 3. baseline の取得順序に欠陥がある

Issue #237 §5 は owner / grants digest と `pg_dump -s` を `obs.pitr_sentinel` の DROP より**前**に取る順序になっているため、DROP 後の状態を復元する latest restore の復元先とは必ず不一致になる。
本回は復元先の値が baseline と食い違ったあと、コンテナ内に残していた 2 つのスキーマダンプの `diff` と、DROP 後の元サーバーでの再取得（07:05:12Z）で、
差分が sentinel の 3 オブジェクト（`CREATE TABLE obs.pitr_sentinel` / `ALTER TABLE … OWNER TO felisadmin` / `PRIMARY KEY (id)`、21 行）だけであることを確認した。
手順は「DROP → digest 取得」の順に直すべきである。

### 4. 復元先には最新マイナーバージョンが当たる

元サーバー 17.10（minorVersion 10）に対し復元先は 17.11（minorVersion 11）で、`pg_dump` のヘッダーコメント（`Dumped from database version`）も変わる。
`server_version` を「一致」条件に含めると常に落ちるため、判定から外して記録のみとする。`pg_dump -s` の md5 も version コメントの影響を受けるので、md5 比較ではなく `diff` で差分を読むほうがよい。

### 5. 復元しただけでは元と同じ構成にならない

`az postgres flexible-server show` で引き継がれなかった設定: **`geoRedundantBackup` Enabled → Disabled、`maintenanceWindow` custom（水曜 17:00）→ Disabled、`availabilityZone` 1 → 2、`minorVersion` 10 → 11**。
一方 sku / storage / retention / HA / tags / `azure.extensions`（許可リスト）/ サーバーパラメータ（`pg_settings` 全量で実質差分なし）は引き継がれた。
実災害時の復旧手順には「復元後に geo 冗長・メンテナンスウィンドウ・（必要なら）AZ を元に戻す」段階が必要である。Terraform 管理下では `terraform plan` の差分として現れる。

### 6. 429 の閾値は未確定。実測された下限は 9 回 / 37 分

本回の `az containerapp exec` は 06:34〜07:11 の 37 分間に 9 回（baseline A / baseline B（ページャ停止）/ baseline B 再実行 / 疎通ポーリング（誤ホスト）/ 疎通ポーリング再実行 / verify（読み取り）/ verify（書き込み）/ 元サーバー再確認 / 元サーバー最終確認）で、**429 は発生しなかった**。
1 回目 4 回・2 回目 3 回・本回 9 回のいずれも 429 なしで、「1 run 5 回以内」という従来の目安は実測の裏づけがない自主規制だった。
今後は回数を節約するために手順を変えず、429 が返ったら `retry-after`（実測 600 s）だけ待って再試行する。

### 7. `az postgres flexible-server delete --ids` は使える

`--ids` に復元先の resource ID を渡して削除できた（rc=0、CLI 所要 1 min 22.6 s）。fail-closed の 3 条件は resource ID 文字列だけで判定できる。

### 8. LATERAL 形の HNSW クエリでプランナは Index Scan を選ぶ

元サーバー・復元先とも `CROSS JOIN LATERAL (… ORDER BY embedding <=> d.embedding LIMIT 5)` の内側で `Index Scan using documents_embedding_hnsw_idx` が選ばれ、`\gset` で 1 行ずつ回す fallback は不要だった。
なお Issue §4 の 18 パラメータ SQL は `IN ('timezone','datestyle','intervalstyle')` が小文字のため 15 行しか返らない（`pg_settings.name` は `TimeZone` / `DateStyle` / `IntervalStyle`）。verify では `lower(name) IN (...)` に直した。

### 9. 復元先が課金対象だった区間は約 16 分

`Accepted` 06:53:50 〜 `delete Succeeded` 07:09:56。1 回目 約 10 分 / 2 回目 約 8 分より長いのは、検証項目の増加と知見 1 の再送ぶんによる。

### 10. 実行上の細かい知見

- exec の payload は gzip + base64 で 2,000 文字未満に収める必要があり、baseline（約 3.4 K）と verify は 2 分割した。base64 の `+` / `/` を `-` / `_` に置換して送り、コンテナ側で `tr` で戻すと URL エンコードの膨張を避けられる
- 同じ replica に前の exec で置いたファイル（SQL・期待値・`pg_settings` ダンプ・スキーマダンプ）を次の exec で再利用できた（replica は 2026-09-02 から同一）。`diff` をコンテナ内で取れるので、baseline と verify の突き合わせに手元へ転記する必要がない
- Activity Log の `Succeeded` は `first_connection_succeeded_at` の 10 分後でも取り込まれていないことがある（本回は `write Succeeded` が 07:06 以降、`delete Succeeded` が 07:12 以降）

## 付録: 実行手順と SQL

コマンドと SQL は Issue #237 のコメントに置いた手順（§1〜§12）に従った。本回で手順から変えた点:

- baseline / verify を 2 exec ずつに分割（payload 上限）。v1 固定値との照合は DO ブロックではなくシェル側の `cmp` で行った（digest の SQL 自体は #230 §2 の逐語のまま）
- すべての psql に `-X -P pager=off`、シェルに `export PAGER=cat`（知見 2）
- 疎通ポーリングの `RHOST` を `fullyQualifiedDomainName` に変更（知見 1）
- 18 パラメータの `WHERE name IN (...)` を `WHERE lower(name) IN (...)` に変更（知見 8）
- 統計カウンタは v1 照合より前（復元先でユーザーテーブルに触る前）に取得した（Issue の順序は v1 → v2 → 統計。読み取りで `seq_scan` が増える前に取るほうが「復元でリセットされた」ことの測定として厳密）
- 書き込みを伴う節の直前に `inet_server_addr()` のガード（10.10.0.71 なら中断）を追加した
- 復元先の値が baseline と食い違った owner / grants / `pg_dump -s` について、DROP 後の元サーバーで再取得して突き合わせる exec を追加した（知見 3）
