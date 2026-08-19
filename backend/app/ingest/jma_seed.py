"""気象庁ホームページ出典の初期シードデータ（実取得値のみ。ADR-0003 / ADR-0007 / ADR-0008）。

方針:

- ここにある値・原文はすべて、2026-08-18 に実際に各ページを取得して確認した
  記述である。ページに書かれていない属性は投入しない（記憶による補完をしない）
- 各プロパティの note には、値の根拠となったページ上の原文（該当文）を残す。
  後から「この値はどの記述から来たか」を検証できることを優先する
- 日本語ソースのため翻訳・要約は行わない。DOCUMENTS のチャンクはページの
  記述の逐語転載であり、行うのはチャンク分割のみ（これが公共データ利用規約上の
  「編集・加工」に当たるため、サービス側で加工表記を行う。ADR-0008）。
  表形式の記述は「列名: セル値」の形で逐語に線形化する（セル値は書き換えない）
- 予報データは一切含めない。過去の記録と解説のみ（気象業務法対応。ADR-0008）
- 利用ページの一覧・再利用根拠の正本は docs/data-sources.md
- embedding は NULL のまま（LLM プロバイダ未確定。RAG 本結線は次フェーズ）
"""

# 取得直後（2026-08-18 07:40-07:45 UTC の取得バッチ完了時）に計測した時刻
RETRIEVED_AT = "2026-08-18T07:44:32+00:00"

# 気象庁ホームページ共通の reuse_basis（docs/data-sources.md に詳細を記録）
_JMA_PDL = (
    "公共データ利用規約（第1.0版）準拠（気象庁ホームページ利用規約。"
    "複製・翻案可、商用利用可、CC BY 4.0 互換。出典表示は気象庁の記載例に従う）"
)

SOURCES: dict[str, dict[str, str]] = {
    "typhoon-1-1": {
        "source_url": "https://www.jma.go.jp/jma/kishou/know/typhoon/1-1.html",
        "source_title": "台風とは",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "知識・解説 > 台風について",
    },
    "typhoon-1-3": {
        "source_url": "https://www.jma.go.jp/jma/kishou/know/typhoon/1-3.html",
        "source_title": "台風の大きさと強さ",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "知識・解説 > 台風について",
    },
    "amehyo": {
        "source_url": (
            "https://www.jma.go.jp/jma/kishou/know/yougo_hp/amehyo.html"
        ),
        "source_title": "雨の強さと降り方",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": (
            "天気予報等で用いる用語。"
            "（平成12年8月作成）、（平成14年1月一部改正）、"
            "（平成29年3月一部改正）、（平成29年9月一部改正）"
        ),
    },
    "tornado-1-1": {
        "source_url": (
            "https://www.jma.go.jp/jma/kishou/know/toppuu/tornado1-1.html"
        ),
        "source_title": "竜巻などの激しい突風とは",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "知識・解説 > 竜巻・ダウンバースト・ガストフロント",
    },
    "tsunami-bosai": {
        "source_url": (
            "https://www.jma.go.jp/jma/kishou/know/jishin/"
            "tsunami_bosai/index.html"
        ),
        "source_title": "津波から身を守るために",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "知識・解説 > 地震・津波",
    },
    "tsunami-generation": {
        "source_url": (
            "https://www.jma.go.jp/jma/kishou/know/jishin/tsunami/"
            "generation.html"
        ),
        "source_title": "津波発生と伝播のしくみ",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "知識・解説 > 地震・津波",
    },
    "snow-info": {
        "source_url": "https://www.jma.go.jp/jma/kishou/know/snow/snow.html",
        "source_title": "大雪に関する情報について",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "知識・解説",
    },
    "shindo-kaisetsu": {
        "source_url": (
            "https://www.jma.go.jp/jma/kishou/know/shindo/kaisetsu.html"
        ),
        "source_title": "気象庁震度階級関連解説表",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "平成21年3月31日改定版。使用にあたっての留意事項がページ冒頭にある",
    },
    "katsukazan-toha": {
        "source_url": (
            "https://www.jma.go.jp/jma/kishou/know/kazan/"
            "katsukazan_toha/katsukazan_toha.html"
        ),
        "source_title": "活火山とは",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "知識・解説 > 火山",
    },
    "faq-wind": {
        "source_url": "https://www.jma.go.jp/jma/kishou/know/faq/faq2.html",
        "source_title": "風について",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "よくお寄せいただくご質問",
    },
    "rankall": {
        "source_url": "https://www.data.jma.go.jp/stats/etrn/view/rankall.php",
        "source_title": "歴代全国ランキング",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": (
            "各地点における観測史上1位の値によるランキング。"
            "旧 URL /obd/stats/etrn/view/rankall.php からリダイレクト。"
            "取得時点の掲載値（記録更新で変わり得る）"
        ),
    },
    "typhoon-air-pressure": {
        "source_url": (
            "https://www.data.jma.go.jp/typhoon/statistics/ranking/"
            "air_pressure.html"
        ),
        "source_title": "中心気圧が低い台風",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "統計期間：1951年～2026年第4号まで（取得時点）",
    },
    "typhoon-landing": {
        "source_url": (
            "https://www.data.jma.go.jp/typhoon/statistics/landing/"
            "landing.html"
        ),
        "source_title": "台風の上陸数",
        "reuse_basis": _JMA_PDL,
        "retrieved_at": RETRIEVED_AT,
        "note": "2025年までの確定値と2026年の速報値（取得時点）",
    },
}

