# 一時 Container App による platform 制約 3 点の実測記録（Issue #183）

ADR-0027（[frontend の Azure デプロイと公開面の構成](../../adr/0027-frontend-azure-deployment-and-public-surface.md)）と
ADR-0028（[/chat の SSE 化と応答契約の固定](../../adr/0028-chat-sse-response-contract.md)）が
「未検証の前提」「未解決」と明記していた次の 3 点を、使い捨ての一時 Container App で実測した記録。
**時刻はすべて UTC**。raw 証跡は [raw/](./raw/) に置く（各ファイル先頭の `note` 行に出所を記載）。

- (a) Easy Auth sidecar 稼働時の `X-MS-CLIENT-PRINCIPAL-*` header 偽装の可否（ADR-0027 決定 10）
- (b) revision 切替（env 変更 apply → 新 revision が 100% traffic）の所要時間（ADR-0027「付随する決定」）
- (c) ingress 既定 240 秒 timeout が総リクエスト時間かアイドル時間か（ADR-0028「影響」）

本記録は platform 制約の実測であり、**SLI threshold の根拠には流用しない**
（ADR-0028「影響」の「platform の制約であって SLO の値ではない」という方針を維持する。Issue #183 受け入れ条件）。
また、観測できなかった事象について「存在しない」とは結論しない。

## 1. 成果物の限界（実行ログからの事後復元）

**この記録は、実測を実施した担当エージェントの実行ログ（セッションログ）からの事後復元である。**
実測自体は 2026-09-01 に成功したが、担当エージェントが記録を書く前にセッション上限で停止し、
一時リソースは記録執筆前に削除された。そのため:

- 本記録の値・引用はすべて実行ログに残っていた実測出力からの転記であり、**Azure 上での再確認はできない**
  （再測定には一時リソースの再作成が必要で、本 PR の範囲外）
- [raw/](./raw/) の SSE クライアントログ・revision 測定ログは、実行時にローカルへ書き出された
  出力ファイルの現物のコピー。テスト 1（header 偽装）の raw は実行ログからの事後抽出で、
  Bearer token 値のみ `[REDACTED]` にマスクした
- ログから読み取れなかった値は本記録では埋めず、§8「ログから復元できなかった情報」に列挙した

## 2. 実施条件（identity）

| 項目 | 値 | 取得根拠 |
| --- | --- | --- |
| 実施日 | 2026-09-01（アプリ作成 09:22:44Z、revision 実測 09:45:40Z〜09:47:36Z。テスト 1 と teardown はその後・同日中） | Azure 応答の `systemData.createdAt`、測定ログの `apply_start` |
| リージョン | Japan East（japaneast） | `az containerapp show` の `location` |
| Resource Group | `rg-felis-ephem-verify-183`（使い捨て。tag: `purpose=ephemeral-verification`, `issue=183`） | `az group create` / `az containerapp create` 出力 |
| Container App | `ca-felis-ephem-verify-183` | 同上 |
| Container Apps Environment | 既存の `cae-felisaichatbot-dev`（`rg-felisaichatbot-dev-tf`）を参照。subscription の quota 制約で新規 CAE を作成できなかったため | `az containerapp show` の `environmentId` |
| イメージ | `acrfelisephem18309a1.azurecr.io/ephemeral-verify:183`（Python 3.12.14 標準ライブラリのみの SSE echo サーバ。[raw/server.py](./raw/server.py) / [raw/Dockerfile](./raw/Dockerfile)） | `az containerapp show` の `image`、SSE 応答の `server` ヘッダ |
| イメージ digest | `sha256:fbdb955a07f0bd21a5c81ce58a9107fa77fab8dbbd09bd36dc2f6e061415e253` | `docker push` 出力と ACR manifest 一覧（タグ付き manifest はこの 1 つのみ。タグ値の表示はログ上で途切れているが、この repository に push したタグは `183` の 1 つだけ） |
| スケール / リソース | `min_replicas = 1` / `max_replicas = 1`、0.25 vCPU / 0.5 Gi、Consumption workload profile | `az containerapp show` |
| ingress | external / HTTP / target-port 8080。timeout 関連の既定値は変更していない | `az containerapp create` の指定 |
| revision モード | single revision mode（既定。新 revision 作成で旧 revision が置換・drain される挙動を観測） | revision 一覧の遷移 |
| Easy Auth 構成（テスト 1 時点） | `platform.enabled = true`、provider は `azureActiveDirectory` のみ、`unauthenticatedClientAction = AllowAnonymous`（[raw/easyauth-config.json.txt](./raw/easyauth-config.json.txt)） | `az containerapp auth show` |
| Entra app registration | `felis-ephem-verify-183-easyauth`（appId `12c7e2ab-3b75-411f-ac23-499b560c9a50`）+ 同 appId の service principal（client credentials 用） | `az ad app create` / `az ad sp create` 出力 |
| 測定クライアント | SDK 不使用。Python 標準ライブラリで SSE の raw バイト列を relative 秒つきで記録（[raw/sse_client.py](./raw/sse_client.py)）、revision 測定は `az` CLI polling（[raw/measure_revision.sh](./raw/measure_revision.sh)） | raw/ の現物 |

