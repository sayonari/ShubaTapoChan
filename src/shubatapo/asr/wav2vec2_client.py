"""wav2vec2-CTC によるスライディング窓 ASR クライアント。

VAD_ASR_emoto/mod_record.py をモジュール化した版。PyAudio 依存を排除し、
外部から 16kHz mono PCM s16le を feed_pcm で流し込む設計。

使用モデル: SiRoZaRuPa/wav2vec2-kanji-base-char-0916 (日本語漢字仮名交じり char)
"""
from __future__ import annotations

import collections
import time
from collections import deque

import numpy as np

from shubatapo.asr.base import ASRClient, ASRResult
from shubatapo.asr.dedup import Dedup


import os

# ローカルディレクトリが優先。環境変数で上書き可能。
# GPU PC 側で ~/models/emoto-wav2vec2/ に配置している想定。
DEFAULT_MODEL_ID = os.environ.get(
    "SHUBATAPO_ASR_MODEL",
    os.path.expanduser("~/models/emoto-wav2vec2"),
)
SAMPLE_RATE = 16000


class SlidingWindowASR(ASRClient):
    """スライディング窓方式の wav2vec2 ASR。

    - 窓幅: window_sec 秒 (デフォルト 3.0)
    - 窓シフト: stride_ms ミリ秒 (デフォルト 200)
    - PCM を feed_pcm で流し込み、pop_results で認識結果を取り出す
    - 窓が埋まった時点から stride ごとに直近 window_sec を推論
    - Dedup で畳み込んで utterance 単位の確定テキストを発行
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        window_sec: float = 3.0,
        stride_ms: int = 200,
        stable_window: int = 3,
        device: str | None = None,
    ):
        self.model_id = model_id
        self.window_sec = window_sec
        self.stride_ms = stride_ms
        self.window_samples = int(SAMPLE_RATE * window_sec)
        self.stride_samples = int(SAMPLE_RATE * stride_ms / 1000)

        # ---- モデル読み込み (__init__ で1回だけ) ----
        # import はここで行う。Mac では transformers/torch ロードが重いので遅延 import。
        import torch
        from transformers import AutoModelForCTC, Wav2Vec2CTCTokenizer, Wav2Vec2Processor
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()

        self._torch = torch
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        print(f"[SlidingWindowASR] loading {model_id} on {device} ...")

        tokenizer = Wav2Vec2CTCTokenizer.from_pretrained(model_id)
        self.processor = Wav2Vec2Processor.from_pretrained(model_id, tokenizer=tokenizer)
        self.model = AutoModelForCTC.from_pretrained(model_id)
        self.model.eval()
        self.model.to(device)
        print(f"[SlidingWindowASR] model ready. window={window_sec}s stride={stride_ms}ms")

        # ---- 状態 ----
        # リングバッファ (int16 を連結保持)。簡易に deque[np.ndarray] で持つ。
        self._pcm_buf: np.ndarray = np.zeros(0, dtype=np.int16)
        self._samples_since_last_infer: int = 0
        self._total_samples_in: int = 0  # これまで feed された累積サンプル数 (時刻換算用)
        self._start_wall: float = time.time()

        self._dedup = Dedup(stable_window=stable_window)
        self._results: collections.deque[ASRResult] = deque()
        # 最新の暫定テキスト (まだ確定していない) も覗けるように保持
        self._last_partial: str = ""
        # 確定テキストの発話開始時刻候補 (空→非空に切り替わった時刻)
        self._utterance_start_ts: float | None = None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def feed_pcm(self, pcm_bytes: bytes) -> None:
        """16kHz mono PCM s16le を追加。窓ごとに推論が走る。"""
        if not pcm_bytes:
            return
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        self._pcm_buf = np.concatenate([self._pcm_buf, arr])
        self._total_samples_in += len(arr)
        self._samples_since_last_infer += len(arr)

        # 窓がまだ埋まらない場合は待つ
        if len(self._pcm_buf) < self.window_samples:
            return

        # stride ごとに推論
        while self._samples_since_last_infer >= self.stride_samples:
            self._samples_since_last_infer -= self.stride_samples
            window = self._pcm_buf[-self.window_samples:]
            text = self._infer(window)
            self._handle_window_text(text)

        # バッファは窓サイズ分だけ保持すれば十分（それ以前は不要）
        # 少しマージンを取って 2*window 以上には伸ばさない
        max_keep = self.window_samples * 2
        if len(self._pcm_buf) > max_keep:
            self._pcm_buf = self._pcm_buf[-max_keep:]

    def pop_results(self) -> list[ASRResult]:
        out: list[ASRResult] = []
        while self._results:
            out.append(self._results.popleft())
        return out

    def close(self) -> None:
        """モデルを解放する。"""
        # flush して残っている partial を確定させる
        final = self._dedup.flush()
        if final:
            self._emit_final(final)
        # GPU メモリ解放
        try:
            del self.model
            del self.processor
            if self.device == "cuda":
                self._torch.cuda.empty_cache()
        except Exception as e:
            print(f"[SlidingWindowASR] close warning: {e}")

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _infer(self, window_i16: np.ndarray) -> str:
        """窓 1つに対して wav2vec2 推論を実行し、テキストを返す。"""
        # int16 → float32 [-1, 1) 程度に正規化
        # VAD_ASR_emoto では float64 のまま渡していたが、processor 内で正規化されるので
        # スケーリングは不要 (processor が int16 値を入れても 0 近辺で扱ってしまうので
        # 念のため float32 のまま渡す。正規化は processor に任せる)。
        audio = window_i16.astype(np.float32)
        inputs = self.processor(
            audio, sampling_rate=SAMPLE_RATE, return_tensors="pt", padding=True
        )
        input_values = inputs.input_values.to(self.device)
        attention_mask = None
        if self.processor.feature_extractor.return_attention_mask:
            attention_mask = inputs.attention_mask.to(self.device)

        with self._torch.no_grad():
            if attention_mask is not None:
                logits = self.model(input_values, attention_mask=attention_mask).logits
            else:
                logits = self.model(input_values).logits
        predicted_ids = self._torch.argmax(logits, dim=-1)
        sentences = self.processor.batch_decode(predicted_ids)
        return sentences[0] if sentences else ""

    def _handle_window_text(self, text: str) -> None:
        """窓ごとのテキストを Dedup に通し、確定したら ASRResult キューに積む。"""
        # 発話開始時刻の候補を覚えておく
        if text.strip() and self._utterance_start_ts is None:
            # この窓の終端（現在時刻）から窓長を引いた時刻を近似開始時刻とする
            self._utterance_start_ts = self._current_ts() - self.window_sec

        self._last_partial = text
        finalized = self._dedup.push(text)
        if finalized is not None:
            self._emit_final(finalized)

    def _emit_final(self, text: str) -> None:
        end_ts = self._current_ts()
        start_ts = self._utterance_start_ts if self._utterance_start_ts is not None else end_ts
        self._results.append(
            ASRResult(text=text, is_final=True, start_ts=start_ts, end_ts=end_ts)
        )
        self._utterance_start_ts = None

    def _current_ts(self) -> float:
        """feed_pcm で投入された累積サンプル数から秒単位時刻を計算。

        壁時計ではなく音声サンプル由来の時刻なので、ジッタに強い。
        """
        return self._total_samples_in / float(SAMPLE_RATE)
