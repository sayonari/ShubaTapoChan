"""Claude Agent SDK 経由で Max プランの利用枠で Claude を使う LLM クライアント。

- 追加 API 課金なし（Max プラン範囲内）
- Sonnet 4.6 / Opus 4.7 が使える
- ツール実行は無効化（音声対話のみ、ファイル操作等は不要）

認証（GPU PC初回のみ）:
    1. 手元のMac等ブラウザのある環境で:   claude setup-token
    2. 表示されたトークンを GPU PC の ~/.bashrc 等に:
           export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-..."
    3. ANTHROPIC_API_KEY は絶対に設定しない（設定するとAPI課金に切替わる）
"""
from __future__ import annotations

import asyncio
import os

from shubatapo.llm.base import LLMClient, LLMMessage


DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_SYSTEM = (
    "あなたはホロライブの大空スバルです。明るく元気で、ちょっと天然で素直な女の子として、"
    "親しみやすい口調（タメ口〜友達感覚）で短めに応答してください。一発言は2〜3文以内。"
    "絵文字や装飾は使わず、音声で自然に発話される口語で答えてください。"
)


def _format_history(history: list[LLMMessage]) -> str:
    """query() は 1 プロンプト文字列。履歴を混ぜて渡す。

    末尾のユーザ発話を最終 prompt として扱い、それ以前は文脈として付ける。
    """
    if not history:
        return ""
    # 末尾が user 発話のはず
    last = history[-1]
    if last.role != "user":
        raise ValueError("history の末尾は role='user' である必要があります")

    if len(history) == 1:
        return last.content

    prior = "\n".join(
        f"{'ユーザ' if m.role == 'user' else 'スバル'}: {m.content}"
        for m in history[:-1]
    )
    return (
        "以下はこれまでの会話履歴です。最後のユーザ発話に短く自然に応答してください。\n"
        f"---\n{prior}\n---\n"
        f"ユーザ: {last.content}"
    )


class ClaudeCodeClient(LLMClient):
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_turns: int = 1,
    ):
        self.model = model
        self.max_turns = max_turns

        # ANTHROPIC_API_KEY が設定されているとAPI課金に切り替わるので警告
        if os.getenv("ANTHROPIC_API_KEY"):
            print(
                "[ClaudeCodeClient] 警告: ANTHROPIC_API_KEY が設定されています。"
                "Maxプラン枠で使いたい場合は unset してください。"
            )
        if not os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
            print(
                "[ClaudeCodeClient] 警告: CLAUDE_CODE_OAUTH_TOKEN が未設定です。"
                "`claude setup-token` で取得して環境変数に設定してください。"
            )

        # 遅延 import（Mac で import が重いのと、依存未インストールの環境でも config.py が読めるように）
        from claude_agent_sdk import ClaudeAgentOptions
        self._options = ClaudeAgentOptions(
            system_prompt=DEFAULT_SYSTEM,
            model=model,
            allowed_tools=[],     # ツール使用を全面禁止
            max_turns=max_turns,
            permission_mode="bypassPermissions",
        )

    def respond(
        self,
        history: list[LLMMessage],
        system: str | None = None,
    ) -> str:
        # system 上書き対応
        if system is not None:
            from claude_agent_sdk import ClaudeAgentOptions
            opts = ClaudeAgentOptions(
                system_prompt=system,
                model=self.model,
                allowed_tools=[],
                max_turns=self.max_turns,
                permission_mode="bypassPermissions",
            )
        else:
            opts = self._options

        prompt = _format_history(history)
        return asyncio.run(self._query_once(prompt, opts))

    @staticmethod
    async def _query_once(prompt: str, options) -> str:
        from claude_agent_sdk import AssistantMessage, TextBlock, query
        pieces: list[str] = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        pieces.append(block.text)
        return "".join(pieces).strip()
