# 応答の接地確認（seed データとの突き合わせ）の実測記録（Issue #206）

- 実施日: 2026-09-02（UTC）
- 対象: deployed 環境（`LLM_PROVIDER=azure-openai`・seed 投入と実 embedding backfill 済み =
  [seed-embedding-backfill](../seed-embedding-backfill/observations.md)）
- 根拠 ADR: [ADR-0010](../../adr/0010-rag-wiring-and-hallucination-guard.md)（検索 0 件または
  最上位類似度が閾値未満なら LLM を呼ばず固定文言を返す。ヒット時は `object_properties` 全件を
  コンテキストに併載）

## 1. 発端（ブラウザでの応答）

ユーザーがブラウザ（Easy Auth 認証済み）で質問した応答（逐語）:

- 「東京の過去最高気温ベスト5」→
  > 参照資料には、東京の過去最高気温のベスト5の具体的な記録は記載されていません。ただし、
  > 全国の最高気温の記録としては群馬県伊勢崎市で41.8℃が観測されたことが記載されています。（略）
- 「じゃあ全国の過去最高気温ベスト5教えて」→
  > 最高気温の歴代全国ランキング1位としては以下の記録があります。- 群馬県伊勢崎市で記録された
  > 41.8℃（2025年8月5日）その他の詳細なベスト5の記録は参照資料に記載がないためお答えできません。

検証すべき点: 「群馬県伊勢崎市 41.8℃」「2025年8月5日」が seed データ
（`backend/app/ingest/jma_seed.py`）に実在する値か（実在しなければガードをすり抜けた
ハルシネーション）。

## 2. seed データの grep（結果: 実在する）

```console
$ grep -n -E '伊勢崎|41\.8|2025年8月5日' backend/app/ingest/jma_seed.py
718:        "value_numeric": 41.8,
722:            '最高気温の高い方からの歴代全国ランキング1位: "群馬県" "伊勢崎" '
723:            '"41.8" ℃ "2025年8月5日"'
```

該当エントリ（`object_properties`。`object="気温"` / `property_name="record_highest_temperature"`
/ `source="rankall"`）:

```python
    {
        "object": "気温",
        "property_name": "record_highest_temperature",
        "value_numeric": 41.8,
        "unit": "celsius",
        "source": "rankall",
        "note": (
            '最高気温の高い方からの歴代全国ランキング1位: "群馬県" "伊勢崎" '
            '"41.8" ℃ "2025年8月5日"'
        ),
    },
```

判定: **接地している**。地点・数値・日付の 3 点とも seed の値と一致し、ADR-0010 の
「ヒット時は `object_properties` 全件を併載する」経路で LLM に渡った値をそのまま答えている。
ハルシネーションガードの穴ではない（Issue の起票なし）。

補足の観察（ガードの問題ではないが事実として記録）:

- seed の地点名は気象庁の観測地点名「伊勢崎」であり、応答の「伊勢崎市」の「市」は LLM の補い。
  事実としては整合するが逐語ではない
- seed に「東京」の最高気温の記録は無い（`東京` の 3 件は大雪・暴風警報の文脈のみ）。
  「歴代全国ランキング」は各要素の **1 位のみ**（8 件）を保持し、2 位以下や「ベスト5」の系列は
  無い。したがって「東京のベスト5 / 全国のベスト5 は参照資料に記載がない」という応答は
  資料の範囲を正しく反映している

## 3. 再現（backend 新 revision `--0000007`、image `backend:sha-b6d90f7`）

backend コンテナ内から `POST http://localhost:8000/chat`（`message` =
「全国の過去最高気温を教えて」）→ **200**、SSE `message` × 55 → `done`。連結した本文（逐語）:

> 全国の過去最高気温の記録は、群馬県伊勢崎市で2025年8月5日に観測された41.8℃です。これが歴代の
> 全国で最も高い気温の記録となっています。

§2 の seed エントリと一致（image 同期後の backend でも接地した応答が返る）。
