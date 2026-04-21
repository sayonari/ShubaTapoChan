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

    # turn 番号は VAD 発話末検出で進める。ASR 確定は後からキューで対応付ける。
    turn = 0
    pending_turns: deque[int] = deque()

    def on_vad_end() -> None:
        """VAD が発話末を検出した瞬間に呼ばれる (Whisper 推論より前)。

        相槌 (ack) を即座に書き出して、mac_runner/tapo_speaker に先行再生させる。
        この時点では user_text はまだ無いので、後段 ASR 確定時に同じ turn 番号で
        main を書く。ノイズ起因で ASR 結果が空だった場合は ack だけが残る。
        """
        nonlocal turn
        turn += 1
        pending_turns.append(turn)
        if not filler_paths:
            return
        ack_src = random.choice(filler_paths)
        ack_out = OUT_DIR / f"turn_{turn:03d}_ack.wav"
        shutil.copyfile(ack_src, ack_out)
        print(f"   ACK: {ack_out.name} ({ack_src.name})")
        if tapo_speaker is not None:
            try:
                tapo_speaker.play_file(ack_out, wait_done=False)
            except Exception as e:
                print(f"   [tapo_speaker ack 失敗] {e}")

    asr.set_on_utterance_end(on_vad_end)

    reader.start()
    print("[voice_loop] ストリーム開始。話しかけてみてください（Ctrl-Cで終了）")
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

                # on_vad_end で予約された turn 番号を取り出す。
                # WhisperASR の内部で VAD 発火 → 同期的に _transcribe されるので順序は保たれる。
                cur_turn = pending_turns.popleft() if pending_turns else 0

                user_text = result.text.strip()
                if len(user_text) < MIN_USER_TEXT_CHARS:
                    # ノイズ起因の短い偽発話を無視。ack は既に再生されているが、main は書かない。
                    print(f"  [skip noise] {user_text!r} (turn={cur_turn})")
                    continue
                print(f"you> {user_text}  (turn={cur_turn})")
                history.append(LLMMessage(role="user", content=user_text))

                t0 = time.perf_counter()
                reply = llm.respond(history=list(history), system=system_prompt)
                t_llm = time.perf_counter() - t0
                history.append(LLMMessage(role="assistant", content=reply))
                print(f"subaru> {reply}    ({t_llm:.2f}s)")

                t0 = time.perf_counter()
                tres = tts.synthesize(reply)
                t_tts = time.perf_counter() - t0

                out = OUT_DIR / f"turn_{cur_turn:03d}_main.wav"
                out.write_bytes(tres.wav_bytes)
                print(
                    f"   TTS: {out.name}  "
                    f"({tres.sample_rate}Hz/{tres.channels}ch/{tres.duration_sec:.2f}s, 合成{t_tts:.2f}s)"
                )

                if tapo_speaker is not None:
                    try:
                        # ack と被らないよう少し待機してから main を送る
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
