"""go2rtc 経由で TAPO C220 のスピーカに音声ファイルを再生させるクライアント。

前提:
    - GPU PC 上で go2rtc コンテナが :1984 で起動している
    - `config/go2rtc.yaml` に `tapo_c220` ストリームが定義されている
    - WAV ファイルパスは go2rtc コンテナから同じ絶対パスで見える
      (setup_go2rtc.sh で /tmp/shubatapo_replies を bind mount している)

API ドキュメント概要 (go2rtc):
    POST /api/streams?dst=<stream>&src=<source>
        指定された source を stream に push する
    src="" で再生停止 (バージイン用途)

    source の例:
        file:/tmp/shubatapo_replies/turn_001_main.wav#input=file
            → ファイル再生モード (リアルタイム変換、途中停止が容易)
        http://.../stream.opus
            → 任意 HTTP ソース
"""
from __future__ import annotations

import time
from pathlib import Path

import requests


class TapoSpeakerClient:
    """go2rtc HTTP API で TAPO スピーカに WAV を流す。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1984",
        stream: str = "tapo_c220",
        timeout_sec: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.stream = stream
        self.timeout_sec = timeout_sec

    def play_file(self, wav_path: Path, wait_done: bool = False, poll_sec: float = 0.5) -> None:
        """ローカルの WAV ファイルを TAPO スピーカで再生する。

        Args:
            wav_path: 再生したい WAV の絶対パス。go2rtc コンテナから同じパスで見える必要あり。
            wait_done: True の場合、再生終了 (stream の consumers=0) まで待機。
                False なら即リターンし、次の処理を並列で進められる。
            poll_sec: wait_done=True 時のポーリング間隔。
        """
        src = f"file:{wav_path}#input=file"
        resp = requests.post(
            f"{self.base_url}/api/streams",
            params={"dst": self.stream, "src": src},
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()

        if wait_done:
            while self.is_busy():
                time.sleep(poll_sec)

    def stop(self) -> None:
        """再生中の音声を即停止する (バージイン用)。"""
        resp = requests.post(
            f"{self.base_url}/api/streams",
            params={"dst": self.stream, "src": ""},
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()

    def is_busy(self) -> bool:
        """tapo_c220 ストリームに生きているプロデューサーがあるかを返す。

        go2rtc の /api/streams?src=<name> はストリーム情報 JSON を返す。
        producers があり recv > 0 なら再生中扱い。
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/streams",
                params={"src": self.stream},
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            return False
        producers = data.get("producers") or []
        for p in producers:
            url = (p.get("url") or "") if isinstance(p, dict) else ""
            if url.startswith("file:"):
                return True
        return False

    def health(self) -> bool:
        """go2rtc API 疎通チェック。"""
        try:
            resp = requests.get(f"{self.base_url}/api/streams", timeout=self.timeout_sec)
            resp.raise_for_status()
            return True
        except requests.RequestException:
            return False
