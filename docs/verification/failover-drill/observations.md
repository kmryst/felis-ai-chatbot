# HA フェイルオーバードリルの実測記録（2026-08-28）

PostgreSQL Flexible Server `pgsql-felisaichatbot-dev` に対して、tier 昇格 → HA（zone-redundant）
有効化 → planned failover → forced failover → HA 無効化 → tier 復帰の 6 操作を実施し、
外形プローブでアプリケーション視点の downtime を実測した記録。**時刻はすべて UTC**。

値には取得元（外形ログ / Activity Log / Azure Monitor メトリクス）を必ず添える。
再確認できなかったものは「未検証」または「記録なし」と明記し、推測で埋めない。

- 対象サーバー: `pgsql-felisaichatbot-dev`（RG `rg-felisaichatbot-dev-tf` / japaneast / PostgreSQL 17）
- 観測窓: **2026-08-28T08:21:11.198Z 〜 10:49:55.552Z**（834 サンプル）
- 目的: HA の failover が実際に zone を跨いで起きることと、その downtime を
  **アプリケーション視点で**実測する。RTO 目標（3 時間）との照合材料を得る
- **本ドリルは Azure への書き込みを伴う実操作である。** 本記録の作成作業自体は
  読み取りのみで行った（`az` の read 系・Activity Log・メトリクスのみ）

> **測定は 10 秒間隔である。** 秒粒度で測らないと決めた判断の記録は
> [ADR-0023](../../adr/0023-no-second-granularity-downtime-measurement.md)。
> したがって本記録の downtime はすべて **±20 秒の粒度誤差**を持つ（§3-1）。

## 1. 環境（ドリル開始前 = 終了後）

| 項目 | 値 |
| --- | --- |
| SKU | `Standard_B1ms` |
| tier | `Burstable` |
| HA | `Disabled` |
| zone | `1` |
| storage | `32` GiB |
| state | `Ready` |

**ドリル終了後の再取得（2026-08-29 実測。読み取りのみ）でも上表と完全に一致した。**

```console
$ az postgres flexible-server show -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
    --query "{sku:sku.name,tier:sku.tier,ha:highAvailability.mode,haState:highAvailability.state,zone:availabilityZone,standbyZone:highAvailability.standbyAvailabilityZone,storage:storage.storageSizeGb,state:state}" -o json
{
  "ha": "Disabled",
  "haState": "NotEnabled",
  "sku": "Standard_B1ms",
  "standbyZone": null,
  "state": "Ready",
  "storage": 32,
  "tier": "Burstable",
  "zone": "1"
}
```

**`storage` は全工程を通じて 32 のまま**だった（§4 の zone 遷移の各観測点でも 32）。
tier を Burstable → GeneralPurpose → Burstable と往復させてもストレージサイズは変わらない。
これは事前に確認していなかった挙動で、**実測で確かめた**（storage は tier とは独立に
スケールする軸である、という §7-3 の公称と整合）。

### 1-1. なぜ tier 昇格が必要だったか

Burstable tier では HA を有効化できない。公式・逐語:

> The **Burstable** tier doesn't support high availability. Only the **General purpose** and
> **Memory optimized** tiers support high availability.

（訳）

> **Burstable** ティアは高可用性をサポートしない。高可用性をサポートするのは
> **General purpose** と **Memory optimized** の 2 ティアだけである。

- 出典: "Configure High Availability" の *Limitations and considerations* 節
  <https://learn.microsoft.com/en-us/azure/postgresql/high-availability/how-to-configure-high-availability>
  （2026-08-29 確認）

したがって tier 昇格（`Standard_B1ms` → `Standard_D2ds_v5`）は**ドリルの前提条件**であって、
ドリルの対象そのものではない。**ただし downtime はこの前提条件のほうが 1 桁大きかった**（§3）。

## 2. 実行した 6 コマンド

操作の識別に効く引数はドリル記録の逐語。`-g` / `-n` は本サーバーの固定の識別子である。

```bash
# 1. tier 昇格（HA 有効化の前提条件）
az postgres flexible-server update -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --tier GeneralPurpose --sku-name Standard_D2ds_v5 --yes

# 2. HA（zone-redundant）有効化
az postgres flexible-server update -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --zonal-resiliency Enabled --yes

# 3. planned failover
az postgres flexible-server restart -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --failover Planned

# 4. forced failover
az postgres flexible-server restart -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --failover Forced

# 5. HA 無効化
az postgres flexible-server update -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --zonal-resiliency Disabled --yes

# 6. tier 復帰
az postgres flexible-server update -g rg-felisaichatbot-dev-tf -n pgsql-felisaichatbot-dev \
  --tier Burstable --sku-name Standard_B1ms --yes
```

