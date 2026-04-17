"""LLM抽象インターフェイス。Claude/Ollama/Gemma 等を差し替え可能に。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str


class LLMClient(ABC):
    @abstractmethod
    def respond(
        self,
        history: list[LLMMessage],
        system: str | None = None,
    ) -> str:
        """history の末尾がユーザー発話。応答テキストを1本返す。"""
