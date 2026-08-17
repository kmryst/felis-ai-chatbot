# Architecture Decision Records

このディレクトリは、`felis-ai-chatbot` の重要な設計判断を ADR（Architecture Decision Record）として残す場所です。

## 番号付け

- ファイル名は `NNNN-kebab-case-title.md` とする
- `NNNN` は 4 桁の連番とし、一度使った番号は再利用しない
- 番号は ADR ファイルを追加する PR の時点で、`docs/adr/` 配下の最大番号 + 1 として確定する。Issue / ブランチの段階では番号を予約しない
- supersede する場合も古い ADR は削除せず、新しい ADR から参照する

## 形式

各 ADR は少なくとも次の項目を含めます。

- `ステータス`
- `日付`
- `決定内容`
- `背景`
- `検討した選択肢`
- `採択理由`
- `影響`
- `関連`

### ステータスの語彙

- `Proposed` — 提案中。まだ採択されていない
- `Accepted` — 採択済み。現在有効な判断
- `Superseded` — 後続の ADR に置き換えられた（置き換え先 ADR を `関連` から参照する）
- `Deprecated` — 廃止。置き換え先はないが、もう採用しない

### 日付の扱い

`日付` は **ADR を記録した日**であり、元の判断が行われた時期とは限りません。

## 一覧

| ADR | ステータス | 決定 |
| --- | --- | --- |
| [0001](./0001-bootstrap-by-manual-skeleton-copy.md) | Accepted | idp-golden-path の service-baseline skeleton を手動コピーしてリポジトリを立ち上げる |
| [0002](./0002-alembic-for-schema-migrations.md) | Accepted | DB スキーマ管理に Alembic（raw SQL マイグレーション）を採用する |
| [0003](./0003-provenance-schema-design.md) | Accepted | provenance を数値単位で保持する題材非依存スキーマ（プロパティ行テーブル + sources 正規化・vector(1536) 固定） |
