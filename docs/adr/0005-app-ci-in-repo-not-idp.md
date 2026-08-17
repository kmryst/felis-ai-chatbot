# ADR-0005: アプリケーション層の CI は本リポジトリに置き、idp-golden-path へ共通化しない

## ステータス

Accepted

## 日付

2026-08-17

## 決定内容

- ガバナンス層の CI は、これまでどおり [idp-golden-path](https://github.com/kmryst/idp-golden-path) の
  reusable workflow を `@v1` タグ固定で消費する（ADR-0001 / idp-golden-path ADR-0008）
- **アプリケーション層（build / test / lint）の CI は本リポジトリに置く。**
  idp-golden-path 側への reusable workflow 化はしない

### 境界の定義

| 層 | 置き場所 | 内容 |
| --- | --- | --- |
| ガバナンス層（共有） | idp-golden-path | どのリポジトリでも同じであるべきもの。PR Policy Check / Commitlint / Markdown Lint / Gitleaks / Toolchain Version Check / Issue Template Check / Sync Labels |
| アプリケーション層（固有） | 本リポジトリ | このアプリだから必要なもの。backend のテスト実行（`backend-tests.yml`）、frontend の lint / 型検査 / ビルド（`frontend-checks.yml`）、pgvector のサービスコンテナ、Python / Node のセットアップ |

## 背景

`backend-tests.yml` に続いて frontend 用の CI（ESLint / `tsc --noEmit` / `next build`）を
追加するにあたり、「アプリの CI も idp-golden-path の reusable workflow にすべきではないか」が
論点になった。後から見返したときに迷う点なので、しない判断とその根拠を記録する。

## 検討した選択肢

1. **アプリケーション層の CI は本リポジトリに置く**（採択）
2. アプリケーション層の CI も idp-golden-path の reusable workflow として共通化し、`@v1` で消費する

## 採択理由

1. **consumer が 1 つしかない抽象化を避ける。** kmryst 配下の他 3 リポジトリ
   （idp-golden-path / terraform-hannibal / ticket-c2c-platform）は Terraform / AWS 構成で、
   Python も Next.js も使っていない。N=1 での共通化は利益がなく管理コストだけが増える
2. **開発速度。** 共通化すると CI を 1 行直すたびに idp-golden-path への PR → マージ → タグ →
   参照バージョン更新という 2 リポジトリ往復が発生する。5 日開発では致命的
3. **開始方法の判断（ADR-0001）との一貫性。** 本リポジトリは「新規サービス側だけの変更で完結できること」
   「idp-golden-path 本体に変更を要さないこと」を評価軸に選定された。アプリ CI を IDP に置くと
   その判断を自ら崩すことになる
4. idp-golden-path の reusable workflow 群は言語・クラウド非依存のガバナンス層として設計されている
   （idp-golden-path ADR-0008）。アプリ CI はその設計意図から外れる

## 却下理由

- 選択肢 2: 上記 1〜4 の裏返し。現時点では共通化の受益者が存在せず、変更コストだけが増える

## 影響

- `backend-tests.yml` / `frontend-checks.yml` の正本は本リポジトリであり、変更は本リポジトリの PR で完結する
- これらの check は branch protection の required status checks に**追加しない**。
  path filter 付き workflow を required にすると、該当パスに触れない PR で check が作成されず
  PR を恒久的にブロックするため（`docs/operations/branch-protection.md` / idp-golden-path ADR-0006）
- **将来 IDP に昇格させる条件**: 2 つ目の Python / Next.js サービスが生まれ、実際に重複が発生したとき。
  N=1 では抽象化しない

## 関連

- Issue: #26
- ADR-0001（skeleton 手動コピーによる立ち上げ・reusable workflow の消費側規約）
- ADR-0004（CI から実 LLM を呼ばない）
- idp-golden-path ADR-0006（required status checks と path filter の相互作用）
- idp-golden-path ADR-0008（ガバナンス層 reusable workflow の設計意図）
