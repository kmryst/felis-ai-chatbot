#!/usr/bin/env bash
# readyz-probe.yml の鮮度ゲート判定ロジックの境界テスト（PR CI / ローカル。Issue #106）
#
# 方式: workflow の run ブロックを yq で「逐語」抽出し、curl を PATH shim で
# 差し替えて実行する。抽出実行なのでテスト対象と出荷物が乖離しない。
# 必須 repository variables の env mapping と fail-closed な設定検証も同時に確認する。
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

# 必須 repository variables は fallback を持たず、対応する job env へ直接束ねる。
# ここで固定すると、YAML 側だけ別名・既定値へ戻した場合に境界テストが素通りしない。
assert_repo_var_mapping() { # env_name repository_var_name
	local actual expected
	actual="$(yq -r ".jobs.probe.env.$1 // \"\"" "$workflow_file")"
	expected="\${{ vars.$2 }}"
	[ "$actual" = "$expected" ] || {
		echo "invalid mapping: .jobs.probe.env.$1 must be $expected (got: $actual)" >&2
		exit 2
	}
}
assert_repo_var_mapping PROBE_ENABLED PROBE_ENABLED
assert_repo_var_mapping READYZ_URL READYZ_URL
assert_repo_var_mapping OBS_FRESHNESS_ENFORCE OBS_FRESHNESS_ENFORCE
# 系列別閾値も workflow の env: 定義から実際に読む。ここをテスト側でハードコードすると、
# 「env: のキー名だけ改名して run ブロックの参照を直し忘れた（またはその逆）」という
# 追随漏れをテストが素通ししてしまう（実運用では変数が空になり判定が壊れる）。
# 実測: ハードコードしていた版では env: 名だけ旧名に戻した mutant が 17/17 pass した
threshold_env() { # var_name
	local v
	v="$(yq -r ".jobs.probe.env.$1 // \"\"" "$workflow_file")"
	if [ -z "$v" ] || [ "$v" = "null" ]; then
		echo "failed to read .jobs.probe.env.$1 from $workflow_file" >&2
		exit 2
	fi
	printf '%s' "$v"
}
heartbeat_max_age="$(threshold_env HEARTBEAT_MAX_AGE)"
stats_max_age="$(threshold_env STATS_MAX_AGE)"
pgstattuple_max_age="$(threshold_env PGSTATTUPLE_MAX_AGE)"

echo "# workflow: $workflow_file"
echo "# required repository variable mappings: PROBE_ENABLED / READYZ_URL / OBS_FRESHNESS_ENFORCE"
echo "# thresholds from workflow env: heartbeat=$heartbeat_max_age stats=$stats_max_age pgstattuple=$pgstattuple_max_age"

# テストケースの値（120 / 700 / 1200 ...）は下の既定閾値を前提に書いてある。
# 閾値そのものを変えたときにケースが黙って意味を失わないよう、ここで突き合わせる
if [ "$heartbeat_max_age" != "600" ] || [ "$stats_max_age" != "900" ] || [ "$pgstattuple_max_age" != "10800" ]; then
	echo "thresholds changed in the workflow; update the test case values accordingly" >&2
	exit 2
fi

# curl の PATH shim: -o の出力先に fixture をコピーし、-w 相当の
# "http_code time_total" を stdout に返す。STUB_CODE=000 は接続失敗を模す
mkdir -p "$workdir/bin"
cat > "$workdir/bin/curl" <<'SHIM'
#!/usr/bin/env bash
printf 'called\n' >> "$STUB_CALLS_FILE"
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

