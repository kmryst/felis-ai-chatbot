# PITR ドリルの復旧目標（RPO / RTO）— 実測前の宣言

PITR ドリル（手順の正本: [day3-5-execution-plan.md](./day3-5-execution-plan.md) §4-3 /
[credit-window-execution-plan.md](./credit-window-execution-plan.md) §7）で計測する値を
評価するための**目標値の宣言**。本書は目標だけを持ち、実測値は一切書かない。
実測は従来どおり `docs/verification/restore-drill/` に記録する。

## 1. なぜ実測より前に、単独のコミットで宣言するか

RPO / RTO は**目標値であって測定値ではない**。実測の前に目標が宣言されていなければ、
測った値はただの数字であり、「速かった」のか「遅かった」のかを言えない。

したがって本書は、**ドリルを実施する前に、単独のコミットとして `main` に入っている**
必要がある。実測と同じコミットに混ぜると、「実測の前に宣言した」ことを git の履歴で
示せなくなる。本書のコミットがドリル記録のコミットより前にあること自体が、
この宣言の証跡である（Issue #153）。

## 2. 宣言する目標

| 目標 | 値 | 位置づけ |
| --- | --- | --- |
| RPO 目標 | **5 分** | aspirational target（未検証の暫定目標）。**保証値ではない** |
| RTO 目標 | **3 時間** | aspirational target（未検証の暫定目標）。**保証値ではない** |

- **aspirational target** は Azure Well-Architected Framework の用語（§3-5）。
  復旧の実測でまだ裏づけられていない、関係者と議論するための暫定目標を指す
- **RPO 目標 5 分は保証ではない**。出典の原文（§3-1）が "In general" / "can be up to"
  という書き方であり、SLA でもない。この 5 分は、**超過した場合に調査対象とするための
  線**として置く（超過 = 即失敗ではなく、なぜ超過したかを記録・調査する閾値）
- RTO 目標 3 時間の導出は §4 に書く。**3 時間という数字自体に出典はない**（§4-2）

## 3. 出典（Azure が言っていること）

本節は Microsoft の文書の逐語引用と日本語訳のみを置く。**このプロジェクトの解釈は
一切含めない**（解釈は §4 に分離する）。引用はすべて 2026-08-27 に URL を実際に開き、
逐語が存在することを確認した。

### 3-1. RPO 5 分の根拠

> Transaction log backups happen at varied frequencies, depending on the workload and
> when the WAL file is filled and ready to be archived. In general, the delay RPO
> (recovery point objective) can be up to five minutes.

（訳）

> トランザクションログのバックアップは、ワークロードと、WAL ファイルが満杯になり
> アーカイブ可能になるタイミングに応じて、さまざまな頻度で行われる。一般に、
> この遅延による RPO（recovery point objective）は最大 5 分程度になり得る。

- 出典: Azure Database for PostgreSQL Flexible Server, "Backup and Restore in Azure
  Database for PostgreSQL Flexible Server" の *Backup frequency* 節
  <https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore>
  （2026-08-27 確認。canonical URL は
  `learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore`）
- 注記: [day3-5-execution-plan.md](./day3-5-execution-plan.md) §2-1 No.2 は同じ文を
  "the delay RPO can be up to five minutes" と引用している（2026-08-19 確認時点の表記）。
  2026-08-27 時点のページでは "(recovery point objective)" の挿入句が入っており、
  本書は現時点の逐語をそのまま引く

### 3-2. 復旧レンジの公称値（RTO の前提）

> The time required to recover by using the latest and custom restore point options
> varies based on factors such as the volume of transaction logs to process since the
> last backup and the total number of databases being recovered simultaneously in the
> same region. The overall recovery time usually takes from few minutes up to a few hours.

（訳）

> 最新復元ポイントおよびカスタム復元ポイントを使う復旧に要する時間は、直近バックアップ
> 以降に処理すべきトランザクションログの量や、同一リージョンで同時に復旧中のデータベース
> 数などの要因によって変動する。全体の復旧時間は、通常、数分から数時間程度である。

- 出典: 同上（*Point-in-time recovery* 節）。<https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore>（2026-08-27 確認）

### 3-3. RTO を締めない判断の根拠（その 1）

> While it's tempting to aim for an RTO and RPO of zero (no downtime and no data loss
> in the event of a disaster), in practice it's difficult and costly to implement.
> It's important for technical and business stakeholders to discuss these requirements
> together and decide on realistic requirements.

（訳）

> 災害時のダウンタイムもデータ損失もゼロ、つまり RTO と RPO をゼロにしたくなるものだが、
> 実際にはその実装は困難で費用もかかる。技術側と事業側の関係者がこれらの要件を一緒に
> 議論し、現実的な要件を決めることが重要である。

- 出典: Azure Reliability, "What are Business Continuity, High Availability, and
  Disaster Recovery?" の *Disaster recovery requirements* セクションの Note ボックス
  <https://learn.microsoft.com/en-us/azure/reliability/concept-business-continuity-high-availability-disaster-recovery>（2026-08-27 確認）

### 3-4. RTO を締めない判断の根拠（その 2）

> These criticality tiers influence the appropriate recovery objectives.
> Higher-criticality components demand faster recovery and more frequent data
> protection, while lower-criticality components can tolerate slower restoration.

（訳）

> これらの重要度ティアは、適切な復旧目標に影響する。重要度の高いコンポーネントほど
> 迅速な復旧と高頻度のデータ保護を要求し、重要度の低いコンポーネントはより遅い復旧を
> 許容できる。

- 出典: Azure Well-Architected Framework, "Architecture strategies for disaster
  recovery" の *Prioritize by business impact* セクション
  <https://learn.microsoft.com/en-us/azure/well-architected/reliability/disaster-recovery>（2026-08-27 確認）

