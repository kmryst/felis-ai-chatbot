# 利用データソース一覧（気象庁ホームページ）

本サービスが取り込み・加工して利用している気象庁ホームページのページ一覧です（出典表示の正本。ADR-0007 / ADR-0008）。

- 再利用根拠: すべて**公共データ利用規約（第1.0版）**（<https://www.digital.go.jp/resources/open_data/public_data_license_v1.0>）。気象庁ホームページのコンテンツは権利表記の記載がない限り同規約に準拠して利用でき（複製・公衆送信・翻訳・変形等の翻案等が可能。商用利用可。CC BY 4.0 互換）、出典の記載方法は気象庁「[気象庁ホームページについて](https://www.jma.go.jp/jma/kishou/info/coment.html)」の記載例に従う
- 加工内容: 本サービスはページ本文の記述を**逐語のままチャンク分割**して格納している（翻訳・要約は行わない）。このチャンク分割が規約上の「編集・加工」に当たるため、次の加工表記を行う

> 出典：気象庁ホームページ（下表の各ページ）
> 本サービスは気象庁ホームページの情報を felis-ai-chatbot が加工して作成したものであり、気象庁が作成・提供するものではありません。

## 解説ページ

| ページタイトル | URL | 取得日 |
| --- | --- | --- |
| 台風とは | <https://www.jma.go.jp/jma/kishou/know/typhoon/1-1.html> | 2026-08-18 |
| 台風の大きさと強さ | <https://www.jma.go.jp/jma/kishou/know/typhoon/1-3.html> | 2026-08-18 |
| 雨の強さと降り方 | <https://www.jma.go.jp/jma/kishou/know/yougo_hp/amehyo.html> | 2026-08-18 |
| 竜巻などの激しい突風とは | <https://www.jma.go.jp/jma/kishou/know/toppuu/tornado1-1.html> | 2026-08-18 |
| 津波から身を守るために | <https://www.jma.go.jp/jma/kishou/know/jishin/tsunami_bosai/index.html> | 2026-08-18 |
| 津波発生と伝播のしくみ | <https://www.jma.go.jp/jma/kishou/know/jishin/tsunami/generation.html> | 2026-08-18 |
| 大雪に関する情報について | <https://www.jma.go.jp/jma/kishou/know/snow/snow.html> | 2026-08-18 |
| 気象庁震度階級関連解説表 | <https://www.jma.go.jp/jma/kishou/know/shindo/kaisetsu.html> | 2026-08-18 |
| 活火山とは | <https://www.jma.go.jp/jma/kishou/know/kazan/katsukazan_toha/katsukazan_toha.html> | 2026-08-18 |
| 風について（よくお寄せいただくご質問） | <https://www.jma.go.jp/jma/kishou/know/faq/faq2.html> | 2026-08-18 |

## 数値・統計ページ

| ページタイトル | URL | 取得日 |
| --- | --- | --- |
| 歴代全国ランキング | <https://www.data.jma.go.jp/stats/etrn/view/rankall.php> | 2026-08-18 |
| 中心気圧が低い台風 | <https://www.data.jma.go.jp/typhoon/statistics/ranking/air_pressure.html> | 2026-08-18 |
| 台風の上陸数 | <https://www.data.jma.go.jp/typhoon/statistics/landing/landing.html> | 2026-08-18 |

歴代全国ランキングは旧 URL（`/obd/stats/etrn/view/rankall.php`）から上記へリダイレクトされる。

## 取り込み方針

- **予報データは一切取り込まない。** 過去の記録と解説のみを対象とする（気象業務法第17条第1項・第23条対応。ADR-0008）
- ページに書かれていない属性は投入しない（記憶による補完をしない）。各数値の根拠原文は DB の `object_properties.note` / `sources.reuse_basis` に保持する（ADR-0003）
- 「風の強さと吹き方」の詳細表は PDF 提供のため取り込み対象外

## 利用制約の確認記録

| ページ | URL | 取得日 |
| --- | --- | --- |
| 気象庁ホームページについて（利用規約） | <https://www.jma.go.jp/jma/kishou/info/coment.html> | 2026-08-18 |
| 気象業務法「第十七条」（予報業務の許可） | <https://www.jma.go.jp/jma/kishou/info/ml-17.html> | 2026-08-18 |
| 気象業務法「第二十三条」（警報の制限） | <https://www.jma.go.jp/jma/kishou/info/ml-23.html> | 2026-08-18 |
| 公共データ利用規約（第1.0版） | <https://www.digital.go.jp/resources/open_data/public_data_license_v1.0> | 2026-08-18 |
