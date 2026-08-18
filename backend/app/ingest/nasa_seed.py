"""NASA 出典の初期シードデータ（実取得値のみ。ADR-0003 / ADR-0006）。

方針:

- ここにある値・原文はすべて、2026-08-18 に実際に各ページを取得して確認した
  記述である。ページに書かれていない属性は投入しない（記憶による補完をしない）
- 各プロパティの note には、値の根拠となったページ上の原文（該当文）を残す。
  後から「この値はどの記述から来たか」を検証できることを優先する
- NASA の解説ページは数値の原典（論文）を示していない。これは許容する方針だが、
  記録上は reuse_basis に明記して区別する。マグネターのニュース記事のみ
  Nature / Nature Astronomy の論文を典拠として明示しているため、そこは分けて書く
- ページ間で数値が食い違う場合（中性子星の直径・母星質量など）は、両方を
  それぞれの source_id 付きで保持する（UNIQUE (object_id, property_name,
  source_id) が同一属性の複数出典を許す）。documents のチャンクは新しい
  science.nasa.gov の記述を優先する
- https://science.nasa.gov/universe/black-holes/anatomy/ も取得したが、
  定量的な記述が得られなかったため投入していない
- documents のチャンクは逐語転載を最小限にした日本語の要点要約。
  embedding は NULL のまま（LLM プロバイダ未確定。RAG 本結線は次フェーズ）
"""

# 取得直後（2026-08-18 05:45-05:50 UTC の取得バッチ完了時）に計測した時刻
RETRIEVED_AT = "2026-08-18T05:50:45+00:00"

# NASA 解説ページ共通の reuse_basis（原典未提示を記録に残す）
_NASA_PD_NO_CITATION = (
    "public domain (NASA media usage guidelines);"
    " page does not cite primary literature"
)

SOURCES: dict[str, dict[str, str]] = {
    "science-black-holes": {
        "source_url": "https://science.nasa.gov/universe/black-holes/",
        "source_title": "Black Holes - NASA Science",
        "reuse_basis": _NASA_PD_NO_CITATION,
        "retrieved_at": RETRIEVED_AT,
        "note": "ページ表示の最終更新: Aug 12, 2026",
    },
    "science-star-types": {
        "source_url": "https://science.nasa.gov/universe/stars/types/",
        "source_title": "Types - NASA Science",
        "reuse_basis": _NASA_PD_NO_CITATION,
        "retrieved_at": RETRIEVED_AT,
        "note": "ページ表示の最終更新: Aug 12, 2026",
    },
    "science-neutron-stars": {
        "source_url": (
            "https://science.nasa.gov/universe/stories/quick-reads/"
            "neutron-stars-are-weird/"
        ),
        "source_title": "Neutron Stars Are Weird! - NASA Science",
        "reuse_basis": _NASA_PD_NO_CITATION,
        "retrieved_at": RETRIEVED_AT,
        "note": "ページ表示の最終更新: Aug 12, 2026",
    },
    "science-hubble-quasars": {
        "source_url": (
            "https://science.nasa.gov/mission/hubble/science/"
            "science-behind-the-discoveries/hubble-quasars/"
        ),
        "source_title": "Hubble Quasars - NASA Science",
        "reuse_basis": _NASA_PD_NO_CITATION,
        "retrieved_at": RETRIEVED_AT,
        "note": "ページ表示の最終更新: Jun 18, 2026",
    },
    "imagine-black-holes": {
        "source_url": (
            "https://imagine.gsfc.nasa.gov/science/objects/black_holes1.html"
        ),
        "source_title": "Black Holes (Imagine the Universe!)",
        "reuse_basis": _NASA_PD_NO_CITATION,
        "retrieved_at": RETRIEVED_AT,
        "note": (
            "ページ表示の最終更新: Thu, Sep 23, 2021。"
            "science.nasa.gov と食い違う場合は science.nasa.gov を優先する"
        ),
    },
    "imagine-white-dwarfs": {
        "source_url": (
            "https://imagine.gsfc.nasa.gov/science/objects/dwarfs1.html"
        ),
        "source_title": "White Dwarfs (Imagine the Universe!)",
        "reuse_basis": _NASA_PD_NO_CITATION,
        "retrieved_at": RETRIEVED_AT,
        "note": (
            "本文の執筆表示は December 2006（ページ最終更新は Thu, Sep 23, 2021）。"
            "science.nasa.gov と食い違う場合は science.nasa.gov を優先する"
        ),
    },
    "imagine-neutron-stars": {
        "source_url": (
            "https://imagine.gsfc.nasa.gov/science/objects/neutron_stars1.html"
        ),
        "source_title": "Neutron Stars (Imagine the Universe!)",
        "reuse_basis": _NASA_PD_NO_CITATION,
        "retrieved_at": RETRIEVED_AT,
        "note": (
            "ページ表示の最終更新: Thu, Sep 23, 2021。"
            "science.nasa.gov と食い違う場合は science.nasa.gov を優先する"
        ),
    },
    "nasa-magnetar-eruptions": {
        "source_url": (
            "https://www.nasa.gov/universe/"
            "nasa-missions-unmask-magnetar-eruptions-in-nearby-galaxies/"
        ),
        "source_title": "NASA Missions Unmask Magnetar Eruptions in Nearby Galaxies",
        "reuse_basis": (
            "public domain (NASA media usage guidelines);"
            " article cites primary literature: 'Papers analyzing different"
            " aspects of the event and its implications were published on"
            " Jan. 13 in the journals Nature and Nature Astronomy.'"
        ),
        "retrieved_at": RETRIEVED_AT,
        "note": "記事の公開日: Jan 13, 2021。マグネター既知数（29）は 2021 年時点の値",
    },
}

