# frontend（Next.js standalone）のコンテナイメージ（ADR-0027 決定 7）。
#
# ローカル検証:
#   cd frontend
#   docker build -t felis-frontend:sha-$(git rev-parse --short HEAD) .
#
# 設計方針（backend/Dockerfile と同じ作法）:
# - ベースは node:24.18.0-slim（Debian / glibc）。バージョンは .mise.toml の node
#   （24.18.0）と一致させる
# - マルチステージ: deps で npm ci、builder で next build（output: "standalone"）、
#   runtime へは standalone 出力と静的アセットだけをコピーする
# - 非 root ユーザー（uid 10001）で実行する
# - secret（CHAT_API_KEY 等）は一切焼き込まない。すべて実行時の環境変数で渡す
#   （NEXT_PUBLIC_ は廃止済み = ADR-0027 決定 2。build 時に埋め込まれる値が無い）
# - イメージタグは git commit SHA 由来の不変タグを使う。latest 禁止（ADR-0015）

FROM node:24.18.0-slim AS deps

WORKDIR /app

# 依存定義だけを先にコピーして npm ci し、アプリコードの変更で
# 依存インストールのレイヤーキャッシュが無効化されないようにする
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.18.0-slim AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# ビルド時の telemetry 送信を無効化する（ビルド環境から外部へ出さない）
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24.18.0-slim AS runtime

# 実行専用の非 root ユーザー。ホームディレクトリ・シェルログインは不要
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --shell /usr/sbin/nologin --no-create-home app

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# standalone 出力は server.js と最小限の node_modules を含む自己完結ディレクトリ。
# 静的アセット（.next/static / public）は standalone に含まれないため別途コピーする
# （出典: https://nextjs.org/docs/app/api-reference/config/next-config-js/output ）
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER app

# Next.js standalone server の既定ポート
EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
