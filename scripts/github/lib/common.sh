#!/usr/bin/env bash
# scripts/github/*.sh の共通関数。
# 各スクリプトから `source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"` で読み込む。

die() {
	printf 'Error: %s\n' "$1" >&2
	exit 1
}

require_prefix() {
	local value="$1"
	local prefix="$2"

	if [[ $value != "$prefix"* ]]; then
		die "Expected label '$value' to start with '$prefix'"
	fi
}

# type/risk/cost/area ラベルの共通バリデーション
# 使い方: validate_required_labels "$type_label" "$risk_label" "$cost_label" "${area_labels[@]}"
validate_required_labels() {
	local type_label="$1"
	local risk_label="$2"
	local cost_label="$3"
	shift 3

	[[ -n $type_label ]] || die "--type is required"
	[[ $# -ge 1 ]] || die "At least one --area is required"
	[[ -n $risk_label ]] || die "--risk is required"
	[[ -n $cost_label ]] || die "--cost is required"

	require_prefix "$type_label" "type:"
	require_prefix "$risk_label" "risk:"
	require_prefix "$cost_label" "cost:"

	local area_label
	for area_label in "$@"; do
		require_prefix "$area_label" "area:"
	done
}

# Issue 本文のテンプレート検証（issue-template-check と同条件のローカル版）
# 必須見出し（## または ###、完全一致）と中身が空でないことを検証する。
# 検査ロジックの正本は idp-golden-path の reusable workflow（@v1）側。
# 使い方: validate_issue_body_template path/to/body.md
validate_issue_body_template() {
	local body_file="$1"
	local heading
	local missing=""

	for heading in "目的" "対象" "受け入れ条件"; do
		if ! awk -v h="$heading" '
			$0 ~ ("^##(#)?[ \t]+" h "[ \t]*$") { insec = 1; next }
			insec && /^##(#)?[ \t]+/ { insec = 0 }
			insec && NF > 0 { found = 1 }
			END { exit found ? 0 : 1 }
		' "$body_file"; then
			missing="${missing} ${heading}"
		fi
	done

	if [[ -n $missing ]]; then
		die "Issue body is missing required non-empty headings:${missing} (## or ###). Template: docs/issue-templates/feature_request.md"
	fi
}
