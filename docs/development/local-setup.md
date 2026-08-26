# ローカル開発環境のセットアップ

`felis-ai-chatbot` をローカルで動かす手順です。
Azure 上の構成・観測・検証については [README.md](../../README.md) を参照してください。

## 1. PostgreSQL（pgvector）を起動する

```bash
cp .env.example .env   # 初回のみ（.env はコミット禁止）
docker compose up -d   # pgvector 入り PostgreSQL 17
docker compose ps      # STATUS が healthy になるまで待つ
```

停止は `docker compose down`（データ保持）、破棄は `docker compose down -v`。

## 2. DB スキーマを適用する（マイグレーション）

```bash
cd backend
uv sync
set -a && source ../.env && set +a   # DATABASE_URL を読み込む
uv run alembic upgrade head          # スキーマ適用
uv run alembic downgrade base        # 全て戻す（破壊的。ローカル検証用）
```

スキーマ設計は [ADR-0003](../adr/0003-provenance-schema-design.md)、
ツール選定は [ADR-0002](../adr/0002-alembic-for-schema-migrations.md) を参照。

## 3. backend（FastAPI）を起動する

```bash
mise install          # .mise.toml どおりの python を取得
cd backend
uv sync               # 依存インストール（.venv 作成）
set -a && source ../.env && set +a   # DATABASE_URL 等を読み込む
uv run uvicorn app.main:app --reload
```

- `GET /livez` — liveness（プロセス生存のみ。依存先は見ない。DB 停止中でも 200）
- `GET /readyz` — readiness（DB へ `SELECT 1`。到達不能なら 503。接続 timeout は `DB_CONNECT_TIMEOUT_SECONDS`、既定 2 秒）
- `DATABASE_URL` は必須。欠けていると起動時に即 fail する
- `POST /chat` — チャット応答。LLM は既定でスタブ（[ADR-0004](../adr/0004-stub-llm-and-no-llm-in-ci.md)。API キー不要・実 LLM は呼ばない）。実 LLM（Azure OpenAI。[ADR-0009](../adr/0009-azure-openai-as-llm-provider.md)）を使う場合は `.env` に Azure 接続情報を設定し `LLM_PROVIDER=azure-openai` にする（CI・テストは常にスタブのまま）

  ```bash
  curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
    -d '{"message": "こんにちは"}'
  ```

- ログは JSON 1 行形式。`X-Request-ID` ヘッダを尊重し、無ければ採番してレスポンスヘッダとログに貫通させる
- 設定は環境変数から読む。secret は `.env`（gitignore 済み）にのみ置く

## 4. frontend（Next.js）を起動する

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

- チャット UI からのメッセージは backend の `POST /chat` に送られる
- backend の URL は `NEXT_PUBLIC_BACKEND_URL` で上書き可能（既定 `http://localhost:8000`）
- backend 側の CORS 許可 origin は `CORS_ALLOWED_ORIGINS`（既定 `http://localhost:3000`）
- backend で `CHAT_API_KEY` を設定している場合は、frontend 側にも同じ値を
  `NEXT_PUBLIC_CHAT_API_KEY` で渡す（未設定だと `/chat` が 401 になる）

## 5. テストを実行する

```bash
# テスト用 DB（開発用 DB とは分離。テストはスキーマを作り直すため必須）
docker exec felis-db psql -U felis -d postgres -c "CREATE DATABASE felis_test"

cd backend
TEST_DATABASE_URL=postgresql://felis:local-dev-only@localhost:5433/felis_test \
  uv run pytest -v
```

- `TEST_DATABASE_URL` 未設定なら DB テストは skip される（それ以外は常に実行）
- テストは実 LLM・外部 API を一切呼ばない（[ADR-0004](../adr/0004-stub-llm-and-no-llm-in-ci.md)）。
  pgvector 類似検索は手書きの固定ベクトルで決定的に検証する
- CI（`.github/workflows/backend-tests.yml`）は `services:` の pgvector コンテナで同じテストを実行する

## 6. CI と同じチェックをローカルで走らせる

```bash
mise install   # .mise.toml の宣言どおりに Node.js 等を取得する
npm ci
npm run lint:md
npm run commitlint -- --from origin/main --to HEAD --verbose
```
