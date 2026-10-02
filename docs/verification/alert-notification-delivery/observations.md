# Azure Monitor の Action Group からアラートのメールが届かない件（Issue #296）実施記録

- 対象 Issue: #296。発端の記録は [key-vault-secret-references/observations.md](../key-vault-secret-references/observations.md) の「アラート発火試験」節
- メールアドレスは sha256 の先頭 12 桁で書く。`02406007e366` = 本番の email receiver の宛先、`16458216cf25` = Azure にサインインしているアカウントのアドレス（どちらも gmail.com）
- subscription ID・テナント ID・アカウント名は伏せる。時刻は UTC（必要に応じて JST を併記）

## 結論

- 原因は本番の Action Group `ag-felisaichatbot-dev-email` の email receiver `opsmail`。同じアドレス宛てでも、新しく作った Action Group からはメトリクスアラート・log search alert のどちらのメールも届き、同じ時刻に旧 Action Group 宛てに発火させた分だけが届かなかった
- アラートの種類（メトリクスアラート / log search alert）、Microsoft Entra のプロフィールの Email は原因ではなかった
- Action Group を `ag-felisaichatbot-dev-email-02`（email receiver `opsmail-02` + Azure app push receiver `push`）として Terraform で作り直し、apply 後に発火させたアラートのメールと push 通知が届くことを確認した
- `opsmail` で何が起きていたか（Azure 内部の状態）は、公開 API からは見えないため分からない。分かっているのは経緯だけ: 2026-09-19 に OTP（one-time passcode）未確認のアドレスで作成 → 確認されないまま失効 → 2026-10-01 に同じ receiver 名のままアドレスを付け替え、OTP を確認。Azure portal の表示は「確認済み」だった

## 調査前に分かっていたこと（2026-10-01〜02）

| 項目 | 結果 |
| --- | --- |
| アラートの発火 | `alert-kv-secret-sync-failed`（log search alert）が 2026-10-01 に 2 回 `Fired`、2 回 `Resolved` |
| Action Group の実行 | alert の history に `ActionsTriggered`（"Action group ag-felisaichatbot-dev-email executed (Configured on alert rule)" = Action Group を実行した）が 4 件。`actionStatus.isSuppressed: false` |
| receiver | `opsmail` は `status: Enabled`、`useCommonAlertSchema: true`。portal の「メール アドレスの確認」は「確認済み」 |
| 受信 | OTP 確認メールと "You've been added to an Azure Monitor action group" は届いた。アラートの Fired / Resolved メールは 0 通 |
| テスト通知 | Action Group の「テスト」（API `actionGroups/createNotifications`）は、Free Trial のサブスクリプションでは `Conflict`（"Free subscription not supported" = 無料のサブスクリプションには対応していない）を返して使えない |
| 配送結果の確認手段 | 通常の通知の配送結果（受理 / 拒否 / 遅延）を見る公開 API は無い。Action Group の実行までは alert の history で確認できるが、その先は受信側でしか確認できない |

## 事前確認（読み取りのみ、2026-10-02）

| 確認 | 結果 |
| --- | --- |
| 2026-09-19 のメトリクスアラート `alert-pgsql-cpu-credits-remaining-low` の history | `AlertCreated` 07:05:55 → `ActionsTriggered` 07:05:56 → `Resolved` 07:40:42 → `ActionsTriggered` 07:40:42。メトリクスアラートでも Action Group の実行までは記録がある（当時の receiver は OTP 未確認だったので、未着の判定材料にはならない） |
| Service Health（2026-09-15 以降） | Action Group / 通知に関する告知は無い |
| 実行ユーザーのロール | subscription スコープで `Owner`（2026-09-18 から） |
| Microsoft Entra のプロフィールの Email（Microsoft Graph の `mail`） | 空（`otherMails` も空）。比較試験の前にユーザーが `02406007e366` を設定した |

## 比較試験（2026-10-02）

試験用の Action Group と、必ず発火するメトリクスアラート（PostgreSQL の `is_db_alive` の `Minimum` が `>= 1`、window 5 分 / 評価 1 分、Sev4）を az CLI で一時的に作った。
log search alert は、必ず 1 行返すクエリ（`ContainerAppSystemLogs_CL | where TimeGenerated > ago(1h) | summarize Count = count()`、行数 `> 0`、評価 5 分 / window 1 時間、Sev4）で作った。
試験用リソースは Terraform の管理に入れず、試験後にすべて削除した。

