# ADR-0021: `obs.heartbeat` への毎分書き込みを recovery marker と位置づける（負荷生成ではない）

## ステータス

Accepted

## 日付

2026-08-27

## 決定内容

- `obs.heartbeat` への**毎分 1 行 INSERT** は、**PITR の復旧時点を確定させるための
  recovery marker**（既知の書き手 = known writer）と位置づける。
  autovacuum / bloat を駆動する**負荷生成ではない**
- docs とコメントで使ってきた「観測ワークロード」「合成負荷」「低負荷ベースライン（の書き込み）」
  という呼び方を、この位置づけに合わせて是正する
- **識別子は据え置く**。テーブル名 `obs.heartbeat`、`/readyz` の応答キー
  `heartbeat_age_seconds`、workflow 環境変数 `HEARTBEAT_MAX_AGE`、
  Terraform のリソース名・変数名は 1 文字も変えない
- フェーズ 2 の負荷生成（churn generator）は**本装置とは別物**であり、**未マージ**である
  （Issue #112 / PR #120）

## 背景

外部レビューで「毎分 1 行の書き込みを『観測負荷』と呼ぶと、負荷生成として不足していると読まれる」
という指摘を受けた。指摘の結論（負荷生成としては不足）は正しいが、**その指摘が挙げた根拠
（「毎分 insert のみでは dead tuple が生まれない」）は本リポジトリの実装と食い違う。**
`backend/observability/collect.sql` の T1 は毎分 `obs.counter` を UPDATE しており、
autovacuum は実際に自然発火している（22.63 時間で 26 回、約 52 分周期。下記）。

負荷生成として不足していると言える正確な根拠は、次の 2 点である。

### 1. 規模が足りない（`DELETE` が一切ない）

`collect.sql` の T1 が毎分行う書き込みは 2 つだけである。

- `INSERT INTO obs.heartbeat DEFAULT VALUES;` — 1 行 INSERT
- `UPDATE obs.counter SET n = n + 1, updated_at = now() WHERE id = 1;` — 1 行 UPDATE

したがって dead tuple の供給は **1 個/分 = 1,440 個/日**にとどまり、`collect.sql` 全体を通して
**`DELETE` は 1 文も存在しない**（T2 のスナップショット 3 系列も INSERT-only）。

フェーズ 1 の 72h 窓（`[2026-08-23T08:16:19Z, 2026-08-26T08:16:19Z)`）の実測:

| 観測 | 実測値 | 出典 |
| --- | --- | --- |
| `obs.heartbeat`（当時 `obs.marker`）の行数 | **4,320 / 名目 4,320（100.0%）** = 1,440 行/日 | [observations.md §9-1](../verification/observation-phase1/observations.md) |
| `obs.counter` の autovacuum 自然発火 | **22.63 時間で 26 回**（約 52 分周期） | [observations.md §4-7](../verification/observation-phase1/observations.md) |
| `obs.counter` の `max(n_dead_tup)` | **50** | 同上 |
| `obs.heartbeat`（当時 `obs.marker`）の `max(n_dead_tup)` | **0**（INSERT-only なので dead tuple が出ない） | 同上 |
| DB サイズの増加 | **+630,784 B / 22.63 時間** | [observations.md §4-7](../verification/observation-phase1/observations.md) |

autovacuum は「動いている」が、**1 行テーブルの dead tuple を 50 個ためては刈るだけ**である。
bloat の成長、vacuum が追いつかない状況、閾値のレンジ分布といった、
本来この観測で見たい現象を発生させられる規模ではない。

### 2. HNSW 劣化は原理的に観測できない

このリポジトリで HNSW index が張られているのは `public.documents` の
`documents_embedding_hnsw_idx` **1 本だけ**である
（`backend/migrations/versions/0001_initial_schema.py`。
`CREATE INDEX documents_embedding_hnsw_idx ON documents USING hnsw (embedding vector_cosine_ops)`）。
`obs.*` のどのテーブルにも HNSW index は無い。