OBJECTS: list[dict[str, str]] = [
    {"name": "ブラックホール", "kind": "black_hole", "note": "black hole"},
    {"name": "中性子星", "kind": "neutron_star", "note": "neutron star"},
    {"name": "マグネター", "kind": "magnetar", "note": "magnetar"},
    {"name": "白色矮星", "kind": "white_dwarf", "note": "white dwarf"},
    {"name": "褐色矮星", "kind": "brown_dwarf", "note": "brown dwarf"},
    {
        "name": "赤色巨星",
        "kind": "red_giant",
        "note": (
            "red giant。巨星の専用解説ページは NASA に存在せず、"
            "属性は星の種類ページ等の断片的な記述のみ"
        ),
    },
    {"name": "クエーサー", "kind": "quasar", "note": "quasar"},
]

# object: OBJECTS の name / source: SOURCES のキー / note: ページ上の原文（該当文）
PROPERTIES: list[dict] = [
    # --- ブラックホール ---
    {
        "object": "ブラックホール",
        "property_name": "most_massive_known_mass",
        "value_numeric": 6.6e10,
        "unit": "solar_mass",
        "source": "science-black-holes",
        "note": (
            '"The most massive black hole observed, TON 618, tips the scales'
            " at 66 billion times the Sun's mass.\""
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "lightest_known_mass",
        "value_numeric": 3.8,
        "unit": "solar_mass",
        "source": "science-black-holes",
        "note": (
            "\"The lightest-known black hole is only 3.8 times the Sun's mass.\""
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "sagittarius_a_star_mass",
        "value_numeric": 4.0e6,
        "unit": "solar_mass",
        "source": "science-black-holes",
        "note": (
            "\"Our is called Sagittarius A* (pronounced ey-star), and it's"
            " 4 million times the Sun's mass.\"（原文ママ）"
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "nearest_known_distance",
        "value_numeric": 1500.0,
        "unit": "light_year",
        "source": "science-black-holes",
        "note": (
            '"The nearest known black hole, called Gaia BH1, is about'
            ' 1,500 light-years away."'
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "most_distant_known_distance",
        "value_numeric": 1.3e10,
        "unit": "light_year",
        "source": "science-black-holes",
        "note": (
            '"The most distant black hole detected, at the center of a galaxy'
            ' called QSO J0313-1806, is around 13 billion light-years away."'
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "fastest_known_spin",
        "value_text": "over 1,000 rotations per second (GRS 1915+105)",
        "unit": "rotations_per_second",
        "source": "science-black-holes",
        "note": (
            '"The fastest-known – named GRS 1915+105 – clocks in at over'
            ' 1,000 rotations per second."'
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "stellar_mass_range",
        "value_text": "about 5-20 solar masses",
        "unit": "solar_mass",
        "source": "imagine-black-holes",
        "note": (
            '"those with masses about 5-20 times that of the sun, which are'
            ' called stellar-mass black holes"'
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "supermassive_mass_range",
        "value_text": "millions to billions of solar masses",
        "unit": "solar_mass",
        "source": "imagine-black-holes",
        "note": (
            '"those with masses millions to billions times that of the sun,'
            ' which are called supermassive black holes"'
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "sun_schwarzschild_radius",
        "value_numeric": 3.0,
        "unit": "km",
        "source": "imagine-black-holes",
        "note": (
            '"For something the mass of our sun would need to be squeezed'
            ' into a volume with a radius of about 3 km"'
        ),
    },
    {
        "object": "ブラックホール",
        "property_name": "earth_schwarzschild_radius",
        "value_numeric": 9.0,
        "unit": "mm",
        "source": "imagine-black-holes",
        "note": (
            "\"If we squished the Earth's mass into a sphere with a radius of"
            ' 9 mm, the escape velocity would be the speed of light"'
        ),
    },
    # --- 中性子星 ---
    {
        "object": "中性子星",
        "property_name": "max_mass",
        "value_numeric": 2.0,
        "unit": "solar_mass",
        "source": "science-neutron-stars",
        "note": (
            '"Neutron stars squeeze up to two solar masses into a city-size'
            ' volume."'
        ),
    },
    {
        "object": "中性子星",
        "property_name": "progenitor_mass_range",
        "value_text": "roughly 7 to 19 solar masses",
        "unit": "solar_mass",
        "source": "science-neutron-stars",
        "note": (
            "\"If it's roughly 7 to 19 times the mass of our Sun, we are left"
            ' with a neutron star." 同ページに "If it started with more than'
            ' 20 times the mass of our Sun, it becomes a black hole." とあり、'
            "ページ間で 7-20 / 8-20 / 8 以上と幅がある（既知の食い違い）"
        ),
    },
    {
        "object": "中性子星",
        "property_name": "collapsing_core_mass_range",
        "value_text": "between about 1 and 3 solar masses",
        "unit": "solar_mass",
        "source": "imagine-neutron-stars",
        "note": (
            '"If the core of the collapsing star is between about 1 and 3'
            ' solar masses, these newly-created neutrons can stop the'
            ' collapse"（母星全体ではなくコアの質量）'
        ),
    },
    {
        "object": "中性子星",
        "property_name": "density_sugar_cube_mass",
        "value_numeric": 1.0e12,
        "unit": "kg",
        "source": "science-neutron-stars",
        "note": (
            '"one sugar cube of neutron star material would weigh about'
            ' 1 trillion kilograms (or 1 billion tons) on Earth"'
        ),
    },
    {
        "object": "中性子星",
        "property_name": "density_sugar_cube_mass",
        "value_numeric": 1.0e12,
        "unit": "kg",
        "source": "imagine-neutron-stars",
        "note": (
            '"One sugar cube of neutron star material would weigh about'
            ' 1 trillion kilograms (or 1 billion tons) on Earth"'
            "（science.nasa.gov と同一の記述）"
        ),
    },
    {
        "object": "中性子星",
        "property_name": "size_comparison",
        "value_text": "city-size volume",
        "unit": None,
        "source": "science-neutron-stars",
        "note": (
            '"That is what happens when you cram a star with up to twice the'
            ' mass of our Sun into a sphere the diameter of a city."'
            "（このページは具体的な km 値を示さない。km 値は imagine 側の"
            " diameter を参照）"
        ),
    },
    {
        "object": "中性子星",
        "property_name": "diameter",
        "value_numeric": 20.0,
        "unit": "km",
        "source": "imagine-neutron-stars",
        "note": (
            '"These stellar remnants measure about 20 kilometers (12.5 miles)'
            ' across." 同ページ冒頭では "a sphere about 12 miles across" とも'
            "記載（12 mi と 12.5 mi の揺れはページ内に存在）"
        ),
    },
    {
        "object": "中性子星",
        "property_name": "mass_vs_earth",
        "value_numeric": 5.0e5,
        "unit": "earth_mass",
        "source": "imagine-neutron-stars",
        "note": (
            '"A neutron star is the densest object astronomers can observe'
            " directly, crushing half a million times Earth's mass into a"
            ' sphere about 12 miles across"'
        ),
    },
    {
        "object": "中性子星",
        "property_name": "fastest_pulsar_spin",
        "value_numeric": 43000.0,
        "unit": "rotations_per_minute",
        "source": "science-neutron-stars",
        "note": (
            '"The fastest known pulsar, named PSR J1748-2446ad, spins 43,000'
            ' times every minute."'
        ),
    },
    {
        "object": "中性子星",
        "property_name": "magnetic_field_vs_earth",
        "value_text": "billions and trillions of times stronger than Earth's",
        "unit": None,
        "source": "science-neutron-stars",
        "note": (
            '"While all known neutron stars have magnetic fields billions and'
            " trillions of times stronger than Earth's, a type of neutron star"
            ' known as a magnetar can have a magnetic field another thousand'
            ' times stronger."'
        ),
    },
    {
        "object": "中性子星",
        "property_name": "magnetic_field_vs_earth",
        "value_text": "trillions of times that of the Earth's magnetic field",
        "unit": None,
        "source": "imagine-neutron-stars",
        "note": (
            '"In a typical neutron star, the magnetic field is trillions of'
            " times that of the Earth's magnetic field; however, in a"
            ' magnetar, the magnetic field is another 1000 times stronger."'
            "（science.nasa.gov は billions and trillions と記載。"
            "食い違いは両方保持し、新しい science 側を優先）"
        ),
    },
    # --- マグネター ---
    {
        "object": "マグネター",
        "property_name": "magnetic_field_vs_neutron_star",
        "value_text": "up to a thousand times the intensity of typical neutron stars",
        "unit": None,
        "source": "nasa-magnetar-eruptions",
        "note": (
            '"Magnetars are neutron stars with the strongest-known magnetic'
            ' fields, with up to a thousand times the intensity of typical'
            ' neutron stars and up to 10 trillion times the strength of a'
            ' refrigerator magnet."'
        ),
    },
    {
        "object": "マグネター",
        "property_name": "magnetic_field_vs_neutron_star",
        "value_text": "another thousand times stronger (than typical neutron stars)",
        "unit": None,
        "source": "science-neutron-stars",
        "note": (
            '"While all known neutron stars have magnetic fields billions and'
            " trillions of times stronger than Earth's, a type of neutron star"
            ' known as a magnetar can have a magnetic field another thousand'
            ' times stronger."'
        ),
    },
    {
        "object": "マグネター",
        "property_name": "magnetic_field_vs_refrigerator_magnet",
        "value_numeric": 1.0e13,
        "unit": "refrigerator_magnet",
        "source": "nasa-magnetar-eruptions",
        "note": (
            '"... and up to 10 trillion times the strength of a refrigerator'
            ' magnet."（up to の値）'
        ),
    },
    {
        "object": "マグネター",
        "property_name": "known_count_milky_way",
        "value_numeric": 29.0,
        "unit": "count",
        "source": "nasa-magnetar-eruptions",
        "note": (
            '"Most of the 29 magnetars now cataloged in our Milky Way galaxy'
            ' exhibit occasional X-ray activity, but only two have produced'
            ' giant flares."（2021-01-13 時点の値）'
        ),
    },
    {
        "object": "マグネター",
        "property_name": "giant_flare_2004_distance",
        "value_numeric": 28000.0,
        "unit": "light_year",
        "source": "nasa-magnetar-eruptions",
        "note": (
            '"The most recent event, detected on Dec. 27, 2004, produced'
            " measurable changes in Earth's upper atmosphere despite erupting"
            ' from a magnetar located about 28,000 light-years away."'
        ),
    },
    {
        "object": "マグネター",
        "property_name": "sgr_1806_20_flare_energy_comparison",
        "value_text": (
            "released more energy in one-tenth of a second than the sun has"
            " emitted in the last 100,000 years"
        ),
        "unit": None,
        "source": "imagine-neutron-stars",
        "note": (
            '"A magnetar called SGR 1806-20 had a burst where in one-tenth of'
            ' a second it released more energy than the sun has emitted in'
            ' the last 100,000 years!"'
        ),
    },
    # --- 白色矮星 ---
    {
        "object": "白色矮星",
        "property_name": "size_comparison",
        "value_text": "usually Earth-size",
        "unit": None,
        "source": "science-star-types",
        "note": (
            '"A white dwarf is usually Earth-size but hundreds of thousands'
            ' of times more massive."'
        ),
    },
    {
        "object": "白色矮星",
        "property_name": "mass_vs_earth",
        "value_text": "hundreds of thousands of times more massive (than Earth)",
        "unit": "earth_mass",
        "source": "science-star-types",
        "note": (
            '"A white dwarf is usually Earth-size but hundreds of thousands'
            ' of times more massive."'
        ),
    },
    {
        "object": "白色矮星",
        "property_name": "typical_mass_comparison",
        "value_text": "about as massive as the Sun, only slightly bigger than the Earth",
        "unit": None,
        "source": "imagine-white-dwarfs",
        "note": (
            '"A typical white dwarf is about as massive as the Sun, yet only'
            ' slightly bigger than the Earth."'
        ),
    },
    {
        "object": "白色矮星",
        "property_name": "progenitor_mass_max",
        "value_numeric": 8.0,
        "unit": "solar_mass",
        "source": "imagine-white-dwarfs",
        "note": (
            '"A low or medium mass star (with mass less than about 8 times'
            ' the mass of our Sun) will become a white dwarf."'
        ),
    },
    {
        "object": "白色矮星",
        "property_name": "density_teaspoon_comparison",
        "value_text": "a teaspoon of its material would weigh more than a pickup truck",
        "unit": None,
        "source": "science-star-types",
        "note": (
            '"A teaspoon of its material would weigh more than a pickup'
            ' truck."'
        ),
    },
    {
        "object": "白色矮星",
        "property_name": "young_wd_interior_temperature",
        "value_numeric": 100000.0,
        "unit": "degrees",
        "source": "imagine-white-dwarfs",
        "note": (
            '"X-rays come from inside the visible surface of the white dwarf.'
            ' This region is very dense and can be as hot as 100,000 degrees'
            ' in a very young white dwarf."（温度スケールの単位表記はページ上'
            "に明示なし）"
        ),
    },
    {
        "object": "白色矮星",
        "property_name": "sun_becomes_white_dwarf_in",
        "value_numeric": 1.0e10,
        "unit": "years",
        "source": "science-star-types",
        "note": (
            '"In about 10 billion years, after its time as a red giant, the'
            ' Sun will become a white dwarf."'
        ),
    },
    # --- 褐色矮星（取得できた属性は質量域 1 点のみ） ---
    {
        "object": "褐色矮星",
        "property_name": "mass_range",
        "value_text": "between 13 and 80 times the mass of Jupiter",
        "unit": "jupiter_mass",
        "source": "science-star-types",
        "note": (
            '"Generally, they have between 13 and 80 times the mass of'
            ' Jupiter."'
        ),
    },
    # --- 赤色巨星（専用解説ページなし。断片的な記述のみ） ---
    {
        "object": "赤色巨星",
        "property_name": "progenitor_mass_max",
        "value_numeric": 8.0,
        "unit": "solar_mass",
        "source": "science-star-types",
        "note": (
            '"When a main sequence star less than eight times the Sun\'s mass'
            ' runs out of hydrogen..."'
        ),
    },
    {
        "object": "赤色巨星",
        "property_name": "sun_becomes_red_giant_in",
        "value_numeric": 5.0e9,
        "unit": "years",
        "source": "science-star-types",
        "note": '"The Sun will become a red giant in about 5 billion years."',
    },
    {
        "object": "赤色巨星",
        "property_name": "sun_red_giant_phase_duration",
        "value_numeric": 1.0e9,
        "unit": "years",
        "source": "imagine-white-dwarfs",
        "note": (
            '"The Sun will only spend one billion years as a red giant, as'
            ' opposed to the nearly 10 billion it spent busily burning'
            ' hydrogen."'
        ),
    },
    # --- クエーサー ---
    {
        "object": "クエーサー",
        "property_name": "luminosity_vs_milky_way",
        "value_text": "between 10 to 100,000 times that of our Milky Way galaxy",
        "unit": None,
        "source": "science-hubble-quasars",
        "note": (
            '"Quasars have been found with luminosities between 10 to 100,000'
            ' times that of our Milky Way galaxy, generated from an area just'
            ' a few light-days to a few light-years across."'
        ),
    },
    {
        "object": "クエーサー",
        "property_name": "emitting_region_size",
        "value_text": "a few light-days to a few light-years across",
        "unit": None,
        "source": "science-hubble-quasars",
        "note": (
            '"Quasars have been found with luminosities between 10 to 100,000'
            ' times that of our Milky Way galaxy, generated from an area just'
            ' a few light-days to a few light-years across."'
        ),
    },
    {
        "object": "クエーサー",
        "property_name": "luminosity_vs_galaxy",
        "value_text": "100 to 1,000 times as much light as an entire galaxy",
        "unit": None,
        "source": "science-hubble-quasars",
        "note": (
            "\"Though they aren't much bigger than Earth's solar system, they"
            ' emit 100 to 1,000 times as much light as an entire galaxy."'
        ),
    },
    {
        "object": "クエーサー",
        "property_name": "size_comparison",
        "value_text": "not much bigger than Earth's solar system",
        "unit": None,
        "source": "science-hubble-quasars",
        "note": (
            "\"Though they aren't much bigger than Earth's solar system, they"
            ' emit 100 to 1,000 times as much light as an entire galaxy."'
        ),
    },
    {
        "object": "クエーサー",
        "property_name": "nearest_distance",
        "value_text": "hundreds of millions of light-years away",
        "unit": "light_year",
        "source": "science-hubble-quasars",
        "note": (
            '"The closest quasars to Earth are hundreds of millions of'
            ' light-years away."'
        ),
    },
    {
        "object": "クエーサー",
        "property_name": "brightest_example_luminosity",
        "value_numeric": 6.0e14,
        "unit": "solar_luminosity",
        "source": "science-hubble-quasars",
        "note": (
            "\"The quasar's brightness is equivalent to about 600 trillion"
            ' Suns and the supermassive black hole powering it is several'
            ' hundred million times as massive as our Sun"'
        ),
    },
    {
        "object": "クエーサー",
        "property_name": "brightest_example_black_hole_mass",
        "value_text": "several hundred million times as massive as our Sun",
        "unit": "solar_mass",
        "source": "science-hubble-quasars",
        "note": (
            "\"The quasar's brightness is equivalent to about 600 trillion"
            ' Suns and the supermassive black hole powering it is several'
            ' hundred million times as massive as our Sun"'
        ),
    },
]

# RAG 用チャンク（要点保持の日本語要約。逐語転載は最小限）。
# ページ間の食い違いは science.nasa.gov の記述を優先している（ADR-0003 / 上記方針）
DOCUMENTS: list[dict[str, str]] = [
    {
        "source": "science-black-holes",
        "content": (
            "ブラックホールのスケール感: 観測された最大のブラックホール TON 618 は"
            "太陽の 660 億倍の質量を持つ。最も軽い既知のブラックホールは太陽の "
            "3.8 倍。天の川銀河の中心にはいて座 A*（太陽の 400 万倍の質量）がある。"
            "既知で最も近いものは Gaia BH1 で約 1,500 光年先、最も遠いものは "
            "QSO J0313-1806 銀河の中心で約 130 億光年先にある。最も速く自転する "
            "GRS 1915+105 は毎秒 1,000 回転を超える。"
        ),
    },
    {
        "source": "imagine-black-holes",
        "content": (
            "ブラックホールの成り立ちのスケール感: 地球（脱出速度 11.2 km/s）を"
            "半径 9 mm の球に押し込むと脱出速度が光速になる。太陽の質量なら半径"
            "約 3 km。恒星質量ブラックホールは太陽の約 5〜20 倍、超大質量ブラック"
            "ホールは太陽の数百万〜数十億倍の質量を持つ。"
        ),
    },
    {
        "source": "science-neutron-stars",
        "content": (
            "中性子星のスケール感: 太陽の最大 2 倍の質量が都市サイズの体積に"
            "詰まっている。角砂糖 1 個分の物質が地球上で約 1 兆 kg（10 億トン）に"
            "相当する密度。太陽のおおよそ 7〜19 倍の質量の星が一生を終えると"
            "中性子星になり、20 倍を超えるとブラックホールになる。最速の"
            "パルサー PSR J1748-2446ad は毎分 43,000 回転する。磁場は地球の"
            "数十億〜数兆倍に達する。"
        ),
    },
    {
        "source": "imagine-neutron-stars",
        "content": (
            "中性子星の大きさと密度: 直径は約 20 km（12.5 マイル）で、地球の"
            "約 50 万倍の質量がその球に詰まっている。典型的な中性子星の磁場は"
            "地球の数兆倍。パルサーはミリ秒〜秒の規則的な周期で放射のパルスを"
            "示す回転する中性子星である。"
        ),
    },
    {
        "source": "nasa-magnetar-eruptions",
        "content": (
            "マグネターのスケール感: マグネターは既知で最強の磁場を持つ中性子星で、"
            "典型的な中性子星の最大 1,000 倍、冷蔵庫のマグネットの最大 10 兆倍の"
            "磁場強度を持つ。2021 年時点で天の川銀河には 29 個がカタログ化されて"
            "いる。2004 年 12 月 27 日の巨大フレアは約 28,000 光年離れていたにも"
            "かかわらず地球の超高層大気に測定可能な変化を起こした。"
        ),
    },
    {
        "source": "imagine-neutron-stars",
        "content": (
            "マグネターの爆発の凄まじさ: SGR 1806-20 というマグネターは、"
            "0.1 秒の間に太陽が過去 10 万年間に放出した以上のエネルギーを"
            "放出するバーストを起こした。"
        ),
    },
    {
        "source": "science-star-types",
        "content": (
            "白色矮星のスケール感: 白色矮星はふつう地球サイズだが、質量は地球の"
            "数十万倍。ティースプーン 1 杯分の物質がピックアップトラックより重い。"
            "太陽は約 100 億年後、赤色巨星の期間を経て白色矮星になる。"
        ),
    },
    {
        "source": "imagine-white-dwarfs",
        "content": (
            "白色矮星の成り立ち: 太陽の約 8 倍未満の質量の星は白色矮星になる。"
            "典型的な白色矮星は太陽と同程度の質量で、大きさは地球よりわずかに"
            "大きい程度。生まれて間もない白色矮星の内部は 100,000 度もの高温に"
            "なりうる。"
        ),
    },
    {
        "source": "science-star-types",
        "content": (
            "褐色矮星のスケール感: 褐色矮星の質量はおおむね木星の 13〜80 倍。"
            "恒星と惑星の中間にあたる質量域である。"
        ),
    },
    {
        "source": "science-star-types",
        "content": (
            "赤色巨星のスケール感: 太陽の 8 倍未満の質量の主系列星は水素を"
            "使い果たすと赤色巨星になる。太陽は約 50 億年後に赤色巨星になる。"
        ),
    },
    {
        "source": "imagine-white-dwarfs",
        "content": (
            "赤色巨星の期間: 太陽が赤色巨星として過ごすのは 10 億年だけで、"
            "水素を燃やして過ごした約 100 億年に比べて短い。"
        ),
    },
    {
        "source": "science-hubble-quasars",
        "content": (
            "クエーサーのスケール感: クエーサーは太陽系程度の大きさしかないのに、"
            "1,000 億の星を含む銀河全体の 100〜1,000 倍の光を放つ。光度は天の川"
            "銀河の 10〜100,000 倍で、放射領域は数光日〜数光年程度。地球に最も"
            "近いクエーサーでも数億光年離れている。ある明るいクエーサーは太陽"
            "約 600 兆個分の明るさで、それを駆動する超大質量ブラックホールは"
            "太陽の数億倍の質量を持つ。"
        ),
    },
]
