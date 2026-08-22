"""migrations/env.py の DSN 受け渡し回帰テスト（Issue #98）。

Azure に渡す DSN は URL エンコード等で `%` を含む。env.py が
`config.set_main_option("sqlalchemy.url", ...)` へ生の `%` を渡すと、値が
ConfigParser を通るため `ValueError: invalid interpolation syntax` になり、
DB 接続の前に落ちる（private access の疎通不良と誤診しやすい）。
ここでは実 DB に接続せず、offline / online 両経路で
「例外を出さないこと」「SQLAlchemy に渡る URL が元の DSN と一致すること」を検証する。

出典（Alembic 公式 Config.set_main_option）:
  "Note that this value is passed to ``ConfigParser.set``, which supports
  variable interpolation using pyformat (e.g. ``%(some_value)s``). A raw
  percent sign not part of an interpolation symbol must therefore be
  escaped, e.g. ``%%``."
  https://alembic.sqlalchemy.org/en/latest/api/config.html
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext

# パスワードを URL エンコードした現実的な DSN（`%40` = `@`）。
# `%4` は pyformat の補間記号として不正なため、エスケープ漏れがあると
# ConfigParser が ValueError を投げる
_PERCENT_DSN = (
    "postgresql://felis:p%40ssw0rd@pgsql.example.private.postgres."
    "database.azure.com:5432/felis?sslmode=require"
)
# env.py は postgresql:// を postgresql+psycopg:// に書き換えてから渡す
_EXPECTED_URL = _PERCENT_DSN.replace("postgresql://", "postgresql+psycopg://", 1)


class _Captured(Exception):
    """URL を捕捉したら DB 接続へ進む前に env.py を打ち切るための例外。"""


def _alembic_config() -> Config:
    return Config(
        os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    )


def test_offline_mode_passes_percent_dsn_unchanged(monkeypatch):
    """offline 経路（get_main_option）: `%` 入り DSN が例外なく元の値のまま渡る。"""
    monkeypatch.setenv("DATABASE_URL", _PERCENT_DSN)
    captured = {}

    def fake_configure(self, **kwargs):
        captured["url"] = kwargs.get("url")
        raise _Captured()

    monkeypatch.setattr(EnvironmentContext, "configure", fake_configure)

    with pytest.raises(_Captured):
        command.upgrade(_alembic_config(), "head", sql=True)

    assert captured["url"] == _EXPECTED_URL


def test_online_mode_passes_percent_dsn_unchanged(monkeypatch):
    """online 経路（get_section → engine_from_config）: 同上。実 DB には接続しない。"""
    monkeypatch.setenv("DATABASE_URL", _PERCENT_DSN)
    captured = {}

    import sqlalchemy

    def fake_engine_from_config(configuration, prefix="sqlalchemy.", **kwargs):
        captured["url"] = configuration.get(prefix + "url")
        raise _Captured()

    # env.py は alembic 実行のたびに exec され、その時点の
    # sqlalchemy.engine_from_config を取り込むため、ここでの差し替えが効く
    monkeypatch.setattr(
        sqlalchemy, "engine_from_config", fake_engine_from_config
    )

    with pytest.raises(_Captured):
        command.upgrade(_alembic_config(), "head")

    assert captured["url"] == _EXPECTED_URL
