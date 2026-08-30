# ADR-0025: serving を min_replicas 1 へ変更し cold start による可用性 SLI の汚染を排除する

## ステータス

Accepted

## 日付

2026-08-30

## 決定内容

serving Container App `ca-felisaichatbot-dev` の `min_replicas` を **0 から 1 へ変更する**（`terraform/ephemeral/main.tf`）。

これは [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) 検討した選択肢 2-(a)「min_replicas 0 / max_replicas 1（採択）」の**上書き**である。ただし ADR-0015 の判断を無効化するのではない。「コールドスタート遅延は walking skeleton の検証（`/readyz` を叩いて 200 を見る）に影響しない」という当時の前提は walking skeleton 段階では正しかった。その後、外形監視（#106）で可用性 / レイテンシの SLI を蓄積するフェーズに移行し（[ADR-0020](./0020-credit-window-resource-strategy.md)）、**cold start が SLI を汚染することが実測で確定した**ため、前提の変化として記録する。ops / migrate Job / obs Job には触れない（ops の `min_replicas = 1` は ADR-0015 追記 #100 のとおり既に是正済み）。

timeout 系（`.github/workflows/readyz-probe.yml` の `--max-time 30`、`DB_CONNECT_TIMEOUT_SECONDS`、`STATS_MAX_AGE` 等）は**本決定に含めない**（理由は「検討した選択肢」3）。

## 背景

数値はすべて 2026-08-30 取得。取得手段は各項に記す。

### 失敗 3 件はすべて偽陽性で、可用性 97.71% は障害を 1 件も含んでいなかった

外形監視 probe（5 分ごと・`curl --max-time 30`）で `--max-time 30` により打ち切られた失敗 3 件を、Log Analytics のコンテナコンソールログ / システムイベントと突き合わせた結果（2026-08-30 実施）:

| probe `ts` | Uvicorn が listen するまで（実測） |
| --- | --- |
| 2026-08-24T22:22:05Z | 40.50s |
| 2026-08-25T10:18:11Z | 34.53s |
| 2026-08-25T20:51:19Z | 39.61s |

3 件とも `/readyz` のアクセスログが 1 行もなく、リクエストがアプリに到達する前に curl 側が切断している。**アプリは 3 件とも正常に起動していた**。つまり可用性 97.71% は障害を 1 件も含まず、実質「cold start が 30 秒以内に完了する率」を測っていた。

### probe レイテンシの内訳（Log Analytics 実測、n=128。curl 実測値との差は 50〜60ms）

| 区間 | p50 | max |
| --- | --- | --- |
| probe → `AssigningReplica` | 0.10s | 4.93s |
| `AssigningReplica` → `ContainerStarted` | **15.43s** | **21.60s** |
| `ContainerStarted` → Uvicorn 起動 | 0.97s | 2.09s |
| Uvicorn → `/readyz` 到達 | 5.10s | 11.58s |
| 合計 | 21.43s | 28.69s |

### cold start の全体分布（`AssigningReplica`→`ContainerStarted`、n=172、2026-08-21〜08-30、Log Analytics）

- min 8.00s / p50 15.45s / p90 16.76s / p95 18.35s / max 39.78s
- 二峰性: 8〜20 秒に 169/172（98.3%）、外れ値 33.2 / 38.4 / 39.8 秒の 3 件
- イメージ pull は常に 2.8〜3.1 秒で無実。遅延はすべて `PulledImage` → `ContainerCreated` の間（正常時 7〜17 秒、外れ値時 35.3 秒）。Issue #131 で obs Job に見つかった「約 38 秒 gap」と同じ位置・同じオーダーの現象
- 実測最悪ケース: 39.78（起動）+ 2.09（Uvicorn）+ 11.58（probe 待ち）+ 0.06（NW）≒ **53.5 秒**

### ACA 既定 probe は Terraform 作成の app にも適用されている（観測事実。公式記述は未発見）

ARM 上は `properties.template.containers[0].probes` が空配列であるにもかかわらず、実ログに `ProbeFailed: "Probe of StartUp failed with status code: 1"` 25 件、`ReplicaUnhealthy: "readiness probe failed: connection refused"` 13 件が出ている（Log Analytics、2026-08-30 確認）。公式ドキュメント（<https://learn.microsoft.com/en-us/azure/container-apps/health-probes> 、2026-08-30 確認）は

> the portal automatically adds the following default probes

（訳:「**ポータル**が既定でこれらの probe を追加する」）

としか書いておらず、**Terraform 作成でも適用される旨の公式記述は見つかっていない（未確認）**。適用されている事実は実ログによる観測である。同ページの既定値（2026-08-30 確認）:

- Startup: TCP / Timeout 3s / Period 1s / Initial delay 1s / Failure threshold 240
- Readiness: TCP / Timeout 5s / Period 5s / Initial delay 3s / Failure threshold 48

内訳表の「Uvicorn → `/readyz` 到達 5.10s」はこの Readiness の Period 5 秒で説明できる。

## 検討した選択肢

### 1. min_replicas 1 へ変更し、warm レプリカを常駐させる（採択）

cold start が SLI の測定対象から消え、可用性 SLI が本来の「サービスが応答できるか」を測るようになる。コストは「採択理由」のとおり残クレジットに対して無視できる規模。

### 2. min_replicas 0 のまま `--max-time` を延長する（却下）

偽陽性 3 件は max-time 40 秒超で解消し得るが、SLI が「cold start 込みの応答時間の分布」を測り続ける構造は変わらない。レイテンシ SLI は p50 で 21 秒台のままで、warm 時の実力（1 秒未満）と 1 桁半ずれた数字を蓄積し続ける。Issue #115 の外部レビューが指摘した「SLI の限定」問題の解決にならない。

### 3. min_replicas 1 と timeout 見直しを同時に行う（却下）

`min_replicas` と `--max-time` 等を同時に変えると、変更後に SLI の数字が動いたときに**どちらの影響か切り分けられない**。timeout の見直しは本変更の効果を観測してから別途判断する（ユーザー判断 2026-08-30 = 分離を選択）。`--max-time 30` は warm なら 1 秒台で応答するため「緩すぎる上限」として無害であり、据え置きで実害がない。

## 採択理由（コスト見積もりとその限界）

- 常時 1 レプリカの実測目安 **0.0769 USD/日**（同環境の ops コンテナ `ca-felisaichatbot-dev-ops` の 2026-08-29 実測 = 課金データ）
- teardown 2026-09-15（[credit-window-execution-plan.md](../operations/credit-window-execution-plan.md) §9）まで 16 日 × 0.0769 ≒ **1.2 USD**
- 残クレジット 195.12 USD（2026-08-30 実測）に対して 0.6%。定常バーンレートは 0.30 → 約 0.38 USD/日

見積もりの限界（未検証の前提を断定しない）:

- **0.0769 USD/日は ops コンテナの値**であり、serving app 自身の常時稼働コストは未実測。serving は 5 分ごとの probe リクエストを処理するため、idle 適格条件（HTTP 処理なし等。出典は ADR-0015 追記 #100 の billing 逐語）を probe 処理中は外れ、ops より高くなる可能性がある
- **9 月は ACA の無料付与枠がリセットされる可能性がある**（8 月は 8/27 から課金開始、それ以前はゼロ）。9 月はしばらく無料になり得るが**未検証**であり、上記見積もりには織り込まない

## 影響

- `terraform/ephemeral/main.tf`: serving app の `min_replicas` 0 → 1（この 1 行と根拠コメントのみ。ops / migrate Job / obs Job は不変更）
- 可用性 SLI: 以後の probe は warm レプリカに当たるため、失敗は「実際に応答できなかった」ケースへ純化する。フェーズ 1 の確定値 97.71% は「cold start が 30 秒以内に完了する率」だったという限定つきで読む（過去の実測記録は書き換えない）
- レイテンシ SLI: cold start 分布（p50 21.43s）から warm 応答時間へ切り替わる。変更前後の数字は連続していない
- **Issue #115 への影響**: 同 Issue の受け入れ条件 1「probe のコールドスタートコストの実測」は、本変更により cold start 自体が発生しなくなるため、**実施しないまま前提が消える**。この事実を本 ADR で記録する（#115 は close しない。受け入れ条件 2 の「min_replicas 1 にするかの判断」は本 ADR が回答になる）
- [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md): 検討した選択肢 2-(a) の serving スケールゼロのみ本 ADR で変更。他の決定（SKU / イメージタグ方針 / ACR pull 認証等）は引き続き有効

## 関連

- [ADR-0015](./0015-ephemeral-layer-acr-container-apps-design.md) — 上書き対象（serving の min_replicas 0）。ops の是正（追記 #100）の同型判断
- [ADR-0020](./0020-credit-window-resource-strategy.md) — 常時稼働・観測フェーズへの転換（前提が変わった源）
- [ADR-0023](./0023-no-second-granularity-downtime-measurement.md) / [ADR-0024](./0024-readyz-freshness-not-completeness.md) — 観測系が SLI を歪めない構造を守る同系列の判断
- Issue: #170（本変更）/ #115（SLI 限定とコールドスタートコスト実測。前提消滅を上記に記録）/ #131（`PulledImage`→`ContainerCreated` gap の先行観測）/ #106（外形監視の導入元）
