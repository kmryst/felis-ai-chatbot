# SLI measurement record schema

| 項目 | 値 |
| --- | --- |
| Status | Draft（実装・検証前の仕様案） |
| Date | 2026-09-14 |
| Owner | project owner（kmryst） |
| Schema version | 未採用。prototype の検証対象となる版を固定する時に割り当てる |
| Implementation / validation | 未実装・未検証 |

## この文書で定義すること

SRE の指針である [operations/slo/](../../operations/slo/slo-document.md) をもとに、felis-ai-chatbot の authenticated synthetic transaction の
記録項目とデータ形式を定義する。felis 固有の SLI implementation の仕様として、この文書で管理する。
保存項目名、論理的な型、null 条件、状態値、算出方法はこの文書にまとめ、他の文書や実装から参照する。
現在は実装・検証前の仕様案（Draft）である。collector の実装・検証と SLO の採用は、別途 runbook の手順で行う。

- SLI specification、eligible / good / bad event、SLO、timestamp fields / event time / clock の定義は
  [slo-document.md](../../operations/slo/slo-document.md) を正本とする。
- 実装の選定・検証、baseline、SLO の採用・review は [slo-review-runbook.md](../../operations/slo/slo-review-runbook.md) を正本とする。
- SSE event の文法と data schema は [共有 contract](../../contracts/chat-sse/README.md) を正本とする。

本書は保存先や DB の物理 schema を指定しない。JSON Schema、collector、scheduler、credential、保存先、実行頻度、measurement timeout の具体値、
latency threshold、SLO target は未決定または未実装である。これらは runbook の手順で選定・検証する。
本書の追加によって SLI specification や error budget policy の意味、SLO の Draft 状態は変わらない。

## 記録の単位と責任

全項目を一つの結果 object に押し込めず、次の記録を関連付ける。同じ名称の共通項目は同じ意味で使う。

| 記録 | 書き手・根拠 | 識別と関連付け |
| --- | --- | --- |
| 予定 | scheduler の計画を保存する処理 | `schedule_id` と `scheduled_for` の組。job が起動する前から存在する |
| job 実行 | scheduler / runner の実行証跡を収集する処理 | `run_id`。対応する予定を参照する |
| 送信試行と測定結果 | synthetic client / verifier | `attempt_id`。`run_id` と予定を参照する |
| 収集・永続化の確認 | 保存先の受領証跡と実行証跡を照合する処理 | `attempt_id`。結果が欠落していても管理する |
| 分類・集計結果 | version 管理された query | 試行・入力記録の固定された参照・`query_version`・適用する `slo_version` を関連付ける |

一つの予定に複数の job、一つの job に複数の試行がある可能性を保持する。request を再送した場合は別の `attempt_id`、
同じ結果を再 upload した場合は同じ `attempt_id` を使う。結果の重複受領と、実際に複数回送信した request を混同しない。

予定と実行・収集管理の記録は、欠落し得る測定結果とは独立して保持する。管理記録自身が取得できない場合も確認不能とする。
`attempt_id` は送信準備中に確保してよいが、ID の存在だけでは送信開始を証明しない。実際の開始を確認できない場合、
`attempt_started_at` を予定や job 開始時刻で埋めず、開始の不確実性を記録する。
clock の取得と request 開始の間に永続化待ちを挟まない。

## 共通の型と命名

- `string` は文字列、`integer` は整数、`number` は有限の数値、`array<number>` は数値の配列を表す。
  `NaN` / `Infinity`、負の duration を有効な計測値として保存しない。
- 型に `null` を含める項目は、未到達・未観測・対象外を許す。理由は結果、状態、分類理由と組み合わせて区別する。
  `null` を 0、成功、対象外と解釈しない。適用される項目を黙って省略しない。
- `sse_events` は配列で、表中の `[]` は各要素の field path を表す。
- 保存項目名は既存の timestamp fields に合わせて snake_case とし、経過時間は `_ms` で保存単位を明示する。
  これは felis の命名規則であり、snake_case にしただけで標準 identifier になるわけではない。
