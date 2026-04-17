"""ASR抽象インターフェイス。wav2vec2 以外のモデルにも差し替え可能に。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ASRResult:
    """ASR の1出力。

    - text: 認識テキスト
    - is_final: utterance が確定したかどうか（True なら発話単位が完結）
    - start_ts: feed 開始時点を 0.0 とした秒単位の発話開始時刻（概算）
    - end_ts: 同じく発話終了時刻（概算）
    """

    text: str
    is_final: bool
    start_ts: float
    end_ts: float


class ASRClient(ABC):
    @abstractmethod
    def feed_pcm(self, pcm_bytes: bytes) -> None:
        """16kHz mono PCM s16le を流し込む。内部でバッファに蓄積される。"""

    @abstractmethod
    def pop_results(self) -> list[ASRResult]:
        """溜まっている ASRResult をまとめて取り出す（非ブロッキング、空なら空リスト）。"""

    @abstractmethod
    def close(self) -> None:
        """終了処理。モデル解放など。"""