そして `public.documents` は**静的・少数行**（38 行。[ADR-0010](./0010-rag-wiring-and-hallucination-guard.md)）で、
`collect.sql` は `public` スキーマに 1 行も書き込まない。
PR #120 の負荷生成も書き込み先を `load` スキーマのみに限定している。

したがって、**現行の毎分書き込みでも PR #120 をマージ・実行しても、
HNSW index の劣化は原理的に観測対象にならない。**

## `pt-heartbeat` との用途差

`heartbeat table` という語は Percona Toolkit の `pt-heartbeat` を代表例とするが、
**その本来の用途は replication lag の計測**である。公式ドキュメントは目的を
"Monitor MySQL replication delay." と述べ、
"pt-heartbeat is a two-part MySQL and PostgreSQL replication delay monitoring system that
measures delay by looking at actual replicated data." と定義する。
親側（`--update`）が定期的に heartbeat テーブルの timestamp を更新し、
子側（`--monitor` / `--check`）が複製されたその行と現在時刻の差から lag を求める、という構造である。

- 出典: <https://docs.percona.com/percona-toolkit/pt-heartbeat.html> （2026-08-27 確認）

**本テーブルは replica を持たず、lag も測らない。**
同じ機構（一定間隔で 1 行書き、最新行との時刻差を取る）を、
**PITR の復旧時点確定 — known-writer / recovery marker — へ転用したもの**である。
`/readyz` が返す `heartbeat_age_seconds` は「複製の遅れ」ではなく
「**採取パイプラインが今も書けているか（= 復旧時点の物差しが生きているか）**」を表す。

PostgreSQL 自身の restore point（`pg_create_restore_point()` / `recovery_target_name`）とも別物である。
公式ドキュメントは `recovery_target_name` を
"This parameter specifies the named restore point (created with `pg_create_restore_point()`)
to which recovery will proceed." と定義しており、これは**1 点に打つ目印**である。
本テーブルは連続的に刻む点で用途が異なる（この整理自体は migration
`0004_rename_obs_marker_to_heartbeat.py` の docstring で既に述べている）。

- 出典: <https://www.postgresql.org/docs/17/runtime-config-wal.html> の `recovery_target_name` 節（2026-08-27 確認）

## 検討した選択肢

### (a) 呼称のみ是正し、識別子は据え置く（**採択**）

docs とコメントの言葉づかいだけを直し、テーブル名・応答キー・環境変数・Terraform の
リソース名と変数名はすべて据え置く。コード挙動の変更はゼロで、
Azure への apply も ops イメージの再ビルドも不要。

### (b) `obs.recovery_marker` へ再改名する（却下）

**却下**。改名の負債が既に 1 世代ある。2026-08-26 に `obs.marker` -> `obs.heartbeat` の改名
（Issue #133 / migration `0004`）を実施した結果、

- `docs/verification/observation-phase1/probe-records.jsonl` の**凍結証跡 131 行**は、
  抽出元の GitHub Actions ログとの再現性を保つため旧名 `marker_age` のまま残っている
- `scripts/collect-probe-records.sh` は新旧どちらのフィールド名も読めるよう**分岐**を抱えている
  （`has("heartbeat_age")` の判定）

という費用を既に払っている。2 世代目の改名は、この負債をもう一段積むだけで、
得られるのは名前の正確さの微増にとどまる。
さらに `0004` は「`marker` は説明的だが**業界標準語ではない**」として捨てた名前であり、
`recovery_marker` はその捨てた語へ戻ることになる。

### (c) 何もしない（却下）

**却下**。「合成負荷」という呼び方を残したまま「負荷としては不足」と説明を足すと、
読み手には「不足した負荷生成」に見え続ける。装置の目的（recovery marker）と
未実装の装置（churn generator）が同じ言葉で語られている状態こそが誤読の原因なので、
言葉を分けることが是正になる。

## 採択理由

- 誤読の原因は**呼び方**であって識別子ではない。呼び方だけを直せば、
  コード挙動・稼働中の Job・凍結証跡のいずれにも影響を出さずに解消できる
