# PITR ドリル実測記録（Issue #230）

Issue [#230](https://github.com/kmryst/felis-ai-chatbot/issues/230) の PITR ドリルの実測記録。時刻はすべて UTC。
用語（`t0` / `t1` / 実測復元所要区間 / 復元点精度）の定義は Issue #230 §1 が正本であり、本ファイルはその定義に従って実測値だけを残す。
実測値は **RPO / RTO とは呼ばない**（[restore-drill-recovery-objectives.md](../../operations/restore-drill-recovery-objectives.md) §6-1）。

**記録の単位は「復元手法」ではなく「1 回の演習」である。** digest ベースラインとセンチネル S1 / S2 / S3 は 2 回の復元で共有しており、
2 回の `t1 − t0` / 復元点精度を並べた比較こそがこの演習の成果物なので、1 ファイルにまとめる。
次回以降の演習は日付付きの別ファイルにして系列にする。

## このドリルの構成

| # | 復元方式 | 状態 | 記録先 |
| --- | --- | --- | --- |
| 手順 0 | （共通の前提）digest ベースライン固定・センチネル S1 投入 | 完了（2026-09-04） | [手順 0](#手順-0-digest-ベースラインの固定2026-09-04t133630895z) |
| 1 回目 | custom restore（任意時刻 + WAL 再生） | **完了**（2026-09-04） | [1 回目](#1-回目-custom-restore完了) |
| 2 回目 | fast restore（最新 Full backup 起点） | **完了**（2026-09-05） | [2 回目](#2-回目-fast-restore完了) |

**2 回とも完了した。** 主成果物は次の「1 回目と 2 回目の比較」表と、そこから読み取れる考察である。

### 共通の前提

- 元サーバー: `pgsql-felisaichatbot-dev`（rg-felisaichatbot-dev-tf / Japan East / PostgreSQL 17.10 / Standard_B1ms）
- 復元先: `pgsql-felisaichatbot-dev-restored`（同 VNet・委任サブネット・private DNS zone。各回とも検証後に削除する）
- 実行経路: `az containerapp exec` → `ca-felisaichatbot-dev-ops`（revision `ca-felisaichatbot-dev-ops--0000006`）→ `psql`
- **元サーバーは全工程を通じて無傷**。元サーバーへの操作は SELECT と `obs.pitr_sentinel` への `CREATE TABLE` / `INSERT` のみで、破壊的操作（`DROP TABLE` など）は一切行っていない
- 照合の正本は手順 0 で 1 回だけ取得した固定 digest。照合のために元サーバーを読み直さない

## 1 回目と 2 回目の比較（この演習の成果物）

2 回とも完了した。両回の値はそれぞれ独立に記録したものであり、差分を restore mode のみに帰属させて断定はしない
（対象バックアップ・復元指定時刻・Azure 側の混雑条件も同時に変わる）。WAL 再生スパンは共変量として併記する。

| 項目 | 1 回目: custom restore | 2 回目: fast restore |
| --- | --- | --- |
| 実施日時 | 2026-09-04 | 2026-09-05 |
| 復元指定時刻 | 2026-09-04T13:50:00Z | 2026-09-05T07:28:18.423447Z |
| 起点 Full backup（completedTime） | `backup_639241036648747354` / 2026-09-04T07:27:45.874735Z | `backup_639241900974234471` / 2026-09-05T07:28:18.423447Z |
| **WAL 再生スパン** | **6 h 22 min 14.125 s** | **0 s** |
| `t0`（Activity Log `Accepted`） | 14:06:55.069282Z | 07:29:09.978411Z |
| `t1`（最初の `SELECT 1` 成功） | 14:13:46.224Z | 07:34:52.108Z |
| **実測復元所要区間 `t1 − t0`** | **6 min 51.155 s** | **5 min 42.130 s** |
| `state=Ready` 初観測 − `t0` | 8 min 12.499 s（60 s ポーリング） | 6 min 6.051 s（30 s ポーリング） |
| Activity Log `Succeeded` − `t0` | 9 min 6.539 s | 7 min 9.751 s |
| **復元点精度** | **39.035 s**（heartbeat 1 分粒度の標本化誤差を含む） | **0.473 s**（同上） |
| digest 4 テーブルの一致 | 全一致 | 全一致 |
| `documents WHERE embedding IS NULL` | 0 | 0 |
| センチネル期待 → 実測 | S1 存在 / S2・S3 不在 → 一致 | S1・S2 存在 / S3 不在 → 一致 |
| 復元先サーバーの削除 | 完了（所要 1 min 32.319 s） | 完了（所要 1 min 19.874 s） |

### この表から読み取れること

もっとも大きな差は**復元点精度**で、39.035 s（custom）から 0.473 s（fast）へ 2 桁改善している。これは復元手法の速さではなく
**復元指定時刻の置き方**の帰結である。fast restore では復元指定時刻が起点 Full backup の `completedTime` そのものなので
**WAL 再生スパンが 0 s** になり、復元点が backup 完了時点に一致する。custom restore は任意時刻を指定するぶん
WAL を 6 時間 22 分ぶん再生する必要があり、そのぶん復元点の観測（1 分粒度の heartbeat）との距離が開く。
どちらの値も heartbeat 1 分間隔による標本化誤差を含む上限値であり、0.473 s は「たまたま復元指定時刻の 0.47 s 前に
heartbeat があった」ことによる小さい値である点も併記しておく。
一方 `t1 − t0` は 6 min 51 s → 5 min 42 s で、差は約 1 分にとどまる。WAL 再生スパンが 6 時間 22 分から 0 s に減ったにもかかわらず
所要時間はほぼ変わらないので、**この規模のデータでは所要時間の支配項は WAL 再生ではなくサーバー作成そのもの**だと読める
（`state=Ready − t0` と `Succeeded − t0` も同様に 2 分前後の差にとどまる）。ただし n = 1 ずつの観測であり、
Azure 側の混雑条件も統制していないため、この読みは示唆であって断定ではない。

## 実施順序を Issue #230 の記載と入れ替えた

Issue #230 は「1 回目 = fast restore、2 回目 = custom restore」の順で書かれているが、実際は **custom restore を先に実施した**。
fast restore は「S1 投入後に完了した最新 Full backup」を必要とし、それが得られるのは日次 Full backup の翌 2026-09-05 07:2xZ 以降になるためである。
この入れ替えで壊れる受け入れ条件はない。センチネルの期待値だけを次の表のとおり読み替える。

| id | 投入時刻（サーバー `ts`） | 位置づけ | custom restore（13:50:00Z）の期待 | fast restore（07:28:18.423447Z）の期待 |
| --- | --- | --- | --- | --- |
| S1 | 2026-09-04 13:36:31.223339+00 | custom 復元指定時刻より前 | **存在**（肯定側） | 存在（肯定側） |
| S2 | 2026-09-04 14:04:30.993218+00 | custom 復元指定時刻より後、fast 復元指定時刻より前 | **不在**（否定側） | 存在（肯定側） |
| S3 | 2026-09-05 07:28:52.696990+00 | fast 復元指定時刻より後 | 不在 | **不在**（否定側） |

Issue 本文の受け入れ条件の文言「1 回目: S1 存在 / S2・S3 不在」「2 回目: S1・S2 存在 / S3 不在」は、
**custom: S1 存在 / S2・S3 不在**、**fast: S1・S2 存在 / S3 不在** と読み替える。
どちらの復元指定時刻についても、肯定側（あるべきものがある）と否定側（あってはならないものがない）の両方が成立する配置になっている。

## 手順 0: digest ベースラインの固定（2026-09-04T13:36:30.895Z）

すべての復元より前に、元サーバーで 1 回だけ取得した固定ベースライン。以後の照合はこの固定値と復元サーバーの値の比較で行い、照合のために元サーバーを読み直さない。
SQL は Issue #230 §2 の逐語。セッション GUC として次を先に流している。

```sql
SET timezone = 'UTC';
SET datestyle = 'ISO, MDY';
SET extra_float_digits = 3;
SET intervalstyle = 'postgres';
SET client_min_messages = warning;
```

サーバー既定値は `timezone=UTC` / `datestyle=ISO, MDY` / `extra_float_digits=1` / `intervalstyle=postgres` であり、
この `SET` 群で実際に変わるのは `extra_float_digits` のみ（実測）。digest の再現性のため明示する。

| table | n | digest (md5) |
| --- | --- | --- |
| documents | 38 | `e7deb2d1473bd7a5ce66540c4c7c78d4` |
| object_properties | 53 | `f3cf355b403988282a33bf62c4ad4f17` |
| objects | 15 | `4244aa6dffd5e181ad46930d3bedaa5d` |
| sources | 13 | `ae32dbe92dabb4e4ec9de08481280d4e` |

- `documents WHERE embedding IS NULL` = **0**
- digest 取得時刻（`clock_timestamp()`）: 2026-09-04 13:36:30.895409+00
- 同時点の heartbeat: 17,627 行 / `max(ts)` = 2026-09-04 13:36:20.69233+00

### センチネル `obs.pitr_sentinel`

digest 取得の**あと**に、psql から直接 DDL で作成した（ベースラインにセンチネルは混入していない）。

```sql
CREATE TABLE obs.pitr_sentinel (id text PRIMARY KEY, note text, ts timestamptz DEFAULT now());
```

- `CREATE TABLE` 直前のサーバー時刻: 13:36:31.022734+00（作成前の `to_regclass('obs.pitr_sentinel')` は NULL）
- **S1 投入時刻（`ts` = `now()`）: 2026-09-04 13:36:31.223339+00**

### 手順 0 時点のバックアップ一覧（`az postgres flexible-server backup list`, 13:35:00.822Z）

保持 7 日分の Full / Automatic が 7 件。最古・最新のみ抜粋する。

```text
Name                       BackupType    CompletedTime                     Source
-------------------------  ------------  --------------------------------  ---------
backup_639235849746676708  Full          2026-08-29T07:22:55.667670+00:00  Automatic
（中略: 08-30 〜 09-03 の日次 Full 5 件）
backup_639241036648747354  Full          2026-09-04T07:27:45.874735+00:00  Automatic
```

最新 = `backup_639241036648747354`（completedTime **2026-09-04T07:27:45.874735+00:00**）。これは S1 投入より前に完了しているため、
fast restore に使う「S1 投入後に完了した最新 Full backup」としては使えない。翌 2026-09-05 07:2xZ の日次分を待つ必要がある。

## 1 回目: custom restore（完了）

実施日 2026-09-04。復元指定時刻を任意に指定し、直前の Full backup から WAL を再生して到達させる方式。

### 復元の実行

- 復元指定時刻（`--restore-time`）: **2026-09-04T13:50:00Z**
- 直前 Full backup: `backup_639241036648747354` / completedTime 2026-09-04T07:27:45.874735+00:00
- **WAL 再生スパン（復元指定時刻 − 直前 backup completedTime）: 6 h 22 min 14.125 s**
- 発行直前の `earliestRestoreDate`: 2026-08-29T07:22:55.667670+00:00（取得 14:06:49.980Z）。指定時刻 13:50:00Z は窓内

```bash
az postgres flexible-server restore -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-restored \
  --source-server pgsql-felisaichatbot-dev --restore-time "2026-09-04T13:50:00Z" --no-wait --yes \
  --vnet vnet-felisaichatbot-dev --subnet snet-felisaichatbot-dev-pgsql \
  --private-dns-zone felisaichatbot-dev.private.postgres.database.azure.com -o json
```

CLI 出力（抜粋）:

```text
restore_time=2026-09-04T13:50:00Z
t0-cli-before=2026-09-04T14:06:50.984Z
restore_cli_rc=0
t0-cli-after=2026-09-04T14:06:55.013Z
```

### タイムライン

| 項目 | 時刻 | 備考 |
| --- | --- | --- |
| S1 投入 | 13:36:31.223339 | 手順 0 |
| **復元指定時刻** | **13:50:00.000000** | |
| S2 投入 | 14:04:30.993218 | ops exec セッション冒頭 |
| 疎通ポーリング開始（15 s 間隔） | 14:04:31.010 | restore 発行より前から回した |
| t0-cli（送信直前） | 14:06:50.984 | 参考値 |
| Activity Log `Started` | 14:06:53.9443098 | 参考値 |
| **t0（正本）= Activity Log `Accepted`** | **14:06:55.069282** | |
| t0-cli（CLI 正常終了 rc=0） | 14:06:55.013 | |
| `state=Provisioning` 初観測 | 14:08:01.938 | 60 s ポーリング（14:07:01 は `ResourceNotFound`） |
| DNS 解決成功に転じた試行 | 14:11:03.642（try=27） | エラーが `could not translate host name` → `connection to server ...` に変化 |
| **t1 = 最初の `SELECT 1` 成功** | **14:13:46.224**（試行開始 14:13:43.589, try=36） | ポーリング間隔 15 s を含む上限値 |
| 復元サーバー `pg_postmaster_start_time()` | 14:14:58.587321 | **t1 より後**（後述の注記） |
| `state=Ready` 初観測 | 14:15:07.568 | 60 s ポーリング（14:14:06 は Provisioning） |
| 検証（verify2）実行 | 14:15:26.324 〜 14:15:27.240 | |
| Activity Log `Succeeded` | 14:16:01.6082432 | |
| delete 発行 / 完了 | 14:15:34.008 / 14:17:06.327 | rc=0 |
| `flexible-server list` で不在確認 | 14:17:06.329 | |

### 実測復元所要区間（`t1 − t0`）

正本 `t0` = Activity Log の `status=Accepted` の `eventTimestamp`。

| 区間 | 値 | 注記 |
| --- | --- | --- |
| **`t1 − t0` = 14:13:46.224 − 14:06:55.069** | **6 min 51.155 s** | ポーリング間隔 15 s を含む**上限値**。ただし t1 時点の接続先は復元途中の中間状態（後述） |
| `t1 − Started` | 6 min 52.280 s | 参考 |
| `t1 − t0-cli`（送信直前） | 6 min 55.240 s | 参考。CLI の起動・認証・送信を含む |
| `state=Ready` 初観測 − `t0` | 8 min 12.499 s | 60 s ポーリングを含む上限値 |
| 復元指定時刻どおりの内容を確認できた最初の時刻（verify2）− `t0` | 8 min 31.255 s | `state=Ready` 観測後に exec を張った時間を含む |
| Activity Log `Succeeded` − `t0` | 9 min 6.539 s | Azure 側の完了イベント |

`t0-cli`（送信直前 14:06:50.984Z）は `Accepted` より **4.085 s** 早い。`Started` と `Accepted` の差は本回 **1.12 s** だった。

### 復元点精度

- 復元サーバーの `max(obs.heartbeat.ts)` = 2026-09-04 13:49:20.964559+00
- **復元指定時刻 − `max(heartbeat.ts)` = 39.035 s**
- 注記: heartbeat は毎分 1 行 INSERT のため、この値には**最大 1 分の標本化誤差**が含まれる。
  13:49:20 の次の heartbeat は 13:50:20 頃であり、復元指定時刻 13:50:00 より後になる。
  したがって 39.035 s は「復元点のずれ」ではなく「1 分粒度の観測点で測れる上限」である

### 検証結果（verify2、`state=Ready` 観測後の 14:15:26Z）

| table | n | digest | ベースライン（手順 0） | 判定 |
| --- | --- | --- | --- | --- |
| documents | 38 | `e7deb2d1473bd7a5ce66540c4c7c78d4` | 同左 | 一致 |
| object_properties | 53 | `f3cf355b403988282a33bf62c4ad4f17` | 同左 | 一致 |
| objects | 15 | `4244aa6dffd5e181ad46930d3bedaa5d` | 同左 | 一致 |
| sources | 13 | `ae32dbe92dabb4e4ec9de08481280d4e` | 同左 | 一致 |

- `documents WHERE embedding IS NULL` = 0
- センチネル: **S1 存在**（note 本文まで一致）/ **S2 不在** / S3 不在（未投入）→ **肯定側・否定側の両方が成立**
- `pg_is_in_recovery()` = `f`、復元サーバー `inet_server_addr()` = 10.10.0.68（元サーバー 10.10.0.71）
- 同時刻の元サーバー: S1 / S2 ともに存在、heartbeat `max(ts)` = 14:15:18.549624+00（稼働継続。無傷）

生出力（`verify2` 抜粋）:

```text
restored_now|recov|pm_start|sentinel_tbl|addr
2026-09-04 14:15:26.530955+00|f|2026-09-04 14:14:58.587321+00|t|10.10.0.68
hb_rows|hb_max
17640|2026-09-04 13:49:20.964559+00
id|note|ts
S1|PITR drill S1: before restore-time #1 (fast restore)|2026-09-04 13:36:31.223339+00
```

### 復元先サーバーの削除と後始末

```text
delete_start=2026-09-04T14:15:34.008Z
delete_rc=0
delete_end=2026-09-04T14:17:06.327Z
list_check=2026-09-04T14:17:06.329Z
Name                      Resource Group            Location    Version   Tier       SKU            State
------------------------  ------------------------  ----------  --------  ---------  -------------  -----
pgsql-felisaichatbot-dev  rg-felisaichatbot-dev-tf  Japan East  17        Burstable  Standard_B1ms  Ready
```

- 削除所要 1 min 32.319 s。`az postgres flexible-server list` は**元サーバーのみ**を返し、復元先は不在
- 削除後の private DNS zone のレコードは**元サーバーの A レコード（→ 10.10.0.71）のみ**。復元先の A レコードは残っていない
- 復元先が課金対象だったのは 14:06:55（`Accepted`）〜 14:17:06（削除完了）の約 10 分

## 2 回目: fast restore（完了）

実施日 2026-09-05。最新の Full backup の `completedTime` そのものを `--restore-time` に指定する方式。
公式手順どおり fast restore 専用の引数は存在しないため、`backup list` の `completedTime` をマイクロ秒まで逐語でコピーして渡した。

**限定表現**: サービスが実際に fast パスを通ったことは API から確認できない。本節は「Full backup 完了時刻ちょうどを
`--restore-time` に指定した復元」の実測である。ただし後述のとおり **WAL 再生スパンが 0 s** であることは指定値から自明であり、
復元点精度 0.473 s がその帰結として観測されている。

### 復元の実行

- 復元指定時刻（`--restore-time`）: **`2026-09-05T07:28:18.423447+00:00`**（`completedTime` の逐語コピー）
- 起点 Full backup: `backup_639241900974234471` / completedTime 2026-09-05T07:28:18.423447+00:00
- **WAL 再生スパン（復元指定時刻 − 起点 backup completedTime）: 0 s**
- 発行直前の `earliestRestoreDate`: 2026-08-30T07:22:48.397652+00:00（取得 07:29:04.394Z）。指定時刻は窓内。
  前日 09-04 の実測値 2026-08-29T07:22:55.667670Z から約 24 時間ジャンプしており、「知見 4」の鋸歯状の動きが再現している

```bash
az postgres flexible-server restore -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev-restored \
  --source-server pgsql-felisaichatbot-dev --restore-time "2026-09-05T07:28:18.423447+00:00" --no-wait --yes \
  --vnet vnet-felisaichatbot-dev --subnet snet-felisaichatbot-dev-pgsql \
  --private-dns-zone felisaichatbot-dev.private.postgres.database.azure.com -o json
```

CLI 出力（抜粋）:

```text
earliestRestoreDate_check=2026-09-05T07:29:04.394Z
{
  "earliestRestoreDate": "2026-08-30T07:22:48.397652+00:00",
  "state": "Ready"
}
restore_time=2026-09-05T07:28:18.423447+00:00
t0-cli-before=2026-09-05T07:29:04.937Z
restore_cli_rc=0
t0-cli-after=2026-09-05T07:29:08.432Z
```

### 起点 Full backup の出現を待った記録

当日分の日次 Full backup は 30 s 間隔の `backup list` ポーリングで待った。07:27:57Z 時点では前日分が最新で、
07:28:30Z の試行で当日分が初めて現れた（`completedTime` は 07:28:18.423447Z）。

```text
2026-09-05T07:27:57.476Z backup_639241036648747354 2026-09-04T07:27:45.874735+00:00 Full
2026-09-05T07:28:30.352Z backup_639241900974234471 2026-09-05T07:28:18.423447+00:00 Full
```

出現後の `backup list`（07:28:47Z）。保持 7 日分の Full / Automatic が 7 件で、最古は 08-30 分に入れ替わっている。

```text
Name                       BackupType    CompletedTime                     Source
-------------------------  ------------  --------------------------------  ---------
backup_639236713673976526  Full          2026-08-30T07:22:48.397652+00:00  Automatic
（中略: 08-31 〜 09-03 の日次 Full 4 件）
backup_639241036648747354  Full          2026-09-04T07:27:45.874735+00:00  Automatic
backup_639241900974234471  Full          2026-09-05T07:28:18.423447+00:00  Automatic
```

### タイムライン

| 項目 | 時刻 | 備考 |
| --- | --- | --- |
| 起点 Full backup `completedTime` = **復元指定時刻** | **07:28:18.423447** | |
| `backup list` で当日分を初観測 | 07:28:30.352 | 30 s ポーリング |
| S3 投入 | 07:28:52.696990 | ops exec セッション冒頭。復元指定時刻の **34.27 s 後** |
| 疎通ポーリング開始（15 s 間隔） | 07:28:52.719 | restore 発行より前から回した |
| `earliestRestoreDate` 再取得 | 07:29:04.394 | 窓内であることを確認 |
| t0-cli（送信直前） | 07:29:04.937 | 参考値 |
| Activity Log `Started` | 07:29:08.8377657 | 参考値 |
| t0-cli（CLI 正常終了 rc=0） | 07:29:08.432 | |
| **t0（正本）= Activity Log `Accepted`** | **07:29:09.978411** | |
| `state=NOTFOUND` → `Provisioning` | 07:29:15.038 → 07:29:47.856 | 30 s ポーリング |
| DNS 解決成功に転じた試行 | 07:31:53.940（try=13） | エラーが `could not translate host name` → `connection to server ...` に変化 |
| **t1 = 最初の `SELECT 1` 成功** | **07:34:52.108**（試行開始 07:34:51.960, try=23） | ポーリング間隔 15 s を含む上限値 |
| t1 直後の観測（同セッション） | 07:34:52.383 | `pg_postmaster_start_time` = 07:34:27.065911、`obs.pitr_sentinel` **存在**、`max(heartbeat.ts)` = 07:28:17.950554 |
| `state=Ready` 初観測 | 07:35:16.029 | 30 s ポーリング（07:34:43 は Provisioning） |
| 検証（verify）実行 | 07:35:34.475 〜 07:35:35.387 | このとき `pg_postmaster_start_time` = 07:35:04.817384（**t1 後にもう一度再起動している**） |
| Activity Log `Succeeded` | 07:36:19.7290004 | |
| delete 発行 / 完了 | 07:35:41.525 / 07:37:01.399 | rc=0 |
| `flexible-server list` で不在確認 | 07:37:01.400 | `DELETE_CONFIRMED` |

### 実測復元所要区間（`t1 − t0`）

正本 `t0` = Activity Log の `status=Accepted` の `eventTimestamp`（1 回目と同一ルール）。

| 区間 | 値 | 注記 |
| --- | --- | --- |
| **`t1 − t0` = 07:34:52.108 − 07:29:09.978** | **5 min 42.130 s** | ポーリング間隔 15 s を含む**上限値** |
| `t1 − Started` | 5 min 43.270 s | 参考 |
| `t1 − t0-cli`（送信直前） | 5 min 47.171 s | 参考。CLI の起動・認証・送信を含む |
| `state=Ready` 初観測 − `t0` | 6 min 6.051 s | 30 s ポーリングを含む上限値 |
| 検証（verify）− `t0` | 6 min 24.497 s | `state=Ready` 観測後に exec を張った時間を含む |
| Activity Log `Succeeded` − `t0` | 7 min 9.751 s | Azure 側の完了イベント |

`t0-cli`（送信直前 07:29:04.937Z）は `Accepted` より **5.041 s** 早い。`Started` と `Accepted` の差は本回 **1.14 s**（1 回目は 1.12 s）。
なお CLI の正常終了（07:29:08.432Z）は `Accepted` の `eventTimestamp` より 1.5 s 早く、Activity Log の `eventTimestamp` が
CLI の応答受信後に打刻されうることを示している。

### 復元点精度

- 復元サーバーの `max(obs.heartbeat.ts)` = 2026-09-05 07:28:17.950554+00
- **復元指定時刻 − `max(heartbeat.ts)` = 0.472893 s**
- 注記: heartbeat は毎分 1 行 INSERT のため、この値には**最大 1 分の標本化誤差**が含まれる。
  今回は復元指定時刻のわずか 0.47 s 前に heartbeat が入っていたため小さい値になった。
  したがって 0.473 s は「復元点のずれ」ではなく「1 分粒度の観測点で測れる上限」である

### 検証結果（`state=Ready` 観測後の 07:35:34Z）

| table | n | digest | ベースライン（手順 0） | 判定 |
| --- | --- | --- | --- | --- |
| documents | 38 | `e7deb2d1473bd7a5ce66540c4c7c78d4` | 同左 | 一致 |
| object_properties | 53 | `f3cf355b403988282a33bf62c4ad4f17` | 同左 | 一致 |
| objects | 15 | `4244aa6dffd5e181ad46930d3bedaa5d` | 同左 | 一致 |
| sources | 13 | `ae32dbe92dabb4e4ec9de08481280d4e` | 同左 | 一致 |

- `documents WHERE embedding IS NULL` = 0
- センチネル: **S1 存在 / S2 存在**（いずれも note 本文まで一致）/ **S3 不在** → **肯定側・否定側の両方が成立**
- `pg_is_in_recovery()` = `f`、復元サーバー `inet_server_addr()` = 10.10.0.68（1 回目と同じアドレスが再利用された）
- 同時刻の元サーバー: S1 / S2 / S3 の 3 行すべて存在、heartbeat `max(ts)` = 07:35:17.871312+00（稼働継続。無傷）

生出力（`verify` 抜粋）:

```text
restored_now|recov|pm_start|sentinel_tbl|addr
2026-09-05 07:35:34.697943+00|f|2026-09-05 07:35:04.817384+00|t|10.10.0.68
hb_rows|hb_max
18697|2026-09-05 07:28:17.950554+00
id|note|ts
S1|PITR drill S1: before restore-time #1 (fast restore)|2026-09-04 13:36:31.223339+00
S2|PITR drill S2: after custom restore-time 2026-09-04T13:50:00Z, before fast restore-time|2026-09-04 14:04:30.993218+00
(2 rows)
```

### Activity Log 生出力（取得 07:46:01Z）

`t1` 確定から 11 分後に後追いで取得した。同一クエリに 09-04 の custom restore 分も含まれる。

```text
Ts                            Sub                   Status     Corr
----------------------------  --------------------  ---------  ------------------------------------
2026-09-05T07:36:19.7290004Z  2026-09-05T07:38:17Z  Succeeded  397b6d6b-0fbb-428b-a4f5-d96ae2677de4
2026-09-05T07:29:09.978411Z   2026-09-05T07:31:13Z  Accepted   397b6d6b-0fbb-428b-a4f5-d96ae2677de4
2026-09-05T07:29:08.8377657Z  2026-09-05T07:31:13Z  Started    397b6d6b-0fbb-428b-a4f5-d96ae2677de4
2026-09-04T14:16:01.6082432Z  2026-09-04T14:18:15Z  Succeeded  3581875f-1f9c-48ef-8583-2c7ce81139db
2026-09-04T14:06:55.069282Z   2026-09-04T14:07:50Z  Accepted   3581875f-1f9c-48ef-8583-2c7ce81139db
2026-09-04T14:06:53.9443098Z  2026-09-04T14:07:50Z  Started    3581875f-1f9c-48ef-8583-2c7ce81139db
```

- 取り込み遅延（`submissionTimestamp` − `eventTimestamp`）は本回 約 1 min 58 s 〜 2 min 4 s
- 復元サーバー削除完了（07:37:01Z）より後の 07:46:01Z に取得できており、「削除後でも Activity Log は取れる」を再確認した

### 復元先サーバーの削除と後始末

```text
delete_start=2026-09-05T07:35:41.525Z
delete_rc=0
delete_end=2026-09-05T07:37:01.399Z
list_check=2026-09-05T07:37:01.400Z try=1
Name                      Resource Group            Location    Version   Tier       SKU            State
------------------------  ------------------------  ----------  --------  ---------  -------------  -----
pgsql-felisaichatbot-dev  rg-felisaichatbot-dev-tf  Japan East  17        Burstable  Standard_B1ms  Ready
DELETE_CONFIRMED
```

- 削除所要 **1 min 19.874 s**（1 回目は 1 min 32.319 s）。`az postgres flexible-server list` は**元サーバーのみ**を返す
- 復元先が課金対象だったのは 07:29:09（`Accepted`）〜 07:37:01（削除完了）の約 8 分

### 本ドリル全期間を通じた元サーバーの不変性（2026-09-05T12:12:52.846Z 再取得）

全復元の完了後に、元サーバーで手順 0 と同一の SQL（同一 GUC `SET` 群込み）を再実行した。
**照合の正本はあくまで手順 0 の固定値**であり、この再取得は不変性の確認にすぎない。

| table | n | digest（再取得） | ベースライン（手順 0） | 判定 |
| --- | --- | --- | --- | --- |
| documents | 38 | `e7deb2d1473bd7a5ce66540c4c7c78d4` | 同左 | 一致 |
| object_properties | 53 | `f3cf355b403988282a33bf62c4ad4f17` | 同左 | 一致 |
| objects | 15 | `4244aa6dffd5e181ad46930d3bedaa5d` | 同左 | 一致 |
| sources | 13 | `ae32dbe92dabb4e4ec9de08481280d4e` | 同左 | 一致 |

- `documents WHERE embedding IS NULL` = 0。**4 テーブルすべてが手順 0 のベースラインと一致**し、
  ドリル 2 回（09-04 13:36 〜 09-05 12:12）を通じて元サーバーのアプリ本体データは無傷だった
- 同時点の `obs.pitr_sentinel` には S1 / S2 / S3 の 3 行が残存している（後述「後片付けの状況」）

### 実行中断について（実測には影響なし）

2 回目の実行中、2026-09-05T07:46:34Z にセッションのレート制限で作業エージェントの turn が中断された。
ただし**中断時点で検証・復元サーバーの削除・削除確認・Activity Log の取得はすべて完了しており、本節の実測値に影響はない**。
復元サーバーが放置されることもなかった（07:37:01Z に不在確認済み）。事実として記録に残す。

## 知見

### 1. 「接続できた」は「復元完了」ではない（最重要）

`SELECT 1` は 14:13:46.224 に成功したが、**その直後に同一セッションで走らせた検証では `obs.pitr_sentinel` が存在しなかった**。

```text
2026-09-04T14:13:43.589Z 2026-09-04T14:13:46.224Z try=36 rc=0 1
=== verify restored ===
（documents / object_properties / objects / sources の digest はベースラインと一致、embedding NULL = 0）
-- sentinel
ERROR:  relation "obs.pitr_sentinel" does not exist
```

一方 `state` は 14:14:06 時点でまだ `Provisioning` で、復元サーバーの `pg_postmaster_start_time()` は **14:14:58.587321**（t1 より 1 分 12 秒あと）だった。
つまり **14:13:46 に接続できた相手は、復元処理の途中段階のインスタンス**（S1 投入 13:36:31 より前、Full backup 直後に近い状態）であり、
WAL 再生の完了後に postmaster が再起動して 14:14:58 に最終状態になったとみられる。
`state=Ready` 観測（14:15:07）後の再検証（verify2, 14:15:26）では、S1 存在 / S2 不在 / heartbeat 13:49:20 と、復元指定時刻どおりの内容になっていた。

**運用上の教訓**: Azure Database for PostgreSQL Flexible Server の PITR では、**復元完了前に接続を受け付ける中間状態が存在する**。
`SELECT 1` の成功だけを完了判定に使うと、復元されていないデータを「復元済み」と誤認しうる。
**次回以降（fast restore を含む）は、`SELECT 1` 成功後に `state=Ready` を待ってから内容の検証を行う。**
本ファイルでは定義どおり `t1` = 14:13:46.224 を記録しつつ、内容が復元指定時刻に到達していたことを確認できた最初の時刻（verify2 の 14:15:26）を併記する。

#### 2 回目（fast restore）での再確認 — 別経路で同じ結論になった

2 回目は 1 回目と現れ方が違った。`t1`（07:34:52.108）直後の同一セッション観測では **`obs.pitr_sentinel` が既に存在**し、
`max(heartbeat.ts)` も最終値 07:28:17.950554 と一致していた。つまり「t1 の相手が中間状態だった」という 1 回目の症状は出ていない。

それでも **`pg_postmaster_start_time()` は t1 直後 07:34:27.065911 → 検証時（07:35:34）07:35:04.817384 と変化している**。
`t1` のあとにもう一度 postmaster の再起動が起きており、`t1` の時点のインスタンスは最終状態ではなかった。
症状（センチネルの有無）は異なるが、**「`SELECT 1` の成功は復元完了の判定に使えない」という 1 回目の教訓は別経路で裏づけられた**。
2 回目も `state=Ready` 初観測（07:35:16）を待ってから内容検証を行っており、この運用は次回以降も維持する。

### 2. `t0` は Activity Log の `Accepted` を正本にする

- `az monitor activity-log list` で復元先の `resourceId` に対する `Microsoft.DBforPostgreSQL/flexibleServers/write` を引くと、
  同一 `correlationId` に `Started` → `Accepted` → `Succeeded` が並ぶ。`eventTimestamp` は 100 ns 分解能で取れる
- `Started` と `Accepted` の差は本回 1.12 s。Issue #230 §1 で参照した過去の実測では 1.8 s / 11.8 s。
  **どちらを採るかで最大十数秒ぶれる**ため、両回に同一ルール（`Accepted` を正本）を適用する
- Activity Log には**取り込み遅延**がある（本回の `submissionTimestamp` − `eventTimestamp` は約 55 s 〜 2 min 13 s）。
  そのため **`t1` 確定から 10 分以上あとに後追いで取得する**（本回は 14:26:06Z に取得。t1 の 12 分後）
- Activity Log は 90 日保持されるので、**復元先サーバーを削除したあとでも取得できる**。
  実際、本回のサーバー削除完了（14:17:06）より後の 14:26:06 に取得している

### 3. `az containerapp exec` の実務的な制約

VNet 統合により PostgreSQL はプライベート到達のみで、ops コンテナ経由でしか SQL を実行できない。その `az containerapp exec` に固有の制約が 4 つある。

- **`--command` の長さ上限**: exec の command は WebSocket URL の query string に載る。
  非圧縮 base64 5,029 文字（URL エンコード後 約 5.5 KB）のトークンで `Handshake status 404 Not Found`（IIS）になった。
  IIS 既定の `maxQueryString` 2048 に当たったとみられる。`gzip -9 | base64 -w0` で 1,326 文字（エンコード後 1,444）に畳んだら成功した。
  **エンコード後 2 KB 未満に収めるのが目安**
- **`--command` はシェルを通らない**: 空白で分割され引用符も除去されるため、パイプやヒアドキュメントをそのまま書けない。
  `${IFS}` を空白の代わりに使い、base64 をファイルにデコードしてから `sh` で実行する形にする

  ```bash
  az containerapp exec -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops \
    --command "sh -c echo${IFS}<b64>|base64${IFS}-d|gunzip>/tmp/s.sh;sh${IFS}/tmp/s.sh"
  ```

- **TTY が必要**: 非対話環境では `script -qec` で疑似 TTY に包んで実行する
- **429 レート制限がある**（`retry-after: 600` を実測）。呼び出しを最小化し、1 回の exec で必要な処理をまとめて流す。
  1 回目の当日の exec は 4 回（うち 1 回は上記の 404）で、429 は発生しなかった。
  2 回目の当日（2026-09-05）の exec は **3 回**（疎通ポーリング / 検証 / 元サーバー digest 再取得）で、こちらも 429 は発生していない。
  **gzip 圧縮でエンコード後 2 KB 未満に収める**という 1 回目の知見は 2 回目でもそのまま有効だった

### 4. `earliestRestoreDate` は連続スライドではなく鋸歯状に動く（既存の予測を反証）

[observations.md](./observations.md) フェーズ 1 に「保持 7 日の窓が満杯になった後、`earliestRestoreDate` は
『現在時刻 − 7 日』を追って毎日スライドし始めるはず（**未検証の予測**）」と記録していた。本ドリルの実測で**この予測は否定された**。

- 復元発行直前（2026-09-04T14:06:49.980Z）の `earliestRestoreDate` = **2026-08-29T07:22:55.667670+00:00**
- 同日 13:35:00Z の `backup list` の最古 Full = `backup_639235849746676708` / completedTime **2026-08-29T07:22:55.667670+00:00**
- 両者は**マイクロ秒まで完全に一致する**

連続スライドであれば 09-04T14:06Z 時点の左端は 08-28T14:06Z 付近になるはずだが、実際は保持ウィンドウ内の**最古スナップショットの `completedTime` そのもの**だった。
日次 Full backup が毎朝 07:2xZ に完了して最古スナップショットが 1 つ落ちるたびに、左端が**約 24 時間ジャンプする鋸歯状**の動きになる。
実測ウィンドウ幅は 08-29T07:22:55 〜 09-04T14:06:49 で **約 6 日 6.7 時間**であり、公称の 7 日より短い時間帯が常に存在する。

**運用上の含意**: 「7 日前まで復元できる」とは限らない。復元可能な最古時刻は日次バックアップの完了時刻に量子化されており、
毎朝のジャンプ直後がもっとも窓が狭い。復元時刻を選ぶ前に必ず `earliestRestoreDate` の実値を確認する。

### 5. `completedTime` はマイクロ秒まで逐語でコピーする

fast restore に専用の引数はなく、`az postgres flexible-server backup list` の `completedTime` を
`--restore-time` へ渡すことが公式手順である。このとき **マイクロ秒を切り捨てずに逐語でコピーする**。

2 回目では `2026-09-05T07:28:18.423447+00:00` をそのまま渡し、**WAL 再生スパン 0 s**（復元指定時刻 − 起点 backup の
`completedTime` = 0）を成立させた。その帰結として復元点精度 0.473 s が観測されており、
**指定値が Full backup の完了時刻と厳密に一致していたことが実測から裏づけられている**。
秒未満を切り捨てて指定すると、その差だけ WAL 再生が入り、この性質は崩れる。

## 後片付けの状況

| 項目 | 状態 | 備考 |
| --- | --- | --- |
| 復元サーバー `pgsql-felisaichatbot-dev-restored` の削除 | **完了** | 両回とも `flexible-server list` で不在確認済み（14:17:06Z / 07:37:01Z） |
| 元サーバーでの digest 再取得（不変性の裏づけ） | **完了** | 2026-09-05T12:12:52.846Z。4 テーブルすべてベースライン一致 |
| 元サーバーの無傷 | **確認済み** | 破壊的操作なし。SELECT と `obs.pitr_sentinel` への `CREATE TABLE` / `INSERT` のみ |
| `obs.pitr_sentinel` の DROP | **未実施（意図的に残す）** | 3 回目のドリルでセンチネル表を再利用する設計（S4 を UPDATE と同一トランザクションに入れる）のため、数日後に作り直す churn を避ける判断。S1 / S2 / S3 の 3 行のドリル用一時テーブルで実害はない。Issue #230 の受け入れ条件「`obs.pitr_sentinel` を元サーバーから削除した」は 3 回目の完了時に持ち越す |
| ops コンテナの `min_replicas` を 0 に戻す | **未実施（残作業）** | terraform 管理のため、本ドリルのセッションでは実行していない |

## この検証方式の限界

1〜2 回目で使った検証方式には既知の限界があり、そのまま 3 回目の設計課題になる。

- **digest 一致は「いつの時点に復元されたか」を直接証明していない。** アプリテーブル（`documents` / `object_properties` など）は
  2026-09-01 の embed Job 以降不変であり、どの復元指定時刻を選んでも digest は同じ値になる。
  digest が担保しているのは「データが壊れていないこと」であって「復元点が正しいこと」ではない。
  時点の正当性は `obs.pitr_sentinel` という**別テーブルの有無からの推論**に依存している
- **digest は `t::text` に落としたヒープ行しか見ていない。** HNSW インデックス・シーケンスの現在値・サーバーパラメータ・
  インストール済み拡張は、この照合を素通りする。これらが復元後に正しい状態かどうかは今回測っていない

**3 回目のドリルでは、この 2 点を推論ではなく直接測定に変える計画がある**（設計は別途レビュー中のため、本ファイルには詳細を書かない）。

## 残作業

- 両回の実測値が揃ったので、[restore-drill-recovery-objectives.md](../../operations/restore-drill-recovery-objectives.md) の
  aspirational target と実測の突き合わせを行う（本 Issue の対象外。別 Issue で扱う）
- ops コンテナの `min_replicas` を 0 に戻す（terraform 管理）
- `obs.pitr_sentinel` の DROP は 3 回目のドリル完了時まで持ち越す（上記「後片付けの状況」）
- 3 回目のドリルで、上記「この検証方式の限界」を直接測定に置き換える