試験用の Action Group:

| Action Group | receiver |
| --- | --- |
| `ag-felisaichatbot-dev-delivery-test`（short name `felistest`） | Email `email-same`（`02406007e366`）/ Email Azure Resource Manager role `armrole-owner`（Owner）/ Azure app push notifications `push`（`16458216cf25`） |
| `ag-felisaichatbot-dev-delivery-test-arm`（short name `felisarm`） | Email Azure Resource Manager role（Owner）のみ |

`ag-felisaichatbot-dev-delivery-test` の作成時、`02406007e366` に OTP の確認要求は来ず、"You're now in the felistest action group" が届いた。
Microsoft Learn [Create and manage action groups in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups) の Email 行
"This verification persists across all past and future action groups within the same tenant."（確認は同じテナント内の過去・将来のすべての Action Group に引き継がれる）のとおり。

### 発火と受信

| alert ルール | 種類 | 宛先の Action Group | 発火 | `02406007e366` | `16458216cf25` | push |
| --- | --- | --- | --- | --- | --- | --- |
| `alert-delivery-test` | メトリクス | 試験用 | 05:05:34 | 届いた（`email-same`） | 届いた（ARM role） | 届いた |
| `alert-delivery-test-prod-ag` | メトリクス | **本番** + `-arm` | 05:15:49 | **届かない（本番 `opsmail` の分）** | 届いた（`-arm` の ARM role） | 対象外 |
| `alert-delivery-test-log` | log search alert | **本番** + 試験用 | 05:18:54 | 1 通だけ届いた。本文末尾は felistest（試験用の分）。**本番 `opsmail` の分は届かない** | 届いた（ARM role） | 届いた |
| `alert-delivery-test-2` | メトリクス | 試験用 | 05:32:53 | 届いた（`email-same`） | 届いた（ARM role） | 届いた |

どのルールも、発火の約 1 秒後に、宛先のすべての Action Group について `ActionsTriggered` が記録された。発火は作成から 2〜5 分。

メールの件名には Action Group 名が入らない（例: "Fired:Sev4 Azure Monitor Alert alert-delivery-test-log on log-felisaichatbot-dev ( microsoft.operationalinsights/workspaces ) at 10/2/2026 5:18:54 AM"）。
どの Action Group から送られたかは、本文末尾の "You're receiving this notification as a member of the felistest action group."（felistest action group のメンバーとしてこの通知を受け取っている）で見分けられる（入るのは short name）。

### 判定

| 仮説 | 結果 |
| --- | --- |
| アラートの種類（log search alert のメールだけ落ちる） | 否定。試験用 Action Group からは log search alert のメールも届いた |
| 本番の receiver `opsmail` の経緯 | 支持。同じアドレス・同じ時刻・同じアラートで、旧 Action Group の分だけ届かなかった |
| OTP 確認の反映の遅れ | 否定。OTP 確認から約 23 時間後の 05:15 / 05:18 でも本番の分は届かなかった |
| 一過性の配送障害 | 否定。同じ時刻の試験用の分は届いた |

### Microsoft Entra のプロフィールの Email

`alert-delivery-test-2` は、ユーザーがプロフィールの Email を `02406007e366` から `16458216cf25` に書き換えた約 4 分後に発火させた（空にする操作は portal で「ユーザーを更新できませんでした」となり、できなかった）。
通常の Email receiver（`02406007e366`）には届いたので、プロフィールの Email は通常の Email receiver の配送には効いていない。
ただし変更の直後なので、変更前の値が使われた可能性は残る。

### Email Azure Resource Manager role の宛先

Owner 宛てのメールは、4 回とも `16458216cf25`（サインインしているアカウントのアドレス）に届いた。プロフィールの Email が `02406007e366` だったときも同じだった。
Microsoft Learn の同じページは "Enter the primary email address configured for the Microsoft Entra user."（Microsoft Entra ユーザーに設定された primary email address を入力する）、
"Make sure an email address is configured for the user in their Microsoft Entra profile."（Microsoft Entra のプロフィールにメールアドレスが設定されていることを確認する）、
"It can take up to 24 hours for a customer to start receiving notifications after they add a new Azure Resource Manager role to their subscription."（新しい ARM role を追加してから通知が届き始めるまで最大 24 時間かかることがある）としているが、
"primary email" が Microsoft Entra のどの属性を指すか、外部アカウント（UPN が `#EXT#` 形式）でどう決まるか、プロフィールの変更がいつ反映されるかは書かれていない。
プロフィールの Email が空のときの宛先は測っていない。宛先の決まり方を確かめきれていないため、本番には ARM role receiver を入れない。

