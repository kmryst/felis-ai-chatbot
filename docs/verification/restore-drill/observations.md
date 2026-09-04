# バックアップ観測記録（restore drill 用）

[day3-5-execution-plan.md](../../operations/day3-5-execution-plan.md) §3-3 の観測記録。時刻はすべて UTC。
コマンドと生の出力をそのまま残し、Day 4 起動後の同一コマンドとの差分で
「停止中は新規バックアップなし・保持分課金は継続」（§2-1 No.6）が実地でどう見えるかを確かめる。

## Day 3: サーバー作成直後（2026-08-21）

### 前提（この観測の基準点）

- `terraform -chdir=terraform/persistent apply` 実行: 2026-08-21T05:52:14Z 開始 → 2026-08-21T05:59:12Z 完了（`Apply complete! Resources: 3 added, 0 changed, 0 destroyed.`）
- サーバー本体（`pgsql-felisaichatbot-dev`）の作成所要は 5m32s。`state: Ready` を 05:56:10Z に確認
- **作成直後（05:56〜05:57 頃）の `az postgres flexible-server show` では `backup.earliestRestoreDate` は `null` だった**。下記 05:59:12Z の観測では値が入っている。「作成直後は null で、Ready から数分内に初回スナップショット由来の値が入る」という遷移として記録する（初回フルスナップショットの完了タイミングの実測。§2-2 の未実測項目に対応）

### §3-3 コマンドと生出力（2026-08-21T05:59:12Z）

```console
$ az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
    --query "{state: state, earliestRestoreDate: backup.earliestRestoreDate, retention: backup.backupRetentionDays, geo: backup.geoRedundantBackup}" -o json
{
  "earliestRestoreDate": "2026-08-21T05:59:00.967587+00:00",
  "geo": "Disabled",
  "retention": 7,
  "state": "Ready"
}

$ az monitor metrics list \
    --resource "$(az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev --query id -o tsv)" \
    --metric backup_storage_used --interval PT1H -o table
Timestamp             Name                 Average
--------------------  -------------------  ---------
2026-08-21T04:59:00Z  Backup Storage Used  2861497.0
```

- `earliestRestoreDate = 2026-08-21T05:59:00Z`: 復旧ウィンドウの左端がサーバー作成直後に開いた。Day 4 の PITR ドリルはこの時刻以降の任意時刻を指定できる
- `Backup Storage Used = 2,861,497 bytes（約 2.7 MiB）`: 初回スナップショット直後の実測値。無料枠（プロビジョン済みストレージと同量の 32 GiB。ADR-0011）に対し無視できる規模
- メトリックの Timestamp `04:59:00Z` は `--interval PT1H` の集計バケット開始時刻であり、観測時刻（05:59:12Z）の直近 1 時間バケットを指す

### Day 4 に取る差分（宿題）

- stop 中に `earliestRestoreDate` が動くか（保持ウィンドウの左端が進むか）
- stop 中の `backup_storage_used` の推移（新規バックアップなし・保持分課金は継続、が数値でどう見えるか）
- 起動後に同じ 2 コマンドを再実行し、本節の生出力と並べて記録する

> **注記（2026-08-21 追記）**: 夜間 stop の運用は [ADR-0017](../../adr/0017-no-nightly-stop-for-postgresql.md) で廃止した（停止中は新規バックアップが取得されず、主成果物 Backup / PITR の材料を減らすため。12か月無料枠の判明でコスト根拠も消えた）。このため上記の stop 前提の差分観測は**取りやめ**る。Day 4 朝は、連続稼働中の推移として同じ 2 コマンドを記録する（計画書 §4-1）。

## フェーズ 1: `earliestRestoreDate` のベースライン時系列（2026-08-24 開始）

計画 [credit-window-execution-plan.md](../../operations/credit-window-execution-plan.md) §3 の項目 4
（「**8/29 頃に保持 7 日の窓が満杯になり `earliestRestoreDate` が動き出す**。この窓がスライドし始める
瞬間自体が時間でしか取れない観測」）のための記録。**窓が動き出す前の値を残すこと自体が目的**なので、
値が変わらなくても毎日 1 行追記する。

取得コマンド（毎回これを実行して、生の値をそのまま貼る）:

```bash
az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --query "{earliest: backup.earliestRestoreDate, retention: backup.backupRetentionDays, state: state}" -o json
```

| 取得時刻 (UTC) | `earliestRestoreDate` | 復元ウィンドウの幅 | retention | state | 備考 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-22T07:16:21Z（作成直後） | `2026-08-22T07:16:21.309783+00:00` | 0 | 7 | Ready | VNet 統合カットオーバーで再作成した新サーバーの起点（[vnet-cutover/observations.md](../vnet-cutover/observations.md) ステップ A） |
| **2026-08-24T05:50:40Z** | `2026-08-22T07:16:21.309783+00:00` | **約 46.6 時間** | 7 | Ready | **未だ動いていない**（保持 7 日の窓が満杯でないため。左端はサーバー作成時刻に固定） |

