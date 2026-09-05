#!/usr/bin/env bash
# scripts/github/lib/common.sh の validate_issue_body_template の境界テスト（ローカル実行）
#
# 方式: common.sh を source して validate_issue_body_template を直接呼ぶ。
# die が exit するため、各ケースはサブシェルで実行して終了コードだけを見る。
#
# 実行: scripts/test/issue-body-template-test.sh
# 依存: bash / awk
#
# 検査ロジックの正本は idp-golden-path の reusable workflow（issue-template-check@v1）側であり、
# ここで検証するのは本リポジトリの helper 側（ローカル版）の実装である。
# 同じ修正の横展開が必要かどうかは idp-golden-path 側で別途判断する。

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../github/lib/common.sh
source "$repo_root/scripts/github/lib/common.sh"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

pass=0
fail=0

# run_case <name> <expected_exit> <body>
#   expected_exit: 0 = 検査を通る / 1 = die で弾かれる
run_case() {
	local name="$1" expected="$2" body="$3"
	local body_file="$workdir/body.md"
	printf '%s' "$body" > "$body_file"
	local actual=0
	# die は exit するのでサブシェルで隔離する
	( validate_issue_body_template "$body_file" ) > "$workdir/out.log" 2>&1 || actual=$?
	if [ "$actual" = "$expected" ]; then
		echo "PASS: $name (exit $actual)"
		pass=$((pass + 1))
	else
		echo "FAIL: $name (expected exit $expected, got $actual)"
		sed 's/^/  | /' "$workdir/out.log"
		fail=$((fail + 1))
	fi
}

# 正常系の土台。各ケースはここから一部だけ差し替える
ok_body='## 目的

目的の本文。

## 対象

対象の本文。

## 受け入れ条件

- 条件 1
'

run_case "全見出しに直下の本文がある（既存の正常系）" 0 "$ok_body"

run_case "## 対象 の直下が ### 小見出し + 本文（Issue #230 で踏んだケース）" 0 '## 目的

目的の本文。

## 対象

### 小見出し

小見出しの本文。

## 受け入れ条件

- 条件 1
'

run_case "## 対象 の直下に本文があり、その後に ### 小見出しが続く" 0 '## 目的

目的の本文。

## 対象

対象の本文。

### 小見出し

小見出しの本文。

## 受け入れ条件

- 条件 1
'

run_case "見出し自体が ### で、直下が #### 小見出し + 本文" 0 '### 目的

目的の本文。

### 対象

#### さらに深い小見出し

本文。

### 受け入れ条件

- 条件 1
'

run_case "## 対象 の直後にすぐ次の ## 見出しが来る（本当に空の節）" 1 '## 目的

目的の本文。

## 対象
## 受け入れ条件

- 条件 1
'

run_case "## 対象 の直下が空行だけで次の ## が来る" 1 '## 目的

目的の本文。

## 対象


## 受け入れ条件

- 条件 1
'

# 修正後の仕様: 小見出し行そのものも「節の中身」として数える。
# 検査の目的はテンプレートを埋めずに出した空節を弾くことであり、
# 小見出しが 1 つでも書かれている節は空ではない、と扱う。
run_case "## 対象 の直下が ### 小見出しだけ（小見出し自体を中身として数える）" 0 '## 目的

目的の本文。

## 対象

### 小見出し

## 受け入れ条件

- 条件 1
'

run_case "必須見出し（対象）そのものが存在しない" 1 '## 目的

目的の本文。

## 受け入れ条件

- 条件 1
'

# Issue #230 の本文構造の再現。`## 対象` / `## 受け入れ条件` の直下が ### で始まる
run_case "Issue #230 の本文構造（複数の節が ### 直下始まり）" 0 '## 目的

PITR ドリルを定期実行し、復旧手順の実効性を確認する。

## 対象

### 対象リソース

- PostgreSQL Flexible Server

### 対象手順

- restore / verify

## 受け入れ条件

### 必須

- ドリルが完走する

### 任意

- 所要時間を記録する

## 補足

なし。
'

echo
echo "result: pass=$pass fail=$fail"
[ "$fail" = "0" ]
