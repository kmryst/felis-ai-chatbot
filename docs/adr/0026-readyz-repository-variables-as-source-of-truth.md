# ADR-0026: readyz probe の実行設定を repository variables に一本化する

## ステータス

Accepted

## 日付

2026-08-30

## 決定内容

`.github/workflows/readyz-probe.yml` の実行時設定 `PROBE_ENABLED` / `READYZ_URL` /
`OBS_FRESHNESS_ENFORCE` は、GitHub repository variables を唯一の正本とする。workflow 内には
fallback や環境固有 URL を持たせず、3 変数を必須として直接参照する。

workflow は curl や停止判定より前に全変数を検証する。2 つのスイッチは小文字の `true` / `false`、
URL は `https://<host>/readyz` だけを許可し、未設定・不正値は fail-closed にする。
`PROBE_ENABLED=false` は従来どおり probe 全体の正常停止、
`OBS_FRESHNESS_ENFORCE=false` は probe と SLI 記録を継続したまま鮮度ゲートだけを止める。

`READYZ_URL` は `terraform/ephemeral` の安定 FQDN output `container_app_fqdn` から組み立てる。
CAE と DB を再作成する場合は、probe 停止 → apply → 新 URL の DB 到達性検証 → repository variable
更新 → Alembic migration 成功 → `/readyz` の `.obs` 契約検証 → probe 再開の順序を守る。

## 背景

変更前は、3 変数が「YAML 内の既定値 + 任意の repository variable 上書き」だった。
2026-08-30 の変更前確認では repository variables は 0 件で、実効値はすべて YAML の fallback から
供給されていた。

この構成には次の問題がある。

- YAML と GitHub 設定の 2 箇所が値の供給元になり、上書きが存在すると YAML の更新が実行時に
  反映されない。特に CAE 再作成後の `READYZ_URL` は古い値が見えにくく残り得る
- 未登録の `vars.*` を GitHub Actions エディタ拡張が repository 情報から解決できず、正しい
  fallback 式にも `Context access might be invalid` 警告が出る
- fallback だけを削除すると、未設定の `PROBE_ENABLED` は空文字になる。既存の
  `if [ "$PROBE_ENABLED" != "true" ]` では正常停止として exit 0 になり、probe が無音で止まる
- 同様に、未設定の鮮度ゲート変数はゲート無効として扱われ、fail-open になる

したがって、警告だけを隠すのではなく設定の正本を一本化し、正本の欠落を明示的な workflow failure にする。

## 検討した選択肢

### 1. repository variables を必須の正本にする（採択）

teardown の停止スイッチ、障害対応時の鮮度ゲート非常口、環境再作成で変わり得る URL をコード変更なしで
操作できる。workflow 側には必須項目の名前・型・検証を残すため、設定の契約は version control と
テストでレビューできる。

値自体は GitHub 側の設定になるため、移行・再作成・ロールバックの順序を運用手順に固定する必要がある。

### 2. YAML の既定値と任意上書きを維持する（却下）

未設定でも動く利点はあるが、2 つの値供給元と URL drift の余地が残る。警告解消のために同じ値を
repository variables へ登録すると、まさに同値の二重管理になる。

### 3. YAML だけを正本にして repository variables を廃止する（却下）

警告と二重管理は消えるが、teardown 前の probe 停止や障害対応時の鮮度ゲート停止にコード変更が必要になる。
5 分間隔の外形監視に必要な運用スイッチとして不適切である。

### 4. 式を難読化してエディタの静的検証だけを回避する（却下）

実行時設定の構造は変わらず、可読性と静的検証能力だけを落とす。設定欠落の検出にもならない。

## 採択理由

この3値は versioned なアプリケーション定数ではなく、外形監視の運用状態とデプロイ先を表す。
repository variables はその変更頻度と操作主体に合う。一方、値が GitHub 側にあるだけでは削除や誤記を
検知できないため、必須性と型を workflow 冒頭で fail-closed にし、テストで curl より先に失敗することを
固定する。この組み合わせなら、操作可能性を保ちながら無音停止を防げる。

## 影響

- merge 前に現在の実効値と同じ3変数を登録する。現行 workflow は同じ値を上書きとして読むため、
  この段階では挙動を変えない
- 新規環境や変数削除時は workflow が失敗する。初期設定漏れを green にしない意図した挙動である
- `ENFORCE` という job env alias は廃止し、`OBS_FRESHNESS_ENFORCE` に統一する。機械可読ログの
  `enforce=` field 名は既存集計との互換性のため維持する
- Phase 1 の実測記録は当時 repository variables が 0 件だった証跡なので書き換えない
- rollback は workflow の fallback を先に復元する。repository variables を先に削除すると、変更後
  workflow が5分ごとに失敗するため順序を逆にしない

## 関連

- Issue #175 — 本決定の実装
- Issue #106 — `/readyz` 外形監視の導入
- Issue #116 — 鮮度ゲートの自動発動と通常時有効化
- Issue #135 — revision 固有でない安定 FQDN output
- Issue #141 — 旧 `ENFORCE` alias と repository variable 名の対応記録
- [外形監視を含む実行計画](../operations/credit-window-execution-plan.md)
- [VNet 統合 cutover 手順](../operations/vnet-integration-cutover.md)
