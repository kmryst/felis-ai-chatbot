#!/usr/bin/env bash
# readyz-probe.yml の鮮度ゲート判定ロジックの境界テスト（ローカル実行。Issue #106）
#
# 方式: workflow の run ブロックを yq で「逐語」抽出し、curl を PATH shim で
# 差し替えて実行する。抽出実行なのでテスト対象と出荷物が乖離しない。
# ENFORCE の既定値も workflow の env: 定義から実際にパースして使う
# （repository variable 未設定時の挙動をそのまま再現するため）。
#
# 実行: scripts/test/readyz-probe-freshness-test.sh
# 依存: bash / jq / yq (mikefarah v4)
# 別版の workflow を対象にする場合: WORKFLOW_FILE=/path/to/file を指定

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow_file="${WORKFLOW_FILE:-$repo_root/.github/workflows/readyz-probe.yml}"

command -v yq >/dev/null || { echo "yq is required" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# run ブロックを逐語抽出する
yq -r '.jobs.probe.steps[0].run' "$workflow_file" > "$workdir/probe.sh"
[ -s "$workdir/probe.sh" ] || { echo "failed to extract run block" >&2; exit 2; }

# ENFORCE の既定値を env: 定義（${{ vars.X || 'default' }}）からパースする
default_enforce="$(yq -r '.jobs.probe.env.ENFORCE' "$workflow_file" \
	| sed -n "s/.*|| *'\([^']*\)'.*/\1/p")"
[ -n "$default_enforce" ] || { echo "failed to parse ENFORCE default" >&2; exit 2; }
echo "# workflow: $workflow_file"
echo "# ENFORCE default (repository variable unset): $default_enforce"

# curl の PATH shim: -o の出力先に fixture をコピーし、-w 相当の
# "http_code time_total" を stdout に返す。STUB_CODE=000 は接続失敗を模す
mkdir -p "$workdir/bin"
cat > "$workdir/bin/curl" <<'SHIM'
#!/usr/bin/env bash
out=""
prev=""
for a in "$@"; do
	[ "$prev" = "-o" ] && out="$a"
	prev="$a"
done
if [ "$STUB_CODE" = "000" ]; then
	exit 7
fi
[ -n "$out" ] && cp "$STUB_BODY_FILE" "$out"
printf '%s %s' "$STUB_CODE" "0.123"
SHIM
chmod +x "$workdir/bin/curl"

pass=0
fail=0

# run_case <name> <expected_exit> <http_code> <body_json|-> [ENFORCE override]
run_case() {
	local name="$1" expected="$2" http_code="$3" body="$4" enforce="${5:-$default_enforce}"
	local body_file="$workdir/body.json" summary="$workdir/summary.md"
	printf '%s' "$body" > "$body_file"
	: > "$summary"
	local actual=0
	# GitHub Actions の run 既定シェル（bash -e -o pipefail）で実行する
	PATH="$workdir/bin:$PATH" \
		STUB_CODE="$http_code" STUB_BODY_FILE="$body_file" \
		PROBE_ENABLED=true READYZ_URL="https://stub.invalid/readyz" \
		MARKER_MAX_AGE=600 STATS_MAX_AGE=900 PGSTATTUPLE_MAX_AGE=10800 \
		ENFORCE="$enforce" GITHUB_STEP_SUMMARY="$summary" \
		bash --noprofile --norc -e -o pipefail "$workdir/probe.sh" \
		> "$workdir/out.log" 2>&1 || actual=$?
	if [ "$actual" = "$expected" ]; then
		echo "PASS: $name (exit $actual)"
		pass=$((pass + 1))
	else
		echo "FAIL: $name (expected exit $expected, got $actual)"
		sed 's/^/  | /' "$workdir/out.log"
		fail=$((fail + 1))
	fi
}

obs='{"status":"ok","db":"ok","obs":'

# 境界ケース（repository variable 未設定 = workflow の既定値で判定）
run_case ".obs キー自体が無い（#104 未デプロイ相当）→ green" \
	0 200 '{"status":"ok","db":"ok"}'
run_case "全系列 null（採取開始前）→ green" \
	0 200 "$obs"'{"marker_age_seconds":null,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}'
run_case "marker のみ値あり・閾値内、他は null（ブートストラップ中）→ green" \
	0 200 "$obs"'{"marker_age_seconds":120,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}'
run_case "marker のみ値あり・閾値超過 → fail" \
	1 200 "$obs"'{"marker_age_seconds":700,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}'
run_case "全系列に値があり全部閾値内 → green" \
	0 200 "$obs"'{"marker_age_seconds":120,"stats_age_seconds":300,"pgstattuple_age_seconds":3600}}'
run_case "stats だけ閾値超過（系列別に効く）→ fail" \
	1 200 "$obs"'{"marker_age_seconds":120,"stats_age_seconds":1200,"pgstattuple_age_seconds":3600}}'
run_case ".obs キーはあるが null（採取側デプロイ済みなのに鮮度クエリ失敗）→ fail" \
	1 200 '{"status":"ok","db":"ok","obs":null}'
run_case "HTTP 503 → fail" 1 503 '{"status":"unavailable","db":"unreachable"}'
run_case "HTTP 000（接続失敗）→ fail" 1 000 '-'
run_case "200 だが body が JSON object でない → fail" 1 200 'not json'
run_case "非常口: ENFORCE=false なら閾値超過でも green（SLI 記録は継続）" \
	0 200 "$obs"'{"marker_age_seconds":700,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}' false

echo
echo "result: pass=$pass fail=$fail"
[ "$fail" = "0" ]
