"""stdin から 16kHz mono PCM s16le を受け取る PcmReader。

Mac 側で ffmpeg -f avfoundation ... | ssh GPU_PC "python -m shubatapo.dialog.voice_loop"
のように、Mac のマイク音声を SSH stdin 経由で GPU PC 側 voice_loop に
流し込むための入力クラス。

インターフェイスは RtspPcmReader と互換 (start / read_chunk / stop / drain)。
"""
from __future__ import annotations

import os
import queue
import sys
import threading


SAMPLE_RATE = 16000
CHUNK_BYTES = 1600 * 2  # 100ms @ 16kHz s16le
DEFAULT_GAIN = float(os.environ.get("SHUBATAPO_AUDIO_GAIN", "1.0"))


class StdinPcmReader:
    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        chunk_bytes: int = CHUNK_BYTES,
        gain: float = DEFAULT_GAIN,
    ):
        self.sample_rate = sample_rate
        self.chunk_bytes = chunk_bytes
        self.gain = gain
        self._q: queue.Queue[bytes] = queue.Queue(maxsize=256)
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        buf = sys.stdin.buffer
        while not self._stop.is_set():
            data = buf.read(self.chunk_bytes)
            if not data:
                # EOF: Mac 側 ffmpeg/ssh が終了した → voice_loop も終了
                print("[StdinPcmReader] stdin EOF")
                break
            if self.gain != 1.0:
                import numpy as np
                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) * self.gain
                np.clip(arr, -32768.0, 32767.0, out=arr)
                data = arr.astype(np.int16).tobytes()
            try:
                self._q.put(data, timeout=0.5)
            except queue.Full:
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

    def drain(self) -> int:
        """キューに溜まった PCM chunk を全破棄。"""
        count = 0
        while True:
            try:
                self._q.get_nowait()
                count += 1
            except queue.Empty:
                return count

    def stop(self) -> None:
        self._stop.set()
