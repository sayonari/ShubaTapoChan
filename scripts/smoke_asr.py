"""SlidingWindowASR の疎通確認 smoke test。GPU PC 上で実行する想定。

動作:
 1. /tmp/tapo_smoke.wav があれば読み込み、なければ RTSP から 5秒録音 (ffmpeg)
 2. 16kHz mono s16le PCM を 200ms ごとに chunk して SlidingWindowASR に流し込む
 3. 取得した ASRResult を全て表示

使い方:
    python scripts/smoke_asr.py [wav_path]
"""
from __future__ import annotations

import io
import subprocess
import sys
import time
import wave
from pathlib import Path

from shubatapo.asr import SlidingWindowASR
from shubatapo.config import load_config


SMOKE_WAV = Path("/tmp/tapo_smoke.wav")
CAPTURE_SEC = 5
SAMPLE_RATE = 16000


def _capture_from_rtsp(out_path: Path, duration_sec: int) -> None:
    cfg = load_config()
    print(f"[smoke_asr] capturing {duration_sec}s from RTSP → {out_path}")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-rtsp_transport", "tcp",
        "-i", cfg.rtsp_url,
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-acodec", "pcm_s16le",
        "-t", str(duration_sec),
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def _load_wav_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        if sr != SAMPLE_RATE or ch != 1 or sw != 2:
            raise RuntimeError(
                f"WAV format mismatch: expected 16kHz mono s16le, got {sr}Hz {ch}ch {sw*8}bit"
            )
        return wf.readframes(wf.getnframes())


def main() -> int:
    # 入力 WAV の用意
    if len(sys.argv) > 1:
        wav_path = Path(sys.argv[1])
    else:
        wav_path = SMOKE_WAV
        if not wav_path.exists():
            _capture_from_rtsp(wav_path, CAPTURE_SEC)

    print(f"[smoke_asr] input WAV = {wav_path}")
    pcm = _load_wav_pcm(wav_path)
    total_sec = len(pcm) / 2 / SAMPLE_RATE
    print(f"[smoke_asr] loaded {len(pcm)} bytes ({total_sec:.2f}s)")

    # ASR 起動
    asr = SlidingWindowASR()

    # 200ms 刻みで流し込み、その都度 pop_results
    chunk_ms = 200
    chunk_bytes = int(SAMPLE_RATE * 2 * chunk_ms / 1000)  # 2=bytes per sample (s16)
    all_results = []
    t0 = time.time()
    for i in range(0, len(pcm), chunk_bytes):
        asr.feed_pcm(pcm[i:i + chunk_bytes])
        for r in asr.pop_results():
            print(f"[smoke_asr] FINAL  [{r.start_ts:6.2f}-{r.end_ts:6.2f}s] {r.text!r}")
            all_results.append(r)

    # 残りを flush (close 内で実行)
    asr.close()
    for r in asr.pop_results():
        print(f"[smoke_asr] FLUSHED [{r.start_ts:6.2f}-{r.end_ts:6.2f}s] {r.text!r}")
        all_results.append(r)

    elapsed = time.time() - t0
    print(f"[smoke_asr] done. total_results={len(all_results)}  elapsed={elapsed:.2f}s (realtime factor={elapsed/max(total_sec,1e-6):.2f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
