"""运行配置：端口、跨域、运行环境，以及数据与产物的约定位置。

约定路径（都可以用环境变量覆盖，换机器部署时无需改代码）：
- 初始化数据：<backend>/data/lightning_seed.json，本地与线上共用同一份；
- 运行时状态：<backend>/var/lightning.json，保存本地已产生的防雷元件记录，不入库；
- 运行日志：<backend>/logs/backend.log，run.sh 启动时自动落盘。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _env_path(key: str, default: Path) -> Path:
    raw = os.environ.get(key)
    return Path(raw).expanduser().resolve() if raw else default


@dataclass(frozen=True)
class Settings:
    app_name: str = "轨道交通信号检修管理平台"
    env: str = os.environ.get("APP_ENV", "local")
    port: int = int(os.environ.get("APP_PORT", "8000"))
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    page_size_default: int = 20
    page_size_max: int = 200
    # 防雷元件：初始化数据 / 运行时状态的约定位置
    lightning_seed_path: Path = _env_path(
        "LIGHTNING_SEED_PATH", BACKEND_ROOT / "data" / "lightning_seed.json"
    )
    lightning_state_path: Path = _env_path(
        "LIGHTNING_STATE_PATH", BACKEND_ROOT / "var" / "lightning.json"
    )
    log_path: Path = _env_path("APP_LOG_PATH", BACKEND_ROOT / "logs" / "backend.log")


settings = Settings()
