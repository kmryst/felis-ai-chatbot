"""Alembic 実行環境。

接続先は環境変数 DATABASE_URL から読む（alembic.ini にはハードコードしない）。
未設定なら即 fail する。secret を含むためログに URL を出さないこと。
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# マイグレーションは raw SQL（op.execute）で書くため autogenerate は使わない
target_metadata = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("必須環境変数が未設定です: DATABASE_URL")
    # SQLAlchemy に psycopg (v3) ドライバを明示する
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _connect_args() -> dict[str, str]:
    """psycopg に追加で渡す接続引数（DB_AUTH_MODE=managed-identity 時の password）。

    backend / Job と同じ環境変数（DB_AUTH_MODE / AZURE_CLIENT_ID）を読み、Entra の
    アクセストークンを password として渡す（Issue #275。ADR-0031）。password モード
    （既定）では何も足さず、DATABASE_URL のパスワードで接続する。keyword の password は
    URL 内の値より優先される（psycopg の conninfo と keyword のマージ規則）。
    マイグレーション 1 回は数秒〜数分で、取得直後のトークンの有効期限内に収まる。
    """
    mode = os.environ.get("DB_AUTH_MODE", "password")
    if mode == "password":
        return {}
    if mode != "managed-identity":
        raise RuntimeError(
            "環境変数 DB_AUTH_MODE の値が不正です"
            "（password か managed-identity を指定してください）"
        )
    client_id = os.environ.get("AZURE_CLIENT_ID")
    if not client_id:
        raise RuntimeError("必須環境変数が未設定です: AZURE_CLIENT_ID")
    # prepend_sys_path = .（alembic.ini）により backend/ 直下の app パッケージが import できる
    from app.entra_auth import DB_TOKEN_SCOPE, ManagedIdentityTokenProvider

    return {"password": ManagedIdentityTokenProvider(client_id).get_token(DB_TOKEN_SCOPE)}


# set_main_option の値は ConfigParser を通り、pyformat 補間（%(name)s）が解釈される。
# Azure に渡す DSN はパスワードの URL エンコード等で生の `%` を含むため、そのまま渡すと
# DB 接続の**前**に `ValueError: invalid interpolation syntax` で落ちる（private access の
# 疎通不良と誤診しやすい）。ローカル用 DATABASE_URL には `%` が無いため、ローカルの
# alembic 実行ではこの問題を踏まない。
# 対処は公式ドキュメントどおり `%` → `%%` のエスケープを選んだ（ConfigParser を迂回する
# 独自経路より、offline（get_main_option）/ online（get_section → engine_from_config）の
# 両読み出しで ConfigParser が `%%` を `%` に戻すことに乗る方が env.py の構造を変えずに済む。
# 両経路とも元の DSN に戻ることは backend/tests/test_migrations_env.py で回帰テスト済み）。
# 出典（Alembic 公式 Config.set_main_option。https://alembic.sqlalchemy.org/en/latest/api/config.html ）:
#   "Note that this value is passed to ConfigParser.set, which supports variable
#    interpolation using pyformat (e.g. %(some_value)s). A raw percent sign not part of
#    an interpolation symbol must therefore be escaped, e.g. %%."
config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=_connect_args(),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