# run_case <name> <expected_exit> <http_code> <body_json|-> [OBS_FRESHNESS_ENFORCE override]
run_case() {
	local name="$1" expected="$2" http_code="$3" body="$4" obs_freshness_enforce="${5:-true}"
	local body_file="$workdir/body.json" summary="$workdir/summary.md" calls_file="$workdir/curl-calls.log"
	printf '%s' "$body" > "$body_file"
	: > "$summary"
	: > "$calls_file"
	local actual=0
	# GitHub Actions の run 既定シェル（bash -e -o pipefail）で実行する
	PATH="$workdir/bin:$PATH" \
		STUB_CODE="$http_code" STUB_BODY_FILE="$body_file" STUB_CALLS_FILE="$calls_file" \
		PROBE_ENABLED=true READYZ_URL="https://stub.invalid/readyz" \
		HEARTBEAT_MAX_AGE="$heartbeat_max_age" STATS_MAX_AGE="$stats_max_age" \
		PGSTATTUPLE_MAX_AGE="$pgstattuple_max_age" \
		OBS_FRESHNESS_ENFORCE="$obs_freshness_enforce" GITHUB_STEP_SUMMARY="$summary" \
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

# run_config_case <name> <expected_exit> <PROBE_ENABLED> <READYZ_URL>
#                 <OBS_FRESHNESS_ENFORCE> <expected_curl_calls>
run_config_case() {
	local name="$1" expected="$2" probe_enabled="$3" readyz_url="$4"
	local obs_freshness_enforce="$5" expected_calls="$6"
	local body_file="$workdir/body.json" summary="$workdir/summary.md" calls_file="$workdir/curl-calls.log"
	printf '%s' '{"status":"ok","db":"ok"}' > "$body_file"
	: > "$summary"
	: > "$calls_file"
	local actual=0 calls
	PATH="$workdir/bin:$PATH" \
		STUB_CODE=200 STUB_BODY_FILE="$body_file" STUB_CALLS_FILE="$calls_file" \
		PROBE_ENABLED="$probe_enabled" READYZ_URL="$readyz_url" \
		HEARTBEAT_MAX_AGE="$heartbeat_max_age" STATS_MAX_AGE="$stats_max_age" \
		PGSTATTUPLE_MAX_AGE="$pgstattuple_max_age" \
		OBS_FRESHNESS_ENFORCE="$obs_freshness_enforce" GITHUB_STEP_SUMMARY="$summary" \
		bash --noprofile --norc -e -o pipefail "$workdir/probe.sh" \
		> "$workdir/out.log" 2>&1 || actual=$?
	calls="$(wc -l < "$calls_file")"
	if [ "$actual" = "$expected" ] && [ "$calls" = "$expected_calls" ]; then
		echo "PASS: $name (exit $actual, curl calls $calls)"
		pass=$((pass + 1))
	else
		echo "FAIL: $name (expected exit/calls $expected/$expected_calls, got $actual/$calls)"
		sed 's/^/  | /' "$workdir/out.log"
		fail=$((fail + 1))
	fi
}

run_config_case "PROBE_ENABLED 未設定 → fail-closed" \
	1 '' 'https://stub.invalid/readyz' true 0
run_config_case "PROBE_ENABLED が true/false 以外 → fail-closed" \
	1 TRUE 'https://stub.invalid/readyz' true 0
run_config_case "READYZ_URL 未設定 → fail-closed" \
	1 true '' true 0
run_config_case "READYZ_URL が HTTPS でない → fail-closed" \
	1 true 'http://stub.invalid/readyz' true 0
run_config_case "READYZ_URL が /readyz でない → fail-closed" \
	1 true 'https://stub.invalid/healthz' true 0
run_config_case "OBS_FRESHNESS_ENFORCE 未設定 → fail-closed" \
	1 true 'https://stub.invalid/readyz' '' 0
run_config_case "OBS_FRESHNESS_ENFORCE が true/false 以外 → fail-closed" \
	1 true 'https://stub.invalid/readyz' enabled 0
run_config_case "PROBE_ENABLED=false → 設定検証後に正常 skip" \
	0 false 'https://stub.invalid/readyz' true 0

obs='{"status":"ok","db":"ok","obs":'

# 鮮度境界ケース（必須 repository variables はテスト harness が明示注入）
run_case ".obs キー自体が無い（#104 未デプロイ相当）→ green" \
	0 200 '{"status":"ok","db":"ok"}'
run_case "全系列 null（採取開始前）→ green" \
	0 200 "$obs"'{"heartbeat_age_seconds":null,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}'
run_case "heartbeat のみ値あり・閾値内、他は null（ブートストラップ中）→ green" \
	0 200 "$obs"'{"heartbeat_age_seconds":120,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}'
run_case "heartbeat のみ値あり・閾値超過 → fail" \
	1 200 "$obs"'{"heartbeat_age_seconds":700,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}'
run_case "全系列に値があり全部閾値内 → green" \
	0 200 "$obs"'{"heartbeat_age_seconds":120,"stats_age_seconds":300,"pgstattuple_age_seconds":3600}}'
run_case "stats だけ閾値超過（系列別に効く）→ fail" \
	1 200 "$obs"'{"heartbeat_age_seconds":120,"stats_age_seconds":1200,"pgstattuple_age_seconds":3600}}'
run_case "pgstattuple だけ閾値超過（系列別に効く）→ fail" \
	1 200 "$obs"'{"heartbeat_age_seconds":120,"stats_age_seconds":300,"pgstattuple_age_seconds":11000}}'
run_case "heartbeat のみ null（他 2 系列は値あり = その系列だけ skip）→ green" \
	0 200 "$obs"'{"heartbeat_age_seconds":null,"stats_age_seconds":300,"pgstattuple_age_seconds":3600}}'
run_case ".obs キーはあるが null（採取側デプロイ済みなのに鮮度クエリ失敗）→ fail" \
	1 200 '{"status":"ok","db":"ok","obs":null}'
run_case "HTTP 503 → fail" 1 503 '{"status":"unavailable","db":"unreachable"}'
run_case "HTTP 000（接続失敗）→ fail" 1 000 '-'
run_case "200 だが body が JSON object でない → fail" 1 200 'not json'
run_case "非常口: OBS_FRESHNESS_ENFORCE=false なら閾値超過でも green（SLI 記録は継続）" \
	0 200 "$obs"'{"heartbeat_age_seconds":700,"stats_age_seconds":null,"pgstattuple_age_seconds":null}}' false
run_case "系列値が整数でも null でもない（契約外の応答）→ fail" \
	1 200 "$obs"'{"heartbeat_age_seconds":"abc","stats_age_seconds":null,"pgstattuple_age_seconds":null}}'
run_case "stats が整数でも null でもない（契約外の応答）→ fail" \
	1 200 "$obs"'{"heartbeat_age_seconds":120,"stats_age_seconds":"abc","pgstattuple_age_seconds":null}}'
run_case "pgstattuple が整数でも null でもない（契約外の応答）→ fail" \
	1 200 "$obs"'{"heartbeat_age_seconds":120,"stats_age_seconds":300,"pgstattuple_age_seconds":"abc"}}'
run_case "系列値が負（クロックスキュー = 新鮮）→ green" \
	0 200 "$obs"'{"heartbeat_age_seconds":-5,"stats_age_seconds":300,"pgstattuple_age_seconds":3600}}'


echo
echo "result: pass=$pass fail=$fail"
[ "$fail" = "0" ]
