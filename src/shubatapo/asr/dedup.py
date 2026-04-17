"""隣接窓の wav2vec2 出力を畳み込んで確定テキストを発行する dedup ロジック。

スライディング窓は 200ms しかシフトしないので、窓幅 3秒なら 2.8秒分は同じ音声を
見ている。単純に concat すると冗長なので「同じテキストが連続したら確定とみなす」
ロジックで畳み込む。

案1 (現在の実装):
    - 直前の出力と一致したら stable_count をインクリメント
    - stable_window 回連続で一致したら utterance 完了とみなし確定テキストを返す
    - 確定後は state をリセット

TODO (案2): 隣接窓の最長共通接尾辞・接頭辞 (difflib.SequenceMatcher) で
    畳み込み、より長い utterance にも追従できるようにする。案1 は utterance が
    3秒窓に収まる前提の簡易実装。
"""
from __future__ import annotations


class Dedup:
    """窓ごとの ASR 出力を受け取り、確定テキストを発行する。

    使い方:
        dedup = Dedup(stable_window=3)
        for raw_text in window_outputs:
            finalized = dedup.push(raw_text)
            if finalized is not None:
                # 確定テキスト
                ...
    """

    def __init__(self, stable_window: int = 3):
        """連続 stable_window 回同じテキストが出たら確定とみなす。

        デフォルト 3 は、窓シフト 200ms のとき約 600ms 変化なしで確定。
        """
        self.stable_window = stable_window
        self.running: str = ""   # 現在畳み込み中のテキスト（確定前）
        self.last: str = ""      # 直前の窓出力
        self.stable_count: int = 0

    def push(self, text: str) -> str | None:
        """新しい窓の出力を足し込む。

        戻り値:
            - 確定したテキスト (str) … 発話が完結したとみなされた場合
            - None … まだ確定していない（継続中 or 無音）
        """
        text = text.strip()

        # 無音/空文字は stable_count 進行中なら確定のトリガとして扱う
        if text == "":
            if self.running:
                finalized = self.running
                self._reset()
                return finalized
            # 空→空 は何もしない
            self.last = ""
            self.stable_count = 0
            return None

        if text == self.last:
            self.stable_count += 1
        else:
            self.stable_count = 1  # 新しいテキストに入れ替わったので 1 からカウント
            self.last = text

        # running は「今表示している暫定テキスト」。窓出力そのものを採用。
        self.running = text

        if self.stable_count >= self.stable_window:
            finalized = self.running
            self._reset()
            return finalized

        return None

    def flush(self) -> str | None:
        """ストリーム終端などで強制的に確定させる。暫定テキストがあれば返す。"""
        if self.running:
            finalized = self.running
            self._reset()
            return finalized
        return None

    def _reset(self) -> None:
        self.running = ""
        self.last = ""
        self.stable_count = 0
