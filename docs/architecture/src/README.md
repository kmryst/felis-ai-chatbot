# 構成図の作図スクリプトと inventory

`docs/architecture/` の構成図（drawio）を生成するスクリプトと、図の元になった inventory を置く。
公開リポジトリに置く判断は [ADR-0033](../../adr/0033-architecture-diagram-source-in-public-repo.md)。

| ファイル | 内容 |
| --- | --- |
| `elements.py` | 共通定義。ノードのラベル・アイコン・大きさ、枠の名前、線の始点・終点・線種・目的のラベル・`[技術]` |
| `gen.py` | 図ごとの配置（座標、ラベルの位置、線の経路）。drawio を書き出す |
| `check_views.py` | 図 1・図 2 の線とラベルが全体図と一致するかの検査 |
| `inventory.md` | リソース一覧と接続関係（根拠の `ファイル:行`） |
| `architecture.drawio` | 全体図（図 1・図 2 の和。検証の正本） |

## 生成

```bash
python3 docs/architecture/src/gen.py
```

次の 3 つを書き出す。

- `docs/architecture/src/architecture.drawio`（全体図）
- `docs/architecture/architecture-request-flow.drawio`（図 1: チャットのリクエストの流れ）
- `docs/architecture/architecture-operations.drawio`（図 2: デプロイ・運用・監視・バックアップ）

引数にディレクトリを渡すと、3 つともそのディレクトリに書き出す（比較用）。
PNG は生成した drawio を draw.io で書き出す。

## 変更のしかた

- ラベル・アイコン・線の向き・`[技術]` を変えるときは `elements.py` を直す。全体図と図 1・図 2 に同時に反映される
- 配置を変えるときは `gen.py` の該当する図の関数だけを直す

## 検査

```bash
python3 docs/architecture/src/check_views.py \
  docs/architecture/src/architecture.drawio \
  docs/architecture/architecture-request-flow.drawio \
  docs/architecture/architecture-operations.drawio
```

不一致が 0 件なら終了コード 0、1 件以上なら 1、引数が足りなければ 2。