### 2-1. ARM 側の所要時間（Activity Log 実測）

```console
$ az monitor activity-log list --start-time 2026-08-28T08:00:00Z --end-time 2026-08-28T11:00:00Z \
    --resource-group rg-felisaichatbot-dev-tf \
    --query "[?contains(resourceId,'flexibleServers')].{time:eventTimestamp,op:operationName.value,status:status.value}" -o tsv
```

| # | 操作 | ARM Started | ARM Succeeded | ARM 所要 |
| --- | --- | --- | --- | --- |
| 1 | tier 昇格 | 08:25:37.315Z | 08:32:44.431Z | 7 分 07 秒 |
| 2 | HA 有効化 | 08:35:48.595Z | 08:47:04.277Z | **11 分 16 秒** |
| 3 | planned failover | 08:50:17.416Z | 09:00:27.374Z | 10 分 10 秒 |
| 4 | forced failover | 09:21:47.486Z | 09:29:56.768Z | 8 分 09 秒 |
| 5 | HA 無効化 | 10:08:10.962Z | 10:11:17.522Z | 3 分 07 秒 |
| 6 | tier 復帰 | 10:11:29.296Z | 10:19:48.559Z | 8 分 19 秒 |

**操作 5 / 6 の時刻はドリル実施時に取得できておらず、本記録の作成時に Activity Log から
read-only で復元した**（2026-08-29 取得。Activity Log の保持期間 90 日の内側）。
操作 1〜4 は実施時の記録と Activity Log の双方がある。

### 2-2. ARM の所要時間と downtime は別物である

操作 1〜4 について、実施時に記録した CLI 発行時刻・`Healthy` 観測時刻と、
上表の ARM Started / Succeeded を突き合わせた。

| # | CLI 発行（実施時記録） | ARM Started | 差 | 完了 / Healthy（実施時記録） | ARM Succeeded | 差 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 08:25:33.259Z | 08:25:37.315Z | +4.1 秒 | 08:32:04.832Z | 08:32:44.431Z | +39.6 秒 |
| 2 | 08:35:42.233Z | 08:35:48.595Z | +6.4 秒 | 08:46:52.961Z | 08:47:04.277Z | +11.3 秒 |
| 3 | 08:50:15.324Z | 08:50:17.416Z | +2.1 秒 | 09:00:02.235Z | 09:00:27.374Z | +25.1 秒 |
| 4 | 09:21:44.999Z | 09:21:47.486Z | +2.5 秒 | 09:29:26.938Z | 09:29:56.768Z | +29.8 秒 |

**2 系列は矛盾していない。** CLI 発行は ARM が `Started` を記録する数秒前、
`Healthy` の観測は ARM が操作レコードを確定させる数十秒前に来る。**どちらも
downtime ではない。** ARM の所要（3〜11 分）と外形の downtime（24 秒〜7 分）は
最大 1 桁違う。Microsoft 自身がこの点を明示している。公式・逐語:

> The overall end-to-end operation time, as reported on the portal, might be longer than the
> actual downtime that the application experiences. You should measure the downtime from the
> application's perspective.

（訳）

> ポータルに表示されるエンドツーエンドの操作全体の所要時間は、アプリケーションが実際に
> 経験する downtime より長いことがある。downtime はアプリケーションの視点から測るべきである。

- 出典: "Configure High Availability" の *Initiate a forced failover* / *Initiate a planned failover*
  の Important ボックス（同一文が両節にある）
  <https://learn.microsoft.com/en-us/azure/postgresql/high-availability/how-to-configure-high-availability>
  （2026-08-29 確認）

**本記録の downtime はすべて外形プローブ（アプリケーション視点）の値である。**

## 3. downtime の実測

### 3-1. 測定方法と誤差

- 外部から `/readyz` と `/livez` を **10 秒間隔**で叩いた 834 サンプル
- `curl --max-time 5`。失敗時は HTTP コードを `000` として記録
- downtime は **「最初の非 200 サンプルの時刻」→「次に 200 を観測した時刻」**で定義する
- **誤差は ±20 秒**（真の障害開始は直前の 200 と最初の非 200 の間、真の復旧は最後の
  非 200 と最初の 200 の間にある。両端に観測間隔ぶんの不確かさが乗る）

834 サンプルの実測間隔は **min 9.18 秒 / max 17.15 秒 / 平均 10.71 秒**だった
（名目 10 秒に対し、最大で 7.15 秒の遅れが 1 回ある）。**誤差 ±20 秒は
この実測間隔の揺れも吸収する幅である。**

### 3-2. 実測表

