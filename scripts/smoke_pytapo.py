"""pytapoでTAPO C220に接続し、基本情報取得とPTZ動作を試す。

GPU PC上で venv 有効化した状態で実行する想定:
    python scripts/smoke_pytapo.py

このスクリプトでは以下を順に行う:
  1. Tapo().getBasicInfo()      ... 接続・認証の確認
  2. Tapo().moveMotor(10, 0)    ... 少しだけ首振り
  3. Tapo().moveMotor(-10, 0)   ... 元の位置へ戻す

注: ユーザー名は Camera Account（Advanced Settings で作成したもの）を想定。
"""
from __future__ import annotations

import sys
import time

from shubatapo.config import load_config


def main() -> int:
    cfg = load_config()
    print(f"[smoke_pytapo] target = {cfg.tapo_host}, user = {cfg.tapo_user}")

    try:
        from pytapo import Tapo
    except ImportError:
        print("[smoke_pytapo] pytapo がインストールされていません。`pip install pytapo` してから再実行してください。", file=sys.stderr)
        return 1

    tapo = Tapo(cfg.tapo_host, cfg.tapo_user, cfg.tapo_password)

    print("[smoke_pytapo] getBasicInfo():")
    info = tapo.getBasicInfo()
    # 長すぎるので主要キーだけ表示
    basic = info.get("device_info", {}).get("basic_info", info)
    for k in ("device_model", "device_type", "hw_version", "sw_version", "mac", "device_alias"):
        if k in basic:
            print(f"  {k}: {basic[k]}")

    print("[smoke_pytapo] moveMotor: +10 pan, 0 tilt")
    tapo.moveMotor(10, 0)
    time.sleep(1.5)
    print("[smoke_pytapo] moveMotor: -10 pan, 0 tilt  (戻す)")
    tapo.moveMotor(-10, 0)

    print("[smoke_pytapo] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
