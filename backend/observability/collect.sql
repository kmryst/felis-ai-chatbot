-- 観測ワークロード + スナップショット採取（Issue #104。毎分の cron Job から実行）
-- 設計の正本: docs/operations/credit-window-execution-plan.md §5-3
--   - マーカー INSERT + カウンタ UPDATE: 毎分（観測される側の書き込み）
--   - 統計スナップショット: 5 分間隔 / pgstattuple: 1 時間間隔（フルスキャンを伴うため）
-- 間隔の判定は「前回採取からの経過時間」で行う（外部レビュー指摘の反映）。
-- 当初の「分の値 % 5 = 0」判定は、ACA のコンテナ起動遅延（コールドスタート 22.7s / 23.1s を
-- 同リポジトリで実測済み）で :05 予定の実行が :06 に開始すると 1 回まるごと無音スキップする。
-- 経過ベース（max(ts) が interval より古ければ採取）なら、遅延時はその回で追いつき、
-- 二重起動時は 2 回目が自然にスキップされる（スキップと二重採取を同時に解決）。
-- すべて INSERT-only（スナップショット側が dead tuple を作らない）。
--
-- トランザクションは 2 本に分ける（Issue #114 の 4。外部レビュー指摘の反映）:
--   T1 = マーカー + カウンタ（観測される側） / T2 = スナップショット 3 系列（観測する側）。
-- 単一トランザクションだと、毎時の pgstattuple が replica_timeout（55 秒）を超えて
-- SIGTERM で切られた場合に、その分のマーカーごとロールバックする。現データ量では
-- 非現実的だが、フェーズ 2（高負荷）では pgstattuple のフルスキャンが伸びて顕在化し得る。
-- 分離により T2 の失敗はマーカー系列に波及しない（T2 の失敗自体は鮮度ゲート
-- （stats / pgstattuple の系列別閾値。#106）が検出する）。
-- ローカル実 PG での実測: 分離前は T2 相当の失敗でマーカーが巻き戻ることを確認してから分離。

\set ON_ERROR_STOP on

-- T1: 観測される側（毎分。ここが止まると PITR の RPO 物差しが止まる = 最優先で守る）
BEGIN;

-- 1) マーカー（毎分）
INSERT INTO obs.marker DEFAULT VALUES;

-- 2) カウンタ UPDATE（毎分。dead tuple 1 個/分の供給源）
UPDATE obs.counter SET n = n + 1, updated_at = now() WHERE id = 1;

COMMIT;

-- T2: 観測する側（スナップショット 3 系列）
BEGIN;

-- 3) テーブル単位統計（5 分間隔）。phase は obs.phase_config から読む（フェーズ遷移は
--    手動 UPDATE 1 回。採取の方法・間隔はフェーズ間で完全に同一 = ラベルだけが変わる）。
--    'load' スキーマはフェーズ 2 の負荷生成テーブル用（存在しない間は行が出ないだけ）
INSERT INTO obs.table_stats (
    phase, relname, n_live_tup, n_dead_tup, n_tup_ins, n_tup_upd,
    autovacuum_count, last_autovacuum, autoanalyze_count, last_autoanalyze
)
SELECT pc.phase, s.relname, s.n_live_tup, s.n_dead_tup, s.n_tup_ins, s.n_tup_upd,
       s.autovacuum_count, s.last_autovacuum, s.autoanalyze_count, s.last_autoanalyze
FROM pg_stat_user_tables s, obs.phase_config pc
WHERE s.schemaname IN ('obs', 'public', 'load')
  AND coalesce((SELECT max(ts) FROM obs.db_stats), '-infinity')
      <= now() - interval '5 minutes';
-- ↑ アンカーは db_stats の max(ts)（table_stats と同じ 5 分系列。db_stats の INSERT より
--   先に評価されるよう、この文を db_stats より前に置く = 両者が同じ判定で歩調を揃える）

-- 4) DB 単位統計（5 分間隔。WAL / サイズ / XID age）
INSERT INTO obs.db_stats (phase, wal_records, wal_bytes, db_size_bytes, frozen_xid_age)
SELECT pc.phase, w.wal_records, w.wal_bytes,
       pg_database_size(current_database()),
       age(d.datfrozenxid)
FROM pg_stat_wal w, pg_database d, obs.phase_config pc
WHERE d.datname = current_database()
  AND coalesce((SELECT max(ts) FROM obs.db_stats), '-infinity')
      <= now() - interval '5 minutes';

-- 5) 実 bloat（1 時間間隔。マーカー系 2 テーブルのみ）
INSERT INTO obs.bloat_stats (phase, relname, table_len, tuple_percent, dead_tuple_percent, free_percent)
SELECT pc.phase, t.relname, s.table_len, s.tuple_percent, s.dead_tuple_percent, s.free_percent
FROM (VALUES ('obs.marker'), ('obs.counter')) AS t(relname),
     LATERAL pgstattuple(t.relname) AS s,
     obs.phase_config pc
WHERE coalesce((SELECT max(ts) FROM obs.bloat_stats), '-infinity')
      <= now() - interval '1 hour';

COMMIT;
