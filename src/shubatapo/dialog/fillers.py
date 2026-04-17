"""相槌（backchannel）キャッシュ。

ユーザ発話末検出と同時に短い相槌WAVを即座に出力し、LLM応答生成中の待ち時間を
感じさせないための仕組み。起動時に TTS で各フレーズを一度合成してキャッシュする。
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from shubatapo.tts.base import TTSClient


# 相槌フレーズとキャッシュファイル名のペア
FILLERS: Sequence[tuple[str, str]] = (
    ("うーん、", "filler_umm.wav"),
    ("はいはい、", "filler_haihai.wav"),
    ("おーっ、", "filler_oh.wav"),
    ("なるほどー、", "filler_naruhodo.wav"),
    ("えっと、", "filler_etto.wav"),
    ("そっかー、", "filler_sokka.wav"),
)


def prepare_fillers(tts: TTSClient, cache_dir: Path) -> list[Path]:
    """キャッシュディレクトリに相槌 WAV を用意する。無ければ合成、あれば再利用。

    戻り値: 利用可能な相槌 WAV のパス一覧。
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for text, fname in FILLERS:
        p = cache_dir / fname
        if not p.exists():
            print(f"[fillers] synth: {text} -> {p.name}")
            res = tts.synthesize(text)
            p.write_bytes(res.wav_bytes)
        out.append(p)
    return out
