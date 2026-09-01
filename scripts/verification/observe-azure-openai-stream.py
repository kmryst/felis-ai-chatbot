#!/usr/bin/env python3
"""Azure OpenAI chat completions stream の raw chunk 観測スクリプト（Issue #184）。

使い捨ての観測スクリプトである。アプリケーションコードからは import されず、
CI からも呼ばれない（ADR-0004: CI から実 LLM を呼ばない）。ADR-0028 決定 5 の
表の前提を実測で確認するためだけに存在し、目的を果たしたら削除してよい。

- SDK を使わず、標準ライブラリ（http.client）で SSE の raw バイト列を読む。
  chunk の「形状」が論点のため、パース済みオブジェクトでは足りない
- 受信した SSE の各行を、到達順・到達時刻（リクエスト送信からの相対 ms）つきで
  JSONL に保存する。recv 単位の byte 到達境界も記録する
- API キーは .env から読むだけで、出力には一切含めない

実行方法（リポジトリルート = .env のあるディレクトリで）:

    python3 scripts/verification/observe-azure-openai-stream.py <出力ディレクトリ>

.env に AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_CHAT_DEPLOYMENT
が必要。api-version は Issue #184 の指定どおり 2024-10-21 に固定する。
"""

import http.client
import json
import pathlib
import sys
import time
import urllib.parse

API_VERSION = "2024-10-21"  # Issue #184 指定。.env の値ではなくこの値を明示する

RUNS = [
    {
        "run_id": "run1-normal",
        "purpose": "通常応答（短い応答での基本系列の観測）",
        "messages": [
            {
                "role": "user",
                "content": (
                    "気象庁の発表する「注意報」と「警報」の違いを2文で説明してください。"
                ),
            }
        ],
        "extra": {},
    },
    {
        "run_id": "run2-filter-candidate",
        "purpose": (
            "content filter が発火し得るプロンプト"
            "（明らかに架空の物語の戦闘描写。filter の回避・迂回は試みない）"
        ),
        "messages": [
            {
                "role": "user",
                "content": (
                    "架空のファンタジー小説の一場面として、勇者がドラゴンと剣で戦い、"
                    "切り合いの末に討ち倒すまでの戦闘シーンを、負傷や流血の様子も含めて"
                    "具体的に描写してください。"
                ),
            }
        ],
        "extra": {},
    },
    {
        "run_id": "run3-long",
        "purpose": "長い応答（多数の chunk と長時間 stream の観測）",
        "messages": [
            {
                "role": "user",
                "content": (
                    "日本の四季（春・夏・秋・冬）それぞれの気象の特徴を、"
                    "季節ごとに見出しを付けて詳しく説明してください。"
                    "全体で1500字程度でお願いします。"
                ),
            }
        ],
        "extra": {},
    },
    {
        "run_id": "run4-usage-optin",
        "purpose": "stream_options.include_usage 明示 opt-in 時の usage chunk の到達位置",
        "messages": [
            {
                "role": "user",
                "content": "「梅雨」とは何ですか。1文で説明してください。",
            }
        ],
        "extra": {"stream_options": {"include_usage": True}},
    },
]


REQUIRED_ENV_KEYS = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
)


def load_env(path: pathlib.Path) -> dict:
    """`.env` を読み、必須キーの存在を検証する。

    ファイル不在・キー欠落は stack trace ではなく、必要なキー名だけを示して
    即終了する（値は表示しない。API キーの値を出力しないため）。
    """
    if not path.is_file():
        print(f"エラー: .env が見つかりません: {path}")
        print("リポジトリルート（.env のあるディレクトリ）で実行してください。")
        print(f"必須キー: {', '.join(REQUIRED_ENV_KEYS)}")
        sys.exit(1)
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    missing = [k for k in REQUIRED_ENV_KEYS if not env.get(k)]
    if missing:
        print(f"エラー: .env に必須キーが不足しています: {', '.join(missing)}")
        sys.exit(1)
    return env


def observe(env: dict, run: dict, out_dir: pathlib.Path) -> None:
    endpoint = urllib.parse.urlparse(env["AZURE_OPENAI_ENDPOINT"])
    deployment = env["AZURE_OPENAI_CHAT_DEPLOYMENT"]
    path = (
        f"/openai/deployments/{deployment}/chat/completions"
        f"?api-version={API_VERSION}"
    )
    body = {"messages": run["messages"], "stream": True, **run["extra"]}

    out_path = out_dir / f"{run['run_id']}.jsonl"
    records = []

    conn = http.client.HTTPSConnection(endpoint.hostname, timeout=120)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    t0 = time.monotonic()
    conn.request(
        "POST",
        path,
        body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "api-key": env["AZURE_OPENAI_API_KEY"],
        },
    )
    resp = conn.getresponse()
    t_headers = (time.monotonic() - t0) * 1000

    # api-key 以外のレスポンスヘッダは観測対象（region・request id 等）
    headers = {k.lower(): v for k, v in resp.getheaders()}
    records.append(
        {
            "type": "meta",
            "run_id": run["run_id"],
            "purpose": run["purpose"],
            "started_utc": started_utc,
            "api_version": API_VERSION,
            "deployment": deployment,
            "request_body": body,
            "status": resp.status,
            "t_headers_ms": round(t_headers, 1),
            "response_headers": headers,
        }
    )

    # raw バイト列を recv 単位で読み、SSE の行へ分解する。
    # http.client は chunked transfer encoding を解いた payload バイト列を返す
    buf = b""
    line_index = 0
    while True:
        chunk = resp.read1(65536)
        t_ms = round((time.monotonic() - t0) * 1000, 1)
        if not chunk:
            records.append({"type": "eof", "t_ms": t_ms})
            break
        records.append({"type": "recv", "t_ms": t_ms, "bytes": len(chunk)})
        buf += chunk
        while b"\n" in buf:
            raw_line, _, buf = buf.partition(b"\n")
            records.append(
                {
                    "type": "line",
                    "i": line_index,
                    "t_ms": t_ms,
                    "line": raw_line.decode("utf-8", errors="replace"),
                }
            )
            line_index += 1
    if buf:
        records.append(
            {
                "type": "trailing-bytes-without-newline",
                "line": buf.decode("utf-8", errors="replace"),
            }
        )
    conn.close()

    with out_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{run['run_id']}: status={resp.status} lines={line_index} -> {out_path}")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    out_dir = pathlib.Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    env = load_env(pathlib.Path.cwd() / ".env")
    for run in RUNS:
        observe(env, run, out_dir)
        time.sleep(2)  # rate limit への配慮


if __name__ == "__main__":
    main()
