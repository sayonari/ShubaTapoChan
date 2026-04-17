#!/usr/bin/env bash
# GPU PC 上で venv を作って依存をインストールする初期セットアップ。
# 実行場所: ShubaTapoChan プロジェクトのルート（GPU PC側）
# 使い方: ./scripts/setup_gpu.sh
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PY:-python3}"
VENV=".venv"

echo "[setup_gpu] python: $("$PY" --version)"
if [ ! -d "$VENV" ]; then
  echo "[setup_gpu] creating venv at ${VENV}"
  "$PY" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "${VENV}/bin/activate"

echo "[setup_gpu] upgrading pip"
python -m pip install --quiet --upgrade pip

echo "[setup_gpu] installing torch (CUDA 12.1 wheels)"
pip install --quiet --index-url https://download.pytorch.org/whl/cu121 torch torchaudio

echo "[setup_gpu] installing project deps"
pip install --quiet -e .

echo "[setup_gpu] done"
python - <<'PY'
import torch
print(f"torch: {torch.__version__}, cuda_available: {torch.cuda.is_available()}, device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}")
PY
