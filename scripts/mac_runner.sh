#!/usr/bin/env bash
# Mac 側で対話を進行させるランナー。
# GPU PC 上の voice_loop を起動（未起動なら）し、新しい応答WAVをポーリングして afplay で再生。
# 開始・各ターン前に "しゃべってー" と macOS say でプロンプト。
#
# 使い方:
#   ./scripts/mac_runner.sh
# 終了: Ctrl-C

set -euo pipefail

cd "$(dirname "$0")/.."
# .env は `KEY=VALUE` 形式の行のみ抽出（コメント・空行・行分割された値を無視）
set -a; source <(grep -E '^[A-Z_]+=' .env); set +a
# ~ を $HOME に展開
GPU_SERVER_SSH_KEY="${GPU_SERVER_SSH_KEY/#\~/$HOME}"

SSH="ssh -i ${GPU_SERVER_SSH_KEY} -o ConnectTimeout=5"
SCP="scp -i ${GPU_SERVER_SSH_KEY}"
HOST="${GPU_SERVER_USER}@${GPU_SERVER_HOST}"
LOCAL_DIR="$HOME/.shubatapo_replies"
REMOTE_DIR="/tmp/shubatapo_replies"
REMOTE_LOG="/tmp/voice_loop.log"
TTS_URL="http://${GPU_SERVER_HOST}:8766/api/synthesize"
PROMPT_WAV="$LOCAL_DIR/_prompt_speak.wav"

mkdir -p "$LOCAL_DIR"

synth_subaru() {
  # $1: テキスト, $2: 保存先パス
  curl -s --max-time 15 -X POST "$TTS_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"text\":\"$1\",\"ref_file\":\"seg_000143.wav\"}" \
    -o "$2"
}

is_running() {
  $SSH "$HOST" "pgrep -f 'shubatapo.dialog.voice_loop' > /dev/null" 2>/dev/null
}

start_loop() {
  echo "[runner] GPU PC で voice_loop を起動します..."
  $SSH "$HOST" "cd ~/ShubaTapoChan && rm -f ${REMOTE_DIR}/*.wav ${REMOTE_LOG} && source .venv/bin/activate && nohup python -u -m shubatapo.dialog.voice_loop > ${REMOTE_LOG} 2>&1 & disown"
  echo "[runner] モデルロード待ち (10秒)..."
  sleep 10
}

cleanup() {
  echo
  echo "[runner] 終了。voice_loop は GPU PC で動き続けています (手動停止: ssh ${HOST} 'pkill -f shubatapo.dialog.voice_loop')"
  exit 0
}
trap cleanup INT TERM

# --- 起動チェック & 準備 ----------------------------------------------
if is_running; then
  echo "[runner] voice_loop は既に起動中。"
else
  start_loop
fi
# turn_*.wav だけ削除（プロンプトWAVは残す）
rm -f "$LOCAL_DIR"/turn_*.wav

# プロンプトWAVをSubaru TTSで生成（無ければ）
if [ ! -f "$PROMPT_WAV" ]; then
  echo "[runner] プロンプト音声を合成中..."
  synth_subaru "しゃべってー！" "$PROMPT_WAV"
fi

# --- メインループ --------------------------------------------------------
afplay "$PROMPT_WAV" &

last_seen=""
echo "[runner] 待機中。TAPO に話しかけてください。Ctrl-C で終了。"
while true; do
  # 新しい応答 WAV の有無を確認
  latest=$($SSH "$HOST" "ls -1t ${REMOTE_DIR}/*.wav 2>/dev/null | head -1" 2>/dev/null || true)
  if [ -n "$latest" ] && [ "$latest" != "$last_seen" ]; then
    base=$(basename "$latest")
    $SCP -q "${HOST}:${latest}" "$LOCAL_DIR/$base"
    last_seen="$latest"
    echo "[runner] 再生: $base"
    afplay "$LOCAL_DIR/$base"
    sleep 0.2
    afplay "$PROMPT_WAV"
  fi
  sleep 1
done
