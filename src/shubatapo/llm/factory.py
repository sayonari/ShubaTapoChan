"""設定に応じて LLM バックエンドを切り替えるファクトリ。"""
from __future__ import annotations

import os

from shubatapo.config import Config
from shubatapo.llm.base import LLMClient


def make_llm_client(cfg: Config) -> LLMClient:
    """環境変数 SHUBATAPO_LLM_BACKEND で切り替え。

    - "api" (既定): ANTHROPIC_API_KEY/CLAUDE_API_KEY で従量課金（ClaudeClient、Haiku既定）
    - "code": Claude Agent SDK で Max プラン枠を消費（ClaudeCodeClient、Sonnet既定）

    環境変数 SHUBATAPO_LLM_MODEL があれば model を上書き。
    """
    backend = os.getenv("SHUBATAPO_LLM_BACKEND", "api").lower()
    override_model = os.getenv("SHUBATAPO_LLM_MODEL")

    if backend == "code":
        from shubatapo.llm.claude_code_client import ClaudeCodeClient, DEFAULT_MODEL
        return ClaudeCodeClient(model=override_model or DEFAULT_MODEL)

    if backend == "api":
        from shubatapo.llm.claude_client import ClaudeClient, DEFAULT_MODEL
        return ClaudeClient(
            api_key=cfg.anthropic_api_key,
            model=override_model or DEFAULT_MODEL,
        )

    raise ValueError(f"未知のバックエンド: {backend} (api または code を指定)")