補足:

- secret（Easy Auth client secret、Bearer token）はいずれも一時ファイル経由でのみ扱い、
  実行ログ・本記録・raw のどこにも値を出力していない（raw 内の `Authorization` は `[REDACTED]`）
- 一時アプリは Terraform 管理外・本番経路と非共有。既存リソースには CAE の参照以外で触れていない

## 3. (a) Easy Auth principal header 偽装

### 観測した事実

**baseline（Easy Auth 有効化前 = sidecar 無し）**: 偽装した `X-MS-CLIENT-PRINCIPAL-ID` /
`X-MS-CLIENT-PRINCIPAL-NAME` を付けた request は、**そのままアプリに到達した**
（アプリの /echo が `x-ms-client-principal-id: attacker-id` 等をそのまま観測。
[raw/t1-baseline-no-easyauth-echo.txt](./raw/t1-baseline-no-easyauth-echo.txt)）。

**テスト 1a（Easy Auth 有効・無認証 + 偽装 header 4 種）**: `X-MS-CLIENT-PRINCIPAL-ID` /
`-NAME` / `-IDP` / `X-MS-CLIENT-PRINCIPAL`（base64 の `{"fake":"principal"}`）をすべて付けた
無認証 request に対し、アプリが観測した principal header は **0 個**（4 種すべて、アプリに
届く前に除去された。[raw/t1a-unauth-spoof-echo.txt](./raw/t1a-unauth-spoof-echo.txt)）。

**テスト 1b（Easy Auth 有効・認証済み + 偽装 header）**: client credentials flow で取得した
Bearer token（`aud = api://<appId>`、`iss = sts.windows.net/<tenant>`）と同じ偽装 header 4 種を
併せて送ったところ、アプリが観測した `x-ms-client-principal` は **sidecar が注入した実 principal**
（`auth_typ = aad`、実 claims 16 個: `aud` / `iss` / `appid` / service principal の `oid` を含む）で、
偽装した `{"fake":"principal"}` は**完全に置換され、`"fake"` キーは残っていなかった**。
`x-ms-client-principal-id` は service principal の oid、`-idp` は `aad`、`-name` は appId に
上書きされていた（[raw/t1b-authed-spoof-echo.txt](./raw/t1b-authed-spoof-echo.txt) /
[raw/t1b-principal-decoded.txt](./raw/t1b-principal-decoded.txt)）。
なお `Authorization` ヘッダ（Bearer token）自体はアプリまで素通しされた。

### 言えること / 言えないこと

- 言えること: この構成（ACA Easy Auth、AAD provider、AllowAnonymous）では、外部 caller による
  `X-MS-CLIENT-PRINCIPAL-*` の偽装は、無認証では**除去**、認証済みでは**実 principal への置換**により
  アプリに到達しなかった。ADR-0027 決定 10 の未検証の前提（「sidecar が偽装 header を上書き・除去する」）は
  この実測と**一致**した
- 言えないこと: 認証済みケースは client credentials（app-only）token の 1 経路のみで、対話ユーザーの
  token では未実測。また `unauthenticatedClientAction = Require` 構成や本番 frontend 実機での挙動は
  本実測の範囲外（Issue #183 の補足どおり、frontend 実装 PR の実地検証を置き換えない）