| # | イベント | 最初の非 200 | 最後の非 200 | 次の 200 | サンプル数 | **downtime** |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | tier 昇格（B1ms → GP） | 08:25:54.892Z | 08:31:13.076Z | 08:31:25.054Z | 26 | **5 分 30 秒** |
| 2 | planned failover | 08:50:35.398Z | 08:50:47.342Z | 08:50:59.287Z | 2 | **23.9 秒** |
| 3 | forced failover | 09:22:02.510Z | 09:22:22.790Z | 09:22:32.913Z | 3 | **30.4 秒** |
| 4 | tier 復帰（GP → B1ms） | 10:12:04.984Z | 10:19:03.387Z | 10:19:14.533Z | 36 | **7 分 10 秒** |
| 5 | 単発の `readyz=000` | 10:44:32.973Z | 同左 | 10:44:48.042Z | 1 | §6 で別扱い |

すべて ±20 秒。参考として、**「最後の 200 → 次の 200」**（上限側の読み）を採ると
それぞれ 340.4 秒 / 35.9 秒 / 43.1 秒 / 439.7 秒になる。上表はこの区間の下限側寄りの
点推定であり、**真値はこの 2 つの間にある**。

観測窓 834 サンプルのうち非 200 は **68 サンプルのみ**（`readyz=503` が 67、`readyz=000` が 1）。
残り 766 サンプルはすべて 200 で、レイテンシは **中央値 0.144 秒 / p95 0.193 秒 / max 1.194 秒**。
**cold start（フェーズ 1 実測の中央値 21.49 秒）はこの窓に 1 件も混入していない**
（max 1.194 秒 ≪ 21 秒）。ドリル前にウォームアップした効果である。

### 3-3. downtime がゼロだった 2 操作

**HA 有効化（操作 2）と HA 無効化（操作 5）では、非 200 サンプルが 1 件も出なかった。**

- HA 有効化: ARM 08:35:48Z 〜 08:47:04Z。この 11 分 16 秒のあいだ、外形は全サンプル 200
- HA 無効化: ARM 10:08:10Z 〜 10:11:17Z。この 3 分 07 秒のあいだ、外形は全サンプル 200

これは公称の "online operation" の実証である。公式・逐語:

> When you enable or disable high availability on an Azure Database for PostgreSQL flexible
> server, the service doesn't change other settings. These settings include networking
> configuration, firewall settings, parameters, and backup retention. Enabling or disabling
> high availability is an online operation. This operation doesn't affect your application
> connectivity and operations.

（訳）

> Azure Database for PostgreSQL flexible server で高可用性を有効化または無効化しても、
> サービスは他の設定を変更しない。ここでいう設定にはネットワーク構成・ファイアウォール設定・
> パラメーター・バックアップ保持期間が含まれる。高可用性の有効化・無効化は online operation
> である。この操作はアプリケーションの接続性および操作に影響しない。

- 出典: "Configure High Availability" の *Limitations and considerations* 節
  <https://learn.microsoft.com/en-us/azure/postgresql/high-availability/how-to-configure-high-availability>
  （2026-08-29 確認）

**限定**: 測定は 10 秒間隔なので、**10 秒未満の瞬断は原理的に検出できない**。
本記録が言えるのは「10 秒粒度で観測可能な downtime は無かった」までであり、
「downtime が厳密にゼロだった」ではない。

## 4. zone の遷移（failover が実際に起きた証明）

| 時点 | zone（primary） | standbyZone |
| --- | --- | --- |
| ドリル開始 | 1 | なし（HA 無効） |
| HA 有効化後 | 1 | **2**（Azure が自動選択） |
| planned failover 後 | **2** | **1** ← 入れ替わり |
| forced failover 後 | **1** | **2** ← 再度入れ替わり。開始時の配置に復帰 |
| HA 無効化後 | 1 | なし |

**downtime が 24 秒 / 30 秒と短くても、primary は確かに別の zone へ移っている。**
zone が入れ替わっていなければ「単に再起動しただけ」と区別がつかないため、
この表が failover の成立を示す一次証拠である。

forced failover 後に zone が 1 に戻ったのは偶然ではない。planned で 1 → 2 に移り、
forced で 2 → 1 に戻ったため、**2 回の failover で開始時の配置に復帰した**。
結果として、ドリル終了時の zone がドリル開始時と一致している（§1）。

## 5. 応答時間から読める失敗の性質

`--max-time 5` に対し、非 200 サンプルの応答時間は 2 つの値に強く集中した。

- **t = 0.04〜0.09 秒**: 接続が即座に拒否された（TCP レベルで到達不能。**サーバーがいない**）
- **t = 2.05 秒前後**: `connect_timeout = 2 秒` に張り付いた（接続を試みて待たされた。
  **いるが応答しない**）

