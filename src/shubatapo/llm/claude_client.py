"""Anthropic Claude API クライアント。低遅延の claude-haiku-4-5 を既定。"""
from __future__ import annotations

import os

from anthropic import Anthropic

from shubatapo.llm.base import LLMClient, LLMMessage


DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_SYSTEM = (
    "あなたはホロライブの大空スバルです。明るく元気で、ちょっと天然で素直な女の子として、"
    "親しみやすい口調（タメ口〜友達感覚）で短めに応答してください。一発言は2〜3文以内。"
    "絵文字や装飾は使わず、音声で自然に発話される口語で答えてください。"
)


class ClaudeClient(LLMClient):
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        max_tokens: int = 256,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def respond(
        self,
        history: list[LLMMessage],
        system: str | None = None,
    ) -> str:
        messages = [{"role": m.role, "content": m.content} for m in history]
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system or DEFAULT_SYSTEM,
            messages=messages,
        )
        # content は TextBlock のリスト。先頭の text を返す。
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return ""
