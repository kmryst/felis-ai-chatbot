#!/usr/bin/env bash
# /readyz 外形監視（readyz-probe.yml）の PROBE レコードを GitHub Actions のログから
# 抽出して JSONL に保全する（Issue #106 / #115 / §3-5 の TODO）。
#
# PROBE レコードは Actions のログの中にしか存在しない（artifact は 0 件、DB にも入らない）。
# ログ保持は 90 日で maximum_allowed_days も 90 のため延長できない。期間観測が終わったら
# 必ずこのスクリプトでリポジトリへ落としてから teardown する。
#
# 実行例:
#   scripts/collect-probe-records.sh \
#     --since 2026-08-23T08:16:19Z --until 2026-08-26T08:16:19Z \
#     --out docs/verification/observation-phase1/probe-records.jsonl
#
# 依存: bash / gh (認証済み) / jq
#
# 実装上の注意（いずれも実測で確認した罠。変更するときは理由を残すこと）:
#   1. run の列挙は `gh api --paginate`。`gh run list` は `--limit` が無いと 20 件で暗黙に
#      打ち切られ、母集団が黙って欠ける
#   2. ログ取得は REST `/repos/{owner}/{repo}/actions/jobs/{job_id}/logs`。
#      `gh run view --log` は failure run に対して 0 バイト（終了コード 0・エラー出力なし）を
#      返す。可用性 SLI で数えたい失敗レコードだけが黙って落ちるため使わない
#   3. 抽出は行頭アンカーを使わない。ログの行頭には
#      `probe<TAB>ステップ名<TAB>2026-...Z ` のプレフィクスが付くので `grep '^PROBE '` は
#      0 件になる。逆に `grep 'PROBE '` だと run ブロック内のコマンドエコー行まで拾って
#      二重計上する。`grep -aoE 'PROBE ts=[0-9][^\r]*'` で実レコードだけを 1 件ずつ取る
#   4. 集計対象は `event == "schedule"` のみ。`workflow_dispatch` の手動 probe を混ぜない

set -euo pipefail

usage() {
	cat <<'EOF'
Usage:
  collect-probe-records.sh \
    --since 2026-08-23T08:16:19Z \
    --until 2026-08-26T08:16:19Z \
    [--out path/to/records.jsonl]

Required:
  --since       窓の開始時刻（ISO 8601 UTC）。run の created_at がこれ以上
  --until       窓の終了時刻（ISO 8601 UTC）。run の created_at がこれ未満

Optional:
  --out         出力先 JSONL（省略時は標準出力）
  --repo        owner/repo（省略時は gh の既定リポジトリ）
  --workflow    workflow ファイル名（既定: readyz-probe.yml）
  --event       run の event フィルタ（既定: schedule）

Notes:
  - 窓は [since, until) の半開区間。72h 窓を隣り合わせても run が重複しない
  - 1 run につき 1 行。PROBE レコードが取れなかった run も ts=null の行として出力し、
    レコード取得率の分母を保つ
EOF
}

die() {
	printf 'Error: %s\n' "$1" >&2
	exit 1
}

since=""
until_=""
out=""
repo=""
workflow="readyz-probe.yml"
event="schedule"

