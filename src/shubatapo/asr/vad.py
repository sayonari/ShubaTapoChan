"""webrtcvad ベースの発話区間検出（VAD）ゲート。

16kHz mono PCM s16le を feed すると、発話開始→無音800ms継続で「1発話分のPCM」を
utterance としてまとめて返す。Whisper など utterance 単位の ASR 前段で使う。
"""
from __future__ import annotations

from dataclasses import dataclass


# webrtcvad は 10 / 20 / 30 ms フレームのみサポート
FRAME_MS = 30
SAMPLE_RATE = 16000
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2  # 30ms @ 16kHz s16le = 960 bytes


@dataclass(frozen=True)
class Utterance:
    pcm: bytes           # 16kHz mono s16le PCM, 末尾にトレイリング無音を含む
    start_ms: float      # feed 開始を 0 とした発話開始時刻
    end_ms: float        # 発話終了時刻（無音確定点）


class VADGate:
    """push(pcm_bytes) -> list[Utterance]。

    アルゴリズム:
      - 30ms フレームごとに webrtcvad で speech/silence 判定
      - speech 検出 → 発話開始、バッファ蓄積
      - silence 継続時間が silence_timeout_ms を超え、かつ speech 累積が
        min_speech_ms を超えていれば「1発話」として emit
      - min_speech_ms 未満ならノイズ扱いで捨てる
    """

    def __init__(
        self,
        aggressiveness: int = 2,          # 0-3 (大きいほど silence 判定厳しめ)
        silence_timeout_ms: int = 800,    # 発話末とみなす無音継続時間
        min_speech_ms: int = 300,         # これ未満はノイズとして捨てる
    ):
        import webrtcvad
        self._vad = webrtcvad.Vad(aggressiveness)
        self.silence_timeout_ms = silence_timeout_ms
        self.min_speech_ms = min_speech_ms

        self._pending = bytearray()       # まだフレーム化されてないバイト
        self._utt_buf = bytearray()       # 発話中の蓄積
        self._in_speech = False
        self._speech_ms = 0
        self._silence_ms = 0
        self._total_ms = 0                # feed 開始からの累積時刻
        self._utt_start_ms = 0.0

    def push(self, pcm_bytes: bytes) -> list[Utterance]:
        out: list[Utterance] = []
        if not pcm_bytes:
            return out
        self._pending.extend(pcm_bytes)
        while len(self._pending) >= FRAME_BYTES:
            frame = bytes(self._pending[:FRAME_BYTES])
            del self._pending[:FRAME_BYTES]
            self._total_ms += FRAME_MS
            is_speech = self._vad.is_speech(frame, SAMPLE_RATE)

            if is_speech:
                if not self._in_speech:
                    self._in_speech = True
                    self._utt_start_ms = self._total_ms - FRAME_MS
                    self._utt_buf.clear()
                    self._speech_ms = 0
                self._silence_ms = 0
                self._speech_ms += FRAME_MS
                self._utt_buf.extend(frame)
            else:
                if self._in_speech:
                    # トレイリング無音もバッファに含める（末尾子音が拾いやすい）
                    self._utt_buf.extend(frame)
                    self._silence_ms += FRAME_MS
                    if self._silence_ms >= self.silence_timeout_ms:
                        # 発話末確定
                        if self._speech_ms >= self.min_speech_ms:
                            out.append(
                                Utterance(
                                    pcm=bytes(self._utt_buf),
                                    start_ms=self._utt_start_ms,
                                    end_ms=self._total_ms,
                                )
                            )
                        self._utt_buf.clear()
                        self._in_speech = False
                        self._silence_ms = 0
                        self._speech_ms = 0
                # else: 無音継続、何もしない
        return out

    def flush(self) -> list[Utterance]:
        """ストリーム終端処理。speech 中なら現時点で確定させる。"""
        out: list[Utterance] = []
        if self._in_speech and self._speech_ms >= self.min_speech_ms:
            out.append(
                Utterance(
                    pcm=bytes(self._utt_buf),
                    start_ms=self._utt_start_ms,
                    end_ms=self._total_ms,
                )
            )
        self._utt_buf.clear()
        self._in_speech = False
        self._silence_ms = 0
        self._speech_ms = 0
        return out