OBJECTS: list[dict[str, str]] = [
    {"name": "台風", "kind": "typhoon", "note": "typhoon"},
    {"name": "大雨", "kind": "heavy_rain", "note": "heavy rain"},
    {"name": "竜巻", "kind": "tornado", "note": "tornado"},
    {"name": "ダウンバースト", "kind": "downburst", "note": "downburst"},
    {"name": "ガストフロント", "kind": "gust_front", "note": "gust front"},
    {"name": "津波", "kind": "tsunami", "note": "tsunami"},
    {"name": "大雪", "kind": "heavy_snow", "note": "heavy snow"},
    {"name": "活火山", "kind": "active_volcano", "note": "active volcano"},
    {"name": "風", "kind": "wind", "note": "wind"},
    {
        "name": "気温",
        "kind": "temperature",
        "note": "temperature（歴代全国ランキングの記録を保持する）",
    },
    {
        "name": "震度5弱",
        "kind": "seismic_intensity",
        "note": "JMA seismic intensity 5-lower",
    },
    {
        "name": "震度5強",
        "kind": "seismic_intensity",
        "note": "JMA seismic intensity 5-upper",
    },
    {
        "name": "震度6弱",
        "kind": "seismic_intensity",
        "note": "JMA seismic intensity 6-lower",
    },
    {
        "name": "震度6強",
        "kind": "seismic_intensity",
        "note": "JMA seismic intensity 6-upper",
    },
    {
        "name": "震度7",
        "kind": "seismic_intensity",
        "note": "JMA seismic intensity 7",
    },
]

