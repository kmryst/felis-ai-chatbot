# ADR-0024: `/readyz` の鮮度判定に完全性の検査を持ち込まない（鮮度と完全性の役割分担）

## ステータス

Accepted

## 日付

2026-08-30

## 決定内容

- `backend/app/db.py` の `_OBS_FRESHNESS_SQL` は **`now() - max(ts)` のまま据え置く**。
  時系列の欠落（gap）を走査するクエリを `/readyz` に**入れない**
- 役割分担を次のとおり固定する:
  - **`/readyz` の鮮度判定 = 「いまの鮮度」**。最後のレコードから何秒経ったかだけを返す
  - **obs テーブルの gap 集計 = 「完全性」**。窓を区切った事後の集計で、
    欠落・間隔分布・取得率を判定する
- **この限界を明示する**: 採取が止まり、次の probe より前に復旧した停止は、
  `/readyz` からは**永久に見えない**。`/readyz` が green であることは
  「採取が 1 度も欠けていない」ことを意味しない
- 実装は変更しない。`db.py` には限界を指す docstring の追記のみを行う

（2026-08-30 のユーザー判断。「実装を直さず、限界を受容して明文化する」という判断そのものを本 ADR に残す）

## 背景

`/readyz` は観測 3 系列（`obs.heartbeat` / `obs.db_stats` / `obs.bloat_stats`）の
最新レコードからの経過秒を返し、外形監視（#106）が系列別に鮮度ゲートで判定している
（設計は [credit-window-execution-plan.md](../operations/credit-window-execution-plan.md) §5-3）。

このクエリは 3 系列とも `now() - max(ts)` のみで、**系列の途中の欠落を一切見ていない**。
採取が止まっても、次の probe が来る前に復旧して 1 行でも積まれれば、`max(ts)` は新しくなり
鮮度ゲートは green のまま通過する。**その停止は以後どの probe からも観測できない。**

フェーズ 1 では実際に `obs.db_stats` の取得率が 89.5%（773 / 864）で、鮮度ゲートは
一度も fail していない。この欠落を検出したのは `/readyz` ではなく、
**窓を固定した gap 集計**である（[observation-phase1/observations.md §9-1](../verification/observation-phase1/observations.md)。
最大 gap **393.32 秒** / 閾値 900 秒に対し超過 0 件、2026-08-26T08:51Z 取得。
同記録は改名前の `obs.marker` 表記のまま残す運用のため、系列名が本 ADR と分かれて見える = 計画書 §2 の記法の注記）。

つまり役割分担は**すでに実践されている**。明文化されていないだけだった。

## 検討した選択肢

### 1. `/readyz` に gap スキャンを追加する（却下）

`_OBS_FRESHNESS_SQL` を `lag(ts) OVER (ORDER BY ts)` で窓を舐める形へ拡張し、
閾値を超える gap が窓内に存在したら fail させる案。

- **利点**: 完全性の破れを probe が直接検出でき、事後集計を待たずに気づける
- **欠点**: 採択理由 1 のとおり、**Issue #114 で明示的に避けた構造をこちらから作り直す**ことになる

### 2. `now() - max(ts)` のまま据え置き、完全性は事後の gap 集計に任せる（採択）

- **利点**: readiness probe の時間予算を守る。フェーズ 1 で実際に機能した運用をそのまま固定できる
- **欠点**: 「止まって、次の probe より前に戻った」停止を probe では検出できない。
  この限界を文書に書いて受け入れる

### 3. gap 集計を別エンドポイント / 別ジョブとして常設する（今回は採らない）

- **利点**: 1 の検出力を、readiness の時間予算から切り離して得られる
- **欠点**: 新しい常設物（エンドポイントまたは Job）が増え、それ自体の無音失敗を
  誰が見るかという問題が 1 段増える。クレジット窓（失効 2026-09-18T06:59:34Z）で
  優先する主成果物ではない。**却下ではなく、復活条件つきの見送り**である

## 採択理由

### 1. readiness probe に重いクエリを載せることは、#114 で自分が避けた構造そのもの

`db.py` の `fetch_observation_freshness()` の docstring は、`statement_timeout` を
接続時に明示した理由をこう書いている（Issue #114 の 3）:

> エラーは上の設計で吸収できるが、クエリの遅延はそのまま /readyz の遅延になり、
> 外形監視の 30 秒 timeout に達すると観測系の問題が可用性 SLI の欠測に化ける。

上限は接続 timeout と同じ **2 秒**（既定）である。gap スキャンは `max(ts)` と違って
**窓の全行を走査する**。系列が伸びるほど重くなり、ロック待ちや高負荷時には 2 秒の予算を
先に食い潰す。そうなると `statement_timeout` が効いて例外 → `None` 返却となり、
**「観測が完全か」を見に行った結果として `/readyz` の応答が遅くなる**。

