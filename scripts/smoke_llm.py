"""Claude API クライアントの smoke test。

環境変数 ANTHROPIC_API_KEY が必要。
使い方:
    python scripts/smoke_llm.py "ユーザー発話"
"""
from __future__ import annotations

import sys

from shubatapo.config import load_config
from shubatapo.llm import ClaudeClient, LLMMessage


def main() -> int:
    cfg = load_config()  # .env を読み込む
    user_text = sys.argv[1] if len(sys.argv) > 1 else "おはよう！今日の気分はどう？"
    client = ClaudeClient(api_key=cfg.anthropic_api_key)
    print(f"[smoke_llm] user: {user_text}")
    reply = client.respond(history=[LLMMessage(role="user", content=user_text)])
    print(f"[smoke_llm] subaru: {reply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
