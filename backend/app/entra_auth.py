"""Microsoft Entra ID のアクセストークン取得（managed identity）。

DB（PostgreSQL Flexible Server）と Azure OpenAI の両方で、パスワード / API キーの
代わりに Entra のアクセストークンを使う（Issue #275。ADR-0031）。

- トークンは Container Apps に付与した user-assigned managed identity で取得する。
  Container Apps では user-assigned identity の client ID を明示する必要がある
  （出典: https://learn.microsoft.com/en-us/azure/container-apps/managed-identity ）
- 取得は `azure-identity` の ManagedIdentityCredential に委ねる。キャッシュと
  期限前の再取得は SDK が行うため、呼び出し側は接続のたびに get_token を呼べばよい
- DB 側のスコープ: https://ossrdbms-aad.database.windows.net/.default
  （出典: https://learn.microsoft.com/en-us/azure/postgresql/security/how-to-connect-with-managed-identity ）
- Azure OpenAI 側のスコープ: https://cognitiveservices.azure.com/.default
  （出典: https://learn.microsoft.com/en-us/azure/ai-services/authentication ）
- azure-identity の get_token は同期（ブロッキング HTTP）なので、async 経路では
  asyncio.to_thread で逃がす。aiohttp を依存に足さないための選択

ops コンテナ（psql）と Job からは CLI として使う:

    PGPASSWORD="$(python -m app.entra_auth db)" psql "$DATABASE_URL"

トークンは secret として扱う。ログ・例外メッセージに値を出さないこと
（CLI の標準出力はコマンド置換で受ける前提で、端末に貼り出す用途ではない）。
"""

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Protocol

DB_TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
COGNITIVE_SERVICES_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

# CLI の引数名 → スコープ
CLI_SCOPES = {"db": DB_TOKEN_SCOPE, "openai": COGNITIVE_SERVICES_TOKEN_SCOPE}

# 呼び出しごとに現在有効なトークンを返す非同期 callable
AsyncTokenProvider = Callable[[], Awaitable[str]]


class TokenCredential(Protocol):
    """azure-identity の credential が持つ最小インターフェース（テストで差し替える）。"""

    def get_token(self, *scopes: str):
        ...


class ManagedIdentityTokenProvider:
    """user-assigned managed identity のトークンを返す（同期）。"""

    def __init__(
        self, client_id: str, credential: TokenCredential | None = None
    ) -> None:
        if not client_id and credential is None:
            raise ValueError("managed identity の client_id が空です")
        if credential is None:
            # import を遅延させ、password / api-key モードでは azure-identity を
            # 読み込まない（起動時間と依存の露出を抑える）
            from azure.identity import ManagedIdentityCredential

            credential = ManagedIdentityCredential(client_id=client_id)
        self._credential = credential

    def get_token(self, scope: str) -> str:
        return self._credential.get_token(scope).token

    def async_provider(self, scope: str) -> AsyncTokenProvider:
        """指定スコープのトークンを返す非同期 callable を作る。"""

        async def provide() -> str:
            return await asyncio.to_thread(self.get_token, scope)

        return provide


def main(argv: list[str]) -> int:
    """`python -m app.entra_auth db|openai`: トークンを標準出力に 1 行で出す。

    client ID は環境変数 AZURE_CLIENT_ID から読む（Terraform が Container Apps に
    注入する値。backend / Job と同じ変数）。
    """
    if len(argv) != 1 or argv[0] not in CLI_SCOPES:
        print(
            "使い方: python -m app.entra_auth <db|openai>", file=sys.stderr
        )
        return 2
    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    if not client_id:
        print("必須環境変数が未設定です: AZURE_CLIENT_ID", file=sys.stderr)
        return 1
    token = ManagedIdentityTokenProvider(client_id).get_token(CLI_SCOPES[argv[0]])
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