# object: OBJECTS の name / source: SOURCES のキー / note: ページ上の原文（該当文）
PROPERTIES: list[dict] = [
    # --- 台風 ---
    {
        "object": "台風",
        "property_name": "definition_max_wind_threshold",
        "value_numeric": 17.0,
        "unit": "m/s",
        "source": "typhoon-1-1",
        "note": (
            '"低気圧域内の最大風速（10分間平均）がおよそ17 m/s'
            '（34ノット、風力8）以上のものを「台風」と呼びます"'
        ),
    },
    {
        "object": "台風",
        "property_name": "lifetime_without_energy_supply",
        "value_text": "2～3日で消滅",
        "unit": None,
        "source": "typhoon-1-1",
        "note": (
            '"仮にエネルギーの供給がなくなれば2～3日で消滅してしまいます"'
        ),
    },
    {
        "object": "台風",
        "property_name": "strong_class_max_wind_range",
        "value_text": "33 m/s（64ノット）以上～44 m/s（85ノット）未満",
        "unit": "m/s",
        "source": "typhoon-1-3",
        "note": (
            '強さの階級分けの表より、階級「強い」の最大風速: '
            '"33 m/s（64ノット）以上～44 m/s（85ノット）未満"'
        ),
    },
    {
        "object": "台風",
        "property_name": "very_strong_class_max_wind_range",
        "value_text": "44 m/s（85ノット）以上～54 m/s（105ノット）未満",
        "unit": "m/s",
        "source": "typhoon-1-3",
        "note": (
            '強さの階級分けの表より、階級「非常に強い」の最大風速: '
            '"44 m/s（85ノット）以上～54 m/s（105ノット）未満"'
        ),
    },
    {
        "object": "台風",
        "property_name": "violent_class_max_wind",
        "value_text": "54 m/s（105ノット）以上",
        "unit": "m/s",
        "source": "typhoon-1-3",
        "note": (
            '強さの階級分けの表より、階級「猛烈な」の最大風速: '
            '"54 m/s（105ノット）以上"'
        ),
    },
    {
        "object": "台風",
        "property_name": "large_class_radius_range",
        "value_text": "500 km以上～800 km未満",
        "unit": "km",
        "source": "typhoon-1-3",
        "note": (
            '大きさの階級分けの表より、階級「大型（大きい）」の'
            '風速 15 m/s以上の半径: "500 km以上～800 km未満"'
        ),
    },
    {
        "object": "台風",
        "property_name": "very_large_class_radius",
        "value_text": "800 km以上",
        "unit": "km",
        "source": "typhoon-1-3",
        "note": (
            '大きさの階級分けの表より、階級「超大型（非常に大きい）」の'
            '風速 15 m/s以上の半径: "800 km以上"'
        ),
    },
    {
        "object": "台風",
        "property_name": "strong_wind_area_threshold",
        "value_numeric": 15.0,
        "unit": "m/s",
        "source": "typhoon-1-3",
        "note": (
            '"「大きさ」は強風域（風速15 m/s以上の風が吹いているか、'
            '吹く可能性がある範囲）の半径で、 「強さ」は最大風速で'
            '区分しています"'
        ),
    },
    {
        "object": "台風",
        "property_name": "storm_area_threshold",
        "value_numeric": 25.0,
        "unit": "m/s",
        "source": "typhoon-1-3",
        "note": (
            '"風速25 m/s以上の風が吹いているか、吹く可能性がある範囲を'
            '暴風域と呼びます"'
        ),
    },
    {
        "object": "台風",
        "property_name": "lowest_central_pressure_at_landing",
        "value_numeric": 925.0,
        "unit": "hPa",
        "source": "typhoon-air-pressure",
        "note": (
            '上陸時（直前）の中心気圧が低い台風の表より、1位: 台風番号 "6118"'
            '（"第二室戸台風"）、上陸時気圧 "925" hPa、'
            '上陸日時 "1961年9月16日09時過ぎ"、上陸場所 "高知県室戸岬の西"'
        ),
    },
    {
        "object": "台風",
        "property_name": "second_lowest_central_pressure_at_landing",
        "value_numeric": 929.0,
        "unit": "hPa",
        "source": "typhoon-air-pressure",
        "note": (
            '上陸時（直前）の中心気圧が低い台風の表より、2位: 台風番号 "5915"'
            '（"伊勢湾台風"）、上陸時気圧 "929" hPa、'
            '上陸日時 "1959年9月26日18時頃"、上陸場所 "和歌山県潮岬の西"'
        ),
    },
    {
        "object": "台風",
        "property_name": "muroto_typhoon_reference_pressure",
        "value_numeric": 911.6,
        "unit": "hPa",
        "source": "typhoon-air-pressure",
        "note": (
            '"参考記録：（※統計開始以前のため） 室戸台風　911.6hPa　'
            '1934年9月21日（室戸岬における観測値）"'
        ),
    },
    {
        "object": "台風",
        "property_name": "makurazaki_typhoon_reference_pressure",
        "value_numeric": 916.1,
        "unit": "hPa",
        "source": "typhoon-air-pressure",
        "note": (
            '"参考記録：（※統計開始以前のため） （…） 枕崎台風　916.1hPa　'
            '1945年9月17日（枕崎における観測値）"'
        ),
    },
    {
        "object": "台風",
        "property_name": "most_landings_in_a_year",
        "value_numeric": 10.0,
        "unit": "count",
        "source": "typhoon-landing",
        "note": (
            '台風の上陸数の表より、年間上陸数の最大は "2004" 年の "10" 個'
            "（1951年～2026年（速報値）の全年を確認した最大値。"
            '次点は 6 個（1990・1993・2016 年））'
        ),
    },
    {
        "object": "台風",
        "property_name": "landing_definition",
        "value_text": "台風の中心が北海道、本州、四国、九州の海岸線に達した場合",
        "unit": None,
        "source": "typhoon-landing",
        "note": (
            '"台風の中心が北海道、本州、四国、九州の海岸線に達した場合を'
            '「日本に上陸した台風」としています。ただし、小さい島や半島を'
            '横切って短時間で再び海に出る場合は「通過」としています。"'
        ),
    },
    # --- 大雨 ---
    {
        "object": "大雨",
        "property_name": "rain_10_20mm_term",
        "value_text": "やや強い雨（ザーザーと降る）",
        "unit": "mm/h",
        "source": "amehyo",
        "note": (
            '1時間雨量 "10以上～20未満" の予報用語は "やや強い雨"、'
            '人の受けるイメージは "ザーザーと降る"'
        ),
    },
    {
        "object": "大雨",
        "property_name": "rain_20_30mm_term",
        "value_text": "強い雨（どしゃ降り）",
        "unit": "mm/h",
        "source": "amehyo",
        "note": (
            '1時間雨量 "20以上～30未満" の予報用語は "強い雨"、'
            '人の受けるイメージは "どしゃ降り"'
        ),
    },
    {
        "object": "大雨",
        "property_name": "rain_30_50mm_term",
        "value_text": "激しい雨（バケツをひっくり返したように降る）",
        "unit": "mm/h",
        "source": "amehyo",
        "note": (
            '1時間雨量 "30以上～50未満" の予報用語は "激しい雨"、'
            '人の受けるイメージは "バケツをひっくり返したように降る"'
        ),
    },
    {
        "object": "大雨",
        "property_name": "rain_50_80mm_term",
        "value_text": "非常に激しい雨（滝のように降る（ゴーゴーと降り続く））",
        "unit": "mm/h",
        "source": "amehyo",
        "note": (
            '1時間雨量 "50以上～80未満" の予報用語は "非常に激しい雨"、'
            '人の受けるイメージは "滝のように降る（ゴーゴーと降り続く）"'
        ),
    },
    {
        "object": "大雨",
        "property_name": "rain_80mm_plus_term",
        "value_text": "猛烈な雨（息苦しくなるような圧迫感がある。恐怖を感ずる）",
        "unit": "mm/h",
        "source": "amehyo",
        "note": (
            '1時間雨量 "80以上～" の予報用語は "猛烈な雨"、'
            '人の受けるイメージは "息苦しくなるような圧迫感がある。'
            '恐怖を感ずる"'
        ),
    },
    {
        "object": "大雨",
        "property_name": "record_max_10min_precipitation",
        "value_numeric": 55.0,
        "unit": "mm",
        "source": "rankall",
        "note": (
            '最大10分間降水量の歴代全国ランキング1位: "北海道　渡島地方" '
            '"木古内" "55.0" mm "2021年11月2日"'
        ),
    },
    {
        "object": "大雨",
        "property_name": "record_max_1h_precipitation",
        "value_numeric": 153.0,
        "unit": "mm",
        "source": "rankall",
        "note": (
            '最大１時間降水量の歴代全国ランキング1位（同値2地点）: '
            '"千葉県" "香取" "153" mm "1999年10月27日" および '
            '"長崎県" "長浦岳" "153" mm "1982年7月23日"'
        ),
    },
    {
        "object": "大雨",
        "property_name": "record_max_daily_precipitation",
        "value_numeric": 922.5,
        "unit": "mm",
        "source": "rankall",
        "note": (
            '日降水量の歴代全国ランキング1位: "神奈川県" "箱根" "922.5" mm '
            '"2019年10月12日"'
        ),
    },
    # --- 竜巻・ダウンバースト・ガストフロント ---
    {
        "object": "竜巻",
        "property_name": "damage_area_scale",
        "value_text": (
            "幅数十～数百メートル、長さ数キロメートル"
            "（数十キロメートルに達したことも）"
        ),
        "unit": None,
        "source": "tornado-1-1",
        "note": (
            '"被害域は、幅数十～数百メートルで、長さ数キロメートルの範囲に'
            '集中しますが、数十キロメートルに達したこともあります。"'
        ),
    },
    {
        "object": "ダウンバースト",
        "property_name": "spread_scale",
        "value_text": "数百メートルから十キロメートル程度",
        "unit": None,
        "source": "tornado-1-1",
        "note": (
            '"吹き出しの広がりは数百メートルから十キロメートル程度で、'
            '被害地域は円形あるいは楕円形など面的に広がる特徴があります。"'
        ),
    },
    {
        "object": "ガストフロント",
        "property_name": "spread_scale",
        "value_text": "数十キロメートル以上に達することも",
        "unit": None,
        "source": "tornado-1-1",
        "note": (
            '"水平の広がりは竜巻やダウンバーストより大きく、'
            '数十キロメートル以上に達することもあります。"'
        ),
    },
    # --- 津波 ---
    {
        "object": "津波",
        "property_name": "offshore_speed_comparison",
        "value_text": "沖合いではジェット機に匹敵する速さ",
        "unit": None,
        "source": "tsunami-generation",
        "note": (
            '"津波は、海が深いほど速く伝わる性質があり、沖合いでは'
            'ジェット機に匹敵する速さで伝わります。"'
        ),
    },
    {
        "object": "津波",
        "property_name": "dangerous_height_threshold",
        "value_text": "高さ20～30cm程度でも速い流れに巻き込まれるおそれ",
        "unit": "cm",
        "source": "tsunami-bosai",
        "note": (
            '"津波の力は非常に強く、高さ20～30cm程度の津波であっても'
            '速い流れに巻き込まれてしまうおそれがあります。"'
        ),
    },
    {
        "object": "津波",
        "property_name": "warning_issue_target_time",
        "value_text": "地震発生から約3分（一部の地震は最速2分以内）を目標に発表",
        "unit": None,
        "source": "tsunami-bosai",
        "note": (
            '"地震が発生してから約3分（日本近海で発生する一部の地震に'
            'ついては最速2分以内）を目標に大津波警報・津波警報または'
            '津波注意報を発表します。"（気象庁による発表の説明であり、'
            '本サービスが警報を発表するものではない）'
        ),
    },
    {
        "object": "津波",
        "property_name": "possible_duration",
        "value_text": "半日や１日以上継続することも",
        "unit": None,
        "source": "tsunami-bosai",
        "note": (
            '"広い範囲の沿岸に津波が到達し、津波が半日や１日以上継続する'
            'こともあります。"'
        ),
    },
    {
        "object": "津波",
        "property_name": "peru_2007_travel_time_to_japan",
        "value_text": "ペルーから太平洋を横断し20時間以上かけて日本へ到達",
        "unit": None,
        "source": "tsunami-generation",
        "note": (
            '平成１９年(２００７年)８月１６日にペルーで発生した地震による'
            '津波について: "日本から遠く離れたペルーから太平洋を横断し、'
            '２０時間以上もの時間をかけて日本へ到達している様子がわかります。"'
        ),
    },
    # --- 大雪 ---
    {
        "object": "大雪",
        "property_name": "tokyo_2018_max_snow_depth",
        "value_numeric": 23.0,
        "unit": "cm",
        "source": "snow-info",
        "note": (
            '"平成30年（2018年）1月22～23日に、本州の南海上を進んだ低気圧'
            '（南岸低気圧）により首都圏では広範囲で大雪となり、東京で'
            '最深積雪23センチを記録"'
        ),
    },
    {
        "object": "大雪",
        "property_name": "fukui_2018_max_snow_depth",
        "value_numeric": 147.0,
        "unit": "cm",
        "source": "snow-info",
        "note": (
            '"福井県では、福井市で「昭和56年豪雪（196cm）」以降最も深い'
            '積雪147センチを記録し、国道8号で1500台を超える大規模な'
            '車両滞留が発生して、自衛隊の災害派遣も行われました。"'
        ),
    },
    {
        "object": "大雪",
        "property_name": "fukui_1981_gosetsu_snow_depth",
        "value_numeric": 196.0,
        "unit": "cm",
        "source": "snow-info",
        "note": (
            '"福井県では、福井市で「昭和56年豪雪（196cm）」以降最も深い'
            '積雪147センチを記録"（昭和56年豪雪の福井の積雪 196cm）'
        ),
    },
    {
        "object": "大雪",
        "property_name": "short_time_heavy_snow_info_criteria",
        "value_text": (
            "おおむね3時間で20から25センチ、または6時間で30から40センチの降雪"
        ),
        "unit": "cm",
        "source": "snow-info",
        "note": (
            '気象防災速報（短時間大雪）について: "過去の交通障害等を踏まえ'
            '発表の目安を設定しており、個々の観測地点ごとに値は異なりますが、'
            'おおむね３時間で20から25センチ、または６時間で30から40センチの'
            '降雪を観測し、その後も警報級の降雪が続くと予想される場合に'
            '発表します。"'
        ),
    },
    {
        "object": "大雪",
        "property_name": "record_max_snow_depth",
        "value_numeric": 1182.0,
        "unit": "cm",
        "source": "rankall",
        "note": (
            '最深積雪の歴代全国ランキング1位: "滋賀県" "伊吹山" "1182" cm '
            '"1927年2月14日"（現在観測は実施していない地点）'
        ),
    },
    {
        "object": "大雪",
        "property_name": "record_max_snow_depth_active_station",
        "value_numeric": 566.0,
        "unit": "cm",
        "source": "rankall",
        "note": (
            '最深積雪の歴代全国ランキング2位（現在観測を実施している地点では'
            '最大）: "青森県" "酸ケ湯" "566" cm "2013年2月26日"'
        ),
    },
    # --- 活火山 ---
    {
        "object": "活火山",
        "property_name": "definition",
        "value_text": (
            "概ね過去1万年以内に噴火した火山及び現在活発な噴気活動のある火山"
        ),
        "unit": None,
        "source": "katsukazan-toha",
        "note": (
            '"活火山とは、「概ね過去1万年以内に噴火した火山及び現在活発な'
            '噴気活動のある火山｣のことです。"'
        ),
    },
    {
        "object": "活火山",
        "property_name": "count_in_japan",
        "value_numeric": 111.0,
        "unit": "count",
        "source": "katsukazan-toha",
        "note": '"我が国には、111の活火山があります。"',
    },
    # --- 風 ---
    {
        "object": "風",
        "property_name": "average_wind_definition",
        "value_text": "風速（平均風速）は10分間の平均風速",
        "unit": None,
        "source": "faq-wind",
        "note": (
            '"「風速（または平均風速）」は、１０分間の平均風速を示します。'
            '「瞬間風速」は、ある瞬間の風速を示します。"'
        ),
    },
    {
        "object": "風",
        "property_name": "gust_to_average_ratio",
        "value_text": "瞬間風速は平均風速の1.5倍から3倍程度に達することがある",
        "unit": None,
        "source": "faq-wind",
        "note": (
            '"「瞬間風速」は、「（平均）風速」の１．５倍から３倍程度に'
            '達することがあります。"'
        ),
    },
    {
        "object": "風",
        "property_name": "very_strong_wind_range",
        "value_text": "風速20m/s以上30m/s未満",
        "unit": "m/s",
        "source": "faq-wind",
        "note": (
            '"例えば、「非常に強い風」とは風速２０m/s以上３０m/s未満の風を'
            '指します。"'
        ),
    },
    {
        "object": "風",
        "property_name": "tokyo_storm_threshold",
        "value_numeric": 25.0,
        "unit": "m/s",
        "source": "faq-wind",
        "note": (
            '"暴風警報基準は都道府県ごとに設定しており、例えば、東京地方で'
            '「暴風」と言うのは風速２５m/s以上の風を指しています。"'
        ),
    },
    {
        "object": "風",
        "property_name": "record_max_wind_speed",
        "value_numeric": 72.5,
        "unit": "m/s",
        "source": "rankall",
        "note": (
            '最大風速の歴代全国ランキング1位: "静岡県" "富士山" "72.5" m/s '
            '風向 "西南西" "1942年4月5日"'
        ),
    },
    {
        "object": "風",
        "property_name": "record_max_gust_speed",
        "value_numeric": 91.0,
        "unit": "m/s",
        "source": "rankall",
        "note": (
            '最大瞬間風速の歴代全国ランキング1位: "静岡県" "富士山" "91.0" '
            'm/s 風向 "南南西" "1966年9月25日"'
        ),
    },
    # --- 気温 ---
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
    {
        "object": "気温",
        "property_name": "record_lowest_temperature",
        "value_numeric": -41.0,
        "unit": "celsius",
        "source": "rankall",
        "note": (
            '最低気温の低い方からの歴代全国ランキング1位: '
            '"北海道　上川地方" "旭川" "-41.0" ℃ "1902年1月25日"'
        ),
    },
    # --- 震度（気象庁震度階級関連解説表） ---
    {
        "object": "震度5弱",
        "property_name": "human_perception",
        "value_text": "大半の人が、恐怖を覚え、物につかまりたいと感じる。",
        "unit": None,
        "source": "shindo-kaisetsu",
        "note": (
            '震度階級 "５弱" の「人の体感・行動」: "大半の人が、恐怖を覚え、'
            '物につかまりたいと感じる。"'
        ),
    },
    {
        "object": "震度5強",
        "property_name": "human_perception",
        "value_text": (
            "大半の人が、物につかまらないと歩くことが難しいなど、"
            "行動に支障を感じる。"
        ),
        "unit": None,
        "source": "shindo-kaisetsu",
        "note": (
            '震度階級 "５強" の「人の体感・行動」: "大半の人が、物に'
            'つかまらないと歩くことが難しいなど、行動に支障を感じる。"'
        ),
    },
    {
        "object": "震度5強",
        "property_name": "indoor_situation",
        "value_text": (
            "棚にある食器類や書棚の本で、落ちるものが多くなる。テレビが台から"
            "落ちることがある。固定していない家具が倒れることがある。"
        ),
        "unit": None,
        "source": "shindo-kaisetsu",
        "note": (
            '震度階級 "５強" の「屋内の状況」: "棚にある食器類や書棚の本で、'
            '落ちるものが多くなる。テレビが台から落ちることがある。固定して'
            'いない家具が倒れることがある。"'
        ),
    },
    {
        "object": "震度6弱",
        "property_name": "human_perception",
        "value_text": "立っていることが困難になる。",
        "unit": None,
        "source": "shindo-kaisetsu",
        "note": (
            '震度階級 "６弱" の「人の体感・行動」: '
            '"立っていることが困難になる。"'
        ),
    },
    {
        "object": "震度6強",
        "property_name": "human_perception",
        "value_text": (
            "立っていることができず、はわないと動くことができない。"
            "揺れにほんろうされ、動くこともできず、飛ばされることもある。"
        ),
        "unit": None,
        "source": "shindo-kaisetsu",
        "note": (
            '震度階級 "６強" の「人の体感・行動」: "立っていることができず、'
            'はわないと動くことができない。揺れにほんろうされ、動くことも'
            'できず、飛ばされることもある。"（この記述は震度７にも及ぶ欄）'
        ),
    },
    {
        "object": "震度7",
        "property_name": "indoor_situation",
        "value_text": (
            "固定していない家具のほとんどが移動したり倒れたりし、"
            "飛ぶこともある。"
        ),
        "unit": None,
        "source": "shindo-kaisetsu",
        "note": (
            '震度階級 "７" の「屋内の状況」: "固定していない家具のほとんどが'
            '移動したり倒れたりし、飛ぶこともある｡"'
        ),
    },
]

