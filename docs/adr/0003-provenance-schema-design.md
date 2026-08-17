# ADR-0003: provenance を数値単位で保持する題材非依存スキーマ

## ステータス

Accepted

## 日付

2026-08-17

## 決定内容

初期スキーマを次の4テーブルで構成する。

- `sources` — provenance の正本（source URL / source title / reuse or license basis / retrieved_at / note）。他テーブルから FK で参照する
- `objects` — 題材のオブジェクト（名前・種別・備考のみ。題材固有カラムを持たない）
- `object_properties` — プロパティを**1値=1行**で持ち、`source_id` を NOT NULL にして**数値ごとの出所**を強制する
- `documents` — RAG 用チャンク。`embedding vector(1536)` + cosine 距離の HNSW インデックス。`source_id` NOT NULL

embedding の次元は 1536（`text-embedding-3-small` 相当。Azure OpenAI / OpenAI API で同一）に固定する。

## 背景

- 題材は未確定（当初案: 宇宙・天体スケール比較）のため、スキーマは題材非依存にする必要がある
- 対象データはオブジェクトによって取得可能な property が異なるため、「全オブジェクトに同一カラムの値が存在する」前提を置けない
- 公開データの再利用条件を示せることが要件であり、数値1つずつに出所を紐付けられる構造が必要
- embedding 次元を固定しないと、提供元切り替え時にカラム定義変更 + 全データ再 embedding が発生する（Day 0 bootstrap 手順書の確定事項）

## 検討した選択肢

1. **プロパティ行テーブル（EAV 型）+ sources 正規化**（採択）
2. `objects` に JSONB カラム 1 本（`{property: {value, unit, source...}}`）
3. オブジェクト種別ごとのワイドテーブル（radius / mass ... を列に持つ）

## 採択理由

- 「数値ごとの source」を **`source_id BIGINT NOT NULL REFERENCES sources(id)`** という DB 制約で強制できる。JSONB では出所の欠落を制約で防げず、アプリ側の規律に依存する
- provenance を `sources` に正規化することで、同一出典の重複記載と表記ゆれを防ぎ、「この出典から来た値の一覧」が JOIN 1 回で出せる
- `value_numeric` / `value_text` + `unit` の分離で、数値には型と単位が付き、CHECK 制約（どちらか必須）で空値行を防げる
- 題材が変わってもスキーマ変更が不要（オブジェクト名とプロパティ名は行データ）

## 却下理由

- 選択肢2（JSONB）: 柔軟だが、出所必須・値型・単位を DB 制約で守れない。クエリも `->>` の連鎖になり、面接で「なぜ整合性を DB で守らなかったのか」に答えられない
- 選択肢3（ワイドテーブル）: 「全オブジェクトに同一カラムが存在しない」前提と正面衝突し、NULL だらけの列と題材変更のたびの DDL 変更を招く

## 影響

- Day 2 のデータ投入はこのスキーマに従う。実データ投入前に題材を確定させる（bootstrap 手順書 §13）
- `documents.embedding` は NULL 許容（ingest 後に embedding を埋める2段階投入を許す）
- HNSW インデックスは cosine 距離（`vector_cosine_ops`）。検索クエリは `<=>` 演算子を使う
- プロパティ値の頻繁な集計・比較が必要になった場合、EAV 型はクエリが縦持ちになる。必要になった時点でビューで吸収する

## 未確定・要レビュー

- `value_numeric` を DOUBLE PRECISION にした（天文スケールの桁を想定）。金額等の正確な10進数が必要な題材になった場合は NUMERIC への変更を検討する
- `sources` の UNIQUE (source_url, retrieved_at) の粒度（同一 URL の再取得を別 source として扱う設計）

## 関連

- Issue: #13
- ADR-0002（Alembic）
- `docs/operations/bootstrap.md` §13（題材確定の期限・provenance 要件）