## 4. (b) revision 切替（env 変更 apply → 新 revision 100% traffic）

### 観測した事実

env 値（`REV_MARKER`）の変更を `az containerapp update` で apply し、apply コマンド開始から
「最新 revision が traffic weight 100% かつ running」判定までを polling で計測した。
**クリーンな実測は 4 回**（[raw/t2-revision-switch-s5-s8.log](./raw/t2-revision-switch-s5-s8.log)）:

| iteration | apply_start (UTC) | 新 revision | `az update` 復帰まで | apply 開始 → 100% traffic |
| --- | --- | --- | --- | --- |
| s5 | 09:45:40Z | `--0000004` | 14.96 秒 | **20.31 秒** |
| s6 | 09:46:01Z | `--0000005` | 17.81 秒 | **35.02 秒** |
| s7 | 09:46:36Z | `--0000006` | 12.36 秒 | **28.41 秒** |
| s8 | 09:47:04Z | `--0000007` | 16.45 秒 | **32.48 秒** |

範囲は約 20〜35 秒。このうち `az update` コマンド自身の復帰が 12〜18 秒を占める。
測定の分解能は polling 間隔（`az` CLI の逐次呼び出し）に依存する。

これより前の試行（marker r1〜r2、s1〜s4 相当）は測定スクリプトの判定バグ
（`runningState` の `RunningAtMaxScale` を想定せず、また tsv 出力の読み取り誤り）で
計時が成立しておらず、実測値としては採用しない。

また副次観測として、single revision mode では新 revision 作成時に旧 revision が置換・drain され、
旧 revision への接続中 SSE stream が切断された（§5 の交絡の項）。

### 言えること / 言えないこと

- 言えること: この一時アプリ（極小イメージ・0.25 vCPU・replica 1）では、env 変更 apply から
  新 revision 100% traffic まで 20.31〜35.02 秒（4 回）だった。ADR-0027「付随する決定」の
  rotation 混在窓は、この条件では数十秒オーダーの実時間幅として観測された
- 言えないこと: 本番 frontend / backend のイメージサイズ・起動時間・replica 数での値は未実測であり、
  この 4 回の値をそのまま一般化しない。混在窓の SLO 正本改訂への反映は、実運用構成での値を
  別途得るまで「この条件での実測」としてのみ扱う

## 5. (c) ingress 既定 240 秒 timeout の意味（総リクエスト時間か、アイドル時間か）

### 観測した事実

SSE stream（chunked、`text/event-stream`）で event 送出間隔を変えた 4 本を、
**revision 変更を一切行わない隔離状態**で実測した:

| run | event 間隔 | 結果 | raw |
| --- | --- | --- | --- |
| T3(i) | 30 秒 × 20 event | **総時間 602.30 秒で `done` まで完走**・正常クローズ（切断なし） | [t3i-rerun-interval30.log](./raw/t3i-rerun-interval30.log) |
| T3(ii) | 300 秒 | 最初の event が届く前、**アイドル 237.46 秒（t=237.56）で peer から切断** | [t3ii-rerun-interval300.log](./raw/t3ii-rerun-interval300.log) |
| T3(iii) | 200 秒 × 2 event | **総時間 401.05 秒で完走**（アイドル 200 秒を 2 回挟んでも切断なし） | [t3iii-interval200.log](./raw/t3iii-interval200.log) |
| T3(iv) | 300 秒（再現） | **アイドル 240.19 秒（t=240.27）で peer から切断**（T3(ii) を再現） | [t3iv-interval300-reproduce.log](./raw/t3iv-interval300-reproduce.log) |

初回の実行（[t3-confounded-interval30.log](./raw/t3-confounded-interval30.log) /
[t3-confounded-interval300.log](./raw/t3-confounded-interval300.log)、いずれも約 135〜137 秒で切断）は、
並行して走っていた revision 切替測定が接続先 revision を drain したことによる**交絡で無効**とし、
上表の隔離再実行に置き換えた。

