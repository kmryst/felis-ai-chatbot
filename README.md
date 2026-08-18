# felis-ai-chatbot

pgvector RAG チャットボット。PostgreSQL の Backup / Restore / Maintenance / Monitoring を設計・実装・検証する個人開発

このリポジトリは [idp-golden-path](https://github.com/kmryst/idp-golden-path) の
ゴールデンパステンプレート **service-baseline** から生成されました。
以下の運用基盤（ガードレール）が最初から有効です。

## ローカルでの動かし方

### 1. PostgreSQL（pgvector）を起動する

```bash
cp .env.example .env   # 初回のみ（.env はコミット禁止）
docker compose up -d   # pgvector 入り PostgreSQL 17
docker compose ps      # STATUS が healthy になるまで待つ
```

停止は `docker compose down`（データ保持）、破棄は `docker compose down -v`。

### 2. DB スキーマを適用する（マイグレーション）

```bash
cd backend
uv sync
set -a && source ../.env && set +a   # DATABASE_URL を読み込む
uv run alembic upgrade head          # スキーマ適用
uv run alembic downgrade base        # 全て戻す（破壊的。ローカル検証用）
```

スキーマ設計は [ADR-0003](./docs/adr/0003-provenance-schema-design.md)、ツール選定は [ADR-0002](./docs/adr/0002-alembic-for-schema-migrations.md) を参照。

### 3. backend（FastAPI）を起動する

```bash
mise install          # .mise.toml どおりの python を取得
cd backend
uv sync               # 依存インストール（.venv 作成）
set -a && source ../.env && set +a   # DATABASE_URL 等を読み込む
uv run uvicorn app.main:app --reload
```

- `GET /health` — liveness（プロセス生存のみ。依存先は見ない。DB 停止中でも 200）
- `GET /readyz` — readiness（DB へ `SELECT 1`。到達不能なら 503。接続 timeout は `DB_CONNECT_TIMEOUT_SECONDS`、既定 2 秒）
- `DATABASE_URL` は必須。欠けていると起動時に即 fail する
- `POST /chat` — チャット応答。LLM は既定でスタブ（[ADR-0004](./docs/adr/0004-stub-llm-and-no-llm-in-ci.md)。API キー不要・実 LLM は呼ばない）

  ```bash
  curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
    -d '{"message": "こんにちは"}'
  ```

- ログは JSON 1行形式。`X-Request-ID` ヘッダを尊重し、無ければ採番してレスポンスヘッダとログに貫通させる
- 設定は環境変数から読む。secret は `.env`（gitignore 済み）にのみ置く

### 4. frontend（Next.js）を起動する

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

- チャット UI からのメッセージは backend の `POST /chat` に送られる（現在はスタブ応答）
- backend の URL は `NEXT_PUBLIC_BACKEND_URL` で上書き可能（既定 `http://localhost:8000`）
- backend 側の CORS 許可 origin は `CORS_ALLOWED_ORIGINS`（既定 `http://localhost:3000`）

### 5. テストを実行する

```bash
# テスト用 DB（開発用 DB とは分離。テストはスキーマを作り直すため必須）
docker exec felis-db psql -U felis -d postgres -c "CREATE DATABASE felis_test"

cd backend
TEST_DATABASE_URL=postgresql://felis:local-dev-only@localhost:5433/felis_test \
  uv run pytest -v
```

- `TEST_DATABASE_URL` 未設定なら DB テストは skip される（それ以外は常に実行）
- テストは実 LLM・外部 API を一切呼ばない（[ADR-0004](./docs/adr/0004-stub-llm-and-no-llm-in-ci.md)）。pgvector 類似検索は手書きの固定ベクトルで決定的に検証する
- CI（`.github/workflows/backend-tests.yml`）は `services:` の pgvector コンテナで同じテストを実行する

## このリポジトリに含まれるもの

| 資産 | 役割 |
| --- | --- |
| `CLAUDE.md` | AI Agent（Claude Code）向けの作業ルール入口 |
| `CONTRIBUTING.md` | Issue / Branch / Commit / PR / Label / 軽運用・厳密運用の正本 |
| `.github/labels.yml` | ラベル定義の正本（push で自動同期） |
| `.mise.toml` | ローカル開発ツールチェーン（Node.js 等）のバージョンの正本。CI pin との一致を Toolchain Version Check が検査する |
| `.github/workflows/` | PR Policy Check / Commitlint / Markdown Lint / Gitleaks Secret Scan / Sync Labels / Issue Template Check / Toolchain Version Check（実体は [idp-golden-path の reusable workflows](https://github.com/kmryst/idp-golden-path/tree/main/.github/workflows) をタグ固定 `@v1` で参照。更新は Dependabot のバージョンアップ PR で取り込む） |
| `.github/pull_request_template.md` / `ISSUE_TEMPLATE/` | PR / Issue テンプレート |
| `scripts/github/` | Issue / PR 作成・ラベル同期・ブランチ cleanup の helper |
| `docs/adr/` | Architecture Decision Record（0001 に生成経緯を記録済み） |
| `docs/operations/branch-protection.md` | main ブランチ保護の適用手順（初期状態では未適用） |
| `docs/operations/bootstrap.md` | Day 0 bootstrap の手順と検証証跡（本リポジトリ立ち上げの正本） |

## 初期セットアップ（生成後にやること）

1. ツールチェーンと依存をインストールし、ローカルで CI と同じチェックを実行できるようにする

   ```bash
   mise install   # .mise.toml の宣言どおりに Node.js 等を取得する
   npm ci
   npm run lint:md
   ```

   Terraform を導入する場合は `.mise.toml` のコメントに従って `terraform` を宣言し、
   Terraform を使う workflow の pin も同じ値に揃える。両者の一致は Toolchain Version Check が PR ごとに検査する。

2. ラベルが同期されていることを確認する（初回 push 時に Sync Labels workflow が実行される。
   手動同期は `./scripts/github/sync-labels.sh`）

3. 最初の PR をマージして CI（required checks 候補）の実行実績を作ったあと、
   [docs/operations/branch-protection.md](./docs/operations/branch-protection.md) の手順で
   main ブランチ保護を適用する

4. アプリケーションコードの技術選定は `docs/adr/` に ADR として記録してから実装を始める

## 開発フロー

Issue / PR 駆動開発を基本とします。詳細は [CONTRIBUTING.md](./CONTRIBUTING.md) を参照してください。

```bash
# Issue 作成
./scripts/github/create-issue-with-labels.sh --title "短い要約" \
  --body-file docs/issue-templates/feature_request.md \
  --type type:feature --area area:app --risk risk:low --cost cost:none

# PR 作成（draft で作成される）
./scripts/github/create-pr-with-labels.sh --title "feat: 変更の要約" \
  --body-file /path/to/filled-pr-body.md --issue <issue番号> \
  --type type:feature --area area:app --risk risk:low --cost cost:none --base main
```

## ドキュメント

- 設計判断: [docs/adr/](./docs/adr/README.md)
- 利用データソース一覧（気象庁ホームページ）: [docs/data-sources.md](./docs/data-sources.md)
- Day 0 bootstrap 手順書: [docs/operations/bootstrap.md](./docs/operations/bootstrap.md)

本リポジトリは skeleton の手動コピーで立ち上げたため、Backstage TechDocs / Software Catalog 用ファイル
（`mkdocs.yml` / `catalog-info.yaml`）は含まれていません（[ADR-0001](./docs/adr/0001-bootstrap-by-manual-skeleton-copy.md)）。
