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
| [0004](./0004-stub-llm-and-no-llm-in-ci.md) | Accepted | LLM は故障注入可能なスタブで開発し、CI・テストから実 LLM を呼ばない |
| [0005](./0005-app-ci-in-repo-not-idp.md) | Accepted | アプリケーション層（build / test / lint）の CI は本リポジトリに置き、idp-golden-path へ共通化しない |
| [0006](./0006-nasa-ai-terms-compliance.md) | Superseded | NASA AI 条項準拠 — 帰属の対象を AI 生成文から未加工の原文抜粋へ付け替える（ADR-0008 により置き換え） |
| [0007](./0007-jma-as-content-source.md) | Accepted | 題材の出典を気象庁ホームページ（気象・防災）に選定する |
| [0008](./0008-jma-attribution-and-weather-act-compliance.md) | Accepted | 気象庁の出典表示（記載例準拠）と気象業務法（17条・23条）への設計対応 |
| [0009](./0009-azure-openai-as-llm-provider.md) | Accepted | LLM 提供元を Azure OpenAI（japaneast。chat は無料試用クォータ制約で GlobalStandard）に確定する |
| [0010](./0010-rag-wiring-and-hallucination-guard.md) | Accepted | RAG を結線し、検索結果が閾値未満なら LLM を呼ばないハルシネーション・ガードをコードで担保する |
| [0011](./0011-backup-retention-and-geo-redundancy.md) | Accepted | PostgreSQL のバックアップ保持 7 日（検証 3 日 < 窓 7 日）・geo 冗長無効を作成時に確定する |
| [0012](./0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) | Accepted | CI 用 service principal の最小権限化（PR credential / RBAC Administrator を見送り）と Terraform 管理リソース専用 RG の分離 |
| [0013](./0013-azure-resource-naming-convention.md) | Accepted | Azure リソース命名規則（CAF 略語準拠）の制定と未作成リソース名の統一（稼働中の Azure OpenAI は例外として記録） |
