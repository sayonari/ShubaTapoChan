#!/usr/bin/env bash
# GPU PC上で実行想定。RTSPから10秒だけWAVを録音して疎通確認する。
# 使い方: ./scripts/smoke_rtsp.sh [出力ファイル] [秒数]
set -euo pipefail

cd "$(dirname "$0")/.."
# .env を読み込み (KEY=VALUE形式の行のみ抽出)
set -a
source <(grep -E '^[A-Z_]+=' .env)
set +a

OUT="${1:-/tmp/shubatapo_smoke.wav}"
DUR="${2:-10}"
RTSP="rtsp://${TAPO_CAMERA_USER}:${TAPO_CAMERA_PASSWORD}@${TAPO_CAMERA_HOST}:554/stream1"

echo "[smoke_rtsp] recording ${DUR}s from TAPO → ${OUT}"
# 音声だけ抜き出し、16kHz mono PCM WAV に変換
ffmpeg -y -hide_banner -loglevel warning \
  -rtsp_transport tcp \
  -i "$RTSP" \
  -vn -ac 1 -ar 16000 -acodec pcm_s16le \
  -t "$DUR" \
  "$OUT"

echo "[smoke_rtsp] done. file info:"
ffprobe -v error -show_streams "$OUT" | grep -E 'codec_name|sample_rate|channels|duration' | head -10
ls -lh "$OUT"
