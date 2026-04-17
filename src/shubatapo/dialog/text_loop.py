"""テキスト入力版の対話ループ（MVP - ASR無し版）。

stdin から発話テキストを読み取り → LLM応答 → TTS合成 → WAV保存
対話履歴は直近N往復を保持。

使い方:
    python -m shubatapo.dialog.text_loop
終了は Ctrl-D または 空行でexit。
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from shubatapo.config import load_config
from shubatapo.llm import LLMMessage, make_llm_client
from shubatapo.tts import SubaruTTSClient


HISTORY_TURNS = 6  # 直近6往復保持
OUT_DIR = Path("/tmp/shubatapo_replies")


def main() -> int:
    cfg = load_config()
    llm = make_llm_client(cfg)
    tts = SubaruTTSClient(base_url=cfg.tts_base_url)
    OUT_DIR.mkdir(exist_ok=True)

    history: deque[LLMMessage] = deque(maxlen=HISTORY_TURNS * 2)
    print("[text_loop] ShubaTapoChan テキスト対話モード。空行 or Ctrl-D で終了。")
    turn = 0

    while True:
        try:
            user_text = input("you> ").strip()
        except EOFError:
            print()
            break
        if not user_text:
            break

        history.append(LLMMessage(role="user", content=user_text))

        t0 = time.perf_counter()
        reply = llm.respond(history=list(history))
        t_llm = time.perf_counter() - t0
        print(f"subaru> {reply}    ({t_llm:.2f}s)")

        history.append(LLMMessage(role="assistant", content=reply))

        t0 = time.perf_counter()
        res = tts.synthesize(reply)
        t_tts = time.perf_counter() - t0

        turn += 1
        out = OUT_DIR / f"turn_{turn:03d}.wav"
        out.write_bytes(res.wav_bytes)
        print(
            f"   TTS: {out.name}  "
            f"({res.sample_rate}Hz/{res.channels}ch/{res.duration_sec:.2f}s, "
            f"合成{t_tts:.2f}s)"
        )

    print("[text_loop] 終了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
