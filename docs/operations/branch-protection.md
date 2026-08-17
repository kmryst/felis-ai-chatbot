# main ブランチ保護設定

`main` ブランチの branch protection の適用手順と設定内容の正本です。
GitHub リポジトリ設定は Terraform 管理していないため、このドキュメントを設定内容の正本として扱い、変更時は必ず同じ PR で更新します。

> **注意**: このリポジトリは idp-golden-path の service-baseline テンプレートから生成された直後は
> branch protection が**未適用**です。required status checks は各 workflow の初回実行前に設定すると
> PR を恒久的にブロックし得るため、最初の PR で CI（下記 4 check）の実行実績を作ってから適用してください。
> また、private リポジトリでは GitHub のプランによって branch protection が利用できない場合があります。

## 適用する設定

| 項目 | 値 |
| --- | --- |
| required status checks | `pr-policy-check / PR Policy Check` / `commitlint / Commitlint` / `markdown-lint / Markdown Lint` / `gitleaks / Gitleaks Secret Scan` |
| strict（Require branches to be up to date） | false |
| enforce_admins | true |
| required_approving_review_count | 0 |
| require_code_owner_reviews | false |
| allow_force_pushes | false |
| allow_deletions | false |
| required_linear_history | false |
| required_conversation_resolution | true |

- 少人数運用のため approving review は必須にしない。品質ゲートは required status checks と PR 作成前の計画確認で担保する
- CI ガードレールは kmryst/idp-golden-path の reusable workflows をタグ固定（`@v1`）で呼び出しているため、
  check run 名は `<caller job name> / <called job name>`（例: `pr-policy-check / PR Policy Check`）になる。
  required status checks の名称はこの合成名と一致させる必要がある。
  caller job には `name:` を付けず job id にフォールバックさせている（callee と同名にすると
  `PR Policy Check / PR Policy Check` のように文字列がそのまま重複しコピペミスに見える。
  idp-golden-path#106 参照）。caller 側の job name か reusable workflow 側の job name を
  変える場合は、必ずこの設定も同じタイミングで更新する

## 適用コマンド

```bash
gh api -X PUT repos/kmryst/felis-ai-chatbot/branches/main/protection \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": false,
    "checks": [
      { "context": "pr-policy-check / PR Policy Check" },
      { "context": "commitlint / Commitlint" },
      { "context": "markdown-lint / Markdown Lint" },
      { "context": "gitleaks / Gitleaks Secret Scan" }
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false,
  "required_conversation_resolution": true
}
EOF
```

## 確認コマンド

```bash
gh api repos/kmryst/felis-ai-chatbot/branches/main/protection | jq '{
  checks: .required_status_checks.checks,
  strict: .required_status_checks.strict,
  enforce_admins: .enforce_admins.enabled,
  reviews: .required_pull_request_reviews.required_approving_review_count,
  force_pushes: .allow_force_pushes.enabled,
  deletions: .allow_deletions.enabled
}'
```

## 変更時の注意

- 存在しない check 名を required に指定すると、PR が永久にマージ不能になる。指定前に PR 上で実際の check run 名を確認する
- Dependabot PR でも caller workflow は reusable workflow を必ず呼び出す。called workflow の job も常に起動し、PR 作成者が
  `dependabot[bot]` の場合は検査 step を実行せず、免除理由を記録する step を実行して `Success` で終了する
- caller job や called workflow の job 全体に Dependabot の除外条件を置くと、branch protection が要求する check が作成されないか、
  `Skipped` として表示される。除外条件は called workflow 内の個々の step だけに置く
- 一時的に保護を外す操作（`gh api -X DELETE .../protection`）は、必ずユーザーの明示的な許可を得てから行う