- `heartbeat` という語自体は業界標準語に接続しており（`0004` の判断）、
  「replication lag ではなく PITR の復旧時点へ転用したもの」という**用途差の 1 文**を
  添えれば正確になる。名前を捨てる必要はない
- 位置づけの正本を ADR に置くことで、docs 側の各所からは参照 1 本で済む

## 影響

- **docs とコメントのみの変更**。コード挙動・識別子・Azure リソースは無変更で、
  `terraform apply` も ops イメージの再ビルド・再 push も**不要**
- migration ファイル（`0002` / `0004`）は本文もコメントも変更しない。
  `0004` の docstring 自身が「適用済み revision は書き換えない」と運用を宣言しているため
- `docs/verification/` の本文・測定値・タイムスタンプは書き換えない（読み方の注記を追加するのみ）
- [ADR-0020](./0020-credit-window-resource-strategy.md) の記述は**据え置く**
  （ADR は撤回・更新した判断も当時のまま残す運用）
- `obs.phase_config` の CHECK 制約が持つフェーズラベル `baseline` は、
  もともと「負荷」を含意していない。今回の是正で docs 側の日本語が DB 側に揃う

### churn generator は本装置とは別物であり、未マージである

フェーズ 2 の負荷生成（Issue #112 / PR #120 `feat: フェーズ 2 負荷生成の骨格を実装する（WIP・E2E 未検証）`）は、
`load.load_rows` へ一括 INSERT + `grp` 単位の一括 UPDATE を回す**別の装置**であり、
**2026-08-27 時点で OPEN・未マージ**である。
本 ADR の対象（毎分の recovery marker）とは目的も書き込み先も異なる。

#### PR #120 は revision 番号が衝突しており、再開には 0005 への振り直しが必要

`gh pr diff 120` / `git show origin/112-load-generation:...` で確認した事実（2026-08-27）:

| ブランチ | ファイル | `revision` | `down_revision` |
| --- | --- | --- | --- |
| `main` | `backend/migrations/versions/0004_rename_obs_marker_to_heartbeat.py` | `"0004"` | `"0003"` |
| PR #120 | `backend/migrations/versions/0004_load_schema.py` | `"0004"` | `"0003"` |

`0004` を親 `0003` に持つ revision が 2 本になるため、Alembic のリビジョングラフが分岐する。
**PR #120 を再開するには `0005` への振り直し（ファイル名・`revision`・`down_revision = "0004"`）が必須**である。
PR #120 はブランチ作成時点（2026-08-23）には衝突していなかったが、
2026-08-26 の改名 migration（Issue #133）が先に main へ入ったことで衝突が生じた。

あわせて、**PR #120 をマージ・実行しても HNSW 劣化は観測できない**:

- `load.load_rows` のインデックスは `load_rows_grp_idx`（`grp` の btree）**のみ**で、HNSW は無い
- `load_generate.sh` は INSERT と UPDATE だけを回し、**`DELETE` を 1 文も含まない**
- 書き込み先は `load` スキーマのみで、HNSW index を持つ `public.documents` には触れない

## 関連

- [migration 0004](../../backend/migrations/versions/0004_rename_obs_marker_to_heartbeat.py) — `obs.marker` -> `obs.heartbeat` の改名と命名の根拠（Issue #133）
- [credit-window-execution-plan.md](../operations/credit-window-execution-plan.md) — §5-3（採取設計）/ §5-5（フェーズ 2 の負荷生成）
- [observations.md](../verification/observation-phase1/observations.md) — フェーズ 1 の実測記録（本 ADR の実測値の出典）
- [ADR-0020](./0020-credit-window-resource-strategy.md) — フェーズ 1 / フェーズ 2 の 2 段構成を決めた ADR（記述は据え置く）
- [ADR-0010](./0010-rag-wiring-and-hallucination-guard.md) — `public.documents` の HNSW index の現状（38 行・Seq Scan）
- Issue #112 / PR #120 — フェーズ 2 の負荷生成（churn generator。未マージ）
- Issue #147 — 本 ADR の起票元
