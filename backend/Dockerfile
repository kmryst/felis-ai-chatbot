# backend（FastAPI + uvicorn）のコンテナイメージ。
#
# ローカル検証:
#   cd backend
#   docker build -t felis-backend:sha-$(git rev-parse --short HEAD) .
#
# 設計方針:
# - ベースは python:3.13.14-slim（Debian / glibc）。バージョンは .mise.toml /
#   backend/.python-version（3.13.14）と一致させる。alpine は musl libc のため
#   manylinux wheel が使えず psycopg 等のソースビルドが必要になるので採用しない。
#   distroless はシェルなしでデバッグ困難になり、5日間プロジェクトには過剰
# - マルチステージ: builder で uv が .venv を作り、runtime へは .venv とアプリ
#   コードだけをコピーする（uv・ビルドツールを実行イメージに残さない）
# - 依存解決は uv sync --frozen（uv.lock を正とし、勝手な解決をさせない）
# - 非 root ユーザー（uid 10001）で実行する
# - secret（DATABASE_URL / AZURE_OPENAI_API_KEY 等）は一切焼き込まない。
#   すべて実行時の環境変数で渡す（app/config.py が起動時に検証する）
# - イメージタグは git commit SHA 由来の不変タグを使う。latest 禁止（ADR-0015）

FROM python:3.13.14-slim AS builder

# uv はビルド専用ステージにのみ置く。バージョンは digest でなくタグ固定
# （ローカル開発の uv と同じ系列。更新は Dockerfile の編集で明示的に行う）
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

WORKDIR /app

# - UV_COMPILE_BYTECODE: 起動時の .pyc 生成をビルド時に済ませる
# - UV_LINK_MODE=copy: キャッシュへのハードリンク不可の警告を消し、.venv を自己完結にする
# - UV_PYTHON_DOWNLOADS=never: ベースイメージの Python 以外を勝手に取得させない
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# 依存定義だけを先にコピーして uv sync し、アプリコードの変更で
# 依存インストールのレイヤーキャッシュが無効化されないようにする
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.13.14-slim AS runtime

# 実行専用の非 root ユーザー。ホームディレクトリ・シェルログインは不要
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --shell /usr/sbin/nologin --no-create-home app

WORKDIR /app

# .venv の python は /usr/local/bin/python3.13 への symlink。
# builder と runtime が同一ベースイメージなのでそのまま動く
COPY --from=builder /app/.venv /app/.venv

# 実行に必要なのはアプリ本体のみ（tests / migrations は含めない。
# マイグレーションはローカル・CI から alembic で実行する運用）
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

# docker-compose.yml / frontend 既定（NEXT_PUBLIC_BACKEND_URL）と同じ 8000
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
