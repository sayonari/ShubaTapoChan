"""Subaru_TTS (GPT-SoVITS v4 HTTP API) クライアント。

仕様: ../Subaru_TTS/.output/TTS_API_SPEC.md
 - POST /api/synthesize  {"text": "...", "ref_file": "seg_000001.wav"} -> WAV bytes
 - WAV: 48kHz / 16bit PCM / mono
"""
from __future__ import annotations

import io
import wave

import requests

from shubatapo.tts.base import TTSClient, TTSResult


class SubaruTTSClient(TTSClient):
    def __init__(
        self,
        base_url: str = "http://localhost:8766",
        # 参照音声はユーザ評価で seg_000143 (家庭教師) が品質◎ と判明 (2026-04-17)
        ref_file: str = "seg_000143.wav",
        timeout_sec: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.ref_file = ref_file
        self.timeout_sec = timeout_sec

    def synthesize(self, text: str) -> TTSResult:
        resp = requests.post(
            f"{self.base_url}/api/synthesize",
            json={"text": text, "ref_file": self.ref_file},
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        wav_bytes = resp.content

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            frames = wf.getnframes()
            duration = frames / float(sr)

        return TTSResult(
            wav_bytes=wav_bytes,
            sample_rate=sr,
            channels=ch,
            duration_sec=duration,
        )

    def list_refs(self) -> list[dict]:
        resp = requests.get(f"{self.base_url}/api/refs", timeout=self.timeout_sec)
        resp.raise_for_status()
        return resp.json()
