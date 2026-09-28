"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。

防雷元件（lightning）是例外：它的初始化数据来自仓库内的
data/lightning_seed.json（本地与线上共用），启动时幂等合并到
var/lightning.json，运行期的新增与状态流转也会写回该文件，
因此换台机器重新部署后防雷元件数据与自检 sha256 保持一致。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app import bootstrap
from app.config import settings
from app.seed import SEED_ROWS

logger = logging.getLogger(__name__)

PERSISTED_MODULES = {"lightning"}


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows]
            for name, rows in SEED_ROWS.items()
            if name not in PERSISTED_MODULES
        }
        # 模块名 -> 持久化回调（目前只有防雷元件需要落盘）
        self._persisters: dict[str, Callable[[list[dict[str, Any]]], None]] = {}
        self._init_lightning()

    # ------------------------------------------------------------ 防雷元件

    def _init_lightning(self) -> None:
        """启动装配：成功则内存与本地状态文件一致；种子缺失时留空表交由自检报错。"""
        try:
            result = bootstrap.materialize()
        except bootstrap.SeedError as exc:
            logger.warning("防雷元件初始化跳过：%s", exc)
            self._tables[bootstrap.MODULE] = []
            return
        self._tables[bootstrap.MODULE] = result["rows"]
        self._persisters[bootstrap.MODULE] = lambda rows: bootstrap.save_runtime_rows(
            rows,
            seed_path=settings.lightning_seed_path,
            state_path=settings.lightning_state_path,
        )

    def reinit_lightning(self) -> dict[str, Any]:
        """重新执行幂等初始化：只补缺，不清空、不覆盖已有测试记录。"""
        result = bootstrap.materialize()
        self._tables[bootstrap.MODULE] = result["rows"]
        return result

    def persist(self, module: str) -> None:
        """把某模块的当前内存数据写回本地状态文件；未注册的模块静默跳过。"""
        persister = self._persisters.get(module)
        if persister is None:
            return
        try:
            persister(self.rows(module))
        except OSError as exc:  # 落盘失败不应阻断接口，但要留下日志
            logger.warning("模块 %s 状态写回失败：%s", module, exc)

    # -------------------------------------------------------------- 通用接口

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
