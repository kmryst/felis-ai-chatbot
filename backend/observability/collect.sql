-- 観測ワークロード + スナップショット採取（Issue #104。毎分の cron Job から実行）
-- 設計の正本: docs/operations/credit-window-execution-plan.md §5-3
--   - マーカー INSERT + カウンタ UPDATE: 毎分（観測される側の書き込み）
--   - 統計スナップショット: 5 分間隔（分 % 5 = 0 の実行時のみ）
--   - pgstattuple: 1 時間間隔（分 = 0 の実行時のみ。フルスキャンを伴うため）
-- cron の起動ジッタで分が数十秒ずれても、分の値で判定するため間隔は保たれる。
-- すべて INSERT-only（スナップショット側が dead tuple を作らない）。

\set ON_ERROR_STOP on

BEGIN;

-- 1) マーカー（毎分）
INSERT INTO obs.marker DEFAULT VALUES;

-- 2) カウンタ UPDATE（毎分。dead tuple 1 個/分の供給源）
UPDATE obs.counter SET n = n + 1, updated_at = now() WHERE id = 1;

-- 3) テーブル単位統計（5 分間隔）
INSERT INTO obs.table_stats (
    relname, n_live_tup, n_dead_tup, n_tup_ins, n_tup_upd,
    autovacuum_count, last_autovacuum, autoanalyze_count, last_autoanalyze
)
SELECT relname, n_live_tup, n_dead_tup, n_tup_ins, n_tup_upd,
       autovacuum_count, last_autovacuum, autoanalyze_count, last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname IN ('obs', 'public')
  AND extract(minute FROM now())::int % 5 = 0;

-- 4) DB 単位統計（5 分間隔。WAL / サイズ / XID age）
INSERT INTO obs.db_stats (wal_records, wal_bytes, db_size_bytes, frozen_xid_age)
SELECT w.wal_records, w.wal_bytes,
       pg_database_size(current_database()),
       age(d.datfrozenxid)
FROM pg_stat_wal w, pg_database d
WHERE d.datname = current_database()
  AND extract(minute FROM now())::int % 5 = 0;

-- 5) 実 bloat（1 時間間隔。マーカー系 2 テーブルのみ）
INSERT INTO obs.bloat_stats (relname, table_len, tuple_percent, dead_tuple_percent, free_percent)
SELECT t.relname, s.table_len, s.tuple_percent, s.dead_tuple_percent, s.free_percent
FROM (VALUES ('obs.marker'), ('obs.counter')) AS t(relname),
     LATERAL pgstattuple(t.relname) AS s
WHERE extract(minute FROM now())::int = 0;

COMMIT;
