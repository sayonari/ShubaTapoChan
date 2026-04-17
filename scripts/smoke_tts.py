"""Subaru_TTS サーバーに接続して1フレーズ合成してみる smoke test。

使い方:
    python scripts/smoke_tts.py "合成したい日本語テキスト"
省略時は既定のテキストで合成。
"""
from __future__ import annotations

import sys
from pathlib import Path

from shubatapo.tts import SubaruTTSClient


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "おーい！スバルだよ、調子どう？"
    # GPU PC上で実行する想定。サーバーは同ホストで動いているので localhost を使う。
    client = SubaruTTSClient(base_url="http://localhost:8766")
    print(f"[smoke_tts] text = {text}")
    res = client.synthesize(text)
    out = Path("/tmp/shubatapo_tts.wav")
    out.write_bytes(res.wav_bytes)
    print(f"[smoke_tts] saved {out}  ({res.sample_rate}Hz, {res.channels}ch, {res.duration_sec:.2f}s, {len(res.wav_bytes)/1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