# 逐語チャンク（翻訳・要約なし。分割のみ。表は「列名: セル値」の形で線形化）
DOCUMENTS: list[dict[str, str]] = [
    # --- 台風とは ---
    {
        "source": "typhoon-1-1",
        "content": (
            "熱帯の海上で発生する低気圧を「熱帯低気圧」と呼びますが、この"
            "うち北西太平洋（赤道より北で東経180度より西の領域）または南シナ海"
            "に存在し、なおかつ低気圧域内の最大風速（10分間平均）がおよそ"
            "17 m/s（34ノット、風力8）以上のものを「台風」と呼びます。"
        ),
    },
    {
        "source": "typhoon-1-1",
        "content": (
            "台風は、通常東風が吹いている低緯度では西に移動し、太平洋高気圧の"
            "まわりを北上して中・高緯度に達すると、上空の強い西風（偏西風）に"
            "より速い速度で北東へ進むなど、上空の風や台風周辺の気圧配置の影響"
            "を受けて動きます。また、台風は地球の自転の影響で北～北西へ向かう"
            "性質を持っています。"
        ),
    },
    {
        "source": "typhoon-1-1",
        "content": (
            "台風は暖かい海面から供給された水蒸気が凝結して雲粒になるときに"
            "放出される熱をエネルギーとして発達します。しかし、移動する際に"
            "海面や地上との摩擦により絶えずエネルギーを失っており、仮に"
            "エネルギーの供給がなくなれば2～3日で消滅してしまいます。また、"
            "日本付近に接近すると上空に寒気が流れ込むようになり、次第に台風"
            "本来の性質を失って「温帯低気圧」に変わります。あるいは、熱"
            "エネルギーの供給が少なくなり衰えて「熱帯低気圧」に変わることも"
            "あります。上陸した台風が急速に衰えるのは水蒸気の供給が絶たれ、"
            "さらに陸地の摩擦によりエネルギーが失われるからです。"
        ),
    },
    # --- 台風の大きさと強さ ---
    {
        "source": "typhoon-1-3",
        "content": (
            "気象庁は台風のおおよその勢力を示す目安として、下表のように風速"
            "（10分間平均）をもとに台風の「大きさ」と「強さ」 を表現します。"
            "「大きさ」は強風域（風速15 m/s以上の風が吹いているか、吹く可能性"
            "がある範囲）の半径で、 「強さ」は最大風速で区分しています。"
            "さらに、風速25 m/s以上の風が吹いているか、吹く可能性がある範囲を"
            "暴風域と呼びます。"
        ),
    },
    {
        "source": "typhoon-1-3",
        "content": (
            "強さの階級分け: 階級「強い」は最大風速 33 m/s（64ノット）以上～"
            "44 m/s（85ノット）未満。階級「非常に強い」は 44 m/s（85ノット）"
            "以上～54 m/s（105ノット）未満。階級「猛烈な」は 54 m/s"
            "（105ノット）以上。大きさの階級分け: 階級「大型（大きい）」は"
            "風速 15 m/s以上の半径 500 km以上～800 km未満。階級「超大型"
            "（非常に大きい）」は 800 km以上。"
        ),
    },
    {
        "source": "typhoon-1-3",
        "content": (
            "台風に関する情報の中では台風の大きさと強さを組み合わせて、"
            "「大型で強い台風」のように呼びます。ただし、強風域の半径が"
            "500 km未満の場合には大きさを表現せず、最大風速が33 m/s未満の"
            "場合には強さを表現しません。例えば「強い台風」と発表している"
            "場合、その台風は、強風域の半径が500 km未満で、最大風速は"
            "33～43 m/sで暴風域を伴っていることを表します。"
        ),
    },
    # --- 雨の強さと降り方（表の線形化） ---
    {
        "source": "amehyo",
        "content": (
            "1時間雨量(mm) 10以上～20未満 / 予報用語: やや強い雨 / "
            "人の受けるイメージ: ザーザーと降る / 人への影響: 地面からの"
            "跳ね返りで足元がぬれる / 屋内(木造住宅を想定）: 雨の音で話し声が"
            "良く聞き取れない / 屋外の様子: 地面一面に水たまりができる"
        ),
    },
    {
        "source": "amehyo",
        "content": (
            "1時間雨量(mm) 20以上～30未満 / 予報用語: 強い雨 / "
            "人の受けるイメージ: どしゃ降り / 人への影響: 傘をさしていても"
            "ぬれる / 屋内(木造住宅を想定）: 寝ている人の半数くらいが雨に"
            "気がつく / 車に乗っていて: ワイパーを速くしても見づらい"
        ),
    },
    {
        "source": "amehyo",
        "content": (
            "1時間雨量(mm) 30以上～50未満 / 予報用語: 激しい雨 / "
            "人の受けるイメージ: バケツをひっくり返したように降る / "
            "屋外の様子: 道路が川のようになる / 車に乗っていて: 高速走行時、"
            "車輪と路面の間に水膜が生じブレーキが効かなくなる"
            "（ハイドロプレーニング現象）"
        ),
    },
    {
        "source": "amehyo",
        "content": (
            "1時間雨量(mm) 50以上～80未満 / 予報用語: 非常に激しい雨 / "
            "人の受けるイメージ: 滝のように降る（ゴーゴーと降り続く） / "
            "人への影響: 傘は全く役に立たなくなる / 屋外の様子: 水しぶきで"
            "あたり一面が白っぽくなり、視界が悪くなる / 車に乗っていて: "
            "車の運転は危険"
        ),
    },
    {
        "source": "amehyo",
        "content": (
            "1時間雨量(mm) 80以上～ / 予報用語: 猛烈な雨 / "
            "人の受けるイメージ: 息苦しくなるような圧迫感がある。恐怖を感ずる"
        ),
    },
    # --- 竜巻などの激しい突風とは ---
    {
        "source": "tornado-1-1",
        "content": (
            "発達した積乱雲からは、竜巻、ダウンバースト、ガストフロントと"
            "いった、激しい突風をもたらす現象が発生します。"
        ),
    },
    {
        "source": "tornado-1-1",
        "content": (
            "竜巻: 積乱雲に伴う強い上昇気流により発生する激しい渦巻きで、"
            "多くの場合、漏斗状または柱状の雲を伴います。被害域は、幅数十～"
            "数百メートルで、長さ数キロメートルの範囲に集中しますが、数十"
            "キロメートルに達したこともあります。"
        ),
    },
    {
        "source": "tornado-1-1",
        "content": (
            "ダウンバースト: 積乱雲から吹き降ろす下降気流が地表に衝突して"
            "水平に吹き出す激しい空気の流れです。吹き出しの広がりは数百"
            "メートルから十キロメートル程度で、被害地域は円形あるいは楕円形"
            "など面的に広がる特徴があります。"
        ),
    },
    {
        "source": "tornado-1-1",
        "content": (
            "ガストフロント: 積乱雲の下で形成された冷たい（重い）空気の塊が、"
            "その重みにより温かい（軽い）空気の側に流れ出すことによって発生"
            "します。水平の広がりは竜巻やダウンバーストより大きく、数十キロ"
            "メートル以上に達することもあります。"
        ),
    },
    # --- 津波発生と伝播のしくみ ---
    {
        "source": "tsunami-generation",
        "content": (
            "海底下で大きな地震が発生すると、断層運動により海底が隆起もしくは"
            "沈降します。これに伴って海面が変動し、大きな波となって四方八方に"
            "伝播するものが津波です。"
        ),
    },
    {
        "source": "tsunami-generation",
        "content": (
            "「津波の前には必ず潮が引く」という言い伝えがありますが、必ずしも"
            "そうではありません。地震を発生させた地下の断層の傾きや方向に"
            "よっては、また、津波が発生した場所と海岸との位置関係によっては、"
            "潮が引くことなく最初に大きな波が海岸に押し寄せる場合もあります。"
            "津波は引き波で始まるとは限らないのです。"
        ),
    },
    {
        "source": "tsunami-generation",
        "content": (
            "津波は、海が深いほど速く伝わる性質があり、沖合いではジェット機に"
            "匹敵する速さで伝わります。 逆に、水深が浅くなるほど速度が遅く"
            "なるため、津波が陸地に近づくにつれ、減速した波の前方部に後方部が"
            "追いつくことで、波高が高くなります。"
        ),
    },
    {
        "source": "tsunami-generation",
        "content": (
            "水深が浅いところで遅くなるといっても、人が走って逃げ切れるもの"
            "ではありません。 津波から命を守るためには、津波が海岸にやってくる"
            "のを見てから避難を始めたのでは間に合わないのです。海岸付近で地震"
            "の揺れを感じたら、または、津波警報が発表されたら、実際に津波が"
            "見えなくても、速やかに避難しましょう。"
        ),
    },
    {
        "source": "tsunami-generation",
        "content": (
            "津波の高さは海岸付近の地形によって大きく変化します。さらに、津波"
            "が陸地を駆け上がる（遡上する）こともあります。岬の先端やＶ字型の"
            "湾の奥などの特殊な地形の場所では、波が集中するので、特に注意が"
            "必要です。 津波は反射を繰り返すことで何回も押し寄せたり、複数の"
            "波が重なって著しく高い波となることもあります。このため、最初の波"
            "が一番大きいとは限らず、後で来襲する津波のほうが高くなることも"
            "あります。"
        ),
    },
    # --- 津波から身を守るために ---
    {
        "source": "tsunami-bosai",
        "content": (
            "津波は、地震などによって生じた海底の隆起・沈降に伴い発生した海水"
            "の波が、四方八方へ広がり伝わっていく現象です。沿岸に近づき水深が"
            "浅くなるにつれ、急激に高くなります。津波の伝播速度は非常に速く、"
            "見てから逃げるのでは間に合いません。周辺の地形により反射や屈折を"
            "経て繰り返し襲ってきます。後から来る津波の方が高くなることも"
            "あります。"
        ),
    },
    {
        "source": "tsunami-bosai",
        "content": (
            "津波の力は非常に強く、高さ20～30cm程度の津波であっても速い流れに"
            "巻き込まれてしまうおそれがあります。津波は「引き」から始まるとは"
            "限りません。“潮が引いたら逃げればよい” というのは大きな間違い"
            "です。沿岸の地形の影響などにより、局所的に高くなることもあり"
            "ます。潮位変化が始まってから最大波が観測されるまで数時間以上"
            "かかることもあります。広い範囲の沿岸に津波が到達し、津波が半日や"
            "１日以上継続することもあります。"
        ),
    },
    {
        "source": "tsunami-bosai",
        "content": (
            "津波警報・注意報を見聞きしたり、海辺で強い揺れを感じたり、長く"
            "ゆっくりした揺れを感じたりしたら、海辺から離れ、より高い安全な"
            "場所へ避難しましょう。"
        ),
    },
    {
        "source": "tsunami-bosai",
        "content": (
            "解除まで気を付けて: 津波は繰り返し襲ってきます。津波到達後も"
            "津波警報・注意報が解除されるまで気を緩めず、避難を続けて"
            "ください。津波警報が出ている間は、絶対に戻ってはいけません。"
        ),
    },
    # --- 大雪に関する情報について ---
    {
        "source": "snow-info",
        "content": (
            "平成30年（2018年）1月22～23日に、本州の南海上を進んだ低気圧"
            "（南岸低気圧）により首都圏では広範囲で大雪となり、東京で最深積雪"
            "23センチを記録、鉄道や道路が広範囲でストップし、社会活動に大きな"
            "影響が出ました。また、同年2月3～8日 には冬型の気圧配置となって"
            "強い寒気が流入し、北陸地方を中心として記録的な大雪となりました。"
            "福井県では、福井市で「昭和56年豪雪（196cm）」以降最も深い積雪"
            "147センチを記録し、国道8号で1500台を超える大規模な車両滞留が発生"
            "して、自衛隊の災害派遣も行われました。"
        ),
    },
    {
        "source": "snow-info",
        "content": (
            "大雪となると、道路の通行止めや車両滞留、鉄道の運休や立ち往生、"
            "航空機の欠航等の交通障害、農業用ハウスの倒壊や果樹の枝折れ等の"
            "農業被害、停電などが発生し、経済活動に影響を与えます。また、集落"
            "の孤立や家屋の倒壊などの重大な災害も引き起こします。"
        ),
    },
    # --- 気象庁震度階級関連解説表（表の線形化） ---
    {
        "source": "shindo-kaisetsu",
        "content": (
            "震度階級: ４ / 人の体感・行動: ほとんどの人が驚く。歩いている人"
            "のほとんどが、揺れを感じる。眠っている人のほとんどが、目を覚ます。"
            " / 屋内の状況: 電灯などのつり下げ物は大きく揺れ､棚にある食器類は"
            "音を立てる。座りの悪い置物が、倒れることがある。 / 屋外の状況: "
            "電線が大きく揺れる。自動車を運転していて、揺れに気付く人がいる。"
        ),
    },
    {
        "source": "shindo-kaisetsu",
        "content": (
            "震度階級: ５弱 / 人の体感・行動: 大半の人が、恐怖を覚え、物に"
            "つかまりたいと感じる。 / 屋内の状況: 電灯などのつり下げ物は激しく"
            "揺れ､棚にある食器類、書棚の本が落ちることがある。座りの悪い置物"
            "の大半が倒れる。固定していない家具が移動することがあり、不安定な"
            "ものは倒れることがある。 / 屋外の状況: まれに窓ガラスが割れて"
            "落ちることがある。電柱が揺れるのがわかる。道路に被害が生じること"
            "がある｡"
        ),
    },
    {
        "source": "shindo-kaisetsu",
        "content": (
            "震度階級: ５強 / 人の体感・行動: 大半の人が、物につかまらないと"
            "歩くことが難しいなど、行動に支障を感じる。 / 屋内の状況: 棚にある"
            "食器類や書棚の本で、落ちるものが多くなる。テレビが台から落ちる"
            "ことがある。固定していない家具が倒れることがある。 / 屋外の状況: "
            "窓ガラスが割れて落ちることがある。補強されていないブロック塀が"
            "崩れることがある。据付けが不十分な自動販売機が倒れることがある。"
            "自動車の運転が困難となり、停止する車もある。"
        ),
    },
    {
        "source": "shindo-kaisetsu",
        "content": (
            "震度階級: ６弱 / 人の体感・行動: 立っていることが困難になる。 / "
            "屋内の状況: 固定していない家具の大半が移動し、倒れるものも"
            "ある｡ドアが開かなくなることがある｡ / 屋外の状況: 壁のタイルや"
            "窓ガラスが破損、落下することがある。"
        ),
    },
    {
        "source": "shindo-kaisetsu",
        "content": (
            "震度階級: ６強 / 人の体感・行動: 立っていることができず、はわない"
            "と動くことができない。揺れにほんろうされ、動くこともできず、"
            "飛ばされることもある。 / 屋内の状況: 固定していない家具のほとんど"
            "が移動し、倒れるものが多くなる。 / 屋外の状況: 壁のタイルや窓"
            "ガラスが破損、落下する建物が多くなる。補強されていないブロック塀"
            "のほとんどが崩れる。"
        ),
    },
    {
        "source": "shindo-kaisetsu",
        "content": (
            "震度階級: ７ / 人の体感・行動: 立っていることができず、はわない"
            "と動くことができない。揺れにほんろうされ、動くこともできず、"
            "飛ばされることもある。 / 屋内の状況: 固定していない家具のほとんど"
            "が移動したり倒れたりし、飛ぶこともある｡ / 屋外の状況: 壁のタイル"
            "や窓ガラスが破損､落下する建物がさらに多くなる。補強されている"
            "ブロック塀も破損するものがある。"
        ),
    },
    # --- 活火山とは ---
    {
        "source": "katsukazan-toha",
        "content": (
            "活火山とは、「概ね過去1万年以内に噴火した火山及び現在活発な噴気"
            "活動のある火山｣のことです。我が国には、111の活火山があります。"
        ),
    },
    {
        "source": "katsukazan-toha",
        "content": (
            "昔は、今現在活動している、つまり噴火している火山は「活火山」、"
            "現在噴火していない火山は「休火山」あるいは「死火山」と呼ばれて"
            "いました。例えば、富士山のように歴史時代（文献による検証可能な"
            "時代）に噴火記録はあるものの、現在休んでいる火山のことを指して"
            "「休火山」、歴史時代の噴火記録がない火山のことを指して「死火山」"
            "という表現が使われていました。"
        ),
    },
    {
        "source": "katsukazan-toha",
        "content": (
            "しかし、火山の活動の寿命は長く、数百年程度の休止期間はほんの"
            "つかの間の眠りでしかないということから、噴火記録のある火山や今後"
            "噴火する可能性がある火山を全て「活火山」と分類する考え方が1950"
            "年代から国際的に広まり、1960年代からは気象庁も噴火の記録のある"
            "火山をすべて活火山と呼ぶことにしました。"
        ),
    },
    # --- 風について（FAQ） ---
    {
        "source": "faq-wind",
        "content": (
            "「風速（または平均風速）」は、１０分間の平均風速を示します。"
            "「瞬間風速」は、ある瞬間の風速を示します。「瞬間風速」は、"
            "「（平均）風速」の１．５倍から３倍程度に達することがあります。"
        ),
    },
    {
        "source": "faq-wind",
        "content": (
            "気象庁では、皆様に風の強さの程度を容易にご理解いただくために、"
            "風の強さを「やや強い風」、「強い風」、「非常に強い風」、"
            "「猛烈な風」の４段階に分類してお伝えしています。例えば、"
            "「非常に強い風」とは風速２０m/s以上３０m/s未満の風を指します。"
        ),
    },
    {
        "source": "faq-wind",
        "content": (
            "発達した積乱雲の中には強い上昇気流があります。一方、周辺の風の"
            "分布や地形の影響などによって地面付近には大きな回転性の流れ（渦）"
            "が生じることがあります。この大きな渦の上に積乱雲の上昇流が重なる"
            "と渦は上空に引き伸ばされ、最初は大きかった回転の半径が小さくなり"
            "ます。回転の半径が小さくなると回転のスピードが速くなるので、最初"
            "の渦は風速が弱くても引き伸ばされた渦の風速は非常に強くなります。"
            "これはフィギュアスケートの回転で腕をたたむと回転スピードが上がる"
            "のと同じです。このようにしてできた上下に細長く伸びた速い回転の渦"
            "が竜巻です。"
        ),
    },
]