イベント別の内訳（実測）:

| イベント | 非 200 | t < 0.5 秒 | 0.5〜2.0 秒 | t ≥ 2.0 秒 | 中央値 |
| --- | --- | --- | --- | --- | --- |
| tier 昇格 | 26 | 1 | 0 | **25** | 2.050 秒 |
| planned failover | 2 | 0 | 0 | **2** | 2.053 秒 |
| forced failover | 3 | **3** | 0 | 0 | 0.071 秒 |
| tier 復帰 | 36 | 3 | 1 | **32** | 2.054 秒 |

### 5-1. 当初の読み「failover = いない / tier 変更 = いるが応答しない」は成立しない

ドリル時の見立ては「**failover では接続拒否（0.06 秒）、tier 変更では接続待ち（2.05 秒）**」
というものだった。**ログで裏を取ったところ、この二分法は誤りである。**

- **forced failover の 3 サンプルは確かに全て 0.065〜0.075 秒**（接続拒否）
- **しかし planned failover の 2 サンプルは 2.051 秒 / 2.053 秒**で、
  tier 変更と同じ「接続待ち」側だった

正しい切り分けは **「forced failover」対「それ以外の 3 操作」**である。
これは公式の説明する各操作の内部手順と整合する。

**forced failover は primary を即座に落とす。** 公式・逐語（*Forced failover* の手順表 step 1）:

> Primary server stops shortly after receiving the failover request.

（訳）

> primary サーバーは failover 要求を受け取った直後に停止する。

**planned failover は接続を drain してから切り替える。** 公式・逐語（*Planned failover* 節）:

> Once the process updates the standby replica, it drains primary server connections and
> triggers a failover that activates the standby replica as the primary server with the same
> database server name.

（訳）

> standby レプリカの更新が終わると、プロセスは primary サーバーの接続を drain し、
> standby レプリカを同じデータベースサーバー名の primary サーバーとして起動する failover を
> 実行する。

- 出典（両方）: "High Availability in Azure Database for PostgreSQL flexible server"
  <https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability>
  （2026-08-29 確認）

**primary を落とす forced だけが TCP の接続拒否として観測され、drain を挟む planned と
新 VM への切り替えを行う tier 変更は「待たされる」側に出た。** 応答時間は障害の
種類ではなく、**その操作が接続をどう終わらせるか**を映していた。

**サンプル数の限定**: forced が 3 サンプル、planned が 2 サンプルである。
**この 2 操作の応答時間の性質を 5 サンプルで断定はできない。** 上の説明は
公式の手順と符合するという裏づけがあるが、再現性は未検証である。

## 6. 単発の `readyz=000`（10:44:32Z）

ドリルの 6 操作がすべて終わった後、**どの操作とも無関係な時刻**に 1 サンプルだけ出た。

```text
10:44:22.728Z  readyz=200  livez=200  t=0.171449
10:44:32.973Z  readyz=000  livez=200  t=5.000465000   ← --max-time 5 で切断
10:44:48.042Z  readyz=200  livez=200  t=0.176585
```

**`livez` は 200 のまま**である。プロセスは生きていて、`/readyz` だけが返らなかった。

### 6-1. 原因: `SELECT 1` に statement_timeout が掛かっていない

`backend/app/db.py` の `check_database_ready()`（`/readyz` が DB 到達性の判定に呼ぶ関数）は
接続に `connect_timeout` を渡すが、**クエリ側の上限を設定していない**。

```python
async with await psycopg.AsyncConnection.connect(
    database_url,
    connect_timeout=connect_timeout_seconds,
) as conn:
    await conn.execute("SELECT 1")
```

- 接続の確立には `connect_timeout = 2 秒` が効く
- **`SELECT 1` には `statement_timeout` が掛かっていない**
- したがって **TCP は繋がるが応答が返らない状態になると、無期限に待ち得る**

**同じファイルの `fetch_observation_freshness()` は `statement_timeout` を明示している**
（`options=f"-c statement_timeout={connect_timeout_seconds * 1000}"`。Issue #114 の 3 で対応済み）。
**到達性チェック側だけが取り残されている**という非対称がある。

### 6-2. `--max-time 5` と 10 秒間隔がどちらも効いた

- **`--max-time 5` を付けていたため 5 秒で切れた。** 付けていなければ、この 1 本は
  ぶら下がったままになり得た（`t=5.000465` は curl 側が打ち切った値であり、
  サーバーが 5 秒で応答したわけではない）
