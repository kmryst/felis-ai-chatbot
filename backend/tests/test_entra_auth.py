"""Microsoft Entra 認証（managed identity）への切替のユニットテスト（Issue #275。ADR-0031）。

実際のトークン取得（IMDS / Container Apps の identity endpoint）・DB への Entra ログイン・
Azure OpenAI のロール伝播はここでは検証できない（実測は docs/verification/entra-auth/）。
ここで固定するのは次の契約:

- 認証モードの環境変数の解釈（既定は password / api-key で挙動不変。候補外は即 fail。
  managed-identity なら AZURE_CLIENT_ID 必須。api-key モードでなければ API キーは不要）
- DB 接続: provider があれば取得したトークンが psycopg の password に渡り、無ければ渡らない
- Azure OpenAI transport: bearer provider があれば `Authorization: Bearer` のみ、
  無ければ `api-key` のみを送る。両方 / どちらも無しは組み立て時に弾く
- serving と ingest CLI が共有する組み立て規則（app.credentials）
- alembic env.py の online 経路が managed-identity 時に password を connect_args で渡す
- ops 用 CLI（python -m app.entra_auth）
"""

import asyncio
import dataclasses
import json
import os
from types import SimpleNamespace

import httpx
import pytest

from app import credentials, entra_auth
from app import db as db_module
from app.config import InvalidEnvError, MissingEnvError, Settings
from app.entra_auth import (
    COGNITIVE_SERVICES_TOKEN_SCOPE,
    DB_TOKEN_SCOPE,
    ManagedIdentityTokenProvider,
)
from app.llm.client import AzureOpenAIConfig, AzureOpenAITransport

FAKE_TOKEN = "fake-token-not-real"


class _FakeCredential:
    """azure-identity の credential の代役。要求されたスコープを記録する。"""

    def __init__(self, token: str = FAKE_TOKEN) -> None:
        self.token = token
        self.scopes: list[str] = []

    def get_token(self, *scopes: str):
        self.scopes.extend(scopes)
        return SimpleNamespace(token=self.token, expires_on=0)


def _fake_identity() -> tuple[ManagedIdentityTokenProvider, _FakeCredential]:
    credential = _FakeCredential()
    return ManagedIdentityTokenProvider("client-id", credential=credential), credential


def _patch_azure_identity(monkeypatch, credential: _FakeCredential) -> None:
    """遅延 import される azure.identity.ManagedIdentityCredential を差し替える。"""
    import azure.identity

    def fake_ctor(*, client_id: str):
        credential.client_id = client_id
        return credential

    monkeypatch.setattr(azure.identity, "ManagedIdentityCredential", fake_ctor)


