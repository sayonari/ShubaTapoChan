"""faster-whisper + webrtcvad による発話単位 ASR。

VADで発話区間を切り出してからWhisperに投げるので、スライディング窓よりシンプル
かつ高精度。TAPO の遠距離・8kHz 由来音声でも Whisper は比較的強い。
"""
from __future__ import annotations

import collections
import os
from collections import deque

import numpy as np

from shubatapo.asr.base import ASRClient, ASRResult
from shubatapo.asr.vad import VADGate


DEFAULT_MODEL_SIZE = os.environ.get("SHUBATAPO_WHISPER_MODEL", "large-v3")
DEFAULT_LANGUAGE = os.environ.get("SHUBATAPO_WHISPER_LANG", "ja")
SAMPLE_RATE = 16000

# Whisperが無音/ノイズに当てはめる定番ハルシネーション（日本語）を除外する。
# 完全一致のみでOK（部分一致だと正当な発話を捨てる可能性）。
HALLUCINATION_BLACKLIST = {
    "ご視聴ありがとうございました",
    "ご視聴ありがとうございました。",
    "ご視聴ありがとうございました!",
    "ご視聴ありがとうございました！",
    "ありがとうございました",
    "ありがとうございました。",
    "ありがとうございました!",
    "ありがとうございました！",
    "おやすみなさい",
    "おやすみなさい。",
    "バイバイ",
    "バイバイ。",
    "Thanks for watching!",
    "Thank you for watching.",
    "Thank you.",
}


class WhisperASR(ASRClient):
    def __init__(
        self,
        model_size: str = DEFAULT_MODEL_SIZE,
        language: str = DEFAULT_LANGUAGE,
        device: str = "cuda",
        compute_type: str = "float16",
        beam_size: int = 5,
        # VAD パラメータ (厳しめの既定: ノイズ誤検出を抑制)
        vad_aggressiveness: int = 3,
        silence_timeout_ms: int = 800,
        min_speech_ms: int = 600,
        # Whisper の無音判定閾値 (大きいほど silence とみなしやすい。既定0.6)
        no_speech_threshold: float = 0.6,
        # ハルシネーション除去
        block_hallucinations: bool = True,
    ):
        from faster_whisper import WhisperModel
        print(f"[WhisperASR] loading {model_size} on {device} ({compute_type}) ...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.language = language
        self.beam_size = beam_size
        self.no_speech_threshold = no_speech_threshold
        self.block_hallucinations = block_hallucinations
        print(f"[WhisperASR] model ready.")

        self._vad = VADGate(
            aggressiveness=vad_aggressiveness,
            silence_timeout_ms=silence_timeout_ms,
            min_speech_ms=min_speech_ms,
        )
        self._results: collections.deque[ASRResult] = deque()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def feed_pcm(self, pcm_bytes: bytes) -> None:
        if not pcm_bytes:
            return
        for utt in self._vad.push(pcm_bytes):
            self._transcribe(utt.pcm, utt.start_ms / 1000.0, utt.end_ms / 1000.0)

    def pop_results(self) -> list[ASRResult]:
        out = list(self._results)
        self._results.clear()
        return out

    def close(self) -> None:
        for utt in self._vad.flush():
            self._transcribe(utt.pcm, utt.start_ms / 1000.0, utt.end_ms / 1000.0)
        try:
            del self.model
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception as e:
            print(f"[WhisperASR] close warning: {e}")

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _transcribe(self, pcm: bytes, start_ts: float, end_ts: float) -> None:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,  # 前段で VAD 済
            condition_on_previous_text=False,
            no_speech_threshold=self.no_speech_threshold,
        )
        # segment 生成は lazy。一旦 list 化する間に no_speech_prob もチェック可能。
        seg_list = list(segments)
        text = "".join(s.text for s in seg_list).strip()
        if not text:
            return
        if self.block_hallucinations and text in HALLUCINATION_BLACKLIST:
            print(f"  [WhisperASR] block hallucination: {text!r}")
            return
        self._results.append(
            ASRResult(text=text, is_final=True, start_ts=start_ts, end_ts=end_ts)
        )