### 3-5. 過剰な DR 実装の戒めと、aspirational target という用語

> If a workload uses a disaster recovery solution that excessively satisfies the
> workload's recovery point and time objectives, the excess leads to higher costs
> because of waste.

（訳）

> ワークロードの復旧ポイント目標・復旧時間目標を過剰に満たす災害復旧ソリューションを
> 使うと、その過剰分は無駄となり、コスト増につながる。

- 出典: Azure Well-Architected Framework, "Reliability tradeoffs" の
  *Tradeoff: Increased implementation redundancy or waste*
  <https://learn.microsoft.com/en-us/azure/well-architected/reliability/tradeoffs>（2026-08-27 確認）

> Before you finish this work, discuss aspirational targets with stakeholders, and
> ensure that your architecture design supports the recovery targets to the best of
> your understanding. Clearly communicate to stakeholders that any flows or entire
> workloads that aren't thoroughly tested for recovery metrics shouldn't have
> guaranteed SLAs. Make sure that stakeholders understand that recovery targets can
> change over time as workloads are updated.

（訳）

> この作業を終える前に、aspirational target（到達を目指す暫定目標）を関係者と議論し、
> アーキテクチャ設計が現時点の理解の範囲でその復旧目標を支えられることを確認すること。
> 復旧メトリクスについて十分にテストされていないフローやワークロードには、保証つきの
> SLA を設けるべきでないことを関係者へ明確に伝えること。復旧目標はワークロードの更新に
> つれて時間とともに変わり得ることを、関係者に理解してもらうこと。

- 出典: Azure Well-Architected Framework, "Architecture strategies for defining
  reliability targets" の *Define recovery metrics* セクション
  <https://learn.microsoft.com/en-us/azure/well-architected/reliability/metrics>（2026-08-27 確認）

## 4. このプロジェクトの解釈（§3 とは独立の推論）

**本節はすべてこのプロジェクトの推論であり、Microsoft の文書には書かれていない。**
Microsoft は「事業要件がない環境では RTO を緩めてよい」とは一言も書いていない。
§3 の出典が言っているのはあくまで「重要度ティアに応じて復旧目標を決める」「ゼロを
目指さず現実的に決める」「過剰な DR はコスト増」までである。

### 4-1. この環境を最下層の criticality tier と解釈する

この環境には business stakeholder が存在せず、ユーザートラフィックもない（§5）。
criticality tier としては最下層に相当すると**このプロジェクトが**判断し、§3-4 の
"lower-criticality components can tolerate slower restoration" の適用対象と解釈する。

### 4-2. "a few hours" を 3 時間と読む

RTO 目標 3 時間は、§3-2 の公称レンジ "from few minutes up to a few hours" の上限側
"a few hours" を 3 時間と**このプロジェクトが**読んだ値である。
**この 3 という数字自体に出典はない**（Microsoft は具体値を公表していない）。

### 4-3. 上限側を採る理由

- レンジの上限側を目標に置くことは、§3-3 の言う realistic な要件設定である
  （下限側の「数分」を目標にすると、公称レンジ内の正常な復旧が軒並み目標超過になる）
- 目標を締めても、それを満たすための投資（HA 常設・レプリカ等）はこの環境の重要度に
  見合わない。§3-5 の言う過剰な DR 実装によるコスト増を避ける選択である

### 4-4. RPO 5 分を「調査の線」として使う

§3-1 の "In general ... can be up to five minutes" は一般論であって保証ではない。
そこで 5 分を「達成を約束する値」ではなく、**ドリルの観測がこれを超えた場合に
原因（WAL アーカイブ遅延・heartbeat の標本化誤差 1 分を含む）を調査・記録する線**
として使う。

## 5. この環境の前提（制約の明記）

- ユーザートラフィックが存在しない。SLA を約束する相手もいない
- したがって RTO / RPO の本来の導出 — 事業影響から最大許容停止時間（MTD）を見積もり、
  その内側に RTO を置く — は**この環境では使えない**。本書の目標値は事業要件からの
  導出ではなく、§3 のベンダー公称値と §4 の解釈から置いた値である。
  この制約を隠さず明記することが、本書の数字の誠実さの前提である

## 6. 改定の手順

1. ドリルで実測した値は「**観測復元点ラグ**」（障害時点と復元後に残った最後の
   heartbeat の差）・「**実測復元所要区間**」（restore 発行から接続回復までの区間）と
   呼び、**RPO / RTO とは呼ばない**（目標と実測能力を混同しないための呼び分け。
   実測の定義と式は [day3-5-execution-plan.md](./day3-5-execution-plan.md) §4-3 の 5〜7）
2. ドリル完了後、実測値 + 運用マージンをもとに本書の目標値を改定する
   （§3-5 の "recovery targets can change over time" の運用）。改定も通常の
   Issue / PR フローで行い、改定前の値は git の履歴に残る
3. 事業要件（ユーザー・SLA を約束する相手）が後に発生した場合は、本書の目標値全体を
   再交渉の対象とする（§3-3 の stakeholder 間の議論に相当）

## 関連

- [day3-5-execution-plan.md](./day3-5-execution-plan.md) §4-3 — PITR ドリル手順の正本（RTO / RPO 実測の定義を含む）
- [credit-window-execution-plan.md](./credit-window-execution-plan.md) §7 — ドリル 2 回の日程と変更点、RTO の主張の限定
- [ADR-0021](../adr/0021-heartbeat-table-as-recovery-marker.md) — 実測の物差しとなる `obs.heartbeat`（recovery marker）の位置づけ
- [restore-drill/observations.md](../verification/restore-drill/observations.md) — バックアップ観測記録（実測はここに残る）
- Issue #153 — 本書の起票元
