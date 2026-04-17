"""TTS clients."""
from shubatapo.tts.base import TTSClient, TTSResult
from shubatapo.tts.subaru_client import SubaruTTSClient

__all__ = ["TTSClient", "TTSResult", "SubaruTTSClient"]
