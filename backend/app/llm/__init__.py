"""LLM クライアント境界。

LLM（chat / embedding）への参照はこのパッケージに閉じ込める。
他モジュールは `app.llm.client` の LLMClient 経由でのみ LLM を利用すること。
"""
