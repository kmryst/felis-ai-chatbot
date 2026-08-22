"""テスト共通フィクスチャ。

- 実 LLM・外部 API は一切呼ばない（ADR-0004）
- DB テスト（@pytest.mark.db）は TEST_DATABASE_URL を使う。未設定なら skip
- 開発用 DB（DATABASE_URL）とテスト用 DB は分離する。テストはテスト用 DB の
  スキーマを downgrade base → upgrade head で作り直すため、開発 DB を指すと
  データが消える。conftest はこの取り違えを防ぐため両者が同一なら fail する
"""

import os

import psycopg
import pytest

# app.main は import 時に Settings.from_env() を評価するため、
# テストでは DATABASE_URL が未設定でも import できるようダミーを与える。
# （到達性は /readyz のテストでのみ問題になり、そこでは意図的に差し替える）
os.environ.setdefault(
    "DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test_dummy"
)
# /chat 保護（#107）: テストでは既知のダミーキーを与える（実キーではない）。
# 既存の /chat テストは test_app.py の client フィクスチャが既定ヘッダで送る
os.environ.setdefault("CHAT_API_KEY", "test-chat-key-local")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _require_test_db() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL が未設定のため DB テストを skip")
    if TEST_DATABASE_URL == os.environ.get("DATABASE_URL"):
        pytest.fail(
            "TEST_DATABASE_URL が DATABASE_URL と同一です。"
            "テストはスキーマを作り直すため、開発用 DB とは分離してください"
        )
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """テスト用 DB を用意し、マイグレーションを空から適用して URL を返す。"""
    url = _require_test_db()

    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(
        os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    )
    # migrations/env.py は環境変数 DATABASE_URL を読むため、一時的に差し替える
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")
    finally:
        if original is None:
            del os.environ["DATABASE_URL"]
        else:
            os.environ["DATABASE_URL"] = original
    return url


@pytest.fixture()
def db_conn(test_db_url: str):
    """テスト用 DB への同期接続。テスト毎にデータを空にして渡す。"""
    with psycopg.connect(test_db_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE documents, object_properties, objects, sources"
                " RESTART IDENTITY CASCADE"
            )
        conn.commit()
        yield conn
