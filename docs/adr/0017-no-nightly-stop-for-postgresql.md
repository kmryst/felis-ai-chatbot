# ADR-0017: PostgreSQL Flexible Server を夜間 stop しない（常時稼働に変える）

## ステータス

Accepted

## 日付

2026-08-21

## 決定内容

- [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §3-6 / §4-8 の「Day 3 / Day 4 の終業時に `az postgres flexible-server stop`」をやめ、`pgsql-felisaichatbot-dev`（B1ms）を**常時稼働**させる
- ephemeral 層の毎日 destroy（時間課金を止める運用）は変えない（注記: この前提はその後の private access 化で変更された。夜間 destroy をやめ、destroy は Day 5 の最終 teardown のみ。[ADR-0018 追記](./0018-postgresql-private-access-and-vnet-integration.md)）
- 750 時間の無料枠管理（消費状況の確認手段・リスク・未確定事項）は [azure-resource-inventory.md](../operations/azure-resource-inventory.md) の「12か月無料枠」節を正本とする

## 背景

計画書は当初「使っていない時間帯は課金を止める」（§8）の一環として夜間 stop を置いていた。その唯一の根拠だった**コスト削減が、12 か月無料枠の判明で消えた**。

- 12 か月無料枠に「**750 hours of Flexible Server—Burstable B1MS Instance, 32 GB storage, and 32 GB backup storage**」が含まれる（出典: <https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account> ）
- この枠は **$200 クレジット期間中も適用される**: 「As long as you have unexpired credit or you use only free services within the limits, you're not charged.」（出典: <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account> ）
- 24 時間 × 31 日 = **744 時間 < 750 時間**。B1ms 1 台なら常時稼働でも無料枠内

一方で stop には実害がある。

- **停止中は新規バックアップが取得されない**（「No new backups are performed for stopped servers」。計画書 §2-1 No.6）。本プロジェクトの主成果物は PostgreSQL の Backup / PITR であり（計画書 §0）、**その材料（スナップショット + WAL の蓄積）を毎晩減らす運用は本末転倒**
- 停止中もストレージ + バックアップストレージの課金は継続する（同 No.6。ただし無料枠内）。つまり stop で消えるのはコンピュート課金だけで、それが無料枠内なら stop の得は 0 になる
- **停止後 7 日で自動起動する**（同 No.8）。stop 前提の運用はもともと「止めたまま放置してよい」状態を作れず、管理コストだけが残る

## 検討した選択肢

1. **夜間 stop をやめて常時稼働（採択）**
2. stop を継続（却下: 上記のとおり得るものが 0 になり、失うもの — バックアップ蓄積の連続性・stop / start の運用手数 — だけが残る）
3. 「停止中のバックアップ挙動を実測する」目的で stop を継続（却下: 停止中挙動は公式明文（§2-1 No.6）を計画書に記録済みで、実地裏取りの成果物価値より PITR ドリルの材料の連続性が優先。§2-2 No.3 の実測項目は「取りやめ」と明示して計画書に残す）

## 750 時間の管理（採択に伴う新しい義務）

無料だから無管理でよい、にはならない。

- **Day 4 の PITR ドリルでは復元先としてもう 1 台の B1ms が一時的に立つ**（計画書 §4-3）。2 台分の稼働時間が合算されるなら当月 750 時間を超え得る。超えた場合も**超過分はクレジットから引かれるだけで実支出は $0**（クレジット失効 2026-09-18 まで）
- **未確定事項**（公式に明文を確認できておらず、「確定」として扱わない）: 複数台稼働時に 750 時間が合算されるのか / 停止中の時間が 750 時間を消費するか / 「32 GB」の GB / GiB の厳密解釈
- 消費状況の確認手段と初回確認の宿題（2026-08-23 頃。課金データの反映遅延 1〜2 日を見込む）は計画書 §8 と台帳に記録した
- **無料枠は 2027-08 頃に終了する**（サインアップ 2026-08-19 から 12 か月）。それ以前に従量課金へアップグレードしない場合、クレジット失効（2026-09-18）でサブスクリプションごと無効化される（台帳の「従量課金へのアップグレード」節）

## 影響

- 計画書の改訂: §1（Day 3 行）/ §2-2 No.3（取りやめ）/ §3-3 / §3-6 / §4-1 / §4-8 / §6（成果物 3）/ §8
- [restore-drill/observations.md](../verification/restore-drill/observations.md) の「Day 4 に取る差分（宿題）」は stop 前提だったため取りやめの注記を追記
- Day 5 終了時の destroy（計画書 §5-6）は不変。本 ADR は「日々の運用」の話であり、「プロジェクト終了時」の話ではない（時間軸の区別は台帳 §A）

## 関連

- [ADR-0011](./0011-backup-retention-and-geo-redundancy.md) — バックアップ設計（本 ADR はその材料の蓄積を守る）
- [ADR-0016](./0016-log-analytics-workspace-in-persistent-layer.md) — 同時に行った persistent 層の整備
- [azure-resource-inventory.md](../operations/azure-resource-inventory.md) — 無料枠・750 時間管理の正本
- [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §2-1 No.6 / No.8（stop の実害の出典）
- Issue: #76
