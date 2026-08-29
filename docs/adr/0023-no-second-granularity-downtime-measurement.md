# ADR-0023: HA ドリルの downtime を秒粒度で測らず 10 秒間隔で測る

## ステータス

Accepted

## 日付

2026-08-29

## 決定内容

- HA フェイルオーバードリルの downtime 測定は、**1 秒間隔ではなく 10 秒間隔**で行う
- 結果として、得られる downtime はすべて **±20 秒の粒度誤差**を持つ。
  この誤差を記録に明記し、点推定を精密値として扱わない
- **10 秒未満の断は測らないと決める**。測れなかったのではなく、**測る必要がないと判断した**
- 判定に不要でも**記録は取る**（測定そのものを省略はしない）
- 復活条件は §復活条件に定める

## 背景

2026-08-28 の HA ドリル（実測記録:
[failover-drill/observations.md](../verification/failover-drill/observations.md)）の設計時に、
downtime をどの粒度で測るかを決める必要があった。

failover の downtime は公称で 60〜120 秒（§検討した選択肢の 2）であり、
1 秒間隔で測れば「63 秒」のような値が得られる。10 秒間隔では「±20 秒の 24 秒」までしか言えない。
**精度は明らかに 1 秒間隔のほうが高い。** それでも 10 秒間隔を採った。

## 検討した選択肢

### 1. 1 秒間隔で測る（却下）

- **利点**: downtime を秒精度で言える。公称 60〜120 秒との比較が精密になる
- **欠点**: 下記「取らなかったリスク」の 3 点。とくに `/readyz` のハング時に
  プローブが積み上がる

### 2. 10 秒間隔で測る（採択）

- **利点**: リスクを負わない。判定は変わらない
- **欠点**: ±20 秒の誤差が乗る

### 3. 測定しない（却下）

判定に不要でも、**failover は観測機会が限られる**（§採択理由の 2）。
記録が無ければ後から取り直せない。

## 採択理由

### 1. 判定が変わらない — 桁が 2 つ違う

[restore-drill-recovery-objectives.md](../operations/restore-drill-recovery-objectives.md) §2 が
宣言する **RTO 目標は 3 時間 = 10,800 秒**である。
一方、failover の公称は **60〜120 秒**。

**この 2 つは桁が 2 つ異なる。**

- 1 秒間隔で「63 秒」と測っても、10 秒間隔で「±20 秒の 60 秒」と測っても、
  **RTO 目標 3 時間に対する判定は「大幅に下回る」で同一**である
- 判定を変えるには downtime が 10,800 秒の桁に近づく必要があり、
  そのときは秒精度など問題にならない

**精度を上げても、その精度で何かを決めるわけではない。**
測定の精度は、その精度で判断が変わるときにだけ意味を持つ。

### 2. 代わりに 10 秒間隔を採った理由 — 観測機会が限られる

「判定に不要だから測らない」ではなく「判定に不要でも記録は取る」を採った。
failover は**気軽に再実施できない**。公式・逐語:

> Don't perform immediate, back-to-back failovers. Wait for at least 15 to 20 minutes between
> failovers. This wait time allows the new standby server to be fully established.

（訳）

> 即座の連続したフェイルオーバーを行わないこと。フェイルオーバーとフェイルオーバーの間は
> 少なくとも 15 〜 20 分待つこと。この待ち時間により、新しい standby サーバーが完全に
> 確立される。

- 出典: "Configure High Availability" の *Initiate a forced failover* /
  *Initiate a planned failover* の Important ボックス
  <https://learn.microsoft.com/en-us/azure/postgresql/high-availability/how-to-configure-high-availability>
  （2026-08-29 確認）

さらに、この環境で failover を試すには **tier を Burstable → GeneralPurpose へ昇格させる
必要がある**（Burstable は HA 非対応）。**やり直しのコストが高く、機会が限られる。**

したがって「判定に必要な最小限だけ測る」ではなく、
**リスクを負わない範囲で取れるだけ記録を取る**という設計にした。10 秒間隔はその折衷である。

### 3. 取らなかったリスク（ドリルの実測で裏づけられた）

1 秒間隔にしていた場合に負っていたリスクは、次の 3 点である。
**1 と 3 はドリルの実測で実際に裏が取れた。**