- **1 秒間隔で叩いていたら、この 5 秒のあいだに 4 本が積み上がっていた。**
  serving app は `max_replicas = 1` で逃げ場がない
- **10 秒間隔だったため、積み上がりは起きなかった**（次のサンプルは 15.1 秒後）

**この挙動は事前に予測されていた**（ADR-0023 の「取らなかったリスク」）。
本サンプルはその予測が実際に起きたことの実測である。**判定には影響していない**が、
`/readyz` の実装課題としては残る。

## 7. 公称値との照合

すべて 2026-08-29 に URL を開き、逐語が存在することを確認した。

### 7-1. failover

> - **Zone-redundant**: Azure Database for PostgreSQL automatically fails over to the standby
>   server within 60-120 seconds with zero data loss.

（訳）

> - **ゾーン冗長**: Azure Database for PostgreSQL は 60〜120 秒以内に、データ損失なしで
>   standby サーバーへ自動的にフェイルオーバーする。

- 出典: "High Availability in Azure Database for PostgreSQL flexible server" の
  *Recovery from zone failures* 節
  <https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability>
  （2026-08-29 確認）

関連する限定も同ページにある。公式・逐語（*High availability limitations* 節）:

> Depending on the workload and activity on the primary server, the failover process might take
> longer than 120 seconds because the standby replica needs to recover before it can be promoted.

（訳）

> primary サーバーのワークロードと活動状況によっては、standby レプリカが昇格の前に
> リカバリを完了する必要があるため、failover の処理が 120 秒を超えることがある。

**本ドリルの実測（23.9 秒 / 30.4 秒）が公称の下限 60 秒すら下回った理由は、
この「ワークロードと活動状況」がほぼ皆無だったためと読むのが自然である**
（heartbeat の毎分 1 行のみ。§8-2 の限定と同じ話）。**ただしこれは本記録の推論であり、
Microsoft は「無負荷なら 60 秒未満になる」とは書いていない。**

### 7-2. HA 有効化 / 無効化

逐語と訳は §3-3 に掲げた（"Enabling or disabling high availability is an online operation. ..."）。

### 7-3. tier 変更

> Typically, this process takes anywhere from 2 to 10 minutes with regular scaling.

（訳）

> 通常、この処理は通常のスケーリングでは 2 分から 10 分程度かかる。

同ページの *Considerations and limitations* に、本サーバーに直接効く限定がある。公式・逐語:

> - Near-zero doesn't work if you scale the compute of your server from or to a compute size of
>   1 or 2 vCores of the Burstable tier.

（訳）

> - Burstable ティアの 1 vCore または 2 vCore のコンピューティングサイズとの間で
>   サーバーのコンピューティングをスケールする場合、near-zero（ほぼゼロの downtime）は機能しない。

- 出典（両方）: "Scaling Resources in Azure Database for PostgreSQL Flexible Server" の
  *Near-zero downtime scaling* 節および *Considerations and limitations*
  <https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-scaling-resources>
  （2026-08-29 確認。canonical URL は
  `learn.microsoft.com/en-us/azure/postgresql/scale/concepts-scaling-resources`）

**本サーバーの `Standard_B1ms` は Burstable の 1 vCore である。** したがって
tier 昇格・tier 復帰はどちらも「`from or to` a compute size of 1 vCore of the Burstable tier」に
該当し、**near-zero downtime scaling の対象外**である。同ページが near-zero の場合に挙げる
「10 〜 30 秒」ではなく、`regular scaling` の「2 〜 10 分」が適用される区間だった。

### 7-4. 照合表

| 操作 | 公称 | 実測 | 判定 |
| --- | --- | --- | --- |
| planned failover | 60〜120 秒 | **23.9 秒** | **下回った** |
| forced failover | 60〜120 秒 | **30.4 秒** | **下回った** |
| HA 有効化 | online operation（接続に影響しない） | **downtime 0**（10 秒粒度で非 200 ゼロ） | **一致** |
| HA 無効化 | online operation（接続に影響しない） | **downtime 0**（10 秒粒度で非 200 ゼロ） | **一致** |
| tier 昇格（B1ms → GP） | regular scaling 2〜10 分 | **5 分 30 秒** | **範囲内** |
| tier 復帰（GP → B1ms） | regular scaling 2〜10 分 | **7 分 10 秒** | **範囲内** |

**実測はすべて公称の範囲内、または公称を下回った。** 公称を超えた項目は 1 件もない。

## 8. RTO 目標との照合

[restore-drill-recovery-objectives.md](../../operations/restore-drill-recovery-objectives.md) §2 で
**RTO 目標 3 時間**（aspirational target）を宣言している。

### 8-1. 照合

