"""ASR clients."""
from shubatapo.asr.base import ASRClient, ASRResult
from shubatapo.asr.wav2vec2_client import SlidingWindowASR  # 旧実装 (参考用)
from shubatapo.asr.whisper_client import WhisperASR         # 新実装 (既定)

__all__ = ["ASRClient", "ASRResult", "SlidingWindowASR", "WhisperASR"]
