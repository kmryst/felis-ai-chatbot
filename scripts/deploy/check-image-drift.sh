#!/usr/bin/env bash
# デプロイ済み image と main の乖離検出（Issue #206）
#
# 目的: 「main（HEAD）は進んだのに image を作り直していない」状態を apply の前に検出する。
# .env の DEPLOY_SHA（= 実際に ACR へ push 済みのタグの正本。vnet-integration-cutover.md §0-2）と
# HEAD の間で、image のビルドコンテキスト（backend/ / frontend/）に差分があれば exit 1 で止める。
# #196 で frontend 側の変更が入ったまま image が sha-2df47f9 で据え置かれ、デプロイ済み画面が
# 古い表記のまま残った事故の再発防止。
#
# 実行: scripts/deploy/check-image-drift.sh            # .env の DEPLOY_SHA を読む
#       DEPLOY_SHA=abc1234 scripts/deploy/check-image-drift.sh   # 環境変数で上書き
# 依存: bash / git
# 終了コード: 0 = 差分なし、1 = 差分あり（image の再 build / push が必要）、2 = 前提不足
#
# 検出しないもの（意図的に軽く保つ）:
# - Terraform 変数や secret の反映漏れ（それぞれ *_CONFIG_CHECKSUM が担保する）
# - ACR 上のタグの実在（push 済みかどうかは §2 の手順と az acr repository show-tags で確認する）

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

# image のビルドコンテキストになるパス。Dockerfile の COPY 対象と一致させる
image_paths=(backend frontend)

# DEPLOY_SHA は環境変数を優先し、無ければ .env から読む（.env 全体は source しない = secret を
# シェルへ広げない）
if [ -z "${DEPLOY_SHA:-}" ]; then
	if [ -f .env ]; then
		DEPLOY_SHA="$(sed -n -E 's/^DEPLOY_SHA=([0-9a-f]+)[[:space:]]*$/\1/p' .env | tail -n 1)"
	fi
fi
if [ -z "${DEPLOY_SHA:-}" ]; then
	echo "DEPLOY_SHA が未設定（環境変数にも .env にも無い）。§2 の push 後に書き戻すこと" >&2
	exit 2
fi
if ! git cat-file -e "${DEPLOY_SHA}^{commit}" 2>/dev/null; then
	echo "DEPLOY_SHA=${DEPLOY_SHA} はこのリポジトリのコミットとして解決できない（fetch 漏れ or タグの誤り）" >&2
	exit 2
fi

head_sha="$(git rev-parse --short HEAD)"

# 作業ツリーが dirty だと HEAD の SHA がビルド内容を同定しない（§2 の注意と同じ理屈）
if [ -n "$(git status --porcelain -- "${image_paths[@]}")" ]; then
	echo "作業ツリーに未コミットの変更がある（${image_paths[*]}）。commit してから再実行すること" >&2
	git status --short -- "${image_paths[@]}" >&2
	exit 2
fi

if ! git merge-base --is-ancestor "$DEPLOY_SHA" HEAD; then
	echo "注意: DEPLOY_SHA=${DEPLOY_SHA} は HEAD（${head_sha}）の祖先ではない（別ブランチで push したタグ）" >&2
fi

changed="$(git diff --name-only "$DEPLOY_SHA" HEAD -- "${image_paths[@]}")"
if [ -z "$changed" ]; then
	echo "OK: DEPLOY_SHA=${DEPLOY_SHA} と HEAD=${head_sha} の間に image に影響する差分は無い"
	exit 0
fi

echo "DRIFT: DEPLOY_SHA=${DEPLOY_SHA} → HEAD=${head_sha} で image に影響する差分がある。" >&2
echo "       §2 の手順で 3 image を HEAD の SHA で build / push し、.env の DEPLOY_SHA を更新すること" >&2
echo "$changed" | sed 's/^/  /' >&2
exit 1
