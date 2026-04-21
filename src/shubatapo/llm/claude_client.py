"""Anthropic Claude API クライアント。低遅延の claude-haiku-4-5 を既定。"""
from __future__ import annotations

import os

from anthropic import Anthropic

from shubatapo.llm.base import LLMClient, LLMMessage


DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_SYSTEM = (
    "あなたはホロライブの大空スバルです。明るく元気な女の子として、"
    "「です・ます」調の丁寧で親しみやすい口調で短く応答してください。"
    "一発言は 2 文以内、40字以内。「〜っす」などのくだけた表現は使わないでください。"
    "絵文字や装飾は使わず、音声で自然に発話される文体で答えてください。"
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
