<!-- 書き方ガイド: Doc-onlyは可観測性=No-op、リスク/コストは'なし'を選択 -->

## 目的（推奨）
<!-- なぜこの変更が必要か（1-2行）。軽微変更なら簡潔でOK -->

## 変更内容（推奨）
<!-- 具体的に何を変更したか（1行要点） -->

## 影響範囲（推奨）
<!-- 対象/非対象の一言 -->
- **対象**:
- **非対象**:

## Error budget policy（必須）

次のいずれか 1 つを選ぶ。

- [ ] change freeze は発動していない
- [ ] change freeze は発動中だが、この変更は `docs/operations/slo/error-budget-policy.md` が定める対象変更に該当しない
- [ ] change freeze は発動中で、この変更は対象だが、policy の例外を適用する
- [ ] change freeze は発動中で、この変更は対象かつ例外なし。解除条件を満たすまで merge しない
- **change freeze の Issue**: なし / #...
- **対象外の根拠、例外区分と必要性、または merge を待機する根拠**:
- **Validation / rollback または containment / follow-up Issue**:

## PRラベル（必須）

- **type**: ちょうど1つ必須
- **area**: 1つ以上必須、複数可
- **risk**: ちょうど1つ必須
- **cost**: ちょうど1つ必須
- **例**: `type:docs`, `area:docs`, `risk:low`, `cost:none`

<details>
<summary>影響メモ（必要時のみ）</summary>

**コスト根拠**（小/中/大の場合）:
**リスク根拠**（Medium/Highの場合）:

</details>

## 可観測性/検証 *条件付き*
<!-- Doc-onlyなら"No-op（適用外）"、それ以外は確認手順・合格条件 -->

## ロールバック *条件付き*
<!-- 厳密運用PRでは必須。軽運用PRでは必要時のみ -->

<details>
<summary>テスト結果/検証手順</summary>

</details>

## メモ（レビューポイント）
<!-- レビュアーに見てほしい箇所 -->

<!-- Issue リンク（Closes #<issue番号>）は helper が --issue から自動追記するため、ここには書かない -->
