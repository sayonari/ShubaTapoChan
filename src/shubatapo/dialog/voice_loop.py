"""音声対話ループ（MVP）。

パイプライン:
    TAPO RTSP → 16kHz PCM ストリーム
              → ASR (sliding window wav2vec2 + dedup)
              → 確定テキスト (is_final=True) 到来毎に
              → LLM 応答生成
              → TTS 合成 → /tmp/shubatapo_replies/turn_NNN.wav 保存

音声出力先（TAPOスピーカー）は Phase 7 で go2rtc 経由で追加。
このMVPでは応答WAVはファイル保存のみ。

使い方（GPU PCで実行）:
    python -m shubatapo.dialog.voice_loop
終了: Ctrl-C
"""
from __future__ import annotations

import signal
import time
from collections import deque
from pathlib import Path

from shubatapo.asr import SlidingWindowASR  # sub-agentが提供
from shubatapo.audio import RtspPcmReader
from shubatapo.config import load_config
from shubatapo.llm import LLMMessage, make_llm_client
from shubatapo.tts import SubaruTTSClient


HISTORY_TURNS = 6
OUT_DIR = Path("/tmp/shubatapo_replies")
# ノイズ由来の偽発話を捨てるための最小文字数。この長さ未満のASR確定テキストはLLMに送らない。
MIN_USER_TEXT_CHARS = 3


def main() -> int:
    cfg = load_config()
    OUT_DIR.mkdir(exist_ok=True)

    print(f"[voice_loop] TAPO {cfg.tapo_host} / TTS {cfg.tts_base_url}")
    reader = RtspPcmReader(cfg.rtsp_url)
    asr = SlidingWindowASR()  # デフォルト 3秒窓 / 200msシフト
    llm = make_llm_client(cfg)
    tts = SubaruTTSClient(base_url=cfg.tts_base_url)

    history: deque[LLMMessage] = deque(maxlen=HISTORY_TURNS * 2)

    stop_flag = {"stop": False}

    def _sig(_signum, _frame):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    reader.start()
    print("[voice_loop] ストリーム開始。話しかけてみてください（Ctrl-Cで終了）")
    turn = 0
    try:
        while not stop_flag["stop"]:
            pcm = reader.read_chunk(timeout=0.5)
            if pcm:
                asr.feed_pcm(pcm)

            for result in asr.pop_results():
                # 非確定結果は進捗表示のみ
                if not result.is_final:
                    print(f"  [partial] {result.text}")
                    continue

                user_text = result.text.strip()
                if len(user_text) < MIN_USER_TEXT_CHARS:
                    # ノイズ起因の短い偽発話を無視
                    print(f"  [skip noise] {user_text!r}")
                    continue
                print(f"you> {user_text}")
                history.append(LLMMessage(role="user", content=user_text))

                t0 = time.perf_counter()
                reply = llm.respond(history=list(history))
                t_llm = time.perf_counter() - t0
                history.append(LLMMessage(role="assistant", content=reply))
                print(f"subaru> {reply}    ({t_llm:.2f}s)")

                t0 = time.perf_counter()
                tres = tts.synthesize(reply)
                t_tts = time.perf_counter() - t0

                turn += 1
                out = OUT_DIR / f"turn_{turn:03d}.wav"
                out.write_bytes(tres.wav_bytes)
                print(
                    f"   TTS: {out.name}  "
                    f"({tres.sample_rate}Hz/{tres.channels}ch/{tres.duration_sec:.2f}s, 合成{t_tts:.2f}s)"
                )
    finally:
        reader.stop()
        asr.close()

    print("[voice_loop] 終了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
