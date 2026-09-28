"""初始化数据加载：本地与线上共用同一份 data/seed.json。

数据文件缺失、不是合法 JSON、或内容结构不对时抛 SeedDataError，
由自检（app/bootstrap.py）统一翻译成“数据缺失/损坏”的可读结论，
避免把数据问题误报成依赖没装好。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


class SeedDataError(RuntimeError):
    """初始化数据无法使用：文件缺失、JSON 非法或结构不符合约定。"""


def load_seed_rows(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """读取并校验初始化数据。

    约定：顶层是 {模块名: [记录, ...]}，每条记录必须带整型 id。
    """
    seed_path = Path(path) if path is not None else settings.seed_file
    if not seed_path.exists():
        raise SeedDataError(f"初始化数据文件缺失：{seed_path}")
    try:
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SeedDataError(f"初始化数据不是合法 JSON：{seed_path}（第 {exc.lineno} 行附近）") from exc
    except OSError as exc:
        raise SeedDataError(f"初始化数据无法读取：{seed_path}（{exc}）") from exc

    if not isinstance(raw, dict):
        raise SeedDataError(f"初始化数据结构应为对象映射，实际是 {type(raw).__name__}：{seed_path}")

    rows: dict[str, list[dict[str, Any]]] = {}
    for module, items in raw.items():
        if not isinstance(items, list):
            raise SeedDataError(f"模块「{module}」的记录应为列表，实际是 {type(items).__name__}")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise SeedDataError(f"模块「{module}」第 {index + 1} 条记录不是对象")
            if "id" not in item:
                raise SeedDataError(f"模块「{module}」第 {index + 1} 条记录缺少 id 字段")
            normalized.append(dict(item))
        rows[module] = normalized
    return rows
