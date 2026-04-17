"""TAPO RTSP → 16kHz mono PCM s16le ストリームリーダー。

ffmpeg をサブプロセスで起動し、stdout から生PCMを読む。別スレッドで読みながら
キューに push し、メインスレッドは `read_chunk()` で取り出す。

使い方:
    reader = RtspPcmReader(rtsp_url)
    reader.start()
    while True:
        pcm = reader.read_chunk(timeout=1.0)  # bytes (16kHz mono s16le)
        if pcm is None:
            continue
        asr.feed_pcm(pcm)
    reader.stop()
"""
from __future__ import annotations

import queue
import subprocess
import threading


SAMPLE_RATE = 16000
CHUNK_BYTES = 1600 * 2  # 100ms分 = 1600 sample * 2 byte


class RtspPcmReader:
    def __init__(self, rtsp_url: str, sample_rate: int = SAMPLE_RATE, chunk_bytes: int = CHUNK_BYTES):
        self.rtsp_url = rtsp_url
        self.sample_rate = sample_rate
        self.chunk_bytes = chunk_bytes
        self._proc: subprocess.Popen | None = None
        self._q: queue.Queue[bytes] = queue.Queue(maxsize=256)
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-vn",
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "pipe:1",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        while not self._stop.is_set():
            data = self._proc.stdout.read(self.chunk_bytes)
            if not data:
                break
            try:
                self._q.put(data, timeout=0.5)
            except queue.Full:
                # キュー満杯なら古い方を捨てて新しい方を入れる（遅延を貯めない）
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    pass
                self._q.put_nowait(data)

    def read_chunk(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        self._stop.set()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
