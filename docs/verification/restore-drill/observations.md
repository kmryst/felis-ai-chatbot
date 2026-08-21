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
