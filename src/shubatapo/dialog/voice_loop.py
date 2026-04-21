"""音声対話ループ（リアルタイム志向）。

設計ポリシー:
    - ASR は SlidingWindowASR (wav2vec2, 3秒窓/200msシフト) を既定
      → 窓ごとの partial を時刻付きで溜め続ける
    - VAD (webrtcvad) は voice_loop が**独立に**持つ
      → 発話末検出した瞬間に相槌 (ack) を即発火（ASR 結果を待たない）
      → 同時に発話区間の partial 群を ASR から吸い出し、間引いて LLM に投げる
    - 相槌・応答・TTS は並列化せず逐次。ただし ack は LLM より前に必ず再生される

    SHUBATAPO_ASR=whisper で従来の faster-whisper large-v3 経路にフォールバック可能
    （その場合 VADGate は WhisperASR 内部のものを使う）。

出力先 (SHUBATAPO_AUDIO_OUT):
    - "mac" (既定): WAV をファイル保存のみ。mac_runner.sh が afplay で再生
    - "tapo": go2rtc 経由で C220 スピーカへ push (PCMA/8kHz)
    - "both": 両方

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

from shubatapo.asr.vad import VADGate
from shubatapo.audio import RtspPcmReader, TapoSpeakerClient
from shubatapo.config import load_config
from shubatapo.dialog.fillers import prepare_fillers
from shubatapo.dialog.partials import format_partials_for_llm, thin_partials
from shubatapo.llm import LLMMessage, make_llm_client
from shubatapo.persona import load_persona
from shubatapo.tts import SubaruTTSClient


HISTORY_TURNS = 6
OUT_DIR = Path("/tmp/shubatapo_replies")
FILLER_CACHE_DIR = Path("/tmp/shubatapo_fillers")
# ノイズ由来の偽発話を捨てるための最小文字数
MIN_USER_TEXT_CHARS = 3
# LLM に渡す partial の最大個数 (これ以上は間引かれる)
MAX_PARTIALS_TO_LLM = 6
# VAD パラメータ（相槌タイミングの主役。短いほど即応だが誤切断が増える）
VAD_SILENCE_TIMEOUT_MS = int(os.environ.get("SHUBATAPO_VAD_SILENCE_MS", "600"))
VAD_MIN_SPEECH_MS = int(os.environ.get("SHUBATAPO_VAD_MIN_SPEECH_MS", "400"))


def _main_wav2vec2() -> int:
    """wav2vec2 (SlidingWindowASR) + 独立 VAD による低レイテンシ経路。"""
    from shubatapo.asr import SlidingWindowASR

    cfg = load_config()
    OUT_DIR.mkdir(exist_ok=True)

    audio_out = os.getenv("SHUBATAPO_AUDIO_OUT", "mac").lower()
    if audio_out not in {"mac", "tapo", "both"}:
        raise ValueError(f"SHUBATAPO_AUDIO_OUT は mac|tapo|both のいずれか (現在: {audio_out})")

    persona = load_persona()
    system_prompt = persona.to_system_prompt()
    print(
        f"[voice_loop] ASR=wav2vec2 / TAPO {cfg.tapo_host} / TTS {cfg.tts_base_url} / "
        f"persona={persona.name} / audio_out={audio_out}"
    )
    reader = RtspPcmReader(cfg.rtsp_url)
    asr = SlidingWindowASR()
    vad = VADGate(silence_timeout_ms=VAD_SILENCE_TIMEOUT_MS, min_speech_ms=VAD_MIN_SPEECH_MS)
    llm = make_llm_client(cfg)
    tts = SubaruTTSClient(base_url=cfg.tts_base_url)

    tapo_speaker: TapoSpeakerClient | None = None
    if audio_out in {"tapo", "both"}:
        go2rtc_url = os.getenv("SHUBATAPO_GO2RTC_URL", "http://127.0.0.1:1984")
        tapo_speaker = TapoSpeakerClient(base_url=go2rtc_url)
        if not tapo_speaker.health():
            print(f"[voice_loop] 警告: go2rtc ({go2rtc_url}) に疎通できません。")

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
    print(f"[voice_loop] ストリーム開始 (VAD: silence={VAD_SILENCE_TIMEOUT_MS}ms / "
          f"min_speech={VAD_MIN_SPEECH_MS}ms)。話しかけてみてください。Ctrl-C で終了。")

    turn = 0
    try:
        while not stop_flag["stop"]:
            pcm = reader.read_chunk(timeout=0.5)
            if not pcm:
                continue

            # ASR は裏で partial を溜め続ける（確定は待たない）
            asr.feed_pcm(pcm)

            # VAD が発話末を検出したら相槌＆LLM へ
            for utt in vad.push(pcm):
                turn += 1
                start_ts = utt.start_ms / 1000.0
                end_ts = utt.end_ms / 1000.0
                print(f"\n[VAD utterance end] {start_ts:.2f}s〜{end_ts:.2f}s (turn={turn})")

                # --- 1. 相槌 ack を即発火 -----------------------------------
                if filler_paths:
                    ack_src = random.choice(filler_paths)
                    ack_out = OUT_DIR / f"turn_{turn:03d}_ack.wav"
                    shutil.copyfile(ack_src, ack_out)
                    print(f"   ACK: {ack_out.name} ({ack_src.name})")
                    if tapo_speaker is not None:
                        try:
                            tapo_speaker.play_file(ack_out, wait_done=False)
                        except Exception as e:
                            print(f"   [tapo_speaker ack 失敗] {e}")

                # --- 2. partial 群を抽出・間引き ---------------------------
                partials = asr.get_partials_between(start_ts, end_ts)
                thinned = thin_partials(partials, max_n=MAX_PARTIALS_TO_LLM)
                if not thinned:
                    print(f"   [skip] 有効な partial なし (VAD 誤発火の可能性)")
                    continue

                # デバッグ表示: 間引き後の partial 一覧
                print(f"   partials (raw={len(partials)} → thinned={len(thinned)}):")
                for ts, text in thinned:
                    print(f"     [{ts - start_ts:+5.1f}s] {text}")

                # 最後の partial がまともな長さでなければスキップ
                last_text = thinned[-1][1] if thinned else ""
                if len(last_text) < MIN_USER_TEXT_CHARS:
                    print(f"   [skip noise] 最終 partial 短すぎ: {last_text!r}")
                    continue

                user_msg = format_partials_for_llm(thinned, speech_start_ts=start_ts)
                history.append(LLMMessage(role="user", content=user_msg))
                print(f"you> (partials ×{len(thinned)}) → LLM 送信")

                # --- 3. LLM 応答生成 --------------------------------------
                t0 = time.perf_counter()
                reply = llm.respond(history=list(history), system=system_prompt)
                t_llm = time.perf_counter() - t0
                history.append(LLMMessage(role="assistant", content=reply))
                print(f"subaru> {reply}    ({t_llm:.2f}s)")

                # --- 4. TTS 合成 → main WAV -------------------------------
                t0 = time.perf_counter()
                tres = tts.synthesize(reply)
                t_tts = time.perf_counter() - t0
                out = OUT_DIR / f"turn_{turn:03d}_main.wav"
                out.write_bytes(tres.wav_bytes)
                print(
                    f"   TTS: {out.name}  "
                    f"({tres.sample_rate}Hz/{tres.channels}ch/{tres.duration_sec:.2f}s, 合成{t_tts:.2f}s)"
                )

                if tapo_speaker is not None:
                    try:
                        time.sleep(1.0)  # ack と被らないよう少し待つ
                        tapo_speaker.play_file(out, wait_done=False)
                    except Exception as e:
                        print(f"   [tapo_speaker main 失敗] {e}")

    finally:
        reader.stop()
        asr.close()

    print("[voice_loop] 終了")
    return 0


def _main_whisper() -> int:
    """従来の faster-whisper 経路 (互換用 / ASR 差し替え A/B 比較用)。"""
    from shubatapo.asr import WhisperASR

    cfg = load_config()
    OUT_DIR.mkdir(exist_ok=True)

    audio_out = os.getenv("SHUBATAPO_AUDIO_OUT", "mac").lower()
    if audio_out not in {"mac", "tapo", "both"}:
        raise ValueError(f"SHUBATAPO_AUDIO_OUT は mac|tapo|both のいずれか (現在: {audio_out})")

    persona = load_persona()
    system_prompt = persona.to_system_prompt()
    print(
        f"[voice_loop] ASR=whisper / TAPO {cfg.tapo_host} / TTS {cfg.tts_base_url} / "
        f"persona={persona.name} / audio_out={audio_out}"
    )
    reader = RtspPcmReader(cfg.rtsp_url)
    asr = WhisperASR()
    llm = make_llm_client(cfg)
    tts = SubaruTTSClient(base_url=cfg.tts_base_url)

    tapo_speaker: TapoSpeakerClient | None = None
    if audio_out in {"tapo", "both"}:
        go2rtc_url = os.getenv("SHUBATAPO_GO2RTC_URL", "http://127.0.0.1:1984")
        tapo_speaker = TapoSpeakerClient(base_url=go2rtc_url)

    print("[voice_loop] 相槌キャッシュ準備中...")
    filler_paths = prepare_fillers(tts, FILLER_CACHE_DIR)
    print(f"[voice_loop] 相槌 {len(filler_paths)} 個キャッシュ済")

    history: deque[LLMMessage] = deque(maxlen=HISTORY_TURNS * 2)
    stop_flag = {"stop": False}

    def _sig(_signum, _frame):
        stop_flag["stop"] = True
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    turn = 0
    pending_turns: deque[int] = deque()

    def on_vad_end() -> None:
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
                if not result.is_final:
                    print(f"  [partial] {result.text}")
                    continue
                cur_turn = pending_turns.popleft() if pending_turns else 0
                user_text = result.text.strip()
                if len(user_text) < MIN_USER_TEXT_CHARS:
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
                        time.sleep(1.0)
                        tapo_speaker.play_file(out, wait_done=False)
                    except Exception as e:
                        print(f"   [tapo_speaker main 失敗] {e}")
    finally:
        reader.stop()
        asr.close()

    print("[voice_loop] 終了")
    return 0


def main() -> int:
    asr_kind = os.getenv("SHUBATAPO_ASR", "wav2vec2").lower()
    if asr_kind == "wav2vec2":
        return _main_wav2vec2()
    if asr_kind == "whisper":
        return _main_whisper()
    raise ValueError(f"SHUBATAPO_ASR は wav2vec2 または whisper (現在: {asr_kind})")


if __name__ == "__main__":
    raise SystemExit(main())
