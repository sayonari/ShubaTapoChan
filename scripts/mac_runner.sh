#!/usr/bin/env bash
# Mac 側で対話を進行させるランナー。
#
# 仕組み:
#   - GPU PC の tmux セッション `voice_loop` で voice_loop を常駐起動
#   - /tmp/shubatapo_replies/turn_*.wav を GPU PC にポーリングで問い合わせ
#   - 未再生ファイルを全て名前順で scp + afplay （ack→main の順に鳴る）
#   - 起動時にリモートの既存 WAV を全部「再生済」扱いにして古い応答を再生しない
#   - 起動時に Subaru 合成の挨拶プロンプトを1回再生
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

# SSH ControlMaster を使って毎回のハンドシェイクを省き、ポーリング遅延を抑える。
# 初回接続で socket を作り、以後は再利用する（ControlPersist=10min）。
SSH_CTRL_DIR="$HOME/.ssh/cm"
mkdir -p "$SSH_CTRL_DIR"
SSH_COMMON="-i ${GPU_SERVER_SSH_KEY} -o ConnectTimeout=5 \
  -o ControlMaster=auto \
  -o ControlPath=${SSH_CTRL_DIR}/%r@%h:%p \
  -o ControlPersist=600"
SSH="ssh ${SSH_COMMON}"
SCP="scp ${SSH_COMMON}"
HOST="${GPU_SERVER_USER}@${GPU_SERVER_HOST}"
LOCAL_DIR="$HOME/.shubatapo_replies"
REMOTE_DIR="/tmp/shubatapo_replies"
REMOTE_LOG="/tmp/voice_loop.log"
TMUX_SESSION="voice_loop"
TTS_URL="http://${GPU_SERVER_HOST}:8766/api/synthesize"
PROMPT_WAV="$LOCAL_DIR/_prompt_speak.wav"
# 短すぎるとGPT-SoVITS合成が崩れるので自然な長さの挨拶にする
PROMPT_TEXT="${SHUBATAPO_PROMPT_TEXT:-準備できたよー！で、今日は何だっけ？}"
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
  echo "[runner] プロンプト音声を Subaru TTS で合成: ${PROMPT_TEXT}"
  synth_subaru "${PROMPT_TEXT}" "$PROMPT_WAV"
fi

# 起動時のプロンプト
afplay "$PROMPT_WAV"

# .played: 既に取得/再生したファイル名を1行1つで保存。
# 起動時点でリモートに存在する WAV は全て「再生済」扱いにして古い応答の再生を防ぐ。
PLAYED_FILE="$LOCAL_DIR/.played"
: > "$PLAYED_FILE"
$SSH "$HOST" "ls -1 ${REMOTE_DIR}/turn_*.wav 2>/dev/null | xargs -n1 basename 2>/dev/null" \
  >> "$PLAYED_FILE" 2>/dev/null || true

echo "[runner] 待機中。TAPO に話しかけてください。Ctrl-C で終了。"
# SSH 接続を事前に張っておく（ControlMaster の socket 初期化）
$SSH -fN "$HOST" 2>/dev/null || true

# ノイズ誤認識などで古いターンの応答が溜まると、再生が遅延して体感が悪化する。
# 各ポーリングで「最新ターン」を判定し、それより古いターンは再生せず skip する。
while true; do
  # リモートの全 WAV を名前昇順で取得。turn_001_ack < turn_001_main < turn_002_ack ... の順になる。
  remote_list=$($SSH "$HOST" "ls -1 ${REMOTE_DIR}/turn_*.wav 2>/dev/null | xargs -n1 basename 2>/dev/null" 2>/dev/null || true)
  if [ -n "$remote_list" ]; then
    # 最新ターン番号 (例: turn_020_main.wav → 020)
    latest_turn=$(echo "$remote_list" | sed -n 's/^turn_\([0-9][0-9]*\)_.*/\1/p' | sort -n | tail -1)
    while IFS= read -r base; do
      [ -z "$base" ] && continue
      if grep -Fxq "$base" "$PLAYED_FILE"; then
        continue
      fi
      # ファイル名から turn 番号抽出
      base_turn=$(echo "$base" | sed -n 's/^turn_\([0-9][0-9]*\)_.*/\1/p')
      if [ -n "$latest_turn" ] && [ -n "$base_turn" ] && [ "$base_turn" != "$latest_turn" ]; then
        # 古いターンはダウンロードも再生もせず「再生済」扱いでスキップ
        echo "$base" >> "$PLAYED_FILE"
        echo "[runner] skip (古いターン): $base (最新=$latest_turn)"
        continue
      fi
      $SCP -q "${HOST}:${REMOTE_DIR}/$base" "$LOCAL_DIR/$base"
      echo "$base" >> "$PLAYED_FILE"
      echo "[runner] 再生: $base"
      afplay "$LOCAL_DIR/$base"
    done <<< "$remote_list"
  fi
  sleep 0.3
done
