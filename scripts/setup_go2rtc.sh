#!/usr/bin/env bash
# go2rtc を GPU PC 上で tmux 常駐起動するセットアップスクリプト。
#
# Docker 非依存で、GitHub リリースの単体バイナリ (go2rtc_linux_amd64) を使う。
# $HOME/bin/go2rtc にバイナリを配置し、tmux セッション `go2rtc` で起動する。
#
# 事前条件:
#   - GPU PC (Rasiel) 上で実行する想定
#   - .env に TAPO_CLOUD_PASSWORD が追加済みであること
#   - インターネット接続 (初回のみバイナリダウンロード)
#
# やること:
#   1. config/go2rtc.yaml を .env の値で生成
#   2. $HOME/bin/go2rtc が無ければ GitHub リリースからダウンロード
#   3. 既存の tmux セッション `go2rtc` があれば停止
#   4. tmux で go2rtc を常駐起動 (port 1984 / 8554)
#   5. 疎通チェック (http://127.0.0.1:1984/api/streams)
#
# 再実行すると既存セッションを置き換える。

set -euo pipefail

cd "$(dirname "$0")/.."
set -a; source <(grep -E '^[A-Z_]+=' .env); set +a

: "${TAPO_CAMERA_HOST:?TAPO_CAMERA_HOST missing}"
: "${TAPO_CAMERA_USER:?TAPO_CAMERA_USER missing}"
: "${TAPO_CAMERA_PASSWORD:?TAPO_CAMERA_PASSWORD missing}"
: "${TAPO_CLOUD_PASSWORD:?TAPO_CLOUD_PASSWORD missing (TP-Link cloud account password, .env)}"

TEMPLATE="config/go2rtc.yaml.template"
CONFIG="config/go2rtc.yaml"
TMUX_SESSION="go2rtc"
BIN_DIR="$HOME/bin"
BIN="$BIN_DIR/go2rtc"
# 最新 stable のバイナリ URL (2026 時点)
GO2RTC_URL="${GO2RTC_URL:-https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_amd64}"

[ -f "$TEMPLATE" ] || { echo "template not found: $TEMPLATE" >&2; exit 1; }

# 1. config 生成 (特殊文字を sed の区切り外で扱うため @ 区切りを使用)
sed \
  -e "s|__RTSP_USER__|${TAPO_CAMERA_USER}|g" \
  -e "s|__RTSP_PASS__|${TAPO_CAMERA_PASSWORD}|g" \
  -e "s|__TAPO_HOST__|${TAPO_CAMERA_HOST}|g" \
  -e "s|__TAPO_CLOUD_PASSWORD__|${TAPO_CLOUD_PASSWORD}|g" \
  "$TEMPLATE" > "$CONFIG"
echo "[setup_go2rtc] generated $CONFIG"

# 2. バイナリ確保
mkdir -p "$BIN_DIR"
if [ ! -x "$BIN" ]; then
  echo "[setup_go2rtc] downloading go2rtc binary from $GO2RTC_URL"
  curl -fsSL "$GO2RTC_URL" -o "$BIN"
  chmod +x "$BIN"
fi
echo "[setup_go2rtc] binary: $BIN ($("$BIN" -version 2>&1 | head -1))"

# 3. 既存 tmux セッションがあれば停止
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  echo "[setup_go2rtc] killing existing tmux session $TMUX_SESSION"
  tmux kill-session -t "$TMUX_SESSION"
fi

# 4. tmux で起動
LOG="/tmp/go2rtc.log"
rm -f "$LOG"
tmux new-session -d -s "$TMUX_SESSION" "cd $(pwd) && $BIN -config $(pwd)/$CONFIG 2>&1 | tee $LOG"
echo "[setup_go2rtc] started tmux session $TMUX_SESSION (log: $LOG)"
sleep 2

# 5. 疎通チェック
if curl -fsS "http://127.0.0.1:1984/api/streams" >/dev/null; then
  echo "[setup_go2rtc] OK. WebUI: http://${GPU_SERVER_HOST:-<host>}:1984/"
  echo "[setup_go2rtc] tapo_c220 streams:"
  curl -s "http://127.0.0.1:1984/api/streams" | python3 -m json.tool
else
  echo "[setup_go2rtc] API が返りません。ログ確認: tail -40 $LOG"
  tail -40 "$LOG" || true
  exit 1
fi
