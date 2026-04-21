#!/usr/bin/env bash
# go2rtc を GPU PC 上で Docker 常駐起動するセットアップスクリプト。
#
# 事前条件:
#   - このスクリプトは GPU PC (Rasiel) 上で実行する想定
#   - .env に TAPO_CLOUD_PASSWORD が追加済みであること
#   - docker が利用可能であること
#
# やること:
#   1. config/go2rtc.yaml を .env の値で生成
#   2. docker で AlexxIT/go2rtc を起動 (名前: shubatapo-go2rtc, port 1984/8554)
#   3. 疎通チェック (http://127.0.0.1:1984/api/streams)
#
# 再実行すると既存コンテナを置き換える。

set -euo pipefail

cd "$(dirname "$0")/.."
set -a; source <(grep -E '^[A-Z_]+=' .env); set +a

: "${TAPO_CAMERA_HOST:?TAPO_CAMERA_HOST missing}"
: "${TAPO_CAMERA_USER:?TAPO_CAMERA_USER missing}"
: "${TAPO_CAMERA_PASSWORD:?TAPO_CAMERA_PASSWORD missing}"
: "${TAPO_CLOUD_PASSWORD:?TAPO_CLOUD_PASSWORD missing (TP-Link cloud account password, .env)}"

TEMPLATE="config/go2rtc.yaml.template"
CONFIG="config/go2rtc.yaml"
CONTAINER="shubatapo-go2rtc"
IMAGE="alexxit/go2rtc:latest"

[ -f "$TEMPLATE" ] || { echo "template not found: $TEMPLATE" >&2; exit 1; }

# RTSP URL に特殊文字が入っていると壊れるので sed で安全に置換する。
# @ / : などを含む可能性のある箇所を避けるため、全 URL エンコード相当は go2rtc 側に任せる。
# ここでは単純置換。パスワードに # や % が混じる場合はユーザ側で見直す。
sed \
  -e "s|__RTSP_USER__|${TAPO_CAMERA_USER}|g" \
  -e "s|__RTSP_PASS__|${TAPO_CAMERA_PASSWORD}|g" \
  -e "s|__TAPO_HOST__|${TAPO_CAMERA_HOST}|g" \
  -e "s|__TAPO_CLOUD_PASSWORD__|${TAPO_CLOUD_PASSWORD}|g" \
  "$TEMPLATE" > "$CONFIG"

echo "[setup_go2rtc] generated $CONFIG"

# 既存コンテナを止めて作り直す
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[setup_go2rtc] removing existing container $CONTAINER"
  docker rm -f "$CONTAINER" >/dev/null
fi

docker pull "$IMAGE" >/dev/null

# WAV 再生用に replies/fillers ディレクトリをコンテナ内でも同じパスで見えるようマウント
mkdir -p /tmp/shubatapo_replies /tmp/shubatapo_fillers

docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --network host \
  -v "$(pwd)/config/go2rtc.yaml:/config/go2rtc.yaml:ro" \
  -v /tmp/shubatapo_replies:/tmp/shubatapo_replies:ro \
  -v /tmp/shubatapo_fillers:/tmp/shubatapo_fillers:ro \
  "$IMAGE" \
  -config /config/go2rtc.yaml

echo "[setup_go2rtc] started container $CONTAINER"
sleep 2
echo "[setup_go2rtc] health check ..."
if curl -fsS "http://127.0.0.1:1984/api/streams" >/dev/null; then
  echo "[setup_go2rtc] OK. WebUI: http://${GPU_SERVER_HOST:-<host>}:1984/"
else
  echo "[setup_go2rtc] 起動直後で API が返らない可能性あり。docker logs $CONTAINER を確認。"
fi
