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

### `value_numeric` は DOUBLE PRECISION を採用（NUMERIC にしない）

当初「未確定・要レビュー」としていたが、レビューの結果 DOUBLE PRECISION で確定した。

- **データ適合性**: 扱う値のダイナミックレンジが極端に広い（質量・磁場強度・密度が数十桁にまたがる）。NUMERIC の強みは任意精度による 10 進の厳密性であって指数範囲ではなく、この用途ではその利点が働かない
- **偽の精度を作らない**: 元データは有効数字 2〜4 桁の観測値・推定値。DB 側で 10 進厳密性を保っても出典の不確かさを超える精度は生まれず、むしろ「厳密な値である」という誤った印象を与える。主用途が「太陽の何倍か」という比較・比率演算であることとも整合する
- **可逆性（SRE 観点）**: DOUBLE PRECISION → NUMERIC はマイグレーション 1 本で拡大方向に移行でき安全。逆方向は情報が落ちる。現時点の情報量で決め打つより、後戻りできる側を選ぶ

### `sources` の UNIQUE は `(source_url, retrieved_at)` を維持

当初「未確定・要レビュー」としていたが、レビューの結果この粒度で確定した。

- 同じ URL を再取得したときに履歴が残る形になり、`retrieved_at` を provenance の必須項目としたデータ方針と一致する
- `source_url` 単体を UNIQUE にすると再取得が上書きになり、いつ時点の情報かを追えなくなる。出典の記載が後から変わった場合に、過去に取り込んだ数値がどの版に基づくかを説明できなくなる

## 却下理由

- 選択肢2（JSONB）: 柔軟だが、出所必須・値型・単位を DB 制約で守れない。クエリも `->>` の連鎖になり、面接で「なぜ整合性を DB で守らなかったのか」に答えられない
- 選択肢3（ワイドテーブル）: 「全オブジェクトに同一カラムが存在しない」前提と正面衝突し、NULL だらけの列と題材変更のたびの DDL 変更を招く

## 影響

- Day 2 のデータ投入はこのスキーマに従う。実データ投入前に題材を確定させる（bootstrap 手順書 §13）
- `documents.embedding` は NULL 許容（ingest 後に embedding を埋める2段階投入を許す）
- HNSW インデックスは cosine 距離（`vector_cosine_ops`）。検索クエリは `<=>` 演算子を使う
- プロパティ値の頻繁な集計・比較が必要になった場合、EAV 型はクエリが縦持ちになる。必要になった時点でビューで吸収する
- 将来、金額など 10 進の厳密性が要る題材に変わった場合は、`value_numeric` を NUMERIC へ移行する（DOUBLE PRECISION → NUMERIC は拡大方向のマイグレーション 1 本で移行できる）
- 同一 URL の再取得は `retrieved_at` が異なる別の `sources` 行として蓄積される。過去に取り込んだ数値がどの時点の版に基づくかを説明できる

## 関連

- Issue: #13 / #24（未確定 2 点の確定）
- ADR-0002（Alembic）
- `docs/operations/bootstrap.md` §13（題材確定の期限・provenance 要件）
