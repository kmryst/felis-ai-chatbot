#!/usr/bin/env bash

set -euo pipefail

usage() {
	cat <<'EOF'
Usage:
  create-issue-with-labels.sh \
    --title "Issue title" \
    --body-file path/to/body.md \
    --type type:feature \
    --area area:backstage \
    --risk risk:low \
    --cost cost:none

Required:
  --title       Issue title
  --body-file   Markdown body file passed to gh issue create
  --type        Exactly one type:* label
  --area        One or more area:* labels
  --risk        Exactly one risk:* label
  --cost        Exactly one cost:* label

Notes:
  - Repeat --area for multiple area labels.
  - The script applies required labels at issue creation time.
EOF
}

# shellcheck source=scripts/github/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

title=""
body_file=""
type_label=""
risk_label=""
cost_label=""
declare -a area_labels=()

while [[ $# -gt 0 ]]; do
	case "$1" in
	--title)
		[[ $# -ge 2 ]] || die "--title requires a value"
		title="$2"
		shift 2
		;;
	--body-file)
		[[ $# -ge 2 ]] || die "--body-file requires a value"
		body_file="$2"
		shift 2
		;;
	--type)
		[[ $# -ge 2 ]] || die "--type requires a value"
		type_label="$2"
		shift 2
		;;
	--area)
		[[ $# -ge 2 ]] || die "--area requires a value"
		area_labels+=("$2")
		shift 2
		;;
	--risk)
		[[ $# -ge 2 ]] || die "--risk requires a value"
		risk_label="$2"
		shift 2
		;;
	--cost)
		[[ $# -ge 2 ]] || die "--cost requires a value"
		cost_label="$2"
		shift 2
		;;
	--help | -h)
		usage
		exit 0
		;;
	*)
		die "Unknown argument: $1"
		;;
	esac
done

[[ -n $title ]] || die "--title is required"
[[ -n $body_file ]] || die "--body-file is required"
[[ -f $body_file ]] || die "Body file not found: $body_file"
validate_required_labels "$type_label" "$risk_label" "$cost_label" "${area_labels[@]}"

create_args=(
	issue create
	--title "$title"
	--body-file "$body_file"
	--label "$type_label"
	--label "$risk_label"
	--label "$cost_label"
)

for area_label in "${area_labels[@]}"; do
	create_args+=(--label "$area_label")
done

issue_url=$(gh "${create_args[@]}")
issue_number="${issue_url##*/}"

printf 'Created issue #%s\n%s\n' "$issue_number" "$issue_url"