## 修正（Terraform、persistent 層）

| 項目 | 変更前 | 変更後 |
| --- | --- | --- |
| Action Group | `ag-felisaichatbot-dev-email` | `ag-felisaichatbot-dev-email-02`（short name は `felisdev` のまま） |
| email receiver | `opsmail` | `opsmail-02`（宛先は同じ `02406007e366`） |
| push receiver | なし | `push`（`16458216cf25`。変数 `alert_push_account_email`） |
| lifecycle | なし | `create_before_destroy = true`（新しい Action Group を作ってからアラート 6 件の参照を付け替え、旧を消す） |

receiver の名前だけを変える in-place 更新ではなく、Action Group ごと作り直した。比較試験で届いたのは「新しい Action Group + 新しい receiver」の構成で、
「同じ Action Group + 新しい receiver」で届くかは確かめていないため。アラートルールは置き換わらない（ID 不変）。

| 時刻 | 操作 / 確認 | 結果 |
| --- | --- | --- |
| （apply 前） | `terraform plan -out=tfplan-296`（ユーザー） | `1 to add, 6 to change, 1 to destroy`（Action Group の置き換えとアラート 6 件の参照更新。`tags = {} -> null` を含む） |
| 05:47:13 → 05:49:57 | `terraform apply tfplan-296`（ユーザー） | `Apply complete! Resources: 1 added, 6 changed, 1 destroyed.`。新しい Action Group の作成 5 秒、旧の削除 9 秒 |
| 05:47（14:47 JST） | `02406007e366` の受信箱 | "You're now in the felisdev action group"（Action group name: `ag-felisaichatbot-dev-email-02`）。OTP の要求なし |
| 05:50 | 読み取り確認 | Action Group は `-02` のみ。メトリクスアラート 5 件と `alert-kv-secret-sync-failed` の宛先はすべて `-02` |
| 05:52:50 | 確認用メトリクスアラート `alert-delivery-test-prod-02`（宛先は `-02` のみ、Sev4）が発火 | `02406007e366` に Fired メール（14:52 JST）、iPhone に push。**修正を確認** |
| 05:54:57 | 確認用アラートを削除 | 残りはメトリクスアラート 5 件・`alert-kv-secret-sync-failed`・`ag-felisaichatbot-dev-email-02` のみ |

## 後片付け

| 時刻 | 削除したもの |
| --- | --- |
| 05:43:07 → 05:43:22 | `alert-delivery-test` / `alert-delivery-test-2` / `alert-delivery-test-prod-ag`（メトリクス）、`alert-delivery-test-log`（log search alert）、`ag-felisaichatbot-dev-delivery-test` / `ag-felisaichatbot-dev-delivery-test-arm`（ルールを先、Action Group を後） |
| 05:54:57 | `alert-delivery-test-prod-02` |

削除後の一覧で、試験用のリソースが残っていないことを確認した。

## 分かったこと

- Action Group の email receiver は、portal で「確認済み」と表示され、alert の history に `ActionsTriggered` が記録されていても、メールが届かないことがある。どちらも到達の保証にならない。
  receiver を変えたら、必ずその後に発火したアラートで受信を確かめる（設定変更は以後のアラートにだけ効く。Microsoft Learn [alerts-overview](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview):
  "Configuration changes apply only to future alerts."（設定変更は以後のアラートにだけ適用される））
- テスト通知が使えないサブスクリプションでは、必ず発火する一時的なメトリクスアラート（稼働中は常に真の条件、Sev4）が到達確認の代わりになる。作成から 2〜3 分で発火し、費用は時系列 1 本分
- 同じ alert から複数の Action Group 経由で同じアドレスに届くメールは、件名では区別できない。本文末尾の Action Group の short name で区別する
- メール以外の経路（Azure mobile app の push）を持っておくと、メールだけが落ちたときに気づける
