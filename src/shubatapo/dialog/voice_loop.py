"""音声対話ループ（MVP）。

パイプライン:
    TAPO RTSP → 16kHz PCM ストリーム
              → ASR (sliding window wav2vec2 + dedup)
              → 確定テキスト (is_final=True) 到来毎に
              → 相槌 WAV を turn_NNN_ack.wav として即コピー（体感遅延マスク）
              → LLM 応答生成
              → TTS 合成 → /tmp/shubatapo_replies/turn_NNN_main.wav 保存

出力先 (SHUBATAPO_AUDIO_OUT):
    - "mac" (既定): WAV をファイル保存のみ。Mac ランナー (scripts/mac_runner.sh) が
      ポーリングで取りに来て afplay で再生する（音質◎ / Subaru声質を楽しむ用途）。
    - "tapo": WAV を go2rtc HTTP API で TAPO C220 スピーカに push（音質は
      PCMA/8kHz 電話品質 / カメラから声を出す体験向け）。
    - "both": 上記両方（Mac で確認しつつ C220 からも鳴らす）。

使い方（GPU PCで実行）:
    python -m shubatapo.dialog.voice_loop
終了: Ctrl-C
"""
from __future__ import annotations

import os
import random
import shutil
import signal
import time
from collections import deque
from pathlib import Path

from shubatapo.asr import WhisperASR
from shubatapo.audio import RtspPcmReader, TapoSpeakerClient
from shubatapo.config import load_config
from shubatapo.dialog.fillers import prepare_fillers
from shubatapo.llm import LLMMessage, make_llm_client
from shubatapo.persona import load_persona
from shubatapo.tts import SubaruTTSClient


HISTORY_TURNS = 6
OUT_DIR = Path("/tmp/shubatapo_replies")
FILLER_CACHE_DIR = Path("/tmp/shubatapo_fillers")
# ノイズ由来の偽発話を捨てるための最小文字数。この長さ未満のASR確定テキストはLLMに送らない。
MIN_USER_TEXT_CHARS = 3


def main() -> int:
    cfg = load_config()
    OUT_DIR.mkdir(exist_ok=True)

    audio_out = os.getenv("SHUBATAPO_AUDIO_OUT", "mac").lower()
    if audio_out not in {"mac", "tapo", "both"}:
        raise ValueError(f"SHUBATAPO_AUDIO_OUT は mac|tapo|both のいずれか (現在: {audio_out})")

    persona = load_persona()
    system_prompt = persona.to_system_prompt()
    print(
        f"[voice_loop] TAPO {cfg.tapo_host} / TTS {cfg.tts_base_url} / "
        f"persona={persona.name} / audio_out={audio_out}"
    )
    reader = RtspPcmReader(cfg.rtsp_url)
    asr = WhisperASR()  # VAD + faster-whisper large-v3 (既定)
    llm = make_llm_client(cfg)
    tts = SubaruTTSClient(base_url=cfg.tts_base_url)

    tapo_speaker: TapoSpeakerClient | None = None
    if audio_out in {"tapo", "both"}:
        go2rtc_url = os.getenv("SHUBATAPO_GO2RTC_URL", "http://127.0.0.1:1984")
        tapo_speaker = TapoSpeakerClient(base_url=go2rtc_url)
        if not tapo_speaker.health():
            print(f"[voice_loop] 警告: go2rtc ({go2rtc_url}) に疎通できません。scripts/setup_go2rtc.sh を確認。")

    print("[voice_loop] 相槌キャッシュ準備中...")
    filler_paths = prepare_fillers(tts, FILLER_CACHE_DIR)
    print(f"[voice_loop] 相槌 {len(filler_paths)} 個キャッシュ済")

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

                turn += 1
                # 相槌 (ack) を即座に出力ディレクトリへコピー。mac_runner 側で先に再生される。
                # 名前順で ack < main になるよう suffix を設計している。
                ack_out: Path | None = None
                if filler_paths:
                    ack_src = random.choice(filler_paths)
                    ack_out = OUT_DIR / f"turn_{turn:03d}_ack.wav"
                    shutil.copyfile(ack_src, ack_out)
                    print(f"   ACK: {ack_out.name} ({ack_src.name})")

                # TAPO スピーカ出力: 相槌を即座に流して LLM+TTS 合成中の遅延を埋める
                if tapo_speaker is not None and ack_out is not None:
                    try:
                        tapo_speaker.play_file(ack_out, wait_done=False)
                    except Exception as e:
                        print(f"   [tapo_speaker ack 失敗] {e}")

                t0 = time.perf_counter()
                reply = llm.respond(history=list(history), system=system_prompt)
                t_llm = time.perf_counter() - t0
                history.append(LLMMessage(role="assistant", content=reply))
                print(f"subaru> {reply}    ({t_llm:.2f}s)")

                t0 = time.perf_counter()
                tres = tts.synthesize(reply)
                t_tts = time.perf_counter() - t0

                out = OUT_DIR / f"turn_{turn:03d}_main.wav"
                out.write_bytes(tres.wav_bytes)
                print(
                    f"   TTS: {out.name}  "
                    f"({tres.sample_rate}Hz/{tres.channels}ch/{tres.duration_sec:.2f}s, 合成{t_tts:.2f}s)"
                )

                # TAPO スピーカ出力: main を続けて再生 (ack 再生完了を待ってから push)
                if tapo_speaker is not None:
                    try:
                        # ack の再生が長引くと被るので、少し待機してから main を送る
                        # 相槌は 0.5〜1.5 秒程度なので 1.0 秒固定待機で実用上十分
                        time.sleep(1.0)
                        tapo_speaker.play_file(out, wait_done=False)
                    except Exception as e:
                        print(f"   [tapo_speaker main 失敗] {e}")
    finally:
        reader.stop()
        asr.close()

    print("[voice_loop] 終了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