- 下記の参照元がない追加の項目名と enum は、既存の技術用語を用いた felis 固有の定義である。独自の略語は導入しない。

## Timestamp fields

取得位置、UTC / RFC 3339 の表現、期間帰属の定義は
[slo-document.md の Timestamp fields](../../operations/slo/slo-document.md#timestamp-fields) を参照する。ここでは項目一覧と欠落時の扱いを示す。

| 項目名 | 型 | この schema での null 条件 |
| --- | --- | --- |
| `scheduled_for` | string | 予定の必須項目。関連する実行・試行にも同じ値を保持する |
| `attempt_started_at` | string または null | 未送信、または実際の送信開始時刻を復元できない場合 |
| `completed_at` | string または null | verifier の判定完了を確認できない場合 |
| `ingested_at` | string または null | 永続化を確認できない管理記録では null。保存済み測定結果では保存先が設定する |

`scheduled_for` は遅延実行でも変更しない。保存済み結果を再 upload しても、最初の永続化時刻を再送時刻で上書きしない。
追加の受領や管理状態の変化は履歴として残す。`completed_at` が存在しても永続化済みとは限らない。

## Monotonic clock による経過時間

開始・event 受理・verifier 完了の取得位置は
[既存の clock 定義](../../operations/slo/slo-document.md#monotonic-clock-による-latency-計測)に従う。
同一 process の monotonic clock で取得した未丸めの経過時間を使い、wall-clock timestamp の差から生成しない。

| 項目名 | 型 | 算出方法・null 条件 |
| --- | --- | --- |
| `time_to_first_output_ms` | number または null | 最初の有効な content の `elapsed_ms`。content 未受理、または必要な記録を復元できなければ null |
| `inter_chunk_latency_ms` | array<number> または null | 観測順に隣接する有効 content の `elapsed_ms` の差。完全な観測列に content が 0〜1 件なら `[]`。列が欠落し復元できなければ null |
| `last_content_to_done_duration_ms` | number または null | 有効な `done` と最後の有効 content の `elapsed_ms` の差。どちらかが存在しない、または間の観測列が欠落していれば null |
| `response_time_ms` | number または null | 有効な `done` の `elapsed_ms`。未受理なら null。補助指標であり、新たな SLO threshold を設けない |
| `failure_elapsed_ms` | number または null | request 開始後、最初の確定した失敗を検出した時点の経過時間。measurement timeout では観測を打ち切ると判定した時点。失敗なし・未送信・検出時点不明なら null |
| `attempt_duration_ms` | number または null | request 開始から verifier の処理完了まで。未送信・処理完了未確認・clock の連続性を確認できなければ null |

前半4項目は `sse_events` から算出する。raw な受理時点の記録と別々の時計で測らない。
`failure_elapsed_ms` と `attempt_duration_ms` は同じ開始点を使うが、失敗検出後の判定・終了処理を含むかが異なる。
`attempt_duration_ms` や `completed_at - attempt_started_at` で timeout の観測打切り時点を代用しない。

有効な `done` を受理した後に render の失敗を検出した場合、`response_time_ms` は保持し、`failure_elapsed_ms` と検証失敗を別に残す。
失敗した試行の既に観測できた content の値も消さない。未完了の試行に推定の `done`、最終 interval、完了時間を追加しない。
失敗時刻より前に記録欠落がある場合、`failure_elapsed_ms` だけを根拠にその全区間が観測できたとは扱わない。

`[]` は 0 ms の interval が存在する意味でも、成功した意味でもない。content が1件の `notice` → `done` でも、
最後の content → `done` の時間条件を評価する。隣接 content と最後の content → `done` に同じ threshold を使う既存 SLI を維持する。

## 応答結果と検証結果

| 項目名 | 型 | 意味・値 |
| --- | --- | --- |
| `terminal` | string または null | consumer の結果。`done` / `error` / `failed`。consumer の結果がない、または未確認なら null |
| `http_status_code` | integer または null | 受信した HTTP response の status code。response 未受信・不明なら null |
| `error_type` | string または null | request 開始後の試行の失敗分類。失敗を観測していない場合は null |
| `error_class` | string または null | 有効な SSE `error` event から取得した `class`。識別子は共有 contract を参照する。該当 event がなければ null |
| `parse_status` | string | `passed` / `failed` / `not_observed` |
| `render_status` | string | `passed` / `failed` / `not_observed` |
| `verification_method` | string または null | `http` / `browser`。実行した検証方法を記録し、不明なら null |

`terminal` は [既存 consumer](../../../frontend/lib/chat-sse/consumer.ts) の区別を使う。
`failed` は不正な stream / 終端なし等で consumer が失敗を確定した結果であり、SSE の event 名ではない。
HTTP error や reader の例外などで consumer の結果が得られなければ `terminal = null` とし、`error_type` と観測済みの値を残す。

`error_type` のこの schema における値は `timeout`、`dns_error`、`tls_error`、`connection_error`、`authentication_error`、
`http_error`、`stream_error`、`unexpected_eof`、`parse_error`、`render_error`、`unknown_error` とする。
`unknown_error` は失敗を観測したが種類を特定できない場合であり、結果そのものが不明な場合とは異なる。
`stream_error` は有効な SSE `error` に対応し、詳細は `error_class` に保持する。wire 上の `timeout` と measurement timeout を区別できる。
HTTP status を観測した場合は、認証失敗等の分類を追加しても status code を消さない。
失敗が連鎖した場合は最初の確定した原因を `error_type` / `failure_elapsed_ms` に残し、後続の検証結果はそれぞれの status に残す。

`parse_status` は終端までの系列条件を含む共有 contract の検証を完了した時に `passed`、違反を確認した時に `failed`、
検証を実施・完了できず結果を確認できない場合は `not_observed` とする。timeout までの部分列が正常というだけで `passed` にしない。
有効な `error` の parse 成功は request 成功ではない。
`render_status` はその試行で観測した supported browser の結果であり、HTTP の検証だけなら `not_observed` とする。
fixture の合格結果を、当該試行の browser 描画の `passed` に置き換えない。
共有 fixture / browser automation の別途の検証証跡は `validation_result_ref` と `client_version` で関連付ける。

## SSE event の記録

`sse_events` の型は array<object> または null とする。request 開始から終了・打切りまで、完全に取得できた観測列であれば空配列も許す。
観測列を復元できない場合は null とし、残存する部分的証跡は失わず別の evidence として保持する。
部分列を完全な配列として集計しない。worker の再起動をまたぐ monotonic 値の連結も行わない。

| 項目名 | 型 | 意味 |
| --- | --- | --- |
| `sse_events[].sequence_number` | integer | 0 から始まる連続した受理順序。wall clock で並べ替えない |
| `sse_events[].event` | string | consumer が受理した `message` / `notice` / `error` / `done` |
| `sse_events[].elapsed_ms` | number | request 開始から当該 event の受理までの経過時間 |

framing / UTF-8 / JSON / data schema の検証を経て受理した event を記録する。未完成・不正な event、無視した空 content は数えない。
不正な入力による失敗は `parse_status` / `error_type` に残す。有効な `error` event は `error_class` とともに記録する。
`elapsed_ms` は非減少とする。同じ read 内で受理した複数 event が同じ値になっても、時刻を補間して作らない。
この配列は受理時点の記録であり、元の response bytes や browser の描画証跡を代替しない。
再検証に必要な入力・検証ログは runbook に従って保存し、試行 ID と関連付ける。

## 実行・収集管理

| 項目名 | 型 | 意味・null 条件 |
| --- | --- | --- |
| `schedule_id` | string | 計画の必須識別子。同じ ID が指す schedule の履歴を保持する |
| `run_id` | string または null | 実際の job 実行の識別子。未起動・未確認なら null |
| `attempt_id` | string または null | 1回の送信試行に予約・割当した識別子。未割当・復元不能なら null。保存済み試行結果では必須 |
| `execution_status` | string | `scheduled` / `running` / `completed` / `failed` / `missed` / `unknown` |
| `execution_error_type` | string または null | job の失敗分類。`credential_error` / `configuration_error` / `runner_error` / `unknown_error`。失敗なし・未確認なら null |
| `collection_status` | string | `pending` / `stored` / `failed` / `missing` / `unknown` |
| `collection_error_type` | string または null | 収集・保存の失敗分類。`serialization_error` / `upload_error` / `storage_error` / `validation_error` / `unknown_error`。失敗なし・未確認なら null |

| 状態 | 判定条件 |
| --- | --- |
| `execution_status = scheduled` | 予定があり、起動または未実行の判定がまだ確定していない |
| `execution_status = running` | runner の起動・実行を証跡で確認した |
| `execution_status = completed` | runner が計測・終了処理の完了を報告した。チャットの成功や結果の永続化を意味しない |
| `execution_status = failed` | job 自体の失敗を確認した。送信後の service failure と同一視しない |
| `execution_status = missed` | 設定した判定期限を過ぎ、完全な scheduler / runner の証跡から起動がなかったと確認できた |
| `execution_status = unknown` | 実行の有無・状態を確認する証拠が足りない |
| `collection_status = pending` | 結果の永続化確認を待っている |
| `collection_status = stored` | 保存先が結果を永続化したことを確認した |
| `collection_status = failed` | serialize や保存拒否等の収集失敗を確認した |
| `collection_status = missing` | 試行の開始を確認しているが、設定した判定期限を過ぎても保存先に完全な結果がないことを確認した |
| `collection_status = unknown` | 保存先に到達できないなど、永続化の有無を確認できない |

job 未実行では試行結果と収集状態を捏造しない。送信前の credential 準備失敗では `execution_status = failed` と理由を残し、
`attempt_started_at` を作らない。送信開始後に観測した認証失敗は試行の `error_type` に記録する。
保存応答の喪失などで受領の有無が不明な場合は `unknown` として照合し、失敗や未保存を断定しない。

判定期限・猶予、照合に必要な証跡の保存方法は configuration の未決定項目である。値が未設定または証跡が不完全な時に、
経過時間だけで `missed` / `missing` を確定しない。遅延実行・late ingestion は元の予定・試行へ結び付けて履歴を残す。
SLO の期間帰属を変えず、再集計の入力 snapshot と query version を保存する。
同じ `attempt_id` の同一結果の再受領は冪等に扱い、異なる内容が届いた場合は上書きせず整合性の問題として記録する。
実際に送信した別の試行を、同じ予定から起動したという理由だけで重複として除外しない。

## 再現情報

| 項目名 | 型 | 保存する情報 |
| --- | --- | --- |
| `schema_version` | string | この記録の作成に使った固定された schema の版。保存する各記録で必須 |
| `configuration_version` | string | payload、認証方式、location、schedule、頻度、timeout、同時実行数、欠測判定条件等の設定 snapshot への固定参照 |
| `collector_version` | string または null | 実際に使用した計測プログラムの版 / commit SHA。未実行・確認不能なら null |
| `client_version` | string または null | 検証対象の supported client の版。確認不能なら null |
| `slo_version` | string または null | 試行開始時に有効な SLO Version。未採用の baseline では null |
| `deployment_revision` | object | `frontend` / `backend` を key、実際の revision の string または null を値とする |
| `image_digest` | object | `frontend` / `backend` を key、実際の image digest の string または null を値とする |
| `validation_result_ref` | string または null | 使用した configuration / collector / client に対応する固定された検証結果への参照。未検証・参照不能なら null |

version の文字列だけでなく、その版の設定、code、検証結果を取得できる状態で保持する。
configuration / validation の固定参照で SLI implementation の組合せを追跡し、変更前後の比較可能性を runbook で確認する。
deployment 情報は観測した根拠と関連付け、作業 checkout の HEAD や deployment の予定値で代用しない。
複数 revision に traffic が分散して試行が通った revision を特定できない場合は、その component を null とし、配置状況を別途の証跡に残す。
credential 自体を設定 snapshot に保存せず、認証方式・主体・credential の参照を記録する。

## 分類・集計の出力

これは raw measurement の上書きではなく、固定した入力と query による別の出力である。
分類の定義は [SLI と SLO](../../operations/slo/slo-document.md#sli-と-sloslis-and-slos) と runbook を参照する。

| 項目名 | 型 | 意味・値 |
| --- | --- | --- |
| `eligibility` | string | `eligible` / `excluded` / `unknown`。scope と request の証拠から判定する |
| `outcome` | string | `good` / `bad` / `unknown` / `not_evaluated` |
| `classification_reason` | string | 判定の根拠。除外・判定不能・未評価では理由と不足する証拠を必須とする |
| `query_version` | string | 判定処理の固定された版。対象 window、入力 snapshot、適用する設定・SLO とともに保存する |

分類順序は次のとおりとする。

1. scope の根拠から `eligibility` を判定する。未実行の予定を架空の試行として eligible / bad にしない。
2. 適用する threshold 等の判定規則が未指定なら `outcome = not_evaluated` とする。観測済みの失敗は raw の結果・理由として保持する。
3. 評価対象外なら `not_evaluated`、eligibility を確認できなければ `unknown` とする。
4. eligible な試行で、観測済みの error / timeout / contract 違反 / threshold 超過等から bad が確定すれば `bad` とする。
5. 有効な `done`、必要な時間条件、parse / render の証拠をすべて確認できた場合だけ `good` とする。
6. bad も good も確定できない証拠不足は `unknown` とし、成功にも自動除外にもしない。

threshold をまだ指定していない baseline の収集では `not_evaluated` とする。
SLO 採用前でも、runbook に従って候補の threshold・設定・入力 snapshot・query を固定し、検証・分析用に分類してよい。
その場合は候補への参照と検証・分析目的を分類結果に記録し、未採用の `slo_version` は null のままとする。
この分類結果を正式な SLO compliance や error budget として報告しない。

HTTP synthetic だけで `render_status = not_observed` となる場合、単に `done` があるという理由で `good` にしない。
proxy として何を分類できるか、必要な検証と coverage が何かは、SLI implementation の選定・検証で解決する。
`validation_result_ref` の存在だけで未観測の runtime 挙動を観測済みに置き換えない。

eligible / good / bad / excluded / unknown の件数と、予定・実行・未実行・結果欠落・重複受領の件数は、対応する記録から算出する。
個々の request の `bad` が確定していても、集計全体の data quality / coverage が不十分なら SLO compliance や error budget を報告しない。

## 実装時に確認する例

以下は仕様確認用の仮の経過時間であり、実測値・timeout 設定値・threshold 候補ではない。

| 観測 | 主な記録・算出結果 |
| --- | --- |
| content を 100 / 160 ms、done を 200 ms、verifier 完了を 220 ms で観測 | `time_to_first_output_ms = 100`、`inter_chunk_latency_ms = [60]`、`last_content_to_done_duration_ms = 40`、`response_time_ms = 200`、`failure_elapsed_ms = null`、`attempt_duration_ms = 220` |
| notice を 80 ms、done を 120 ms で観測 | `time_to_first_output_ms = 80`、`inter_chunk_latency_ms = []`、`last_content_to_done_duration_ms = 40`、`response_time_ms = 120` |
| content なしで 900 ms に timeout、930 ms に検証完了 | `time_to_first_output_ms` / `last_content_to_done_duration_ms` / `response_time_ms` は null、完全に取得できた `sse_events` は `[]`、`failure_elapsed_ms = 900`、`attempt_duration_ms = 930` |
| content の後に有効な SSE error | 観測済み `time_to_first_output_ms` / `inter_chunk_latency_ms` を保持。`last_content_to_done_duration_ms` / `response_time_ms` は null。`terminal = error`、`error_type = stream_error` と wire の class を保存 |
| done を受理したが render に失敗 | `response_time_ms` は保持し、`render_status = failed` と失敗検出時刻を保存。done だけで good にしない |
| 結果の一部を喪失 | 復元不能な event 列・派生値は null。部分的な evidence は保持し、`[]` や 0 に置換しない |
| job が起動せず、完全な証跡と判定期限がある | 予定を残して `execution_status = missed`。試行の開始時刻・応答結果は作らない |
| upload 後に応答を喪失 | 同じ `attempt_id` で照合・再送。保存の確認までは `collection_status = unknown`。結果を二重計上しない |

これらに加え、clock 補正、遅延到着、同一 read 内の複数 event、空 content、byte 分割、collector 再起動、保存障害を
runbook と共有 fixture に沿って検証する。実装・validation の証跡を残すまでは本書を検証済みとは扱わない。

## 命名の根拠

公開名を参考に、felis の measurement point、SSE contract、保存単位に合わせて定義した。
改名・単位 suffix・観測対象の変更を含むため、参照元と同一の metric / attribute identifier や同一の計測値とは扱わない。

| 保存項目 | 一次資料 | 参考にした点と相違 |
| --- | --- | --- |
| `time_to_first_output_ms` | [AI SDK の型定義](https://github.com/vercel/ai/blob/6c6c2210b9532a4c369615c044a16d595f3db117/packages/ai/src/generate-text/step-result.ts#L115)、[output 判定](https://github.com/vercel/ai/blob/6c6c2210b9532a4c369615c044a16d595f3db117/packages/ai/src/generate-text/stream-language-model-call.ts#L842) | `timeToFirstOutputMs` は最初の生成 output chunk まで。SDK は reasoning / tool 等も含む。felis は有効な message / notice の受理を対象にする |
| `inter_chunk_latency_ms` | [NVIDIA AIPerf の実装](https://github.com/ai-dynamo/aiperf/blob/7db2ba37a62aa80c882bc90eaf61cc8073e2387b/src/aiperf/metrics/types/inter_chunk_latency_metric.py#L31) | `inter_chunk_latency` は content response の隣接時刻差の配列で、usage-only / DONE を除外。felis は consumer 受理時点の ms を保存する |
| `response_time_ms` | [AI SDK の finish 処理](https://github.com/vercel/ai/blob/6c6c2210b9532a4c369615c044a16d595f3db117/packages/ai/src/generate-text/stream-language-model-call.ts#L588) | `responseTimeMs` は model call から finish 処理まで。felis は public frontend への request 開始から有効な done 受理まで |
| `terminal` / `error_class` | [既存 consumer](../../../frontend/lib/chat-sse/consumer.ts)、[共有 contract](../../contracts/chat-sse/README.md) | consumer の処理結果と wire の class を区別する。保存側の `error_class` は consumer の `errorClass` に対応する |
| `http_status_code` | [OpenTelemetry HTTP attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/http/#http-attributes) | `http.response.status_code` の意味と整数型を参考にする。保存項目名は異なる |
| `error_type` | [OpenTelemetry Error attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/error/#error-attributes) | `error.type` の失敗分類・低 cardinality の考え方を参考にする。felis の値一覧は本書で定義する |

`last_content_to_done_duration_ms` に一致する公開の専用名は、上記資料では確認できていない。
`failure_elapsed_ms` / `attempt_duration_ms` と同様に、必要な区間を既存の技術用語と event 名で表した本 project の保存項目である。
TTFT / inter-token latency へ改名したり、標準名に合わせるために SLI の測定区間を変えたりしない。
