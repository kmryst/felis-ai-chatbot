"""byte 分断耐性の検証（ADR-0028 決定 8）。

任意の byte 境界で分断された SSE stream から無分割時と同一の event 列を
復元できることを、共有 fixture の分断パターン試験データ
（docs/contracts/chat-sse/fixtures/byte-split-patterns.json）と網羅分割で
検証する。分断点には UTF-8 マルチバイト文字の途中・`data:` プレフィクスの
途中・event 区切りの空行の直前後を含む（決定 8 の明示要件）。

対象は upstream 方向（raw_sse を SSEStreamParser で読む = backend transport の
復元経路）。downstream 方向（wire_sse）も同じ parser 実装で分断非依存性を
確認する（frontend parser は同じ fixture を自身の実装で読む）。
"""

import json

import pytest

from app.llm.streaming import SSEStreamParser
from sse_test_helpers import load_fixture

PATTERNS = load_fixture("byte-split-patterns")
SERIES_1 = load_fixture("series-1-normal")


def _parse_with_fragments(fragments: list[bytes]) -> list[str]:
    parser = SSEStreamParser()
    payloads: list[str] = []
    for fragment in fragments:
        payloads.extend(parser.feed(fragment))
    return payloads


def _unsplit_payloads(text: str) -> list[str]:
    return _parse_with_fragments([text.encode("utf-8")])


def _target_text(pattern: dict) -> str:
    fixture = load_fixture(pattern["series"])
    return fixture[pattern["target"]]


@pytest.mark.parametrize(
    "pattern",
    PATTERNS["single_split_patterns"],
    ids=[p["name"] for p in PATTERNS["single_split_patterns"]],
)
def test_named_split_points_do_not_change_payloads(pattern: dict):
    """fixture の分断パターン（マルチバイト途中・プレフィクス途中・空行の
    直前後）で 2 分割しても、無分割時と同一の payload 列になる。"""
    text = _target_text(pattern)
    data = text.encode("utf-8")
    offset = pattern["split_byte_offset"]
    assert 0 < offset < len(data)
    payloads = _parse_with_fragments([data[:offset], data[offset:]])
    assert payloads == _unsplit_payloads(text)


@pytest.mark.parametrize(
    "pattern",
    PATTERNS["chunk_size_patterns"],
    ids=[p["name"] for p in PATTERNS["chunk_size_patterns"]],
)
@pytest.mark.parametrize("target", ["raw_sse", "wire_sse"])
def test_fixed_size_fragments_do_not_change_payloads(
    pattern: dict, target: str
):
    """stream 全体を固定長（1 byte / 3 byte）の断片に刻んでも同一の payload 列。

    1 byte 刻みはすべての分断位置（全マルチバイト途中・全プレフィクス途中・
    全空行前後）を同時に踏む網羅ケースになる。"""
    text = SERIES_1[target]
    data = text.encode("utf-8")
    size = pattern["chunk_size"]
    fragments = [data[i : i + size] for i in range(0, len(data), size)]
    assert _parse_with_fragments(fragments) == _unsplit_payloads(text)


@pytest.mark.parametrize("target", ["raw_sse", "wire_sse"])
def test_every_two_part_split_yields_identical_payloads(target: str):
    """系列 1 の stream を全 byte 位置で 2 分割し、すべて無分割時と一致する。"""
    text = SERIES_1[target]
    data = text.encode("utf-8")
    expected = _unsplit_payloads(text)
    for offset in range(1, len(data)):
        payloads = _parse_with_fragments([data[:offset], data[offset:]])
        assert payloads == expected, f"offset {offset} で payload 列が変わった"


def test_split_payloads_reconstruct_identical_json_chunks():
    """分断後の payload は decode だけでなく JSON としても同一に復元される
    （マルチバイト文字の破損が JSON parse まで到達しないこと）。"""
    text = SERIES_1["raw_sse"]
    data = text.encode("utf-8")
    expected = [
        json.loads(p) for p in _unsplit_payloads(text) if p != "[DONE]"
    ]
    fragments = [data[i : i + 1] for i in range(len(data))]
    actual = [
        json.loads(p)
        for p in _parse_with_fragments(fragments)
        if p != "[DONE]"
    ]
    assert actual == expected


# --- parser 単体の仕様（WHATWG "the event stream format" の最小実装範囲） -----


def test_parser_strips_cr_and_optional_space():
    """CRLF 行末と `data:` 直後の空白 1 個の扱い（WHATWG 準拠）。"""
    parser = SSEStreamParser()
    payloads = parser.feed(b'data: {"a":1}\r\n\r\ndata:{"b":2}\n\n')
    assert payloads == ['{"a":1}', '{"b":2}']


def test_parser_ignores_non_data_fields_and_comments():
    """`event:` / `id:` / comment 行は読み飛ばす（前方互換）。

    実測では `data:` 行のみが届いた（observations.md §5-4）が、SSE 仕様上
    現れ得る field で error 終端しないことを確認する。"""
    parser = SSEStreamParser()
    payloads = parser.feed(
        b'event: message\nid: 1\n: comment\ndata: {"a":1}\n\n'
    )
    assert payloads == ['{"a":1}']


def test_parser_joins_multiple_data_lines_with_lf():
    """複数 `data:` 行は LF で連結する（WHATWG 準拠）。"""
    parser = SSEStreamParser()
    payloads = parser.feed(b"data: line1\ndata: line2\n\n")
    assert payloads == ["line1\nline2"]


def test_parser_discards_incomplete_trailing_event():
    """event 区切りの空行なしに stream が終わった場合、未完成の event は
    確定しない（終端判定は上位の raw_stream_to_deltas が行う）。"""
    parser = SSEStreamParser()
    payloads = parser.feed(b'data: {"a":1}\n\ndata: incomplete')
    assert payloads == ['{"a":1}']