| 実測 | RTO 目標 3 時間 に対して |
| --- | --- |
| planned failover **23.9 秒** | 目標の **約 1/450**。大幅に下回る |
| forced failover **30.4 秒** | 目標の **約 1/355**。大幅に下回る |
| tier 変更 **5 分 30 秒 / 7 分 10 秒** | 目標の約 1/33 〜 1/25。下回る |

**HA failover の実測は RTO 目標を大幅に下回った。**

### 8-2. この実測の限定（重要）

**この値をもって「RTO 3 時間は余裕で守れる」とは言えない。**

- **データ量が極小である。** DB サイズは約 4 GiB。書き込みは heartbeat の毎分 1 行と
  カウンタ 1 行の UPDATE のみ（[ADR-0021](../../adr/0021-heartbeat-table-as-recovery-marker.md)）。
  **standby が昇格前に recover すべき WAL がほとんど無い状態での値**である
- **データ量に対するスケールは未検証。** §7-1 の公称が明示するとおり、failover 時間は
  「standby replica needs to recover before it can be promoted」に依存する。
  本ドリルはこの依存関係を測っていない
- **HA failover は RTO のすべてではない。** RTO 目標が想定しているのは PITR による復旧
  （復元先サーバーの作成 + WAL 適用）であり、**HA failover とは復旧手段そのものが違う**。
  この 23.9 秒 / 30.4 秒は「HA が有効なときの、そのシナリオでの復旧時間」であって、
  「バックアップからの復旧時間」ではない
- **平常時この環境に HA は無い。** ドリル終了時に HA は `Disabled` に戻している（§1）。
  つまり**この failover 時間は平常時の構成では得られない値**である

### 8-3. RTO 目標を改定するかどうかは、本記録では決めない

`restore-drill-recovery-objectives.md` §6 の改定手順は「ドリル完了後、実測値 + 運用マージンを
もとに目標値を改定する」としているが、**そこで言うドリルは PITR ドリルである**。

**本記録は RTO 目標の改定を提案しない。** 判断は **PITR ドリルの実測が揃ってから**行う。
理由は §8-2 のとおり、HA failover の実測は RTO 目標が想定する復旧経路と別物であり、
これだけを根拠に目標を締めると**測っていない経路について締めた**ことになるためである。

## 9. Sev0 アラート `alert-pgsql-is-db-alive` の実測

台帳（[azure-resource-inventory.md](../../operations/azure-resource-inventory.md)）で
**「安全に発火させられないため実発火試験を実施していない」と記録されていた唯一の未試験アラート**。
**本ドリルの tier 変更で、意図せず一巡の実測が取れた。**

### 9-1. 発火の実測

```bash
az rest --method get --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=7d"
```

| # | イベント | downtime | アラート | fired | resolved |
| --- | --- | --- | --- | --- | --- |
| 1 | tier 昇格 | 5 分 30 秒 | **発火** | 08:33:28.842Z | 08:36:33.746Z |
| 2 | planned failover | 23.9 秒 | **沈黙** | — | — |
| 3 | forced failover | 30.4 秒 | **沈黙** | — | — |
| 4 | tier 復帰 | 7 分 10 秒 | **発火** | 10:19:28.077Z | 10:24:32.446Z |

**発火は 2 回である**（tier 昇格と tier 復帰の両方）。どちらも `monitorCondition: Resolved` で、
**発火 → 自動 Resolve まで一巡した**（`autoMitigate: true` の動作実証）。

**これで台帳の未試験アラートは 0 件になった。**

### 9-2. 30 秒程度の failover では発火しない — 設定ではなく入力の分解能の問題

このアラートは `PT5M` window / `Minimum` / `is_db_alive < 1`。
**閾値も集計も window も正しく機能している。** 発火しなかった理由は入力側にある。

```console
$ az monitor metrics list --resource <server> --metric is_db_alive --aggregation Minimum \
    --interval PT1M --start-time 2026-08-28T08:20:00Z --end-time 2026-08-28T10:50:00Z
```

150 データポイント（1 分粒度）のうち **`0` に落ちたのは 12 点だけ**で、**欠測は 0 点**:

| 区間 | 0 になった 1 分バケット |
| --- | --- |
| tier 昇格 | 08:27 / 08:28 / 08:29 / 08:30 / 08:31（**5 点**） |
| tier 復帰 | 10:13 / 10:14 / 10:15 / 10:16 / 10:17 / 10:18 / 10:19（**7 点**） |
| planned failover 前後 | **0 点** |
| forced failover 前後 | **0 点** |

forced failover を含む **09:10Z 〜 09:39Z の全 30 バケットが 1.0** だった。