#### `/readyz` の `SELECT 1` に statement_timeout が掛かっていない

`backend/app/db.py` の `check_database_ready()` は接続に `connect_timeout = 2 秒` を渡すが、
**`SELECT 1` には `statement_timeout` を設定していない。**
TCP は繋がるが応答が返らない状態になると、**無期限に待ち得る。**

**実測でこれが起きた。** 2026-08-28T10:44:32.973Z の 1 サンプルで、
`readyz` が返らず `curl --max-time 5` に切られた（`livez` は 200 のまま）。
詳細は[実測記録 §6](../verification/failover-drill/observations.md)。

- **`--max-time 5` があったため 5 秒で切れた**
- **1 秒間隔で叩いていたら、この 5 秒のあいだに 4 本が積み上がっていた**

#### `max_replicas = 1` で逃げ場がない

serving の Container App は `max_replicas = 1`（[ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md)）。
**積み上がったリクエストを引き受ける別レプリカが存在しない。**
上の 4 本は同じ 1 レプリカに積む。**測定行為そのものが観測対象を壊す**構図になる。

#### cold start の混入

serving は `min_replicas = 0` のため、無リクエスト状態から叩くと cold start が入る。
フェーズ 1 の実測で **中央値 21.49 秒 / p90 24.28 秒 / max 28.74 秒**
（[observation-phase1/observations.md §8-3](../verification/observation-phase1/observations.md)）。

**downtime の測定に 21 秒の cold start が混ざれば、測っているものが何なのか分からなくなる。**
これはドリル前のウォームアップで回避した（ドリル窓の 766 件の 200 応答は
**max 1.194 秒**で、cold start は 1 件も混入していない）。

**1 秒間隔はこの 3 つのリスクをすべて増幅する。** 得られるのは、判定を変えない精度である。

### 4. これは「時間がなかった」ではない

**秒粒度の測定は、実装コストの問題では却下していない。**
1 秒間隔のループを書くコストは 10 秒間隔と変わらない。

却下の理由は上記 1〜3、すなわち **「判定が変わらない」+「測定が観測対象を壊すリスクがある」**である。
コストが十分にあったとしても同じ判断をする。

## 影響

- HA ドリルの downtime はすべて **±20 秒**の粒度誤差を持つ。
  実測記録はこの誤差を各表に明記する
- **10 秒未満の断について、本ドリルは何も主張しない。**
  「HA 有効化・無効化の downtime がゼロ」も、正確には
  **「10 秒粒度で観測可能な downtime が無かった」**である
- `/readyz` の `statement_timeout` 欠落は**本 ADR では直さない**。
  本 ADR は測定粒度の判断であり、アプリの修正ではない。
  課題としては実測記録 §6-1 に残る

## 復活条件

次のいずれかに該当したら、本 ADR の判断を再検討する。

- **RTO 目標が分オーダーに変わった場合。** 目標が 3 時間から例えば 5 分に変われば、
  公称 60〜120 秒との桁差が消える。そのときは downtime を構成要素
  （**DB 復旧 / アプリ復旧 / cold start**）に分解して測る必要が出る。
  合計値だけでは、どこを縮めれば目標に届くかが言えないためである
- **`/readyz` に `statement_timeout` が入り、かつ `max_replicas` が 2 以上になった場合。**
  上記リスク 1 と 2 が消えるため、1 秒間隔の測定が安全になる
- **failover の観測機会が増えた場合**（HA を常設する構成に変わる等）。
  やり直しのコストが下がれば、精度を上げる試行が現実的になる

## 関連

- [failover-drill/observations.md](../verification/failover-drill/observations.md) — 本 ADR の判断に基づいて取った実測（§3-1 が測定方法と誤差、§6 がリスク 1 の実測）
- [restore-drill-recovery-objectives.md](../operations/restore-drill-recovery-objectives.md) §2 — RTO 目標 3 時間（採択理由 1 の前提）
- [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) — `min_replicas = 0` / `max_replicas = 1`（リスク 2 と 3 の前提）
- [observation-phase1/observations.md](../verification/observation-phase1/observations.md) §8-3 — cold start の分布（リスク 3 の実測）
- Issue #158 — 本 ADR の起票元