while [[ $# -gt 0 ]]; do
	case "$1" in
	--since)
		[[ $# -ge 2 ]] || die "--since requires a value"
		since="$2"
		shift 2
		;;
	--until)
		[[ $# -ge 2 ]] || die "--until requires a value"
		until_="$2"
		shift 2
		;;
	--out)
		[[ $# -ge 2 ]] || die "--out requires a value"
		out="$2"
		shift 2
		;;
	--repo)
		[[ $# -ge 2 ]] || die "--repo requires a value"
		repo="$2"
		shift 2
		;;
	--workflow)
		[[ $# -ge 2 ]] || die "--workflow requires a value"
		workflow="$2"
		shift 2
		;;
	--event)
		[[ $# -ge 2 ]] || die "--event requires a value"
		event="$2"
		shift 2
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		usage >&2
		die "Unknown argument: $1"
		;;
	esac
done

[[ -n $since ]] || { usage >&2; die "--since is required"; }
[[ -n $until_ ]] || { usage >&2; die "--until is required"; }

command -v gh >/dev/null || die "gh is required"
command -v jq >/dev/null || die "jq is required"

if [[ -z $repo ]]; then
	repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

# 1. run の列挙。--paginate が必須（gh run list の 20 件打ち切りを踏まない）
runs_json="$(mktemp)"
trap 'rm -f "$runs_json"' EXIT

gh api --paginate \
	-H "Accept: application/vnd.github+json" \
	"repos/$repo/actions/workflows/$workflow/runs?per_page=100&event=$event" \
	-q '.workflow_runs[] | {run_id: .id, created_at: .created_at, conclusion: .conclusion, status: .status, attempt: .run_attempt, head_sha: .head_sha}' \
	| jq -c --arg since "$since" --arg until "$until_" \
		'select(.created_at >= $since and .created_at < $until)' \
	| jq -sc 'sort_by(.created_at) | .[]' \
	>"$runs_json"

run_count="$(wc -l <"$runs_json" | tr -d ' ')"
printf 'collect-probe-records: repo=%s workflow=%s event=%s window=[%s, %s) runs=%s\n' \
	"$repo" "$workflow" "$event" "$since" "$until_" "$run_count" >&2

emit() {
	if [[ -n $out ]]; then
		cat >>"$out"
	else
		cat
	fi
}

if [[ -n $out ]]; then
	: >"$out"
fi

# 抽出パターン。$'\r' で実際の CR を埋め込む（grep -E の [] 内では
# バックスラッシュ表記が展開されず、[^\r] が「r 以外」になって途中で切れる）
probe_pattern=$'PROBE ts=[0-9][^\r]*'

processed=0
while IFS= read -r run; do
	run_id="$(jq -r '.run_id' <<<"$run")"

	# 2. job id を取る（ログ取得は job 単位の REST エンドポイントのみを使う）
	job_id="$(gh api "repos/$repo/actions/runs/$run_id/jobs" \
		-q '.jobs[] | select(.name == "probe") | .id' 2>/dev/null | head -n 1)"

	probe_lines=""
	if [[ -n $job_id ]]; then
		# 3. failure run でも取れるのはこの REST 経路だけ。行頭アンカーを使わずに
		#    実レコードだけを抜く
		probe_lines="$(gh api "repos/$repo/actions/jobs/$job_id/logs" 2>/dev/null \
			| grep -aoE "$probe_pattern" || true)"
	fi

	if [[ -z $probe_lines ]]; then
		jq -c --argjson job "${job_id:-null}" '
			{run_id, created_at, conclusion, status, attempt, head_sha,
			 job_id: $job, ts: null, code: null, latency_ms: null, obs: null,
			 marker_age: null, stats_age: null, pgstattuple_age: null, enforce: null}' \
			<<<"$run" | emit
	else
		while IFS= read -r line; do
			jq -c --argjson job "${job_id:-null}" --arg line "$line" '
				def num: if . == null or . == "null" then null else (tonumber? // .) end;
				($line | ltrimstr("PROBE ") | [splits(" +")]
					| map(capture("^(?<k>[^=]+)=(?<v>.*)$"))
					| map({(.k): .v}) | add) as $f
				| {
					run_id, created_at, conclusion, status, attempt, head_sha,
					job_id: $job,
					ts: ($f.ts // null),
					code: ($f.code // null),
					latency_ms: ($f.latency_ms | num),
					obs: ($f.obs // null),
					marker_age: ($f.marker_age | num),
					stats_age: ($f.stats_age | num),
					pgstattuple_age: ($f.pgstattuple_age | num),
					enforce: ($f.enforce // null)
				}' <<<"$run" | emit
		done <<<"$probe_lines"
	fi

	processed=$((processed + 1))
	if ((processed % 25 == 0)); then
		printf 'collect-probe-records: %s/%s runs\n' "$processed" "$run_count" >&2
	fi
done <"$runs_json"

printf 'collect-probe-records: done (%s runs)\n' "$processed" >&2