- **`is_db_alive` の入力粒度は 1 分**である。23.9 秒 / 30.4 秒の断は、
  **1 分バケットを丸ごと 0 にするには短すぎる**
- **`Minimum` 集計は「窓内の最小のデータポイント」を見るのであって、
  「窓内で一瞬でも落ちたか」を見るのではない。** 落ちた瞬間が 1 分バケットの
  平均に吸収されて 1.0 のまま出れば、`Minimum` を取っても 1.0 である
- したがって **これは window / 閾値 / 集計の設定ミスではなく、入力メトリクスの
  分解能の問題である。** window を PT1M に縮めても、評価頻度を上げても発火しない。
  **1 分より短い断は、このメトリクスでは原理的に検知できない**

**この区別は運用上重要である。** 「Sev0 が鳴らなかった」を設定不備と読むと、
window や閾値をいじって解決しようとして時間を失う。**直すべき対象があるとすれば
それは監視の入力（外形プローブなど、より細かい粒度を持つ系列）側である。**

### 9-3. 副産物: 検知遅延の実測

発火した 2 回について、外形の実測と突き合わせると一貫した遅延がある。

| # | 障害開始（外形） | 最初の 0 バケット | fired | 復旧（外形） | resolved |
| --- | --- | --- | --- | --- | --- |
| 1 | 08:25:54.892Z | 08:27:00Z | 08:33:28.842Z | 08:31:25.054Z | 08:36:33.746Z |
| 4 | 10:12:04.984Z | 10:13:00Z | 10:19:28.077Z | 10:19:14.533Z | 10:24:32.446Z |

- **最初の 0 バケット → fired は 6 分 29 秒 / 6 分 28 秒**（ほぼ同一）
- **復旧 → resolved は 5 分 09 秒 / 5 分 18 秒**（ほぼ同一）
- **障害開始 → fired は 7 分 34 秒 / 7 分 23 秒**

**#4 では、アラートが鳴った 10:19:28Z の時点で、サービスは既に 10:19:14Z に復旧していた。**
つまり **Sev0 のページは復旧の 13.5 秒後に届いた。**

**5〜7 分級の断に対して、このアラートは事後通知にしかならない。**
これは `PT5M` window の構造上そうなる（窓が 0 を含まなくなるまで発火判定が続き、
解消判定にもさらに数分かかる）。**このアラートの役割は「短い断の即時検知」ではなく
「継続的な死亡の検知」である**、と読み直すべきである。

## 10. 測定スクリプトの欠陥（記録として不正確な点）

**外形ログを取った測定スクリプトに欠陥がある。** 判定には影響していないが、記録としては不正確である。

スクリプトは curl の失敗に備えて次のフォールバックを使っていた。

```bash
... || echo "000 5.000"
```

**curl は失敗時にも `-w` の出力を出すことがあり、その場合フォールバック文字列と連結される。**
実際に 834 サンプル中 2 件で桁が崩れた。

| 行 | 記録 | あるべき姿 |
| --- | --- | --- |
| 10:44:32.973Z | `readyz=000 livez=200 t=5.000465000` | `t=5.000465`（curl 実測）と `5.000`（定数）の連結 |
| 09:30:02.351Z | `readyz=200 livez=000000 t=0.146225` | `000`（curl 実測）と `000`（定数）の連結 |

- **HTTP コードの判定には影響していない。** `000` も `000000` も 200 ではないため、
  非 200 の判定は正しく行われる。§3 の downtime 集計は変わらない
- **しかし `t=5.000465000` は数値として不正**であり、`livez=000000` は
  存在しない HTTP コードである。**そのまま集計に入れると壊れる**
- 09:30:02.351Z の `livez=000000` は **`/livez` 側の単発の失敗**で、`/readyz` は 200 だった。
  forced failover の完了（09:29:56Z）直後だが、**因果関係は未検証**（1 サンプルのみ）

### 10-1. これは既知の罠を再発させたものである

**まったく同じ `|| echo` の連結問題を、2 日前に別の場所で発見・修正している。**

- フェーズ 1 の観測記録 §8-4 が、`readyz-probe.yml` の `|| echo "000 30.000"` について
  **「`latency_ms=30000` はちょうどフォールバック定数、`30002` は curl 自身が出した実測値。
  同じ `code=000` でも片方は実測でない」**と記録している（Issue #115 の対象 3）
- **`.github/workflows/readyz-probe.yml` では 2026-08-26 に修正済み**（commit `1183c19` / Issue #133）。
  現在は `read -r http_code latency_s _` で**先頭 2 フィールドだけを採り**、
  連結された残りを捨てる形になっている

