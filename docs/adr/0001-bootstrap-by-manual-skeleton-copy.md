# 0001. idp-golden-path の service-baseline skeleton を手動コピーしてリポジトリを立ち上げる

## ステータス

Accepted

## 日付

2026-08-17

## 決定内容

`felis-ai-chatbot` のリポジトリを、[idp-golden-path](https://github.com/kmryst/idp-golden-path) の
ゴールデンパステンプレート **service-baseline** の skeleton
（`backstage/templates/service-baseline/skeleton/`）を**手動コピー**して立ち上げる。
Backstage / Scaffolder は起動しない。

- Backstage 固有の 3 ファイル（`catalog-info.yaml` / `mkdocs.yml` / `docs/index.md`）は除外する
- テンプレート変数（`${{ values.* }}`）は手動で置換する
- CI は `uses: kmryst/idp-golden-path/.github/workflows/<file>.yml@v1` のタグ参照で
  idp-golden-path の reusable workflow を消費し、ガードレールの正本を自リポジトリに持たない
  （idp-golden-path ADR-0008 の消費側規約に従う）

引き継いだ運用基盤:

- 軽運用 / 厳密運用を分ける GitHub Flow（`CONTRIBUTING.md`）
- 必須 4 ラベル（type / area / risk / cost）と `.github/labels.yml` による定義のコード管理
- CI ガードレール: PR Policy Check / Commitlint / Markdown Lint / Gitleaks Secret Scan / Sync Labels
- Issue / PR helper（`scripts/github/`）と PR / Issue テンプレート
- ADR 運用（`docs/adr/README.md`）と `.mise.toml` によるツールチェーン宣言

## 背景

本プロジェクトは 5 日間の短期開発で、PostgreSQL の Backup / Restore / Maintenance / Monitoring の
設計・実装・検証を主目的とする。運用ガードレール（Issue / PR 駆動・CI・ラベル）は初日から
有効にしたいが、その整備自体に時間を使うことは目的に反する。
idp-golden-path が確立済みの運用基盤を service-baseline テンプレートとして提供している。

## 検討した選択肢

### (a) 空リポジトリから手作業で立ち上げる（見送り）

- 長所: 制約なく自由に構成できる
- 短所: 既存リポジトリで確立済みの運用の再発明になり、抜け漏れが生じやすい

### (b) Backstage Scaffolder を起動してテンプレートから生成する（見送り）

- 長所: テンプレートの正規の消費経路であり、変数置換が自動で行われる
- 短所: Backstage の起動・設定のセットアップコストが 5 日制約に見合わない。
  生成結果は (c) と同一になる

### (c) skeleton を手動コピーし、テンプレート変数を手で置換する（採択）

- 長所: 生成結果は (b) と同一のまま、セットアップコストがゼロ
- 短所: 変数置換の手作業ミスの余地がある（ただし下記のとおり範囲が小さい）

## 採択理由

テンプレート変数は実測で 9 ファイル 25 箇所のみ（Backstage 固有 3 ファイルを除くと
6 ファイル 13 箇所）であり、手動置換が現実的な規模に収まる。
`.github/workflows/**` と `scripts/github/**` は `copyWithoutTemplating` 指定
（`template.yaml:86-88`）で変数を含まず無加工で使える。
Scaffolder 起動のセットアップコストは 5 日制約に見合わない。

Backstage 固有の 3 ファイルは、本リポジトリが Backstage の Software Catalog / TechDocs に
登録されないため除外した。

## 影響

- アプリケーションコードの技術選定（言語・フレームワーク・インフラ）は、実装着手時に新しい ADR として記録する
- branch protection は未適用の状態で立ち上がる。初回 CI 実行後に `docs/operations/branch-protection.md` の手順で適用する
- 生成元テンプレートが更新されても、本リポジトリへは自動反映されない。必要な場合は手動で追随する
- reusable workflow は `@v1` の移動タグ参照のため、idp-golden-path 側の v1 系更新に自動追随する

## 関連

- コピー元: [idp-golden-path — backstage/templates/service-baseline](https://github.com/kmryst/idp-golden-path/tree/main/backstage/templates/service-baseline)
- テンプレートの設計判断: [idp-golden-path ADR-0006](https://github.com/kmryst/idp-golden-path/blob/main/docs/adr/0006-scaffolder-service-baseline-template.md)
- reusable workflow のタグ運用: [idp-golden-path ADR-0008](https://github.com/kmryst/idp-golden-path/blob/main/docs/adr/0008-ci-guardrails-as-reusable-workflows-with-tag-pinning.md)
- Day 0 bootstrap の手順と検証証跡: [docs/operations/bootstrap.md](../operations/bootstrap.md)