- **窓が動き出す予測**: サーバー作成 2026-08-22T07:16:21Z + 7 日 = **2026-08-29T07:16Z 頃**。
  以降は `earliestRestoreDate` が「現在時刻 − 7 日」を追って毎日スライドし始めるはず（**未検証の予測**）。
  → **2026-09-04 の PITR ドリルで反証された。連続スライドではなく、日次 Full backup の完了に合わせて
  約 24 時間ずつジャンプする鋸歯状の動きだった**（[pitr-drill-custom-restore.md](./pitr-drill-custom-restore.md) 知見 4）
- 予測日 8/29 はフェーズ 2a（高負荷 × B1ms。8/29〜8/30 目安）の初日にあたる。
  **スライド開始の瞬間を取り逃さないよう、8/28〜8/30 は取得頻度を上げる**（日次 → 数時間おき）
- PITR ドリル 1 回目（8/28 目安）はこの窓がまだ「作成時刻に固定」の状態で行われる。
  2 回目（9/2 目安）はスライド後の窓に対して 24 時間以上前へ復元する（計画 §2）

### `backup_storage_used` の推移（同じ観測の一部。計画 §3 の 5）

```bash
az monitor metrics list \
  --resource "$(az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev --query id -o tsv)" \
  --metric backup_storage_used --interval PT1H \
  --start-time <開始> --end-time <終了> --aggregation Average -o tsv
```

> **`--end-time` を必ず指定する**。未指定だと未来時刻のバケットに 0.0 のフィラーが入り、
> 「急に 0 に落ちた」ように見える偽データになる（実測済みの罠）。

| バケット開始 (UTC) | Backup Storage Used (bytes) | 備考 |
| --- | --- | --- |
| 2026-08-21T04:59:00Z | 2,861,497 | 旧サーバー作成直後（本ファイル冒頭の Day 3 記録） |
| 2026-08-22T06:00:00Z | 670,490,035 | **旧サーバー。作成の約 24 時間後に約 0.67 GB へ跳ねている** |
| 2026-08-22T08:00:00Z | 4,574,939 | 新サーバー（07:16:21Z 作成）の初回スナップショット |
| 2026-08-23T06:00:00Z | 10,399,932 | 約 250 KB/時で緩やかに増加 |
| **2026-08-23T07:00:00Z** | **780,465,161** | **ステップの開始** |
| **2026-08-23T08:00:00Z** | **1,330,588,404** | **約 1.24 GiB。10.4 MB からの約 128 倍のジャンプ** |
| 2026-08-24T05:00:00Z | 1,337,400,551 | ステップ後は再び約 330 KB/時（≒ 7.9 MB/日）の緩やかな増加 |

取得時刻: 2026-08-24T06:00:38Z / 2026-08-24T06:01:20Z。

- **観測された規則性**: 旧サーバー（作成 8/21 05:59Z → 8/22 06:00Z に 0.67 GB）も
  新サーバー（作成 8/22 07:16Z → 8/23 07:00Z に 0.78 GB → 08:00Z に 1.33 GB）も、
  **作成の約 24 時間後に数百 MB 〜 1.3 GB のステップ**が入っている。初回フルスナップショット後の
  最初のスケジュール済みフルバックアップに相当すると考えられるが、**周期が日次か週次かは未検証**
  （観測点が 2 回しかない。8/24T07:00Z 以降のバケットを見れば判別できる）
- ステップは obs スキーマ作成（8/23 07:15Z の migration）より**前の 07:00 バケットから始まっている**ため、
  観測用テーブルの追加が原因ではない
- 無料枠（プロビジョン済みストレージと同量の 32 GB。ADR-0011）に対して **1.34 GB = 約 4%**。
  ステップが日次で入るとしても teardown（9/4 目安）まで 12 回で約 16 GB と枠内だが、
  **8/24〜8/25 の推移で周期を確定させる**
- geo 冗長バックアップ（ADR-0019、`geoRedundantBackup: Enabled`）分がこのメーターに含まれるかは**未検証**

## フェーズ 2: PITR ドリル本体（2026-09-04 開始）

実測記録は別ファイルに分けている。本ファイルはバックアップ状態の時系列観測、別ファイルは復元そのものの実測。

| ドリル | 記録 | 状態 |
| --- | --- | --- |
| 1 回目: custom restore（任意時刻 + WAL 再生） | [pitr-drill-custom-restore.md](./pitr-drill-custom-restore.md) | **完了**（2026-09-04） |
| 2 回目: fast restore（最新 Full backup 起点） | 未作成 | **未実施**（2026-09-05 の日次 Full backup 完了後に実施予定） |

1 回目で本ファイルの記録に対して確定した事項:

- 上記フェーズ 1 の「毎日スライドし始めるはず」という予測は**反証された**。
  `earliestRestoreDate` は保持ウィンドウ内の**最古スナップショットの `completedTime` とマイクロ秒まで一致**し、
  毎朝 07:2xZ の日次 Full backup 完了に合わせて約 24 時間ジャンプする**鋸歯状**の動きをする
- 実測ウィンドウ幅は 2026-08-29T07:22:55 〜 2026-09-04T14:06:49 の**約 6 日 6.7 時間**で、公称の 7 日より短い時間帯が常に存在する
- 元サーバー `pgsql-felisaichatbot-dev` は 1 回目のドリルを通じて無傷（破壊的操作なし）
