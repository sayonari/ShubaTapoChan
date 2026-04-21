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

import os
import queue
import subprocess
import threading
import time

import numpy as np


SAMPLE_RATE = 16000
CHUNK_BYTES = 1600 * 2  # 100ms分 = 1600 sample * 2 byte
# 音声対話の SN 比改善のため、入力ゲインは既定で 1.0 (ブーストなし)。
# ノイズも同時に増幅されると VAD/ASR が常時 speech 扱いしてしまうため、
# 入力は絞り、ユーザに「大きな声で」喋ってもらう運用が鉄則。
# どうしても小さい場合のみ SHUBATAPO_AUDIO_GAIN=<N> で一時的に上げる。
DEFAULT_GAIN = float(os.environ.get("SHUBATAPO_AUDIO_GAIN", "1.0"))


class RtspPcmReader:
    def __init__(
        self,
        rtsp_url: str,
        sample_rate: int = SAMPLE_RATE,
        chunk_bytes: int = CHUNK_BYTES,
        gain: float = DEFAULT_GAIN,
        watchdog_sec: float = 5.0,
    ):
        self.rtsp_url = rtsp_url
        self.sample_rate = sample_rate
        self.chunk_bytes = chunk_bytes
        self.gain = gain
        self.watchdog_sec = watchdog_sec
        self._proc: subprocess.Popen | None = None
        self._q: queue.Queue[bytes] = queue.Queue(maxsize=256)
        self._reader_thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._stop = threading.Event()
        # 最後に stdout からデータが読めた時刻。ウォッチドッグがこれを監視して
        # stalled な ffmpeg を強制 kill する。
        self._last_data_ts: float = time.time()

    def start(self) -> None:
        self._spawn_ffmpeg()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def _spawn_ffmpeg(self) -> None:
        """ffmpeg を起動する。再接続時にも呼ばれる。"""
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            # RTSP 停滞の救出は watchdog スレッドに任せる (ffmpeg 新バージョンでは
            # -stimeout が廃止されているため)。
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
        self._last_data_ts = time.time()

    def _reader_loop(self) -> None:
        """EOF で ffmpeg が終了しても再接続を繰り返し、永続的に PCM を読み続ける。

        TAPO の RTSP はたまに切断される (ネットワーク瞬断やカメラ側のセッションタイムアウト) ので、
        voice_loop を常駐させるには自動再接続が必須。
        """
        backoff_sec = 1.0
        while not self._stop.is_set():
            if self._proc is None or self._proc.stdout is None:
                self._spawn_ffmpeg()
                assert self._proc is not None and self._proc.stdout is not None

            data = self._proc.stdout.read(self.chunk_bytes)
            if not data:
                # EOF: ffmpeg が終了 (RTSP 切断 or エラー)
                err = ""
                try:
                    if self._proc.stderr is not None:
                        err = self._proc.stderr.read(4096).decode("utf-8", errors="replace").strip()
                except Exception:
                    pass
                rc = self._proc.poll()
                print(
                    f"[RtspPcmReader] ffmpeg 終了 (returncode={rc}). {backoff_sec:.1f}s 後に再接続します"
                    + (f" / stderr: {err[:300]}" if err else "")
                )
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=2)
                except Exception:
                    pass
                self._proc = None
                # 再接続待機 (長引く切断に備えて指数バックオフ、上限 10 秒)
                time.sleep(backoff_sec)
                backoff_sec = min(backoff_sec * 1.5, 10.0)
                continue

            # データが読めたのでバックオフをリセット & ウォッチドッグ用タイムスタンプ更新
            backoff_sec = 1.0
            self._last_data_ts = time.time()

            if self.gain != 1.0:
                data = self._apply_gain(data)
            try:
                self._q.put(data, timeout=0.5)
            except queue.Full:
                # キュー満杯なら古い方を捨てて新しい方を入れる（遅延を貯めない）
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    pass
                self._q.put_nowait(data)

    def _watchdog_loop(self) -> None:
        """一定時間 stdout からデータが届かなければ ffmpeg を強制 kill する。

        ffmpeg は生きているが RTSP 側が静かに止まって stdout.read() が永久に
        ブロックする「stall」状態を救出するのが目的。kill されると
        _reader_loop 側の read() が EOF で返って再接続ループに入る。
        """
        while not self._stop.is_set():
            time.sleep(1.0)
            if self._proc is None or self._proc.poll() is not None:
                continue
            idle = time.time() - self._last_data_ts
            if idle > self.watchdog_sec:
                print(
                    f"[RtspPcmReader] watchdog: {idle:.1f}s 無通信、ffmpeg を kill して再接続"
                )
                try:
                    self._proc.kill()
                except Exception as e:
                    print(f"[RtspPcmReader] kill 失敗: {e}")
                # 次の kill が即座に走らないよう、一旦時刻をリセットして再接続サイクルを待つ
                self._last_data_ts = time.time()

    def _apply_gain(self, data: bytes) -> bytes:
        arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) * self.gain
        np.clip(arr, -32768.0, 32767.0, out=arr)
        return arr.astype(np.int16).tobytes()

    def read_chunk(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> int:
        """現在キューに溜まっている PCM chunk をすべて破棄する。

        SPEAKING→LISTENING 遷移時に呼び、再生中に溜まったエコー由来の
        古い PCM を捨ててから通常処理を再開する。
        """
        count = 0
        while True:
            try:
                self._q.get_nowait()
                count += 1
            except queue.Empty:
                return count

    def stop(self) -> None:
        self._stop.set()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
