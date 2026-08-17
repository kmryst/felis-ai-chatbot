# ADR-0002: DB スキーマ管理に Alembic を採用する

## ステータス

Accepted

## 日付

2026-08-17

## 決定内容

DB スキーマの変更管理に Alembic を採用する。マイグレーション本文は raw SQL（`op.execute`）で書き、ORM モデルからの autogenerate は使わない。接続先は環境変数 `DATABASE_URL` から読み、`alembic.ini` にはハードコードしない。

## 背景

- Day 2 のデータ投入、Day 4 の Backup / Restore 検証（PITR）の前提として、スキーマを再現可能な形で管理する必要がある
- 5日制約のため、導入コストが小さく Python エコシステムに閉じるツールが望ましい
- 本プロジェクトの主役は PostgreSQL 運用であり、「スキーマがバージョン管理され、任意の状態へ upgrade / downgrade できる」こと自体が見せ場になる

## 検討した選択肢

1. **Alembic + raw SQL**（採択）
2. Alembic + SQLAlchemy モデル + autogenerate
3. 素の SQL ファイル + 自作適用スクリプト
4. dbmate / golang-migrate 等の言語非依存ツール

## 採択理由

- Alembic は FastAPI / Python スタックの事実上の標準で、backend の uv 管理にそのまま乗る（別バイナリの導入・pin が不要）
- raw SQL にするのは、pgvector の `vector(1536)` / HNSW インデックスなど PostgreSQL 固有 DDL が中心で、ORM 型マッピングを介す価値が薄いため。適用される SQL がレビューでそのまま読めることを優先した
- autogenerate を使わないため、ORM モデル（SQLAlchemy Declarative）の整備は不要。Day 1 時点でアプリはこれらのテーブルをまだ参照しない

## 却下理由

- 選択肢2: autogenerate はモデル定義の維持コストがかかり、pgvector 型はプラグインなしでは扱えない。5日制約で過剰
- 選択肢3: バージョン追跡・downgrade・適用済み判定を自作することになり、Alembic の再発明になる
- 選択肢4: ツールチェーンが増え、`.mise.toml` / CI の pin 管理対象も増える。Python に閉じる利点を捨ててまで得るものがない

## 影響

- `backend/alembic.ini` と `backend/migrations/` が正本。適用は `uv run alembic upgrade head`
- CI（Day 1 PR 5 予定）ではテスト用 DB に対して同じマイグレーションを適用してからテストを走らせる
- Azure 環境（Day 3 以降）への適用方法（デプロイ時 job 等）は Day 3 で判断する

## 関連

- Issue: #13
- ADR-0003（スキーマ設計）
