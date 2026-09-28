"""运行配置：端口、跨域、运行环境与目录约定。

所有路径都以 backend/ 为根，初始化数据与日志的位置在此统一定义，
本地开发与容器内跑的是同一份 data/seed.json。
可用同名环境变量覆盖：APP_ENV / APP_HOST / APP_PORT / SEED_FILE / LOG_DIR。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"
LOG_DIR = Path(os.environ.get("LOG_DIR", str(BASE_DIR / "logs")))
DEFAULT_SEED_FILE = DATA_DIR / "seed.json"


def _seed_file() -> Path:
    return Path(os.environ.get("SEED_FILE", str(DEFAULT_SEED_FILE)))


@dataclass(frozen=True)
class Settings:
    app_name: str = "轨道交通信号检修管理平台"
    env: str = os.environ.get("APP_ENV", "local")
    host: str = os.environ.get("APP_HOST", "127.0.0.1")
    port: int = int(os.environ.get("APP_PORT", "8000"))
    seed_file: Path = field(default_factory=_seed_file)
    log_dir: Path = field(default_factory=lambda: LOG_DIR)
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    page_size_default: int = 20
    page_size_max: int = 200


settings = Settings()
