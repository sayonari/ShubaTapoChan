"""SlidingWindowASR の partial 群を間引いて LLM へ渡しやすい形に整形する。

VAD が発話末を検出したら、その発話区間の partial 群を ASR から抜き出し、
等間隔で間引いて LLM の user メッセージに変換する。
"""
from __future__ import annotations


def thin_partials(
    partials: list[tuple[float, str]],
    max_n: int = 6,
    min_chars: int = 3,
) -> list[tuple[float, str]]:
    """連続重複を除去した上で、max_n 個を超える場合は等間隔で間引く。

    - min_chars 未満の短い partial は低品質として除外
      （ノイズ由来の「な」「る」等を捨てる）
    - 連続する同一テキストは最初の 1 つだけ残す
    - 先頭と末尾は残り候補から必ず含める
    """
    # 1. 低品質 partial を除去 + 連続同一テキストを畳む
    dedup: list[tuple[float, str]] = []
    for ts, text in partials:
        if not text or len(text) < min_chars:
            continue
        if dedup and dedup[-1][1] == text:
            continue
        dedup.append((ts, text))

    n = len(dedup)
    if n <= max_n:
        return dedup

    # 2. 等間隔で max_n 個選択（先頭と末尾を含む）
    step = (n - 1) / (max_n - 1)
    idx = sorted(set(round(i * step) for i in range(max_n)))
    return [dedup[i] for i in idx]


def format_partials_for_llm(
    thinned: list[tuple[float, str]],
    speech_start_ts: float,
) -> str:
    """間引いた partial 群を LLM 入力用の user メッセージ文字列にする。

    Args:
        thinned: thin_partials() の出力
        speech_start_ts: 発話開始時刻 (絶対秒)。相対時刻表示に使う。
    """
    if not thinned:
        return ""
    if len(thinned) == 1:
        # 窓 1 つで収まった短い発話。そのまま返す。
        return thinned[0][1]

    lines = [
        "以下は同じ話者の連続発話を 3秒窓の音声認識で時系列に認識した断片です（重複あり・誤認ありうる）。"
        "全体から話者が何を言ったかを汲み取って、短く自然に応答してください。",
    ]
    for ts, text in thinned:
        rel = max(0.0, ts - speech_start_ts)
        lines.append(f"[{rel:+5.1f}s] {text}")
    return "\n".join(lines)
