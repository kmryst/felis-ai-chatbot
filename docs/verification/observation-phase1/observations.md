# フェーズ 1（低負荷ベースライン 72h）の実測記録

計画の正本は [credit-window-execution-plan.md](../../operations/credit-window-execution-plan.md)
（§4 仕込み / §5 期間観測 / §5-2 日次チェック）。無料枠と確認手段の正本は
[azure-resource-inventory.md](../../operations/azure-resource-inventory.md)。
**時刻はすべて UTC**。値には取得コマンドと取得時刻を必ず添える。
再確認できなかった数値は「未検証」と明記し、断定しない。

- **T_obs_start = 2026-08-23T08:16:19.71Z**（計画 §4 の E2E 成功時刻の最大値）
- フェーズ 1 終了 = T_obs_start + 72h = **2026-08-26T08:16:19Z**（完走済み）
- 対象コミット: `main` = `56af4ae` / イメージ `sha-56af4ae` / alembic `0003`

> **フェーズ 1 は 2026-08-26T08:16:19Z に完走した。**
> 稼働率・レイテンシ・run 数の確定値は [§8](#8-フェーズ-1-の最終値固定-72h-窓)
> にある（固定 72h 窓・2026-08-26 取得）。
> §1〜§7 の数値は**それぞれ記載の取得時刻における中間値**のまま残してあり、
> 特に §4-5（22.5h 窓）と §6 の 6（70.7h 窓）の coverage は §8 の確定値に置き換わっている。
> 中間値を消していないのは、観測が進むにつれて値がどう動いたかを追えるようにするため。
> 本ファイルへの追記はすべて**失うと再取得できない証跡の保全**が目的で、
> Azure・GitHub Actions・`obs.phase_config` のいずれにも書き込みを行っていない（読み取りのみ）。

## 0. フィールド名の対応表（2026-08-26 の改名。Issue #133）

2026-08-26 に観測系の識別子を業界標準語へ揃えた（`obs.marker` -> `obs.heartbeat` =
heartbeat table、`code=` -> `http_code=` = curl の write-out 変数名）。
**本ファイルと `probe-records.jsonl` の証跡は、当時の名前のまま残している。**

| フェーズ 1 の証跡（旧名） | フェーズ 2 以降（新名） | 同一性 |
| --- | --- | --- |
| `marker_age` / `marker_age_seconds` | `heartbeat_age` / `heartbeat_age_seconds` | **同一の系列**（`obs.marker` を rename しただけで、テーブルもデータも連続している） |
| `code` | `http_code` | **同一の値**（curl の `%{http_code}`） |
| `obs.marker` | `obs.heartbeat` | 同一のテーブル（`ALTER TABLE ... RENAME`。migration `0004`） |
| `MARKER_MAX_AGE` | `HEARTBEAT_MAX_AGE` | 同一の閾値（600 秒） |

改名しない理由: `probe-records.jsonl`（131 行）は **抽出元の GitHub Actions ログとの
再現性を保つ**ために凍結している。`scripts/collect-probe-records.sh` は元ログの
`PROBE` 行から `k=v` を literal で抽出するため、JSONL 側だけ改名すると再抽出で
復元できなくなる。スクリプト側は新旧どちらのフィールド名も読めるようにし、
**出力キーは元ログに出ていた名前に追随する**ので、この窓を再抽出すれば
既存の 131 行と一致する（改名後の 2026-08-26 に実測で確認済み）。
同じ理由で `docs/verification/` 配下の過去の実測記録は当時の表記のまま残す。

**読み方の注記（2026-08-27 追記。本文は書き換えていない）**: 本記録が「低負荷ベースライン」と呼ぶ
区間の書き込みは、毎分 1 行の heartbeat INSERT + カウンタ 1 行 UPDATE のみである。これは
**PITR の復旧時点を確定させるための recovery marker**（既知の書き手）であり、autovacuum / bloat を
駆動する**負荷生成ではない**（負荷生成 = churn generator は Issue #112 / PR #120 の別装置で、
2026-08-27 時点で未マージ）。位置づけの正本は
[ADR-0021](../../adr/0021-heartbeat-table-as-recovery-marker.md)。
**本文の測定値・表記（「低負荷ベースライン」を含む）は当時のまま残し、書き換えない。**

## 1. デプロイ（2026-08-23）

### 1-1. plan の差分要約

**1 to add / 3 to change / 0 to destroy**（**未検証**: apply はローカル実行で、
GitHub Actions に terraform apply の workflow は存在せず（`.github/workflows/` に deploy 系なし）、
plan の生出力が残っていないため前任セッションの報告値をそのまま再現できない）。

ただし Activity Log による**間接的な裏付けは取れている**（2026-08-24T06:03Z 取得。
`az monitor activity-log list --start-time 2026-08-23T07:05:00Z --end-time 2026-08-23T07:20:00Z`）:

| ARM 操作 | 対象 | plan 上の種別（推定） |
| --- | --- | --- |
| `Microsoft.App/jobs/write` | `caj-felisaichatbot-dev-obs` | add（この apply で新設。初回 execution が 07:15:00Z） |
| `Microsoft.App/containerApps/write` | `ca-felisaichatbot-dev` | change |
| `Microsoft.App/containerApps/write` | `ca-felisaichatbot-dev-ops` | change |
| `Microsoft.App/jobs/write` | `caj-felisaichatbot-dev-migrate` | change |

同ウィンドウに delete 系の操作は 1 件もない（= 0 destroy と整合）。
「1 add / 3 change」も write の内訳と一致する。

### 1-2. タイムライン（Activity Log 実測。2026-08-24T06:03Z 取得）

| 時刻 (UTC) | イベント | 出所 |
| --- | --- | --- |
| 07:14:37 | `terraform apply` 開始 | **未検証**（前任報告。ローカル実行のためログなし） |
| 07:14:26 | provider の読み取り（`workspaces/sharedKeys/action` 等）開始 | Activity Log |
| 07:14:41 | 最初の write（`containerApps/write` = serving）Started | Activity Log |
| 07:14:49 | serving 新 revision `ca-felisaichatbot-dev--0000001` 作成 | `az containerapp revision list` |
| 07:14:54 | ops 新 revision `ca-felisaichatbot-dev-ops--0000003` 作成 | 同上 |
| 07:14:57 | `containerApps/write`（serving）Succeeded | Activity Log |
| 07:14:58 | `jobs/write`（migrate / obs）Succeeded | Activity Log |
| 07:15:03 | `containerApps/write`（ops）Succeeded = **最後の write** | Activity Log |
| 07:15:04 | apply 完了 | Activity Log（直後の listSecrets が 07:15:04）/ 前任報告と一致 |
| 07:15:00 | **obs Job の初回 execution（`...-obs-29791155`）が起動 → Failed**（§3-1） | job execution list / console log |
| 07:15:07 | serving 起動完了（`startup complete`） | ContainerAppConsoleLogs |
| 07:15:16 | `jobs/start/action`（migrate Job 手動起動 = alembic 適用） | Activity Log |
| 07:15:41.68 | `obs.phase_config` の初期行 insert（migration 0002 の実行時刻） | `SELECT since FROM obs.phase_config` |
| 07:16:18.84 | obs 3 系列の最初のレコード（marker / db_stats / table_stats / bloat_stats すべて同時刻） | obs テーブル |

### 1-3. 新 revision（2026-08-24T06:03Z 実測）

```console
$ az containerapp revision list -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev \
    --query "[].{name:name, created:properties.createdTime, active:properties.active, image:properties.template.containers[0].image, replicas:properties.replicas, state:properties.runningState}" -o json
[
  {
    "active": true,
    "created": "2026-08-23T07:14:49+00:00",
    "image": "felisaichatbotacrdev.azurecr.io/backend:sha-56af4ae",
    "name": "ca-felisaichatbot-dev--0000001",
    "replicas": 0,
    "state": "ScaledToZero"
  }
]
```

serving は revision 1 本のみ・`ScaledToZero`（= 常駐課金なし）。ops は
`ca-felisaichatbot-dev-ops--0000003` が `minReplicas: 1` で常駐（ADR-0015 追記 #100 の是正どおり）。

## 2. 観測開始 E2E（#104 / #106 / #107）

### 2-1. /chat 保護の遷移（#107）

アプリケーションログ（`ContainerAppConsoleLogs_CL`。2026-08-24T06:02Z 取得）で
**キー無し POST /chat の 401 を実測**した:

```text
2026-08-23T07:16:31.704Z  POST /chat  status_code=401  duration_ms=2.16
2026-08-23T07:16:31.755Z  POST /chat  status_code=401  duration_ms=1.49
2026-08-23T07:16:37.955Z  POST /chat  status_code=200  duration_ms=72.4   ("rag guard rejected")
```

- 前任報告の「07:16:30Z に 200 から 401 へ遷移」は、アプリログ上は **07:16:31.704Z / 07:16:31.755Z**
  が最初の 401。**秒未満の差は curl 実行時刻とログの `time` フィールドの差**で、遷移そのものは裏付けが取れている
- 07:16:37.955Z の 200 は**キー付きの正常系**（同一デプロイでのポジティブ確認）
- 本日（2026-08-24T05:52:56Z）の再実測も **401**:
  `curl -s -o /dev/null -w "%{http_code}" -X POST https://<serving FQDN>/chat -H 'Content-Type: application/json' -d '{"message":"ping"}'` → `401`

### 2-2. obs 3 系列の間隔実測（DB の実データ。2026-08-24T05:57Z 取得）

`az containerapp exec -n ca-felisaichatbot-dev-ops --command bash` 経由で psql（読み取りのみ）。

| 系列 | 設計間隔 | 件数 | 最初 | 最後 |
| --- | --- | --- | --- | --- |
| `obs.marker` | 1 分 | 1,349 | 2026-08-23 07:16:18.843824+00 | 2026-08-24 05:57:18.614009+00 |
| `obs.db_stats` | 5 分 | 242 | 2026-08-23 07:16:18.857677+00 | 2026-08-24 05:54:18.101655+00 |
| `obs.table_stats`（distinct ts） | 5 分 | 242 | 同上 | 同上 |
| `obs.bloat_stats`（distinct ts） | 1 時間 | 23 | 同上 | 2026-08-24 05:26:14.599403+00 |

pgstattuple（1 時間系列）の連続する ts の差（秒）:

```text
3600.85, 3654.93, 3604.00, 3661.50, 3600.11, 3603.42, 3661.20, 3650.11, 3603.85,
3602.85, 3652.46, 3606.27, 3658.04, 3603.61, 3655.78, 3601.15, 3601.09, 3600.18,
3658.38, 3655.96, 3603.55, 3656.47
```

- 前任報告の「bloat_stats 2 点間 3600.85 秒」は**そのまま再現できた**（最初の 2 点の差）
- 22 区間すべてが 3600〜3662 秒に収まる（設計 1 時間に対して最大 +61.5 秒）

marker（1 分系列）で 90 秒を超えたギャップは**意図的停止の 1 箇所のみ**:

```text
2026-08-23 07:31:21.823567+00 -> 2026-08-23 07:45:18.342327+00  gap = 837 秒
```

### 2-3. 意図的欠落の通知試験（計画 §4 の観測開始定義 3）

すべて GitHub Actions のログと Activity Log で**再確認済み**。

| 時刻 (UTC) | 事象 | 出所 |
| --- | --- | --- |
| 07:31:08〜07:31:09 | 採取停止の操作（`Microsoft.App/jobs/write` on `caj-felisaichatbot-dev-obs` の Started / Accepted） | Activity Log |
| 07:31:21.82 | 停止直前の最後の marker | `obs.marker` |
| 07:33 | obs Job の最後の execution（`...-obs-29791171`）。以降 07:46 まで起動なし | ContainerAppSystemLogs |
| 07:42:55 | probe run **32626299320** 開始（`workflow_dispatch`） | `gh run view` |
| 07:43:03.330 | `PROBE ts=2026-08-23T07:43:03.330Z code=200 latency_ms=466 obs=present marker_age=702 stats_age=946 pgstattuple_age=1605 enforce=true` | run log |
| 07:43:03.836 | `::error::freshness[marker] stale: 702s > 600s` | run log |
| 07:43:03.837 | `::error::freshness[stats] stale: 946s > 900s` | run log |
| 07:43:06 | run 32626299320 **failure** で終了 | `gh run view` |
| 07:44:14〜07:44:30 | 復旧操作（`Microsoft.App/jobs/write` Started → Succeeded） | Activity Log |
| 07:44:31 | 復旧後の `jobs/listSecrets/action` Succeeded | Activity Log |
| 07:45:18.34 | 復旧後の最初の marker | `obs.marker` |
| 07:45:36 | probe run **32626423993** 開始 | `gh run view` |
| 07:45:41.19 | `PROBE ts=2026-08-23T07:45:40.539Z code=200 latency_ms=618 obs=present marker_age=23 stats_age=23 pgstattuple_age=1762 enforce=true` | run log |
| 07:45:43 | run 32626423993 **success** で終了 | `gh run view` |

- **系列別判定が実際に効いていることの実証**: 同じ probe 実行で marker（702 > 600）と
  stats（946 > 900）は fail し、**pgstattuple（1605 < 10800）は fail しなかった**。
  束ねた 1 値なら「どれかが古い」しか分からず、どの系列が止まったかを通知で切り分けられない
- 閾値は workflow の env に実測で出ている: `MARKER_MAX_AGE=600` / `STATS_MAX_AGE=900` /
  `PGSTATTUPLE_MAX_AGE=10800` / `ENFORCE=true` / `PROBE_ENABLED=true`（計画 §5-3 の設計値と一致）
- **前任報告との差**: 停止時刻は前任報告 07:31:24Z、Activity Log の write は 07:31:08〜07:31:09Z。
  復旧は前任報告 07:44:31Z、Activity Log の write Succeeded は 07:44:30Z（listSecrets が 07:44:31Z）。
  いずれも CLI 実行の完了時刻と ARM イベント時刻の差の範囲で、**矛盾はない**

#### 通知先への到着記録（#104 / #106 の受け入れ条件）

この試験の目的は「採取が止まったら**気づける**」ことの実証なので、workflow が fail した事実だけでなく
**通知先に届いた事実**を残す。GitHub の通知インボックスに配送記録が残っていることを実測した。

```bash
gh api "notifications?all=true&since=2026-08-23T00:00:00Z"
# 2026-08-25T05:32:05Z 取得
```

`kmryst/felis-ai-chatbot` の `ci_activity` 通知（該当分を抜粋。値は生の JSON のまま）:

```json
{"id":"25247537220","reason":"ci_activity","subject_type":"CheckSuite",
 "subject_title":"readyz-probe workflow run failed for main branch",
 "updated_at":"2026-08-23T07:43:26Z","unread":true}
{"id":"25276989592","reason":"ci_activity","subject_type":"CheckSuite",
 "subject_title":"readyz-probe workflow run failed for main branch",
 "updated_at":"2026-08-24T22:22:58Z","unread":true}
```

| 事象 | run の failure 時刻 (UTC) | 通知の `updated_at` (UTC) | 差 |
| --- | --- | --- | --- |
| 意図的欠落試験（run 32626299320。本節の試験） | 2026-08-23T07:43:06Z | **2026-08-23T07:43:26Z** | **20 秒** |
| 自然発生の failure（run 32784303553。§3-5） | 2026-08-24T22:22:36Z | 2026-08-24T22:22:58Z | 22 秒 |

- **意図的欠落の検知が通知として着弾するまで 20 秒**。2 件目（意図的でない実際の失敗）でも 22 秒で、
  1 点の偶然ではない
- **これはメール受信の実証ではない**。実証できたのは **GitHub の通知インボックス
  （`GET /notifications`）への配送記録が生成されたこと**までであり、
  そこから先のメール / Web push の配送・到達・開封は本記録では確認していない（**未検証**）。
  メール到達まで含めて実証するには受信箱側の証跡が要る
- **今のうちに固定する理由**: `/notifications` は既読化すると `all=true` を付けない限り返らず、
  保持期間も GitHub 側の運用に依存する。上の 2 件は取得時点で `unread: true` だが、
  **この記録を取った時刻の状態として固定**しておく。後から同じ値を再取得できる保証はない

### 2-4. 観測開始チェックリスト（計画 §4）の現在値（2026-08-24 実測）

| # | 項目 | 実測 | 判定 |
| --- | --- | --- | --- |
| 1 | /chat が外部から 401 | 401（05:52:56Z） | OK |
| 2 | 3 系列すべてが設計間隔で積まれている | §2-2 のとおり | OK |
| 3 | 意図的欠落の通知試験に成功 | §2-3 のとおり | OK |
| 4 | 鮮度ゲートが有効（`OBS_FRESHNESS_ENFORCE` の false 上書きなし） | `gh variable list` の出力が空（リポジトリ変数ゼロ）= 既定 true。probe run の env も `ENFORCE: true` | OK |
| 5 | `PROBE_ENABLED` が true | 同上（run env に `PROBE_ENABLED: true`） | OK |
| 6 | `obs.phase_config` が `baseline` | `1\|baseline\|2026-08-23 07:15:41.678169+00`（05:53Z 取得） | OK |

## 3. 構造的な発見（設計に効く知見）

### 3-1. cron Job を migration より先に作る apply 順序は、初回に必ず 1 回失敗する

obs Job（`* * * * *`）は apply の中で 07:14:58Z に作成され、**alembic の適用（07:15:16Z 起動）より前**に
07:15:00Z の分の execution が走った。その結果:

```text
psql:/app/observability/collect.sql:27: ERROR:  relation "obs.marker" does not exist
LINE 1: INSERT INTO obs.marker DEFAULT VALUES;
```

システムログ（同 execution）:

```text
2026-08-23T07:17:42Z  Warning ProcessExited  Pod - caj-felisaichatbot-dev-obs-29791155-88ln5 has a
                      failed container with name: obs-collect, exit code: 3, and reason: ProcessExited
```

- **毎分 cron の Job を Terraform で作る場合、スキーマを作る migration が後段にある限り、
  最初の 1 回の失敗は構造的に不可避**（Job 作成の瞬間から cron が回り始めるため）
- 実害はない（次の分から成功）が、「Job 失敗数 0 件」を受け入れ条件にすると**初回だけ必ず落ちる**。
  日次チェックの失敗カウントは「初回の 1 件を既知として除外する」か、apply 順序を
  「migration → Job 作成」に変える必要がある
- exit code 3 = `psql -v ON_ERROR_STOP=1` の実行時エラー

### 3-2. 経過時間ベース判定により、5 分系列の間隔がラチェット状にずれる

`collect.sql` の 5 分系列は `max(ts) <= now() - interval '5 minutes'` で判定する
（毎分起動の Job のうち条件を満たした回だけ採取）。この判定は「前回から 5 分**以上**」なので、
前回採取が :xx:18.86 のとき次の分（+300.0 秒より僅かに手前）は条件を満たさず、
**1 分後（= +360 秒）にずれる**。実測の間隔分布（241 区間。2026-08-24T05:57Z 取得）:

| 間隔 (秒) | 件数 |
| --- | --- |
| 300〜307 | 99 |
| 312 | 1 |
| 348〜367 | 139 |
| 377 | 1 |
| 1081 | 1（§2-3 の意図的停止） |

先頭 4 点の実データ:

```text
2026-08-23 07:16:18.857677+00   (基準)
2026-08-23 07:21:20.331649+00   +301
2026-08-23 07:27:17.846935+00   +358
2026-08-23 07:45:18.356982+00   +1081  ← 意図的停止
```

- 前任報告の「300 → 358 → 360 秒とラチェット状にずれる」は**再現できた**（301 → 358）。
  ただし「単調にずれ続ける」のではなく、**約 300 秒台と約 360 秒台の 2 つのモードを行き来する**
  （140 対 100 で 360 秒台のほうがやや多い。上表の 348〜367 と 377 を 360 秒台、300〜307 と 312 を 300 秒台として数えた）。ずれは累積せず、5 分の名目に対し実効は約 5.6 分
- 設計意図（コメントに明記のとおり「遅延時はその回で追いつき、二重起動時は 2 回目がスキップされる」）は
  満たしている。**5 分ちょうどの等間隔にはならない**という制約を、分析時に前提として持つ必要がある
- 22.6 時間で 242 点。等間隔 5 分なら 271 点なので**約 89%**

### 3-3. 「SQL は完走しているのに execution は Failed」— replicaTimeout 55 秒による打ち切り

obs Job の失敗 3 件のうち 2 件（2026-08-23T11:53:00Z / 2026-08-24T01:00:00Z）は、
コンソールログ上は **BEGIN 〜 COMMIT がすべて出ており SQL は完走**している。
にもかかわらず Failed で、`ProcessExited` イベントが**存在しない**:

```text
2026-08-23T11:53:55.287Z  Normal SuccessfulDelete  Deleted pod: caj-felisaichatbot-dev-obs-29791433-f92k2
2026-08-24T01:00:55.335Z  Normal SuccessfulDelete  Deleted pod: caj-felisaichatbot-dev-obs-29792220-8brhm
```

いずれも **開始 + 55 秒ちょうど**で pod が削除されている（Job の
`replicaTimeout: 55` / `replicaRetryLimit: 0`。`az containerapp job show` で実測）。

- exit code の集計（ContainerAppSystemLogs、2026-08-23T00:00Z 以降）: **exit 0 が 1,332 件 /
  exit 3 が 1 件**（= §3-1 の初回のみ）。タイムアウトで殺された 2 件は exit code を残さない
- **データは欠けていない**: この 2 件の分の marker も入っており（§2-2 の marker ギャップは
  意図的停止の 1 箇所のみ）、`INSERT`/`COMMIT` はログに出ている。
  打ち切られたのは psql プロセスの終了処理側
- **教訓**: 「Job の execution status」と「採取データの完全性」は別物。status だけを見ると
  データがあるのに障害と誤認し、データだけを見るとタイムアウトの兆候（フェーズ 2 の高負荷で
  顕在化しうる）を見落とす。**両方を日次チェックに入れる**（本記録の §4 はそうしている）
- 原因は**未特定**。55 秒に張り付いている以上「たまたま遅かった」ではなく、
  接続確立か終了処理のどこかで待たされている可能性が高い（**未検証**）

### 3-4. `az containerapp job execution list` は履歴上限があり、失敗率の分母にならない

計画 §5-2 の日次チェックコマンド
（`... execution list --query "[?properties.status!='Succeeded'] | length(@)"`）は
**失敗件数は出せるが、成功件数（= 分母）が上限で切られる**:

```console
$ az containerapp job execution list -g rg-felisaichatbot-dev-tf -n caj-felisaichatbot-dev-obs --query "length(@)"
103        # 内訳: Succeeded 100 / Failed 3
```

毎分 cron で 22.6 時間なら約 1,356 回のはずが 103 件しか返らない（Succeeded がちょうど 100 =
履歴上限）。**成功率を出すには Log Analytics 側で数える**必要がある:

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated > datetime(2026-08-23T00:00:00Z)
| where Log_s has "caj-felisaichatbot-dev-obs" and Reason_s == "AssigningReplica"
| summarize c=count() by bin(TimeGenerated, 1h)
```

- なお Log Analytics の `AssigningReplica` 件数にも取り込み遅延由来の欠落があり
  （2026-08-24T04:09〜04:17Z が 0 件に見える）、**同区間の marker には欠落がない**ため
  ログ側の見かけ上の穴と判断した。**採取の完全性の一次証拠は obs テーブルの実データ**であり、
  ログ件数は補助に留める

### 3-5. `gh run view --log` は failure run に対して 0 バイトを返す — SLI で最重要のレコードだけが黙って落ちる

`readyz-probe.yml:20-22` のコメントに書かれた集計例

```bash
gh run list -w readyz-probe.yml --json databaseId -q '.[].databaseId' |
  xargs -I{} gh run view {} --log | grep '^PROBE '
```

を実際に走らせると **4 つの欠陥が重なって、可用性 SLI の分子も分母も出ない**。
すべて 2026-08-25T05:30〜05:31Z に実測した（`gh version 2.45.0`。読み取りのみ）。

**(a) failure run では `--log` が 0 バイトを返す**

```console
$ gh run view 32784303553 --log | wc -c
0                    # 終了コードは 0。エラーメッセージも出ない
$ gh run view 32784303553 --log-failed | wc -c
0
$ gh run view 32812396447 --log | wc -c      # 同 workflow の success run
15539
```

- run 32784303553 は 2026-08-24T22:22:02Z 開始 / 22:22:36Z 完了の **`schedule` 起動の failure**
  （job `probe` = `databaseId 97612882777`、conclusion `failure`）
- **success では取れて failure では取れない**。可用性 SLI で数えたいのはまさに failure なので、
  この集計例は**最重要のレコードだけを無言で取りこぼす**。失敗が 0 バイトで返るため
  「失敗 run にはログが無い」ようにも見え、**欠落に気づけない**
- 原因の特定は本記録の範囲外（**未検証**）。事実として再現することのみを記録する

**REST なら取得できる**:

```console
$ gh api /repos/kmryst/felis-ai-chatbot/actions/jobs/97612882777/logs | wc -c
10157
$ gh api /repos/kmryst/felis-ai-chatbot/actions/jobs/97612882777/logs | grep 'PROBE ts='
2026-08-24T22:22:35.2752405Z PROBE ts=2026-08-24T22:22:05.250Z code=000 latency_ms=30000 obs=absent marker_age=null stats_age=null pgstattuple_age=null enforce=true
```

この 1 行が失われていた実データで、`code=000`（curl 失敗）= **可用性 SLI の分子から外れる 1 点**。
なお `latency_ms=30000` は実測値ではなく curl 失敗時の固定フォールバック値（Issue #115 の対象 3）。

**(b) `gh run list` は `--limit` 無しだと 20 件しか返さない**

```console
$ gh run list -w readyz-probe.yml --json databaseId -q '.[].databaseId' | wc -l
20
$ gh run list -w readyz-probe.yml --limit 300 --json databaseId -q '.[].databaseId' | wc -l
94        # 2026-08-25T05:31Z 時点の中間値。フェーズ 1 は 8/26 08:16Z まで継続中で、
          # これは最終的な run 総数ではない
```

集計例には `--limit` が無いため、**母集団が 20 件に暗黙に切られる**（§3-4 の
`execution list` 履歴上限と同じ種類の罠）。

**(c) `grep '^PROBE '` は 0 件になる**

`gh run view --log` の各行には `ジョブ名 TAB ステップ名 TAB タイムスタンプ` のプレフィクスが付く:

```text
probe<TAB>Probe /readyz and evaluate per-series freshness<TAB>2026-08-25T05:20:01.8464356Z PROBE ts=2026-08-25T05:19:41.796Z code=200 ...
```

したがって行頭は常に `probe` であり、`grep '^PROBE '` のパターンには**構造上一致しない**。

```console
$ gh run view 32812396447 --log | grep -c '^PROBE '
0
```

**(d) `^` を外すと今度は二重計上する**

```console
$ gh run view 32812396447 --log | grep -c 'PROBE '
3
```

1 run のレコードは 1 行のはずが 3 行返る。残り 2 行は `set -x` 相当のコマンドエコー行
（`echo "PROBE disabled via repository variable ..."` と `echo "PROBE ts=$ts code=$code ..."`）で、
**未展開の変数を含んだ行を実レコードとして数えてしまう**。

**ログが唯一の一次証跡である**:

```console
$ gh api repos/kmryst/felis-ai-chatbot/actions/permissions/artifact-and-log-retention
{"days":90,"maximum_allowed_days":90}
$ gh api repos/kmryst/felis-ai-chatbot/actions/artifacts --jq '.total_count'
0
```

- probe は artifact を 1 件も残していないため、**PROBE レコードは Actions ログの中にしか存在しない**
- 保持は 90 日（`maximum_allowed_days` も 90 で、設定でこれ以上は延ばせない）。
  teardown 目安（2026-09-04）から数えて 90 日後は 2026-12-03 頃で、それ以降は
  **SLI の生データが復元不能になる**。フェーズ 1 終了後に REST 経由でレコードを抽出して
  リポジトリへ保全することを検討する
  → **実施済み**: `scripts/collect-probe-records.sh`（Issue #127）。
  フェーズ 1 の 131 レコードは [probe-records.jsonl](./probe-records.jsonl) に保全した（§8-2）

> **TODO（2026-08-26 以降・別作業）**: `readyz-probe.yml:20-22` の集計例コメントを、
> 上記 (a)〜(d) を踏まえた実際に動く手順（`gh run list --limit N` で run を列挙 → 各 run の
> job id を取り、`gh api /repos/.../actions/jobs/<job_id>/logs` から
> `grep -o 'PROBE ts=.*'` で抽出）へ差し替える。
> **本記録の時点では workflow ファイルを一切変更していない**。`.github/workflows/` への
> commit は workflow の再登録を伴い、進行中のフェーズ 1（〜2026-08-26T08:16Z）の
> 観測条件を変えうるため、**フェーズ 1 完走後に別 Issue / 別 PR で行う**。

## 4. 日次チェック（計画 §5-2）— 2026-08-24

すべて読み取りのみ。Azure への書き込み・Issue/PR 操作・`readyz-probe` への介入は行っていない。

### 4-1. コスト

| 項目 | 値 | 取得コマンド | 取得時刻 (UTC) |
| --- | --- | --- | --- |
| クレジット残（current / estimated） | 200.00 / **199.38** USD | 計画 §8 の balanceSummary API（`BA`/`BP` を CLI で取得して `az rest`） | 2026-08-24T05:50:36Z |
| estimated の日次差分 | **-0.30 USD/日**（2026-08-23T07:04Z の 199.68 → 2026-08-24T05:48Z の 199.38。前日値は前任セッションの実測） | 同上 | 同上 |
| 累計消費（estimated 基準） | 0.62 USD（200.00 - 199.38） | 同上 | 同上 |

**確定分（= 前日以前）の実額**。`az rest .../Microsoft.Consumption/usageDetails?api-version=2024-08-01`
（`$filter=properties/usageStart ge '2026-08-19' and properties/usageEnd le '2026-08-24'`、54 レコード、
`nextLink` なし。2026-08-24T06:01:46Z 取得）。**請求通貨は JPY**:

| 日付 (UTC) | 確定コスト (JPY) | 備考 |
| --- | --- | --- |
| 2026-08-19 | 2.361 | Azure OpenAI の初期検証のみ |
| 2026-08-20 | 0.001 | |
| 2026-08-21 | 19.462 | PostgreSQL 作成（05:59Z）以降 |
| 2026-08-22 | 29.831 | VNet 統合カットオーバー（VNet / 公開 IP / private DNS 追加） |
| **2026-08-23** | **49.740** | **最初の丸 1 日分。これが確定した日額の基準** |
| 2026-08-24 | 0.938 | **未確定（部分反映）**。06:01Z 時点で network 系 4 レコードのみ |

2026-08-23（確定した丸 1 日）の内訳:

| 課金対象 | メーター | 数量 | コスト (JPY) |
| --- | --- | --- | --- |
| Container Registry | Basic Registry Unit | 1.000008 /Day | 27.303 |
| Network | Standard IPv4 Static Public IP | 24 時間 | 19.666 |
| Network | Private Zone | 0.0323 | 2.643 |
| Network | Private Queries | 0.0019 M | 0.125 |
| Storage | All Other Operations | 0.0042 (10K) | 0.003 |
| **PostgreSQL** | **B1MS Compute - Free** | **23 時間** | **0** |
| **PostgreSQL** | **Storage Data Stored - Free** | 0.989 GB/Month | **0** |
| Log Analytics | Analytics Logs Data Ingestion | 0.006408 GB | 0 |
| その他（Free メーター 5 件） | — | — | 0 |
| **合計** | | | **49.740** |

- **PostgreSQL の compute / storage はいずれも `- Free` メーターで課金 0**。日額の実体は
  **ACR Basic（27.3 JPY/日 ≒ 0.165 USD）と静的公開 IP（19.7 JPY/日 ≒ 0.12 USD）**で、
  この 2 つで 94% を占める
- 為替の逆算: 49.74 JPY ÷ 0.30 USD ≒ **166 JPY/USD**。8/19〜8/23 の累計 101.395 JPY ÷
  累計消費 0.62 USD ≒ 164 JPY/USD で整合する（**estimated と usageDetails は別系統の値だが矛盾しない**）
- **Container Apps（`Microsoft.App`）のメーターが 1 件も現れていない**（Free メーターすら無い）。
  ops レプリカが 24/7 常駐している（0.25 vCPU / 0.5 GiB）以上、無料付与枠に収まっているか
  反映されていないかのどちらかだが、**理由は未検証**。付与枠を使い切った時点で日額が跳ねる可能性があり、
  日次チェックで `Microsoft.App` メーターの出現を継続監視する

### 4-2. バックアップ使用量 / 復元ウィンドウ

```console
$ az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
    --query "{state:state, earliest:backup.earliestRestoreDate, retention:backup.backupRetentionDays, geo:backup.geoRedundantBackup, sku:sku, ha:highAvailability.mode, mw:maintenanceWindow, storage:storage.storageSizeGb}" -o json
# 2026-08-24T05:50:40Z
{
  "earliest": "2026-08-22T07:16:21.309783+00:00",
  "geo": "Enabled",
  "ha": "Disabled",
  "mw": { "customWindow": "Enabled", "dayOfWeek": 3, "startHour": 17, "startMinute": 0 },
  "retention": 7,
  "sku": { "name": "Standard_B1ms", "tier": "Burstable" },
  "state": "Ready",
  "storage": 32
}
```

- `earliestRestoreDate` は**サーバー作成時刻（2026-08-22T07:16:21Z）に固定されたまま動いていない**
  （保持 7 日の窓がまだ満杯でないため。動き出す予測日と時系列の記録は
  [restore-drill/observations.md](../restore-drill/observations.md) が正本）
- `backup_storage_used` の推移は同ファイルに記録した（**8/23 07:00〜08:00Z に 10.4 MB → 1.33 GB の
  ステップ**を実測）

### 4-3. 採取ジョブの生存

```console
$ az containerapp job execution list -g rg-felisaichatbot-dev-tf -n caj-felisaichatbot-dev-obs \
    --query "[?properties.status!='Succeeded'] | length(@)"
3        # 2026-08-24T05:50:47Z
```

**失敗は 0 件ではない**。3 件すべての内訳を実データで確認した:

| execution | 開始 (UTC) | 原因 | データ欠落 |
| --- | --- | --- | --- |
| `...-obs-29791155` | 2026-08-23T07:15:00 | `relation "obs.marker" does not exist`（exit 3）。§3-1 の構造的な初回失敗 | なし（次の分から成功） |
| `...-obs-29791433` | 2026-08-23T11:53:00 | replicaTimeout 55 秒で pod 削除。SQL は完走。§3-3 | なし |
| `...-obs-29792220` | 2026-08-24T01:00:00 | 同上 | なし |

- 採取データ側の欠落は**意図的停止の 837 秒（§2-2）1 箇所のみ**
- 成功率の分母は execution list では取れない（§3-4）。ログ側の実測は
  exit 0 が 1,332 件 / exit 3 が 1 件

### 4-4. Service Health / 計画メンテナンス

```console
$ az monitor activity-log list --offset 5d \
    --query "[?category.value=='ServiceHealth' || category.value=='ResourceHealth']" -o json
[]        # 2026-08-24T06:00:41Z

$ az rest --method get --url ".../providers/Microsoft.ResourceHealth/events?api-version=2022-10-01" \
    --query "value[]" -o json
[]        # 同時刻
```

- **Service Health / Resource Health のイベントは 0 件**（直近 5 日）。計画メンテナンスの予告もなし
- メンテナンスウィンドウ設定は `customWindow: Enabled / dayOfWeek: 3（水） / 17:00 UTC`（§4-2 の出力）。
  **次の窓は 2026-08-26T17:00Z**。フェーズ 1 終了（8/26 08:16Z 頃）の直後にあたるため、
  計画 §3 の 8「計画メンテナンス遭遇」の観測機会は 8/26 の窓が本命になる
- 計画 §3 の 8 は「当たらなければ当たらなかったと記録する」としている。**8/24 時点では未遭遇**

### 4-5. obs 3 系列の鮮度（/readyz）と積み上がり

```console
$ curl -s https://ca-felisaichatbot-dev.blackbush-a1db7f50.japaneast.azurecontainerapps.io/readyz
# 2026-08-24T05:52:56Z, http=200, time_total=0.169s
{"status":"ok","db":"ok","obs":{"marker_age_seconds":37,"stats_age_seconds":277,"pgstattuple_age_seconds":1602}}
```

3 系列とも閾値（600 / 900 / 10800 秒）に対して十分新しい。DB の実データ側の積み上がりは §2-2。

外形監視（`readyz-probe` workflow）の実績（`gh run list --workflow readyz-probe.yml --limit 300`。
2026-08-24T06:05Z 取得。**workflow には一切触れていない — 読み取りのみ**）:

| 項目 | 実測 |
| --- | --- |
| 期間 | 2026-08-23T07:18:32Z 〜 2026-08-24T05:50:31Z（22.53 時間） |
| 総 run 数 | 56（`schedule` 53 / `workflow_dispatch` 3） |
| conclusion | success 55 / failure 1（failure は §2-3 の意図的試験 32626299320） |
| **5 分間隔での期待 run 数** | **270** |
| **実際の scheduled run 数** | **53（19.6%）** |
| 実測の平均間隔 / 中央値 / 最大 | **24.58 分 / 20.6 分 / 98.8 分** |

- **可用性 SLI（計画 §3 の 7）の点数が設計の約 1/5 しか取れていない**。原因は
  GitHub Actions の schedule 配送レート（外部レビューに提出中の論点）。
  **本セッションでは条件を変えない**（cron 変更・無効化・手動実行のいずれも未実施）
- 最大 98.8 分の空白は、**鮮度ゲートの検知遅延がその分だけ伸びる**ことを意味する
  （マーカー閾値 600 秒に対し、通知は最悪 1.6 時間遅れる）。無音失敗の一次防衛としては
  計画 §5-3 の想定（probe 5 分間隔）より弱い

### 4-6. `obs.phase_config`

```console
$ psql "$DATABASE_URL" -At -F"|" -c "SELECT id, phase, since FROM obs.phase_config"
1|baseline|2026-08-23 07:15:41.678169+00        # 2026-08-24T05:53Z 取得（ops 経由）
```

`baseline` のまま。フェーズ遷移の手動 UPDATE は行っていない。

### 4-7. 参考: 観測データの現況（計画 §3 の各項目）

2026-08-24T05:57Z 取得（ops 経由 psql、読み取りのみ）。

**autovacuum の自然発火（§3 の 1）** — `obs.table_stats` の最大値:

| relname | autovacuum_count | last_autovacuum | autoanalyze_count | max(n_dead_tup) | max(n_live_tup) |
| --- | --- | --- | --- | --- | --- |
| `counter` | **26** | 2026-08-24 05:35:41.390843+00 | 26 | 50 | 1 |
| `marker` | **1** | 2026-08-24 03:46:39.486007+00 | 13 | 0 | 1,345 |
| `table_stats` | 2 | 2026-08-24 04:54:40.675901+00 | 18 | 0 | 2,892 |
| `db_stats` | 0 | — | 4 | 0 | 241 |
| `bloat_stats` | 0 | — | 0 | 0 | 46 |

- `counter`（1 行 UPDATE / 分）が 22.6 時間で **26 回自然発火**（約 52 分周期）。
  設計時の予測「閾値 50 + 0.2×1 ≈ 50 → 約 50 分周期」と整合
- `marker`（INSERT-only）は **1 回のみ**。閾値
  `autovacuum_vacuum_insert_threshold + autovacuum_vacuum_insert_scale_factor × reltuples`
  = `1000 + 0.2 × reltuples` が行数の増加とともに上がるため、
  発火間隔が延びていく過程（計画 §3 の 1）はまだ 1 点しか取れていない
- **この 1 点で当初の発火予測が外れたことが判明した（2026-08-26 訂正）**:
  - **予測（当初）16.7h / 実測 20.5h**。観測開始 2026-08-23 07:16:18 →
    `last_autovacuum` 2026-08-24 03:46:39 = 20 時間 30 分 21 秒
  - **原因**: 当初は閾値の `reltuples` を「前回 vacuum 時点の行数」として計算していたが、
    `pg_class.reltuples` は **ANALYZE でも更新される**。PostgreSQL 17 公式は
    "It is updated by `VACUUM`, `ANALYZE`, and a few DDL commands such as `CREATE INDEX`." と定義する。
    `marker` は analyze 側の閾値 `50 + 0.1 × reltuples` を INSERT だけで頻繁に越えるので、
    `reltuples` はほぼ現在行数に追随し、vacuum を待つ間も閾値が上がり続ける
  - **補正式と再計算**: 前回 vacuum 以降の INSERT 行数 m が
    `m > 1000 + 0.2 × (前回 vacuum 時点の行数 + m)` で発火。初回は `0.8 m > 1000` →
    m = 1250 行 = 1250 分 = **20.8h**。実測 20.5h と一致する
    （実測がわずかに早いのは `reltuples` が直近 ANALYZE 時点の値で現在行数よりやや小さいため）
  - **補正後の系列**: 発火間隔は公比 1.25 の等比列で **20.8h → 46.9h → 79.4h → 120.1h → 171.0h**。
    フェーズ 1 の 72h で入る発火は **2 回**（当初計画の「3 回」は誤り。計画側も訂正済み）

**WAL / DB サイズ / XID age（§3 の 6・10）** — `obs.db_stats` の最初と最後:

| | ts | wal_records | wal_bytes | db_size_bytes | frozen_xid_age |
| --- | --- | --- | --- | --- | --- |
| 最初 | 2026-08-23 07:16:18.857677+00 | 52,733 | 6,239,010 | 8,681,139 | 11,597 |
| 最後 | 2026-08-24 05:54:18.101655+00 | 101,967 | 11,369,686 | 9,311,923 | 24,049 |
| **差分（22.63 時間）** | | **+49,234** | **+5,130,676 B（4.89 MiB）** | **+630,784 B** | **+12,452** |

日額換算: WAL 約 **5.2 MiB/日** / DB サイズ約 **+0.64 MiB/日** / XID age 約 **+13,200/日**
（いずれも 22.63 時間の差分を 24 時間へ線形換算した値。低負荷ベースライン下のレートであり、
フェーズ 2 の高負荷では成り立たない）。
XID age についての当初の記述（「wraparound 閾値 20 億まで約 15 万日」）は**外挿の分母を取り違えていた**。
20 億に到達する前に `autovacuum_freeze_max_age` による anti-wraparound autovacuum が走るため、
**20 億には到達しない**。PostgreSQL 17 公式は
"To ensure that this does not happen, autovacuum is invoked on any table that might contain unfrozen
rows with XIDs older than the age specified by the configuration parameter `autovacuum_freeze_max_age`.
(This will happen even if autovacuum is disabled.)" と定める。
したがって外挿すべき分母は既定 2 億で、**約 1.5 万日**（200,000,000 ÷ 13,206）で
anti-wraparound autovacuum が走る計算になる。結論は変わらず
**本プロジェクトの期間では問題にならない**（2026-08-26 訂正）。

> **当初は未実測の前提だった（2026-08-26 に解消）**: この 2 億は `autovacuum_freeze_max_age` の
> **公式ドキュメント記載の既定値**で、計画 §5-4 の実測表にある他の autovacuum パラメータと違って
> 本環境の `pg_settings` では実測していなかった。**[§9-5](#9-5-autovacuum_freeze_max_age-の実測) で
> `pg_settings` の実測値が 200000000 であることを確認した**ため、上の外挿は実測値に基づく。

**閾値レンジ（§3 の 3）** — Azure Monitor、`--interval PT5M`、
`--start-time 2026-08-23T08:16:00Z --end-time 2026-08-24T06:05:58Z`（**end-time を必ず指定**。
未指定だと未来時刻に 0.0 のフィラーが入る既知の罠）。n = 262 点:

| メトリック | avg | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- |
| `cpu_percent` | 11.19 | 11.10 | 12.23 | 20.81 | 56.46 |
| `memory_percent` | 56.25 | 56.29 | 57.32 | 57.60 | 58.53 |
| `active_connections` | 6.31 | 6.20 | 7.00 | 7.20 | 9.00 |
| `storage_percent` | 13.12 | 13.12 | 13.13 | 13.13 | 13.13 |

`cpu_credits_remaining`（PT1H）は 2026-08-23T08:16Z の 152.5 から 2026-08-24T05:16Z の
**253.7 まで増加**（Burstable のクレジットを消費しきっていない = 低負荷ベースラインとして健全）。

**Log Analytics 取込量（§3 の 11）** — `Usage | where IsBillable == true`（2026-08-24T06:01:34Z）:

| 日付 (UTC) | 課金対象取込量 (GB) |
| --- | --- |
| 2026-08-21 | 0.0000 |
| 2026-08-22 | 0.0001 |
| 2026-08-23 | **0.0063**（obs Job 稼働の丸 1 日） |
| 2026-08-24（06:01Z まで） | 0.0023 |

内訳は `ContainerAppSystemLogs_CL` と `ContainerAppConsoleLogs_CL` がほぼ半々。
**月換算で約 0.19 GB** と小さく、課金額も 0 JPY（§4-1 の内訳表）。
ADR-0016 が「放置時の総額は実測していない」とした項目に対する初回の実測値。

## 5. PostgreSQL 12か月無料枠 750 時間の消費状況（計画の宿題。期限 2026-08-23 → 8/24 実施）

台帳（[azure-resource-inventory.md](../../operations/azure-resource-inventory.md)）の
「750 時間の消費状況の確認手段」節は **CLI 経路を「未実測」**としていた。本セッションで
**usageDetails 経由の確認手段を確立した**（台帳の更新はこの記録を出典にできる）:

```bash
SUB=$(az account show --query id -o tsv)
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/usageDetails?api-version=2024-08-01&\$filter=properties/usageStart%20ge%20'2026-08-19'%20and%20properties/usageEnd%20le%20'2026-08-24'&\$top=1000" -o json
# → properties.meterName == "B1MS Compute - Free" の quantity（unitOfMeasure = "1 Hour"）を日別に合計する
```

実測（2026-08-24T06:01:46Z 取得）:

| 日付 (UTC) | B1MS Compute - Free (時間) | コスト | 備考 |
| --- | --- | --- | --- |
| 2026-08-21 | 18 | 0 | サーバー作成 05:59Z → 24:00Z で 18 時間 |
| 2026-08-22 | 24 | 0 | VNet カットオーバーの再作成（07:08 destroy / 07:16 create）を含む |
| 2026-08-23 | 23 | 0 | 反映途中の可能性あり（丸 1 日なら 24） |
| **累計（確定分）** | **65** | **0** | |
| 2026-08-24 | （未反映） | — | 06:01Z 時点で PostgreSQL メーターの当日分レコードなし |

- メーター名が `B1MS Compute - Free` でコストが 0 = **無料枠が適用されていることを実データで確認**した
  （従来は「無料枠の対象のはず」という台帳上の記載だけだった）
- **反映ラグの実測**: 8/24 06:01Z 時点で当日分の PostgreSQL メーターは未反映、
  network 系の一部のみ反映。台帳の「1〜2 日程度の遅延」と整合する

### 5-1. teardown 目安（2026-09-04）までの見込み

無料枠は**暦月単位で 750 時間**（台帳の記載）。月をまたぐのでそれぞれ積む:

| 月 | 内訳 | 合計 (時間) | 750h に対して |
| --- | --- | --- | --- |
| 2026-08 | 8/21 18h + 8/22 24h + 8/23 24h + 8/24〜8/31 の 8 日 × 24h = 192h | **258** | **34.4%** |
| 2026-09 | 9/1〜9/3 の 3 日 × 24h + 9/4 の teardown までの部分（最大 24h） | **最大 96** | **12.8%** |

- **超過リスクなし**。8 月は 8/21 から月末まで**連続稼働しても 258 時間**で、750 時間の 3 分の 1 強
- PITR ドリル（8/28 / 9/2）で復元先の B1ms がもう 1 台立ち、
  台帳の未確定事項どおり 750 時間に**合算されると仮定**しても、各ドリル数時間なら 8 月で +10 時間程度。
  仮に**復元先を月末まで消し忘れて放置**しても 8 月は 258 + 約 100 = 約 360 時間で、なお枠内
- 計画 §6 の (b) で B1ms → General Purpose に昇格する 2 日間（8/31〜9/1 目安）は
  **B1MS メーターではなく GP メーターに乗り、そちらは無料枠の対象外**（計画 §1-2）。
  この間は B1MS の消費が止まるため、上表はさらに保守側
- したがって**「750 時間を超える見込み」は無い**。台帳の未確定事項（複数台並行時の合算・
  停止中の扱い）はいずれも本プロジェクトの結論を変えない

## 6. 計画の記載と実測が食い違った点

| # | 計画の記載 | 実測 | 影響 |
| --- | --- | --- | --- |
| 1 | §1-3 / §8: (a) ベースラインの日額は期待 1.5 / ワースト 2.1 USD | **確定日額 0.30 USD（8/23）**。上限 90 USD に対し teardown 9/4 まで積んでも約 4 USD | 上限・打ち切り基準は**まったく逼迫しない**。§5-2 の中間チェックポイント（8/27〜）は形骸化するが、想定外の消費の早期検知として維持する意味は残る |
| 2 | §1-2: ops 常駐は active 0.648 USD/日 | `Microsoft.App` のメーターが 8/23 まで**1 件も出ていない** | 上記 1 の主因。ただし**無料付与枠に収まっているのか未反映なのかは未検証**。枠を使い切った時点で日額が跳ねうるので継続監視 |
| 3 | §1-2: 日額の内訳は PostgreSQL compute 0.624 USD が最大 | PostgreSQL は compute / storage とも **`- Free` メーターで 0**。実際の最大費目は **ACR Basic（27.3 JPY/日）と静的公開 IP（19.7 JPY/日）** | 費目の見立てが違っていた。ACR / 公開 IP は §1-2 の単価表に**行が無い** |
| 4 | §5-2: 採取ジョブの生存は `execution list` の非 Succeeded 件数で見る | 失敗件数は取れるが**成功件数が履歴上限 100 で切られ、成功率の分母にならない**（§3-4） | 日次チェックのコマンドを Log Analytics 併用に改める必要がある |
| 5 | §5-3: 統計スナップショットは 5 分間隔 | 実効は **約 300 秒台と約 360 秒台の 2 モード**（§3-2）。22.6 時間で 242 点 = 等間隔想定の 89% | 分析時に「等間隔ではない」前提が要る。設計意図そのものは満たしている |
| 6 | §5-3: 鮮度ゲートは probe 5 分間隔で「即日検知」 | **固定 72h 窓の確定値で coverage 15.2%（131 / 864）、最大無観測 102.8 分**（§8-3。中間値は 22.5 時間で 53 回 = 19.6% だった） | 検知遅延が最悪 1.7 時間。SLI の点数も設計の約 1/7。原因は外部レビュー中のため**本セッションでは条件を変えていない** |
| 7 | §4 の観測開始定義: Job 失敗 0 件を前提に読める書き方 | **cron Job を migration より先に作る apply 順序では初回 1 回の失敗が構造的に不可避**（§3-1） | 受け入れ条件の書き方を「既知の初回失敗を除外」に直すか、apply 順序を変える |
| 8 | §3 の 5: バックアップ使用量は緩やかな推移を想定 | **8/23 07:00〜08:00Z に 10.4 MB → 1.33 GB のステップ**（[restore-drill/observations.md](../restore-drill/observations.md)） | 無料枠 32 GB に対しては 4% で余裕。ただしステップの周期が日次か週次かは**未検証**（8/24 07:00Z 以降の観測で判別できる） |
| 9 | `readyz-probe.yml:20-22`: 集計例コメント（`gh run list` の出力を `xargs gh run view --log` に流して `grep '^PROBE '` する手順）で SLI を集計できる前提 | **failure run では `--log` が 0 バイト**（success では取れる）。加えて `--limit` 無しで 20 件打ち切り / 行頭プレフィクスにより `grep '^PROBE '` は 0 件 / `^` を外すとコマンドエコー行を二重計上（§3-5） | **可用性 SLI の分子（= failure）が丸ごと落ちる**。集計は REST `/actions/jobs/{job_id}/logs` 経由に改める必要がある。workflow の commit は観測条件を変えうるため修正は **2026-08-26 以降** |

## 7. 本記録で「未検証」としたもの

| 項目 | なぜ検証できなかったか |
| --- | --- |
| plan の `1 add / 3 change / 0 destroy` | apply がローカル実行で、plan の生出力もワークフローのログも残っていない。Activity Log の write 内訳（§1-1）で間接的に裏付けたのみ |
| `terraform apply` 開始時刻 07:14:37Z | 同上。ARM 側の最初の read は 07:14:26Z、最初の write は 07:14:41Z |
| `terraform plan -detailed-exitcode = 0`（ドリフトなし） | 本セッションでは plan を実行していない（state に触れないため）。前任セッションの 2026-08-23 実測のまま |
| /chat が 401 へ「遷移」した瞬間（200 だった直前の記録） | 遷移前（デプロイ前）のアクセスログが取得ウィンドウに無い。401 側（07:16:31.704Z / .755Z）は実測済み |
| replicaTimeout 55 秒に張り付く原因（§3-3） | SQL は完走しており、psql の終了処理側で待たされている可能性が高いが特定できていない |
| `Microsoft.App` メーターが出ない理由（§6 の 2） | 無料付与枠に収まっているのか、単に未反映なのかを区別できる一次情報を取れていない |
| バックアップ使用量のステップの周期 | 観測点が 2 回（旧サーバー 8/22 06:00Z 頃 / 新サーバー 8/23 07:00Z 頃）しかなく、日次か週次か判別できない |
| 通知の**メール到達**（§2-3 の通知先到着記録） | 実証できたのは GitHub 通知インボックス（`GET /notifications`）への配送記録の生成まで。メール / Web push の送信・到達・開封を確認できる証跡を取っていない |
| `gh run view --log` が failure run で 0 バイトになる原因（§3-5） | 再現は確実（success では 15,539 バイト、failure では 0 バイト、終了コードは 0）だが、`gh` 側か API 側かの切り分けはしていない |

## 8. フェーズ 1 の最終値（固定 72h 窓）

**取得時刻: 2026-08-26T08:32:53Z 〜 08:37:15Z（抽出）/ 08:41Z（集計）。すべて読み取りのみ。**
本節の値が、§4-5 / §6 の 6 に載っている進行中の中間値（22.5h 窓・70.7h 窓）を置き換える確定値。

### 8-1. 窓の定義と端の扱い

- **窓 = `[2026-08-23T08:16:19Z, 2026-08-26T08:16:19Z)`**。ちょうど 72h の**半開区間**
- 開始は `T_obs_start`（§4 の観測開始 E2E 成功時刻の最大値）、終了はその 72h 後
- **run を窓に入れるかは `created_at`（GitHub が run を作った時刻）で判定する**。
  レコード内の `ts=` は run 開始から 3〜6 秒後の値で、どちらを使っても中身は変わらないが、
  **coverage の分母が「cron の起動機会」である以上、分子も「起動したこと」を表す時刻で
  揃えるのが筋**だから。間隔（gap）の計算だけは workflow の設計どおり実測 `ts=` を使う
- **半開にした理由**: フェーズ 2a / 2b でも同じ窓幅を隣り合わせで使うため、
  境界に落ちた run を 2 つの窓で二重に数えないようにする
- 実際には**境界に重なる run は無かった**ため、この選択で件数は変わらない。
  窓の直前の scheduled run は `2026-08-23T08:12:53Z`（開始の 3.4 分前）、
  直後は `2026-08-26T08:25:35Z`（終了の 9.3 分後）

### 8-2. 取得コマンド

```console
$ date -u +%FT%TZ
2026-08-26T08:32:53Z
$ scripts/collect-probe-records.sh \
    --since 2026-08-23T08:16:19Z --until 2026-08-26T08:16:19Z \
    --out docs/verification/observation-phase1/probe-records.jsonl
collect-probe-records: repo=kmryst/felis-ai-chatbot workflow=readyz-probe.yml event=schedule window=[2026-08-23T08:16:19Z, 2026-08-26T08:16:19Z) runs=131
collect-probe-records: done (131 runs)
$ wc -l docs/verification/observation-phase1/probe-records.jsonl
131
```

抽出したレコードは [probe-records.jsonl](./probe-records.jsonl) に保全してある。
**Actions のログ保持は 90 日で `maximum_allowed_days` も 90**（§3-5）なので、
このファイルが 2026-11 以降は唯一の一次証跡になる。
スクリプトは §3-5 の (a)〜(d) をすべて踏まえた実装（`gh api --paginate` /
REST job logs / 行頭アンカーを使わない抽出 / `event=schedule` 限定）。

### 8-3. 確定値

| 指標 | 値 | 分子 / 分母 |
| --- | --- | --- |
| coverage（実効起動率） | **15.2%** | scheduled run 131 ÷ 名目 cron 機会 864（72h × 12） |
| PROBE レコード取得率 | **100%** | 有効レコード 131 ÷ 起動した run 131 |
| 可用性（成功率） | **97.71%** | `code=200` 128 ÷ 有効レコード 131 |
| 欠測（unknown） | 733（名目機会の 84.8%） | 864 − 131。**分母から除外**（後述） |

gap（連続する 2 レコードの実測 `ts=` の差。n = 130 区間）

| | 値 |
| --- | --- |
| min | 10.7 分（640 秒） |
| 中央値 | 28.8 分（1,725 秒） |
| p90 | 50.8 分（3,046 秒） |
| **max（最大無観測時間）** | **102.8 分（6,165 秒）** |

- **130 区間すべてが 10 分超**で、設計の 5 分間隔で回った区間は 1 つも無い
- 窓の端の無観測も同様に効く: 窓開始 → 最初のレコードが 31.6 分、
  最後のレコード → 窓終了が 23.9 分。いずれも max の 102.8 分より短いので、
  端を含めても最大無観測時間は **102.8 分**のまま
- 鮮度ゲートの検知遅延は最悪でこの 102.8 分になる。マーカーの閾値 10 分に対して**約 10 倍**

レイテンシ（`code=200` の 128 レコードの `latency_ms`）

| | 値 |
| --- | --- |
| min | 14,027 ms（14.03 秒） |
| 中央値 | 21,490 ms（21.49 秒） |
| p90 | 24,276 ms（24.28 秒） |
| max | 28,740 ms（28.74 秒） |

- 分母は成功レコードのみ。失敗 3 件の `latency_ms` は実測値ではないため除外している（8-4）

### 8-4. 失敗レコード 3 件

| run_id | created_at | レコード |
| --- | --- | --- |
| 32784303553 | 2026-08-24T22:22:02Z | `code=000 latency_ms=30000 obs=absent` |
| 32836517136 | 2026-08-25T10:18:06Z | `code=000 latency_ms=30002 obs=absent` |
| 32897735816 | 2026-08-25T20:51:16Z | `code=000 latency_ms=30002 obs=absent` |

- 3 件とも `code=000` = **curl が `--max-time 30` を超えて打ち切られた**もので、
  HTTP エラー応答（5xx 等）は 1 件も無い。`obs=absent` は「body を読めていない」の意で、
  採取側の異常を意味しない
- `latency_ms=30000` はちょうど `|| echo "000 30.000"` のフォールバック定数、
  `30002` は curl 自身が出した実測値。**同じ `code=000` でも片方は実測でない**
  （Issue #115 の対象 3。この不揃いのため latency 分布からは 3 件とも除外した）
- アプリ側の 5xx ではないので、**アプリ障害ではなく cold start がタイムアウトを
  超えたもの**と読むのが実態に近い

### 8-5. 欠測を unknown として分母から除外した理由

- 名目 864 機会のうち **733 は run そのものが起動していない**。GitHub Actions の
  schedule は起動遅延・スキップがある（#106 の受け入れ条件にも明記した既知の仕様）
- 起動していない機会については **/readyz が 200 を返したのか返さなかったのかを示す
  証跡が一切ない**。success にも failure にも数えられないため、
  可用性 SLI の good events / total events の**どちらにも入れず unknown として扱う**
- したがって「可用性 97.71%」は **72h のうち probe が実際に観測できた 131 点についての値**であって、
  72h の稼働率ではない。**この構成では 72h の稼働率は測れていない**
- coverage 15.2% はこの限定の大きさそのもので、**SLI の値と必ずセットで読む**

**出典の補足（2026-08-30 追記。本文は書き換えていない）**: 上の「GitHub Actions の schedule は
起動遅延・スキップがある」の一次情報は GitHub 公式ドキュメント "Events that trigger workflows" の
`schedule` 節である。逐語引用と日本語訳を残す（2026-08-30 に原文で確認）。

> "The `schedule` event can be delayed during periods of high loads of GitHub Actions workflow runs.
> High load times include the start of every hour. If the load is sufficiently high enough, some
> queued jobs may be dropped. To decrease the chance of delay, schedule your workflow to run at a
> different time of the hour."

（訳）

> 「`schedule` イベントは、GitHub Actions の workflow run が高負荷の期間には遅延することがある。
> 高負荷になる時間帯には毎時 0 分が含まれる。負荷が十分に高い場合、queue された job の一部は
> drop されることがある。遅延の可能性を減らすには、毎時 0 分とは別の時刻に workflow を
> スケジュールするとよい。」

出典 URL:
<https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule>

- 公式が明記しているのは **delay と drop が起こりうる**ことまでで、
  **drop 率も、drop されたことを事後に観測する手段も示していない**
- 実際に「schedule が発火したが run が作られなかった」を観測できる API は**存在しない**
  （2026-08-30 時点の確認範囲。Actions REST API は run を起点とするエンドポイントのみで、
  スケジューラ側のディスパッチ履歴や drop ログを返すエンドポイントはリファレンスに無い）。
  上の 733 を「dropped」ではなく **`unknown`** と呼んだのは、この意味で正しかった
- 本節の 864 / 733 / 15.2% は**当時の固定 72h 窓の確定値のまま**である。
  2026-08-26 以降さらに配送レートが落ちたこと、および原因調査の到達点は
  [計画 §5-6](../../operations/credit-window-execution-plan.md) に別途記録した（**本文は訂正していない**）

### 8-6. この可用性 SLI が測っているもの（限定。Refs #115）

serving は `min_replicas 0` のため、5 分間隔の probe は**毎回 cold start を起こす**（#115 の 1）。
成功レコードの中央値 21.5 秒 / p90 24.3 秒 / max 28.7 秒は、いずれも
**アプリの応答時間ではなく cold start の所要時間の分布**である。

したがってこの可用性は実質**「cold start が curl の `--max-time` 以内に完了する率」**であり、
タイムアウト設定を数秒動かすだけで数字が変わる。保全したレコードで実際に計算すると:

| 仮の `--max-time` | good events / 131 | 可用性 |
| --- | --- | --- |
| 20 秒 | 35 | 26.72% |
| 22 秒 | 79 | 60.31% |
| 25 秒 | 120 | 91.60% |
| 28 秒 | 126 | 96.18% |
| **30 秒（実際の設定）** | **128** | **97.71%** |

- **`--max-time` を 30 秒から 25 秒に縮めるだけで 97.71% → 91.60% に落ちる**。
  この 6 ポイントはアプリの品質差ではなく、閾値の置き方の差
- 逆方向（30 秒より長い側）は**評価できない**。実際の probe が 30 秒で打ち切っているため、
  失敗 3 件が 31 秒で完了したのか永久に返らなかったのかを示すデータが無い（**未検証**）
- `min_replicas` を 1 にすれば cold start は消えて「アプリの可用性」に近い SLI になるが、
  常時課金になる。**この構成のまま限定を明記する**方針を取る（計画 §5-4 の
  「取り繕わない限定の明記」と同じ扱い）

## 9. フェーズ 1 完走後の追補（2026-08-26 取得）

**取得時刻: 2026-08-26T08:49Z 〜 08:54Z。すべて読み取りのみ**（Azure への書き込み・
`.github/workflows/` の変更・probe の手動実行はいずれも行っていない）。
本節は Issue #104 / #106 の受け入れ条件を判定するために取り直した実測値で、
§8 の SLI（probe 側の値）に対して**採取側と課金側**を埋めるもの。

### 9-1. 採取 3 系列の完全性（固定 72h 窓）

窓の定義は §8-1 と同じ `[2026-08-23T08:16:19Z, 2026-08-26T08:16:19Z)`。
ops コンテナ経由の psql（`SELECT` のみ）で取得した。

```bash
az containerapp exec -g rg-felisaichatbot-dev-tf -n ca-felisaichatbot-dev-ops --command bash
# コンテナ内: psql "$DATABASE_URL" -At -F"|" で以下を実行（2026-08-26T08:51Z 取得）
#   SELECT count(*), min(ts), max(ts) FROM obs.<series>
#     WHERE ts >= '2026-08-23T08:16:19Z' AND ts < '2026-08-26T08:16:19Z';
#   gap は lag(ts) OVER (ORDER BY ts) の差の分布
```

| 系列 | 設計間隔 | 名目件数 | 実測件数 | 取得率 | 最初 | 最後 |
| --- | --- | --- | --- | --- | --- | --- |
| `obs.marker` | 1 分 | 4,320 | **4,320** | **100.0%** | 2026-08-23 08:16:19.691958+00 | 2026-08-26 08:15:52.752028+00 |
| `obs.db_stats` | 5 分 | 864 | 773 | 89.5% | 2026-08-23 08:16:19.707919+00 | 2026-08-26 08:12:18.107579+00 |
| `obs.table_stats`（distinct ts） | 5 分 | 864 | 773 | 89.5% | 同上 | 同上 |
| `obs.bloat_stats`（distinct ts） | 1 時間 | 72 | **72** | **100.0%** | 同上 | 2026-08-26 07:54:18.422579+00 |

gap の分布（連続する 2 レコードの ts の差）:

| 系列 | 鮮度ゲートの閾値 | min gap | max gap | 閾値を超えた gap |
| --- | --- | --- | --- | --- |
| `obs.marker` | 600 秒 | 21.26 秒 | **99.28 秒** | **0 件** |
| `obs.db_stats` | 900 秒 | — | **393.32 秒** | **0 件**（600 秒超も 0 件） |
| `obs.bloat_stats` | 10,800 秒 | — | **3,677.18 秒** | **0 件**（7,200 秒超も 0 件） |

- **マーカーは 72h 窓で 1 分も欠けていない**（4,320 / 4,320）。90 秒超の gap は 27 件あるが
  最大でも 99.28 秒で、その分は次の gap が短くなって相殺されている（cron 起動時刻のゆらぎであり、
  分の取りこぼしではない）。件数が名目と完全一致することがその裏付け
- 5 分系列の 89.5% は §3-2 のラチェット（`max(ts) <= now() - interval '5 minutes'` による
  経過時間ベース判定）の帰結で、**欠測ではなく実効間隔が約 5.6 分になっている**もの。
  gap の最大 393.32 秒は鮮度ゲートの閾値 900 秒に対して十分内側にある
- pgstattuple は 72 / 72 で完全。最大 gap 3,677.18 秒は設計 1 時間 + 77 秒

### 9-2. execution status と採取データの完全性は別物である（実測での裏取り）

§3-3 で 2 件だけ観測していた「SQL は完走しているのに execution は Failed」は、
72h 窓では**恒常的に起きていた**。

```console
$ date -u +%FT%TZ
2026-08-26T08:53:28Z
$ az containerapp job execution list -g rg-felisaichatbot-dev-tf \
    -n caj-felisaichatbot-dev-obs --query "length(@)"
144        # 内訳: Succeeded 100（履歴上限。§3-4）/ Failed 43 / Running 1
```

| 項目 | 値 |
| --- | --- |
| 窓内の名目 execution 数 | 4,320 |
| 窓内の Failed | **41**（0.95%） |
| 窓外の Failed | 2 件（`2026-08-23T07:15:00Z` = §3-1 の構造的初回失敗 / `2026-08-26T08:17:00Z` = 窓の直後） |
| 窓内の Succeeded | **数えられない**（履歴上限 100 で切られる。§3-4） |

失敗の原因は Log Analytics の実測で 1 種類に収束する
（`az rest` で `https://api.loganalytics.io/v1/workspaces/<workspace>/query` を叩いた。
2026-08-26T08:53:58Z / 08:54:07Z 取得）:

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated >= datetime(2026-08-23T08:16:19Z) and TimeGenerated < datetime(2026-08-26T08:16:19Z)
| where Log_s has 'caj-felisaichatbot-dev-obs'
| summarize c=count() by Reason_s
```

| `Reason_s` | 件数 |
| --- | --- |
| `SuccessfulCreate` | 4,924 |
| `ProcessExited` | 4,277 |
| `Completed` | 4,275 |
| `PodDeletion` | 4,276 |
| `AssigningReplica` | 4,312 |
| **`DeadlineExceeded`** | **40** |
| `SuccessfulDelete` | 323 |
| `SawCompletedJob` | 24 |
| `FailedDelete` | 1 |

`ProcessExited` の exit code を同じ窓で集計すると:

| exit code | 件数 |
| --- | --- |
| **0** | **4,277** |

- **窓内の `ProcessExited` は 4,277 件すべてが exit 0**。§3-1 の exit 3（`relation "obs.marker"
  does not exist`）は窓の外（07:15:00Z）にあり、窓内には 1 件もない
- **窓内の Failed 41 件は `DeadlineExceeded`（`replicaTimeout: 55` 秒での打ち切り）に対応する**。
  打ち切られた execution は exit code を残さないため、上の 4,277 件には現れない
  （4,320 − 4,277 ≒ 43 が打ち切り側の規模感と整合する）
- **それでも採取データは 1 件も欠けていない**（9-1 のマーカー 4,320 / 4,320）。
  §3-3 の教訓「execution status と採取データの完全性は別物」は、2 件の逸話ではなく
  **72h 窓 41 件の実測で裏が取れた**
- 「毎分の execution が Succeeded」を受け入れ条件にすると、**データが完全でも 41 件で不合格になる**。
  判定は採取データの完全性で行い、execution status は失敗件数と原因を別指標として記録するのが正しい

### 9-3. azurerm provider の Schedule トリガー cron 記法（schema 確認）

`terraform/ephemeral/main.tf` のコメントには「`terraform providers schema -json` で確認済み
（2026-08-23）」とあったが、**出力そのものが記録に残っていなかった**ため取り直した。
`providers schema` は state にもリモートにも触れない読み取り操作である。

```console
$ date -u +%FT%TZ
2026-08-26T08:50:33Z
$ terraform -chdir=terraform/ephemeral providers schema -json | jq '...'
```

azurerm **5.1.0**（`.terraform.lock.hcl` の固定版）の
`azurerm_container_app_job` → `schedule_trigger_config`:

| 属性 | 型 | 必須 | schema の description |
| --- | --- | --- | --- |
| `cron_expression` | string | **required** | （空） |
| `parallelism` | number | optional | （空） |
| `replica_completion_count` | number | optional | （空） |

ブロック自体は `nesting_mode: list` / `max_items: 1`。

- **schema から分かるのは「属性が存在し、必須で、string である」ことだけ**である。
  記法（フィールド数・許容する特殊文字・タイムゾーン）を定める情報は schema には無く、
  provider 側の validation も無い。レジストリのドキュメントも
  "Cron formatted repeating schedule of a Cron Job." としか書いていない
- したがって**記法は provider ではなく ARM 側の仕様**であり、確認は「provider が文字列を
  そのまま渡すこと」と「渡した文字列が意図どおり動くこと」の 2 段で行う必要がある

ARM 側に格納された値の読み取り（2026-08-26T08:50:46Z 取得）:

```console
$ az containerapp job show -g rg-felisaichatbot-dev-tf -n caj-felisaichatbot-dev-obs \
    --query "{triggerType:properties.configuration.triggerType, cron:properties.configuration.scheduleTriggerConfig}" -o json
{
  "cron": { "cronExpression": "* * * * *", "parallelism": 1, "replicaCompletionCount": 1 },
  "triggerType": "Schedule"
}
```

- HCL に書いた `"* * * * *"` が **`cronExpression` へ無加工で入っている**（provider は素通しする）
- **実挙動との突き合わせ**: 5 フィールドの標準 cron として毎分解釈されている。
  9-1 のマーカーが 72h で 4,320 件ちょうど（= 4,320 分に 1 件ずつ）であることが、
  記法の解釈が意図どおりであることの実測証拠になる。起動時刻の秒はゼロ
  （`execution list` の `startTime` がすべて `:00`）で、タイムゾーンは UTC
  （§1-2 のタイムラインと `startTime` が UTC で一致する）

### 9-4. `Microsoft.App` メーターの再確認

§6 の 2 / §7 で「無料付与枠に収まっているのか未反映なのか未検証」としていた点を、
反映ラグ（台帳の記載で 1〜2 日）が明けたタイミングで取り直した。

```console
$ date -u +%FT%TZ
2026-08-26T08:49:47Z
$ SUB=$(az account show --query id -o tsv)
$ az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/usageDetails?api-version=2024-08-01&\$filter=properties/usageStart%20ge%20'2026-08-19'%20and%20properties/usageEnd%20le%20'2026-08-27'&\$top=1000"
# 77 レコード / nextLink なし
```

| 日付 (UTC) | 確定コスト (JPY) | 反映状態 |
| --- | --- | --- |
| 2026-08-23 | 49.748 | 確定（丸 1 日） |
| 2026-08-24 | **49.807** | **確定（丸 1 日）** |
| 2026-08-25 | **49.807** | **確定（丸 1 日）** |
| 2026-08-26 | 8.301 | 部分反映（08:49Z 時点） |

`consumedService` に出現した値は
`Microsoft.CognitiveServices` / `Microsoft.ContainerRegistry` / `Microsoft.DBforPostgreSQL` /
`Microsoft.Network` / `Microsoft.Storage` / `microsoft.operationalinsights` の 6 つで、
**`Microsoft.App` は 1 レコードも無い**（Free メーターすら無い）。

- 8/24 と 8/25 は**丸 1 日分が確定している**（ACR `Basic Registry Unit` 1.000008 /Day、
  PostgreSQL `B1MS Compute - Free` 24 時間、`Standard IPv4 Static Public IP` 24 時間が揃っている）。
  したがって**この 2 日については「反映ラグで見えていない」という説明はもう成り立たない**
- obs Job（毎分 1,440 回/日）と probe による serving の cold start は、この 2 日間も
  途切れずに動いていた。それでも**日額は 49.807 JPY で 8/23 とほぼ同一**であり、
  課金レコード上、両者に由来する増分は現れていない
- ただし**「課金が 0 である」ことを一次情報で確定できたわけではない**。
  PostgreSQL は `- Free` メーターとして 0 円のレコードが出るのに対し、`Microsoft.App` は
  **メーター自体が出ない**。無料付与枠に吸収されて 0 円のレコードすら生成されないのか、
  Container Apps の usage record が別経路なのかを区別できる一次情報を取れていない（**未検証のまま**）
- **obs Job 単体のコスト按分は原理的にできない**。`usageDetails` は
  `resourceName`（= リソース単位）でしか分解できず、`Microsoft.App` のレコードが存在しない以上、
  Job / serving / ops のどれについても行が無い。計画 §5-3 と #104 が想定した
  「active 単価 × 実行秒数 × 1440/日」の検証は、**メーターが出るようになるまで実施できない**。
  引き継ぎ先は Issue #115（cold start の active 課金の実測）

### 9-5. `autovacuum_freeze_max_age` の実測

§4-7 で「公式ドキュメント記載の既定値であり本環境では未実測」としていた値を取得した
（9-1 と同じ psql セッション。2026-08-26T08:51Z）。

```console
=> SELECT setting FROM pg_settings WHERE name = 'autovacuum_freeze_max_age';
200000000
```

Azure Database for PostgreSQL flexible server 側で既定値は変えられておらず、
**§4-7 の外挿（約 1.5 万日で anti-wraparound autovacuum）は実測値に基づく**ものになった。
§4-7 の「未実測の前提」の但し書きは解消する。
