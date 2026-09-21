"""認証方式（Settings）から DB / Azure OpenAI の資格情報の供給元を組み立てる。

backend serving（main.py）と取り込み CLI（ingest/__main__.py）が同じ規則で
組み立てるための共通モジュール（Issue #275。ADR-0031）。

- DB_AUTH_MODE=managed-identity: 接続のたびに Entra トークンを password に渡す
  （app.db の password provider に登録する）
- AZURE_OPENAI_AUTH_MODE=managed-identity: `Authorization: Bearer` で Entra トークンを送る
- 既定（password / api-key）では azure-identity を一切読み込まない
"""

from app.config import Settings
from app.db import set_password_provider
from app.entra_auth import (
    COGNITIVE_SERVICES_TOKEN_SCOPE,
    DB_TOKEN_SCOPE,
    ManagedIdentityTokenProvider,
)
from app.llm.client import AzureOpenAIConfig


def uses_db_managed_identity(settings: Settings) -> bool:
    return settings.db_auth_mode == "managed-identity"


def uses_azure_openai_managed_identity(settings: Settings) -> bool:
    return (
        settings.llm_provider == "azure-openai"
        and settings.azure_openai_auth_mode == "managed-identity"
    )


def managed_identity(settings: Settings) -> ManagedIdentityTokenProvider | None:
    """DB か Azure OpenAI のどちらかが managed-identity モードなら token provider を作る。

    client ID の非空は Settings が起動時に保証している（config.py）。
    """
    if not (
        uses_db_managed_identity(settings)
        or uses_azure_openai_managed_identity(settings)
    ):
        return None
    return ManagedIdentityTokenProvider(settings.azure_client_id)


def install_db_password_provider(
    settings: Settings, identity: ManagedIdentityTokenProvider | None
) -> None:
    """app.db の接続が使う password の供給元をプロセスに設定する。

    password モードでは None を設定し、DATABASE_URL に含まれるパスワードで接続する。
    """
    if identity is not None and uses_db_managed_identity(settings):
        set_password_provider(identity.async_provider(DB_TOKEN_SCOPE))
    else:
        set_password_provider(None)


def sync_db_connect_kwargs(
    settings: Settings, identity: ManagedIdentityTokenProvider | None
) -> dict[str, str]:
    """同期の psycopg.connect に追加で渡す引数（managed-identity 時の password）。"""
    if identity is not None and uses_db_managed_identity(settings):
        return {"password": identity.get_token(DB_TOKEN_SCOPE)}
    return {}


def azure_openai_config(
    settings: Settings, identity: ManagedIdentityTokenProvider | None
) -> AzureOpenAIConfig | None:
    """LLM_PROVIDER=azure-openai のときの transport 設定。stub なら None。"""
    if settings.llm_provider != "azure-openai":
        return None
    bearer = (
        identity.async_provider(COGNITIVE_SERVICES_TOKEN_SCOPE)
        if identity is not None and uses_azure_openai_managed_identity(settings)
        else None
    )
    return AzureOpenAIConfig(
        endpoint=settings.azure_openai_endpoint,
        api_key="" if bearer is not None else settings.azure_openai_api_key,
        bearer_token_provider=bearer,
        api_version=settings.azure_openai_api_version,
        chat_deployment=settings.azure_openai_chat_deployment,
        embedding_deployment=settings.azure_openai_embedding_deployment,
    )
