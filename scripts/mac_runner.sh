#!/usr/bin/env bash
# Mac 側で対話を進行させるランナー。
#
# 仕組み:
#   - GPU PC の tmux セッション `voice_loop` で voice_loop を常駐起動
#   - /tmp/shubatapo_replies/*.wav を GPU PC にポーリングで問い合わせ
#   - 新しいWAVが来たら scp で取ってきて afplay
#   - 起動時と各ターン後に Subaru 合成の「しゃべってー！」プロンプトを再生
#
# 使い方:
#   ./scripts/mac_runner.sh              # 普段使い
#   ./scripts/mac_runner.sh --restart    # voice_loop を強制再起動してから開始
#
# 終了: Ctrl-C (voice_loop は GPU PC で継続)
#   GPU PC で完全に止めたい時: ssh nishimura@133.15.57.36 'tmux kill-session -t voice_loop'

set -euo pipefail

cd "$(dirname "$0")/.."
set -a; source <(grep -E '^[A-Z_]+=' .env); set +a
GPU_SERVER_SSH_KEY="${GPU_SERVER_SSH_KEY/#\~/$HOME}"

SSH="ssh -i ${GPU_SERVER_SSH_KEY} -o ConnectTimeout=5"
SCP="scp -i ${GPU_SERVER_SSH_KEY}"
HOST="${GPU_SERVER_USER}@${GPU_SERVER_HOST}"
LOCAL_DIR="$HOME/.shubatapo_replies"
REMOTE_DIR="/tmp/shubatapo_replies"
REMOTE_LOG="/tmp/voice_loop.log"
TMUX_SESSION="voice_loop"
TTS_URL="http://${GPU_SERVER_HOST}:8766/api/synthesize"
PROMPT_WAV="$LOCAL_DIR/_prompt_speak.wav"
RESTART="no"

for arg in "$@"; do
  [[ "$arg" == "--restart" ]] && RESTART="yes"
done

mkdir -p "$LOCAL_DIR"

synth_subaru() {
  curl -s --max-time 15 -X POST "$TTS_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"text\":\"$1\",\"ref_file\":\"seg_000143.wav\"}" \
    -o "$2"
}

remote_tmux_has_session() {
  $SSH "$HOST" "tmux has-session -t ${TMUX_SESSION} 2>/dev/null"
}

start_voice_loop_in_tmux() {
  echo "[runner] GPU PC で voice_loop を tmux セッション ${TMUX_SESSION} に起動..."
  $SSH "$HOST" "tmux kill-session -t ${TMUX_SESSION} 2>/dev/null; \
    rm -f ${REMOTE_DIR}/*.wav ${REMOTE_LOG}; \
    tmux new-session -d -s ${TMUX_SESSION} 'cd ~/ShubaTapoChan && source .venv/bin/activate && python -u -m shubatapo.dialog.voice_loop 2>&1 | tee ${REMOTE_LOG}'"
  echo "[runner] モデルロード待ち (12秒)..."
  sleep 12
}

cleanup() {
  echo
  echo "[runner] 終了。voice_loop は GPU PC で継続中。"
  echo "       停止するなら: ssh ${HOST} 'tmux kill-session -t ${TMUX_SESSION}'"
  exit 0
}
trap cleanup INT TERM

# --- 起動 ---------------------------------------------------------------
if [[ "$RESTART" == "yes" ]] || ! remote_tmux_has_session; then
  start_voice_loop_in_tmux
else
  echo "[runner] 既存の tmux セッション ${TMUX_SESSION} を使用。"
fi

rm -f "$LOCAL_DIR"/turn_*.wav

# プロンプトWAVをSubaru TTSで合成（無ければ）
if [ ! -f "$PROMPT_WAV" ]; then
  echo "[runner] プロンプト音声を Subaru TTS で合成..."
  synth_subaru "しゃべってー！" "$PROMPT_WAV"
fi

# 起動時のプロンプト
afplay "$PROMPT_WAV"

last_seen=""
echo "[runner] 待機中。TAPO に話しかけてください。Ctrl-C で終了。"
while true; do
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