これは #114 が名指しで避けた「観測系の問題が可用性 SLI の欠測に化ける」経路そのものである。
**自分で立てた設計意図を、後から自分で壊すことになる。**

なお可用性 SLI 側にも同じ構図の実測がある: `/readyz` が返らず `curl --max-time 5` に
切られた 1 サンプルが HA ドリルで観測されており（[ADR-0023](./0023-no-second-granularity-downtime-measurement.md)
の「取らなかったリスク」）、serving は `max_replicas = 1`（[ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md)）で
積み上がったリクエストの逃げ場がない。**probe を重くする方向の変更は、この環境では特に割に合わない。**

### 2. 完全性の一次証拠はすでに別経路で取れており、実運用で機能した

フェーズ 1 の完全性判定は gap 集計で行い、`obs.db_stats` の 89.5% という
**鮮度ゲートが検出しなかった欠落**を実際に拾っている（§背景）。
採取 Job の合否は「execution の成否」ではなく「採取データの完全性」で判定する、という
運用は [obs-job-success-criteria.md](../operations/obs-job-success-criteria.md) が正本で、
`/readyz` はそこに含まれていない。

**役割分担は設計として先に決めたものではなく、運用の結果として成立していた。**
本 ADR はそれを追認して固定するものである。

### 3. 2 つの指標は測っている対象が違う — 片方でもう片方を代替できない

| | `/readyz` の鮮度判定 | obs テーブルの gap 集計 |
| --- | --- | --- |
| 問い | **いま**採取が生きているか | 窓の中で**欠けたか** |
| 時制 | 現在（最後の 1 行だけ） | 過去（窓の全行） |
| 実行主体 | 外形監視 probe（オンライン） | 事後のクエリ（オフライン） |
| 検出できる | 継続中の停止 | 復旧済みの停止・間隔のずれ・取得率 |
| 検出できない | **復旧済みの停止**（本 ADR の限界） | 進行中の停止（次の集計まで気づかない） |
| 時間予算 | 2 秒（`statement_timeout`） | なし |

**gap 集計は「進行中の停止」を即時には教えない。** だから `/readyz` の鮮度判定は必要であり、
どちらか一方に寄せる設計にはならない。2 つで 1 組である。

## 影響

- **`/readyz` の green は「採取が欠けていない」ことの証拠にならない。**
  成果物で完全性を主張するときは、必ず gap 集計の数字を根拠にする
  （フェーズ 1 の書き方が先例 = [observation-phase1/observations.md §9-1](../verification/observation-phase1/observations.md)）
- `backend/app/db.py` は挙動を変えない。`_OBS_FRESHNESS_SQL` の直上に、
  この限界と本 ADR への参照を docstring / コメントとして置く
- 鮮度ゲートの閾値（`obs.db_stats` は 900 秒）は本 ADR では触らない。
  閾値の根拠は計画書 §5-3 のまま
- 「復旧済みの停止を検出できない」は**未解決の課題ではなく、受容した限界**である。
  課題として再燃させる条件は下記に定める

## 復活条件

次のいずれかに該当したら、本 ADR の判断を再検討する。

- **完全性の破れを即時に検出する要求が生まれた場合**（例: 採取の欠落が SLO 違反として
  扱われるようになる）。事後集計では要求を満たせないため、選択肢 3（別経路での常設集計）へ進む
- **`/readyz` の時間予算の制約が消えた場合**。`max_replicas` が 2 以上になり、
  かつ外形監視の timeout に対して十分な余裕が実測で確認できれば、選択肢 1 の欠点が薄まる
- **系列が有限窓で完結しなくなった場合**。現在は窓を固定した事後集計で足りているが、
  無期限に積み上がる系列を扱うようになれば集計側の設計から見直す

## 関連

- `backend/app/db.py` — `_OBS_FRESHNESS_SQL` と `fetch_observation_freshness()`（本 ADR の対象。設計意図は Issue #114 の 3）
- [credit-window-execution-plan.md](../operations/credit-window-execution-plan.md) §5-3 — 3 系列の採取設計と鮮度ゲートの閾値
- [obs-job-success-criteria.md](../operations/obs-job-success-criteria.md) — 採取 Job の合否は採取データの完全性で判定する（#104 / #131 / #137）
- [observation-phase1/observations.md §9-1](../verification/observation-phase1/observations.md) — gap 集計による完全性の実測（最大 gap 393.32 秒、取得率 89.5%）
- [observation-phase1/observations.md §9-2](../verification/observation-phase1/observations.md) — execution status と採取データの完全性は別物である（同じ「指標が別物」の構図）
- [ADR-0023](./0023-no-second-granularity-downtime-measurement.md) — `/readyz` を叩く頻度を上げないという同系統の判断（測定が観測対象を壊す）
- [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) — `max_replicas = 1`（採択理由 1 の前提）
- Issue #114 — `statement_timeout` の明示（避けた構造の出所）
- Issue #166 — 本 ADR の起票元
