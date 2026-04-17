"""ASR clients."""
from shubatapo.asr.base import ASRClient, ASRResult
from shubatapo.asr.wav2vec2_client import SlidingWindowASR

__all__ = ["ASRClient", "ASRResult", "SlidingWindowASR"]
