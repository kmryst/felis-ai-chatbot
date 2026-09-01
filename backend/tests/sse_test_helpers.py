"""SSE テスト共通ヘルパー（共有 fixture の読み込みと parse）。

共有 fixture（docs/contracts/chat-sse/。ADR-0028 決定 9）を backend の
テストから読むための補助。frontend / synthetic verifier も同じ JSON を
読むことで契約解釈の分岐を防ぐ。
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

from app.llm.client import EMBEDDING_DIMENSIONS
from app.llm.streaming import SSEStreamParser

# リポジトリルート = backend/tests/ の 2 つ上
FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "contracts"
    / "chat-sse"
    / "fixtures"
)


def load_fixture(name: str) -> dict:
    """共有 fixture（fixtures/<name>.json）を読み込む。"""
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_raw_series_fixtures() -> list[dict]:
    """raw stream を持つ全系列 fixture（byte-split-patterns を除く）を返す。"""
    fixtures = []
    for path in sorted(FIXTURES_DIR.glob("series-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["raw_sse"] is not None:
            fixtures.append(data)
    return fixtures


def parse_wire_sse(text: str) -> list[dict]:
    """wire の SSE テキストを event 列（{"event", "data"}）へ parse する。

    テスト用の最小 parser。各 event は `event:` 行 1 本 + `data:` 行 1 本
    （決定 2）である前提で読む。
    """
    events: list[dict] = []
    for block in text.split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        assert len(lines) == 2, f"event は 2 行のはず: {lines!r}"
        assert lines[0].startswith("event: "), lines[0]
        assert lines[1].startswith("data: "), lines[1]
        events.append(
            {
                "event": lines[0][len("event: ") :],
                "data": json.loads(lines[1][len("data: ") :]),
            }
        )
    return events


def payloads_from_raw_sse(raw_sse: str) -> list[str]:
    """fixture の raw_sse を SSE data payload の列へ復元する（無分割 parse）。"""
    parser = SSEStreamParser()
    return parser.feed(raw_sse.encode("utf-8"))


class FakeRawStreamTransport:
    """fixture の raw payload 列を chat_stream で返すテスト用 transport。

    - `closed` フラグで provider stream の打ち切り（generator close の連鎖）を
      観測できる
    - embed は決定的なダミーベクトルを返す（LLMClient として組み立てるため）
    """

    def __init__(self, payloads: list[str]) -> None:
        self._payloads = payloads
        self.closed = False
        self.stream_calls = 0

    async def chat_stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        self.stream_calls += 1
        try:
            for payload in self._payloads:
                yield payload
        finally:
            self.closed = True

    async def embed(self, text: str) -> list[float]:
        return [0.1] * EMBEDDING_DIMENSIONS