副次観測として、Easy Auth 有効化前の /echo で `x-envoy-expected-rq-timeout-ms: 1800000`（30 分）
という envoy 由来のヘッダがアプリに到達していた（[raw/t1-baseline-no-easyauth-echo.txt](./raw/t1-baseline-no-easyauth-echo.txt)）。

### 言えること / 言えないこと

- 言えること: この実測では、活動（バイト到達）が続く限り総時間 602 秒でも切断されず、
  アイドルが約 237.5〜240.3 秒に達した 2 回はいずれもそこで切断された。
  **ingress 既定 240 秒 timeout は、この条件ではアイドル（バイト間）timeout として振る舞い、
  総リクエスト時間の上限としては振る舞わなかった**。ADR-0028「影響」が未解決とした
  公式文書内の記述の食い違いは、実測ではアイドル時間側の挙動だった
- 言えないこと: 総時間の上限が「存在しない」とは結論しない（観測した最長は 602.30 秒。
  `x-envoy-expected-rq-timeout-ms: 1800000` の 30 分が総時間の上限として働くかは未実測）。
  また ingress timeout 設定を変更した場合や、本番構成（Easy Auth 経由の SSE 等）での値は未実測

## 6. ADR-0027 / ADR-0028 との突き合わせ

| ADR の記述 | 実測結果 | 食い違い |
| --- | --- | --- |
| ADR-0027 決定 10: sidecar による偽装 header の上書き・除去は「未検証の前提」 | 無認証で除去・認証済みで実 principal に置換を観測（§3） | なし（前提と一致。「未検証」の位置づけを実測で確定） |
| ADR-0027「付随する決定」: rotation 混在窓の実時間幅は実測値でのみ主張する | この条件で 20.31〜35.02 秒（4 回）（§4） | なし（従来値が無かったため食い違いも無し） |
| ADR-0028「影響」: 240 秒 timeout が総時間かアイドルかは「公式文書内で記述が食い違っており未解決」 | アイドル（バイト間）timeout として振る舞うことを実測で判別（§5） | なし（未解決事項の確定。長時間ストリームの扱いを改訂する「総リクエスト時間だった場合」の分岐には入らない） |

ADR 本文への追記（ADR-0027 の「結果次第で追記」条項の消化）は本 PR では行わず、本記録を入力に別途行う。

## 7. teardown の記録

一時リソースはすべて削除済み。削除の実施と確認は次の 2 段階で行われた:

1. 担当エージェントの実行ログに残っている削除操作:
   - 権限確認用 probe app `felis-ephem-verify-183-probe-DELETEME`（appId `549c5866-...`）の削除
   - Easy Auth 用 Entra app `felis-ephem-verify-183-easyauth`（appId `12c7e2ab-...`）と
     service principal の削除（`az ad app delete` 成功まで記録あり）。
     **RG / ACR の削除操作はこのログには残っていない**（直後にセッション上限で停止）
2. coordinator による削除確認（削除確認は coordinator が実施）: RG `rg-felis-ephem-verify-183`、
   Container App `ca-felis-ephem-verify-183`、ACR `acrfelisephem18309a1`、
   Entra app `felis-ephem-verify-183-probe-DELETEME` の**いずれも存在しないことを確認済み**

既存の `rg-felisaichatbot-dev-tf`（CAE・既存アプリ）には削除・変更を加えていない。

## 8. ログから復元できなかった情報

- テスト 1（1a / 1b）と teardown の**実施時刻**（ログに wall-clock が残っておらず、順序のみ確定。
  §2 の時刻アンカー以降・同日中であることまでは確定できる）
- イメージ digest に紐づく**タグ値の直接表示**（ACR manifest 一覧の出力がログ上で途切れている。
  §2 の注記のとおり間接的には確定できる）
- Easy Auth 有効化後の revision restart から テスト 1a までの**待機時間・再試行の有無の詳細**
- 一時 RG / ACR の**削除コマンドの実行記録**（§7 のとおり削除確認は coordinator の別途実施で担保）
- テスト 1b の `x-ms-client-principal` の **16 claims 全列挙**（ログにはデコード済み 4 claims と
  claim 総数 16 のみが残っている）
