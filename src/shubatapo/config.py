"""Load runtime config from .env (project root)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class Config:
    gpu_server_host: str
    gpu_server_user: str
    gpu_server_ssh_key: str
    tapo_host: str
    tapo_user: str
    tapo_password: str

    @property
    def rtsp_url(self) -> str:
        return f"rtsp://{self.tapo_user}:{self.tapo_password}@{self.tapo_host}:554/stream1"


def load_config() -> Config:
    load_dotenv(ENV_PATH)
    missing = [
        k for k in (
            "GPU_SERVER_HOST", "GPU_SERVER_USER", "GPU_SERVER_SSH_KEY",
            "TAPO_CAMERA_HOST", "TAPO_CAMERA_USER", "TAPO_CAMERA_PASSWORD",
        ) if not os.getenv(k)
    ]
    if missing:
        raise RuntimeError(f".env に必須キーが未設定: {missing}")
    return Config(
        gpu_server_host=os.environ["GPU_SERVER_HOST"],
        gpu_server_user=os.environ["GPU_SERVER_USER"],
        gpu_server_ssh_key=os.path.expanduser(os.environ["GPU_SERVER_SSH_KEY"]),
        tapo_host=os.environ["TAPO_CAMERA_HOST"],
        tapo_user=os.environ["TAPO_CAMERA_USER"],
        tapo_password=os.environ["TAPO_CAMERA_PASSWORD"],
    )