@pytest.fixture()
def base_env(monkeypatch):
    """Settings.from_env() に必要な最小の環境。認証モードは既定に戻す。"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x")
    for name in (
        "DB_AUTH_MODE",
        "AZURE_OPENAI_AUTH_MODE",
        "AZURE_CLIENT_ID",
        "LLM_PROVIDER",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


# --- 環境変数の解釈（config.py） ------------------------------------------------


def test_defaults_are_password_and_api_key(base_env):
    """既定は現行どおり（password / api-key）。client ID は不要。"""
    settings = Settings.from_env()
    assert settings.db_auth_mode == "password"
    assert settings.azure_openai_auth_mode == "api-key"
    assert settings.azure_client_id == ""


@pytest.mark.parametrize(
    "name", ["DB_AUTH_MODE", "AZURE_OPENAI_AUTH_MODE"]
)
def test_unknown_auth_mode_fails_fast(base_env, monkeypatch, name):
    monkeypatch.setenv(name, "something-else")
    with pytest.raises(InvalidEnvError) as excinfo:
        Settings.from_env()
    assert excinfo.value.name == name


def test_db_managed_identity_requires_client_id(base_env, monkeypatch):
    monkeypatch.setenv("DB_AUTH_MODE", "managed-identity")
    with pytest.raises(MissingEnvError) as excinfo:
        Settings.from_env()
    assert excinfo.value.names == ["AZURE_CLIENT_ID"]


def test_azure_openai_managed_identity_needs_client_id_not_api_key(
    base_env, monkeypatch
):
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_AUTH_MODE", "managed-identity")
    with pytest.raises(MissingEnvError) as excinfo:
        Settings.from_env()
    assert excinfo.value.names == ["AZURE_CLIENT_ID"]

    monkeypatch.setenv("AZURE_CLIENT_ID", "client-id")
    settings = Settings.from_env()
    assert settings.azure_openai_api_key == ""


def test_azure_openai_api_key_mode_still_requires_key(base_env, monkeypatch):
    """api-key モード（既定）では従来どおり API キーが必須。"""
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    with pytest.raises(MissingEnvError) as excinfo:
        Settings.from_env()
    assert excinfo.value.names == ["AZURE_OPENAI_API_KEY"]


def test_azure_openai_auth_mode_ignored_for_stub(base_env, monkeypatch):
    """stub のときは Azure OpenAI 側の managed-identity 指定があっても client ID は不要。"""
    monkeypatch.setenv("AZURE_OPENAI_AUTH_MODE", "managed-identity")
    settings = Settings.from_env()
    assert settings.azure_client_id == ""


# --- トークン取得（entra_auth.py） ----------------------------------------------


def test_provider_returns_token_for_scope():
    identity, credential = _fake_identity()
    assert identity.get_token(DB_TOKEN_SCOPE) == FAKE_TOKEN
    assert credential.scopes == [DB_TOKEN_SCOPE]


def test_async_provider_runs_sync_credential():
    identity, credential = _fake_identity()
    provide = identity.async_provider(COGNITIVE_SERVICES_TOKEN_SCOPE)
    assert asyncio.run(provide()) == FAKE_TOKEN
    assert credential.scopes == [COGNITIVE_SERVICES_TOKEN_SCOPE]


def test_provider_requires_client_id_when_no_credential():
    with pytest.raises(ValueError):
        ManagedIdentityTokenProvider("")


def test_provider_passes_client_id_to_managed_identity_credential(monkeypatch):
    """user-assigned identity の client ID を明示して credential を作る。"""
    credential = _FakeCredential()
    _patch_azure_identity(monkeypatch, credential)
    identity = ManagedIdentityTokenProvider("client-id-123")
    assert identity.get_token(DB_TOKEN_SCOPE) == FAKE_TOKEN
    assert credential.client_id == "client-id-123"


# --- DB 接続（db.py） ---------------------------------------------------------------


@pytest.fixture()
def capture_connect(monkeypatch):
    """psycopg.AsyncConnection.connect を差し替え、渡された kwargs を記録する。"""
    captured: dict = {}

    async def fake_connect(dsn, **kwargs):
        captured["dsn"] = dsn
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        db_module.psycopg.AsyncConnection, "connect", fake_connect
    )
    yield captured
    db_module.set_password_provider(None)


def test_connect_passes_token_as_password_when_provider_set(capture_connect):
    identity, _ = _fake_identity()
    db_module.set_password_provider(identity.async_provider(DB_TOKEN_SCOPE))
    asyncio.run(db_module.connect("postgresql://user@host/db", 2))
    assert capture_connect["password"] == FAKE_TOKEN
    assert capture_connect["connect_timeout"] == 2


def test_connect_does_not_override_password_without_provider(capture_connect):
    db_module.set_password_provider(None)
    asyncio.run(db_module.connect("postgresql://user:pw@host/db", 2))
    assert "password" not in capture_connect


def test_connect_fetches_token_per_connection(capture_connect):
    """トークンはキャッシュせず接続のたびに provider を呼ぶ（期限管理は SDK に委ねる）。"""
    identity, credential = _fake_identity()
    db_module.set_password_provider(identity.async_provider(DB_TOKEN_SCOPE))
    asyncio.run(db_module.connect("postgresql://user@host/db", 2))
    asyncio.run(db_module.connect("postgresql://user@host/db", 2))
    assert credential.scopes == [DB_TOKEN_SCOPE, DB_TOKEN_SCOPE]


# --- Azure OpenAI transport（llm/client.py） ---------------------------------------


def _azure_config(**overrides) -> AzureOpenAIConfig:
    base = dict(
        endpoint="https://example.openai.azure.com/",
        api_key="test-key-not-real",
        api_version="2024-10-21",
        chat_deployment="chat",
        embedding_deployment="embedding",
    )
    base.update(overrides)
    return AzureOpenAIConfig(**base)


def test_config_rejects_both_or_neither_credential():
    with pytest.raises(ValueError):
        _azure_config(api_key="", bearer_token_provider=None)
    identity, _ = _fake_identity()
    with pytest.raises(ValueError):
        _azure_config(
            bearer_token_provider=identity.async_provider(
                COGNITIVE_SERVICES_TOKEN_SCOPE
            )
        )


def _transport_with(config: AzureOpenAIConfig):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    http_client = httpx.AsyncClient(
        base_url=config.endpoint.rstrip("/"),
        transport=httpx.MockTransport(handler),
    )
    return AzureOpenAITransport(config, http_client=http_client), requests


async def test_transport_sends_bearer_only_with_token_provider():
    identity, credential = _fake_identity()
    config = _azure_config(
        api_key="",
        bearer_token_provider=identity.async_provider(
            COGNITIVE_SERVICES_TOKEN_SCOPE
        ),
    )
    transport, requests = _transport_with(config)
    await transport.chat([{"role": "user", "content": "hi"}])
    request = requests[0]
    assert request.headers["authorization"] == f"Bearer {FAKE_TOKEN}"
    assert "api-key" not in request.headers
    assert credential.scopes == [COGNITIVE_SERVICES_TOKEN_SCOPE]


async def test_transport_sends_api_key_only_without_token_provider():
    transport, requests = _transport_with(_azure_config())
    await transport.chat([{"role": "user", "content": "hi"}])
    request = requests[0]
    assert request.headers["api-key"] == "test-key-not-real"
    assert "authorization" not in request.headers


async def test_transport_streaming_uses_bearer_too():
    """streaming 経路（chat_stream）も同じ認証ヘッダを使う。"""
    identity, _ = _fake_identity()
    config = _azure_config(
        api_key="",
        bearer_token_provider=identity.async_provider(
            COGNITIVE_SERVICES_TOKEN_SCOPE
        ),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = (
            "data: "
            + json.dumps({"choices": [{"delta": {"content": "ok"}}]})
            + "\n\ndata: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body.encode(), headers={"content-type": "text/event-stream"}
        )

    http_client = httpx.AsyncClient(
        base_url=config.endpoint.rstrip("/"),
        transport=httpx.MockTransport(handler),
    )
    transport = AzureOpenAITransport(config, http_client=http_client)
    async for _ in transport.chat_stream([{"role": "user", "content": "hi"}]):
        pass
    assert requests[0].headers["authorization"] == f"Bearer {FAKE_TOKEN}"
    assert "api-key" not in requests[0].headers


# --- 組み立て規則（credentials.py） ------------------------------------------------


def _settings(**overrides) -> Settings:
    os.environ["DATABASE_URL"] = "postgresql://u:p@127.0.0.1:1/x"
    base = Settings.from_env()
    return dataclasses.replace(base, **overrides)


def test_credentials_password_mode_has_no_identity():
    settings = _settings(db_auth_mode="password", llm_provider="stub")
    assert credentials.managed_identity(settings) is None
    assert credentials.sync_db_connect_kwargs(settings, None) == {}
    assert credentials.azure_openai_config(settings, None) is None


def test_credentials_managed_identity_for_db_and_openai(monkeypatch):
    credential = _FakeCredential()
    _patch_azure_identity(monkeypatch, credential)
    settings = _settings(
        db_auth_mode="managed-identity",
        azure_client_id="client-id",
        llm_provider="azure-openai",
        azure_openai_auth_mode="managed-identity",
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_api_key="",
    )
    identity = credentials.managed_identity(settings)
    assert identity is not None
    assert credentials.sync_db_connect_kwargs(settings, identity) == {
        "password": FAKE_TOKEN
    }
    config = credentials.azure_openai_config(settings, identity)
    assert config.api_key == ""
    assert asyncio.run(config.bearer_token_provider()) == FAKE_TOKEN
    assert credential.scopes == [DB_TOKEN_SCOPE, COGNITIVE_SERVICES_TOKEN_SCOPE]


def test_credentials_api_key_mode_keeps_api_key_even_with_db_identity(monkeypatch):
    """DB だけ managed-identity（段階 4）でも Azure OpenAI は api-key のまま（段階 5 まで併存）。"""
    _patch_azure_identity(monkeypatch, _FakeCredential())
    settings = _settings(
        db_auth_mode="managed-identity",
        azure_client_id="client-id",
        llm_provider="azure-openai",
        azure_openai_auth_mode="api-key",
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_api_key="test-key-not-real",
    )
    identity = credentials.managed_identity(settings)
    config = credentials.azure_openai_config(settings, identity)
    assert config.api_key == "test-key-not-real"
    assert config.bearer_token_provider is None


def test_install_db_password_provider_sets_and_clears(monkeypatch, capture_connect):
    _patch_azure_identity(monkeypatch, _FakeCredential())
    settings = _settings(db_auth_mode="managed-identity", azure_client_id="client-id")
    credentials.install_db_password_provider(
        settings, credentials.managed_identity(settings)
    )
    asyncio.run(db_module.connect("postgresql://user@host/db", 1))
    assert capture_connect["password"] == FAKE_TOKEN

    credentials.install_db_password_provider(_settings(db_auth_mode="password"), None)
    capture_connect.clear()
    asyncio.run(db_module.connect("postgresql://user:pw@host/db", 1))
    assert "password" not in capture_connect


# --- alembic env.py（migrations/env.py） --------------------------------------------


class _Captured(Exception):
    pass


def _run_alembic_online(monkeypatch) -> dict:
    """online 経路を engine 作成の直前で打ち切り、engine_from_config の引数を返す。"""
    import sqlalchemy
    from alembic import command
    from alembic.config import Config

    captured: dict = {}

    def fake_engine_from_config(configuration, prefix="sqlalchemy.", **kwargs):
        captured["url"] = configuration.get(prefix + "url")
        captured.update(kwargs)
        raise _Captured()

    monkeypatch.setattr(sqlalchemy, "engine_from_config", fake_engine_from_config)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    with pytest.raises(_Captured):
        command.upgrade(cfg, "head")
    return captured


def test_alembic_online_passes_token_as_password_in_managed_identity_mode(
    monkeypatch,
):
    credential = _FakeCredential()
    _patch_azure_identity(monkeypatch, credential)
    monkeypatch.setenv("DATABASE_URL", "postgresql://ident@host:5432/db?sslmode=require")
    monkeypatch.setenv("DB_AUTH_MODE", "managed-identity")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client-id-123")
    captured = _run_alembic_online(monkeypatch)
    assert captured["connect_args"] == {"password": FAKE_TOKEN}
    assert credential.scopes == [DB_TOKEN_SCOPE]
    assert credential.client_id == "client-id-123"


def test_alembic_online_adds_nothing_in_password_mode(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    monkeypatch.delenv("DB_AUTH_MODE", raising=False)
    captured = _run_alembic_online(monkeypatch)
    assert captured["connect_args"] == {}


def test_alembic_managed_identity_requires_client_id(monkeypatch):
    from alembic import command
    from alembic.config import Config

    monkeypatch.setenv("DATABASE_URL", "postgresql://ident@host:5432/db")
    monkeypatch.setenv("DB_AUTH_MODE", "managed-identity")
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    with pytest.raises(RuntimeError, match="AZURE_CLIENT_ID"):
        command.upgrade(cfg, "head")


# --- ops 用 CLI（python -m app.entra_auth） ---------------------------------------


def test_cli_prints_token_for_db_scope(monkeypatch, capsys):
    credential = _FakeCredential()
    _patch_azure_identity(monkeypatch, credential)
    monkeypatch.setenv("AZURE_CLIENT_ID", "client-id-123")
    assert entra_auth.main(["db"]) == 0
    assert capsys.readouterr().out == FAKE_TOKEN + "\n"
    assert credential.scopes == [DB_TOKEN_SCOPE]


def test_cli_rejects_unknown_scope_and_missing_client_id(monkeypatch, capsys):
    assert entra_auth.main(["storage"]) == 2
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    assert entra_auth.main(["openai"]) == 1
    err = capsys.readouterr().err
    assert "AZURE_CLIENT_ID" in err
    assert FAKE_TOKEN not in err
