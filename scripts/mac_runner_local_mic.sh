#!/usr/bin/env bash
# Mac のマイクを入力源として voice_loop を動かすランナー。
#
# 従来の mac_runner.sh は TAPO C220 の RTSP マイクを入力として使うが、
# こちらは Mac のマイク (AVFoundation) を使い、SN 比・音質を大幅改善する。
#
# 流れ:
#   1. ffmpeg で Mac avfoundation から 16kHz mono s16le PCM を取り出す
#   2. SSH 越しに GPU PC の voice_loop (SHUBATAPO_INPUT=stdin) にパイプ
#   3. 並行して /tmp/shubatapo_replies を scp ポーリング → afplay
#
# 使い方:
#   ./scripts/mac_runner_local_mic.sh                 # デフォルトマイク (:0)
#   ./scripts/mac_runner_local_mic.sh --mic=:1        # マイク index 1
#   ./scripts/mac_runner_local_mic.sh --list-mics     # 利用可能なマイク一覧
#
# 注意:
#   - 初回実行時に macOS のマイクアクセス許可が要求される
#   - 既存の RTSP 入力版 voice_loop (tmux voice_loop) は停止される

set -euo pipefail
cd "$(dirname "$0")/.."

# --list-mics は .env 不要で先に処理
if [[ "${1:-}" == "--list-mics" ]]; then
  echo "[runner/mic] 利用可能な AVFoundation デバイス:"
  ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A 40 'AVFoundation audio devices' || true
  exit 0
fi

set -a; source <(grep -E '^[A-Z_]+=' .env); set +a
GPU_SERVER_SSH_KEY="${GPU_SERVER_SSH_KEY/#\~/$HOME}"

SSH_CTRL_DIR="$HOME/.ssh/cm"
mkdir -p "$SSH_CTRL_DIR"
SSH_COMMON=(-i "${GPU_SERVER_SSH_KEY}" -o ConnectTimeout=5 \
  -o ControlMaster=auto \
  -o "ControlPath=${SSH_CTRL_DIR}/%r@%h:%p" \
  -o ControlPersist=600)
HOST="${GPU_SERVER_USER}@${GPU_SERVER_HOST}"
LOCAL_DIR="$HOME/.shubatapo_replies"
REMOTE_DIR="/tmp/shubatapo_replies"
TTS_URL="http://${GPU_SERVER_HOST}:8766/api/synthesize"
PROMPT_WAV="$LOCAL_DIR/_prompt_speak.wav"
PROMPT_TEXT="${SHUBATAPO_PROMPT_TEXT:-準備できたよー！で、今日は何だっけ？}"
MAC_MIC="${MAC_MIC:-:0}"

for arg in "$@"; do
  [[ "$arg" == --mic=* ]] && MAC_MIC="${arg#--mic=}"
done

mkdir -p "$LOCAL_DIR"

synth_subaru() {
  curl -s --max-time 15 -X POST "$TTS_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"text\":\"$1\",\"ref_file\":\"seg_000143.wav\"}" \
    -o "$2"
}

# プロンプト合成 (初回のみ)
if [ ! -f "$PROMPT_WAV" ]; then
  echo "[runner/mic] プロンプト音声を Subaru TTS で合成: ${PROMPT_TEXT}"
  synth_subaru "${PROMPT_TEXT}" "$PROMPT_WAV"
fi

# 既存の RTSP voice_loop を停止 (両立不可)
echo "[runner/mic] 既存の RTSP voice_loop (tmux) を停止し、入力源を切替..."
ssh "${SSH_COMMON[@]}" "$HOST" "tmux kill-session -t voice_loop 2>/dev/null; rm -f ${REMOTE_DIR}/*.wav" || true

echo "[runner/mic] Mac マイク (${MAC_MIC}) → GPU PC 送信開始..."
# ffmpeg -> ssh 経由で voice_loop 起動 (foreground pipe)
ffmpeg -nostdin -hide_banner -loglevel warning \
    -f avfoundation -i "$MAC_MIC" \
    -ac 1 -ar 16000 -f s16le - 2>/tmp/ffmpeg_mic.log \
  | ssh "${SSH_COMMON[@]}" "$HOST" \
      "cd ~/ShubaTapoChan && source .venv/bin/activate && SHUBATAPO_INPUT=stdin SHUBATAPO_AUDIO_GAIN=1.0 python -u -m shubatapo.dialog.voice_loop 2>&1 | tee /tmp/voice_loop.log" \
  &
PIPE_PID=$!

cleanup() {
  echo
  echo "[runner/mic] 終了: マイク送信プロセスを停止します"
  kill "$PIPE_PID" 2>/dev/null || true
  # リモート側も念のため kill (pipe 切断で自然に終わるはずだが)
  ssh "${SSH_COMMON[@]}" "$HOST" "pkill -f 'shubatapo.dialog.voice_loop' 2>/dev/null" || true
  exit 0
}
trap cleanup INT TERM

echo "[runner/mic] モデルロード待ち (15秒)..."
sleep 15
afplay "$PROMPT_WAV"

# 新規起動なので .played はクリア
PLAYED_FILE="$LOCAL_DIR/.played"
: > "$PLAYED_FILE"
rm -f "$LOCAL_DIR"/turn_*.wav

echo "[runner/mic] 待機中。Mac マイクに話しかけてください。Ctrl-C で終了。"
while true; do
  # パイプが死んだら終了
  if ! kill -0 "$PIPE_PID" 2>/dev/null; then
    echo "[runner/mic] マイク送信/voice_loop が終了しました"
    if [ -s /tmp/ffmpeg_mic.log ]; then
      echo "--- ffmpeg stderr tail ---"
      tail -20 /tmp/ffmpeg_mic.log
    fi
    break
  fi

  remote_list=$(ssh "${SSH_COMMON[@]}" "$HOST" "ls -1 ${REMOTE_DIR}/turn_*.wav 2>/dev/null | xargs -n1 basename 2>/dev/null" 2>/dev/null || true)
  if [ -n "$remote_list" ]; then
    latest_turn=$(echo "$remote_list" | sed -n 's/^turn_\([0-9][0-9]*\)_.*/\1/p' | sort -n | tail -1)
    while IFS= read -r base; do
      [ -z "$base" ] && continue
      grep -Fxq "$base" "$PLAYED_FILE" && continue
      base_turn=$(echo "$base" | sed -n 's/^turn_\([0-9][0-9]*\)_.*/\1/p')
      if [ -n "$latest_turn" ] && [ -n "$base_turn" ] && [ "$base_turn" != "$latest_turn" ]; then
        echo "$base" >> "$PLAYED_FILE"
        echo "[runner/mic] skip (古いターン): $base"
        continue
      fi
      scp "${SSH_COMMON[@]}" -q "${HOST}:${REMOTE_DIR}/$base" "$LOCAL_DIR/$base"
      echo "$base" >> "$PLAYED_FILE"
      echo "[runner/mic] 再生: $base"
      afplay "$LOCAL_DIR/$base"
    done <<< "$remote_list"
  fi
  sleep 0.3
done
