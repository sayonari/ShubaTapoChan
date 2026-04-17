"""TTS抽象インターフェイス。Subaru_TTS完成後に差し替えやすくするため。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TTSResult:
    wav_bytes: bytes   # RIFF/WAV バイト列
    sample_rate: int   # 48000 (Subaru_TTS) / 8000 (TAPO出力用にresample後) など
    channels: int      # 通常 1
    duration_sec: float


class TTSClient(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> TTSResult: ...