```yaml
http_code_time=$(curl -sS -o /tmp/readyz-body.json -w '%{http_code} %{time_total}' \
  --max-time 30 "$READYZ_URL" || echo "000 30.000")
# curl は失敗時にも -w の出力（000 …）を出すことがあり、その場合は
# || のフォールバック文字列と連結される。先頭 2 フィールド（実測値
# 優先）を採る（レビュー指摘対応。実測: 実 curl の timeout で確認済み）
read -r http_code latency_s _ <<<"$http_code_time"
```

**ドリルの測定スクリプトは workflow とは別に書き起こされたため、この修正が反映されなかった。**
本番の workflow で潰した罠を、その場限りの測定スクリプトで作り直した形である。

**教訓**: 使い捨ての測定スクリプトでも、既に潰した罠のチェックは通す。
`|| echo` によるフォールバックは、**フォールバック側だけが出力される前提を置いている**が、
curl はその前提を満たさない。

## 11. Issue #157 の着手条件について

[Issue #157](https://github.com/kmryst/felis-ai-chatbot/issues/157)（`ignore_changes` に
`high_availability` を追加した副作用で、HA の drift が `plan` に現れなくなった件の判断保留）は、
**本ドリルの完了が着手トリガー**である。

**本ドリルは完了した。したがって #157 の判断が可能になった。**

判断材料として本記録が提供するもの:

- HA の有効化・無効化は **online operation** で、10 秒粒度で downtime が観測されない（§3-3）
- HA を有効化すると Azure が standby zone を**自動選択**する（§4。今回は zone 2）。
  つまり `high_availability` ブロックには**ユーザーが書いていない値が Azure 側から入る**
- ドリル終了後の `terraform plan -detailed-exitcode` は **exit 0**（差分なし）に戻っている（§12）

**ただし #157 の判断そのものは本記録では行わない。** 別途 #157 で扱う。

## 12. ドリルの最終ゲート: terraform plan

**`terraform plan -detailed-exitcode` が exit 0（差分なし）に戻っていることを確認した。**
これが「ドリルが構成に痕跡を残していない」ことの最終確認である。

```console
$ terraform -chdir=terraform/persistent plan -detailed-exitcode -input=false
...
No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration
and found no differences, so no changes are needed.

$ echo $?
0
```

2026-08-29 実行。refresh 対象 14 リソース（VNet / subnet 2 / private DNS zone + link /
Log Analytics / PostgreSQL + configuration / Action Group / メトリクスアラート 5）すべてで差分なし。

**注記**: `high_availability` は `ignore_changes` の対象である（Issue #156 / commit `be0f605`）。
**したがってこの exit 0 は「HA が Disabled に戻っている」ことの証明にはならない。**
HA が開始時の状態に戻っていることは **§1 の `az` による直接確認**が根拠である。
この「plan では見えない」という性質そのものが Issue #157 の論点である（§11）。

## 13. この記録が測っていないこと（限定の明記）

- **10 秒未満の断**は原理的に検出できない（§3-3）
- **データ量に対する failover 時間のスケール**は測っていない（§8-2）
- **planned / forced の応答時間の性質**は 2 + 3 サンプルしかなく、再現性は未検証（§5-1）
- **`/livez` の単発失敗（09:30:02Z）の原因**は未検証（§10）
- **同時実行下の failover** は測っていない。ドリル中の DB 書き込みは heartbeat の毎分 1 行のみで、
  **トランザクション実行中に failover が起きた場合の挙動は未検証**
- **アラートのメール受信そのもの**は本記録では確認していない（発火・解消は
  Alerts Management API の記録で確認した。配送経路の実証は台帳 §B の他 4 件による）

## 関連

- [ADR-0023](../../adr/0023-no-second-granularity-downtime-measurement.md) — 秒粒度の downtime 測定を行わない判断（本記録の測定粒度の根拠）
- [restore-drill-recovery-objectives.md](../../operations/restore-drill-recovery-objectives.md) — RPO / RTO 目標の宣言（§8 の照合先）
- [azure-resource-inventory.md](../../operations/azure-resource-inventory.md) §B — Azure Monitor アラートの設計値と試験状況（§9 で更新）
- [ADR-0021](../../adr/0021-heartbeat-table-as-recovery-marker.md) — `obs.heartbeat` の位置づけ（§8-2 のデータ量の前提）
- [observation-phase1/observations.md](../observation-phase1/observations.md) §8-3 / §8-4 — cold start の分布と `|| echo` 連結問題の初出（§3-2 / §10-1）
- Issue #157 — HA の drift の扱い（本ドリルの完了が着手トリガー。§11）
- Issue #158 — 本記録の起票元
