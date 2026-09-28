"""内存数据仓库：启动时从 data/seed.json 加载一份可筛选、可流转的数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。

初始化策略是“按 id 补齐”：
- 数据文件里有、内存里没有的 id 才插入；
- 已存在的 id（含运行中被改过的测试记录）原样保留，不覆盖、不删除。
因此重复初始化是幂等的，不会把已有的测试记录清掉。
"""
from __future__ import annotations

from typing import Any

from app.seed import SeedDataError, load_seed_rows


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        # 数据文件缺失/损坏时服务仍可启动，由 /api/health 与 python -m app.bootstrap 报告
        self.init_error: str | None = None
        self.reload()

    def reload(self, *, replace: bool = False) -> None:
        """重新加载初始化数据。

        replace=False（默认）：按 id 补齐，保留已有记录，重复执行安全。
        replace=True：整体重置，仅供测试使用。
        """
        try:
            seed_rows = load_seed_rows()
        except SeedDataError as exc:
            self.init_error = str(exc)
            if replace:
                self._tables = {}
            return
        if replace:
            self._tables = {name: [dict(row) for row in rows] for name, rows in seed_rows.items()}
        else:
            self.merge_seed(seed_rows)
        self.init_error = None

    def merge_seed(self, seed_rows: dict[str, list[dict[str, Any]]]) -> None:
        """按模块、按 id 把初始化数据并入仓库：只补齐缺失 id，不动已有记录。"""
        for name, incoming in seed_rows.items():
            table = self._tables.setdefault(name, [])
            existing_ids = {int(row.get("id", 0)) for row in table}
            for row in incoming:
                if int(row.get("id", 0)) not in existing_ids:
                    table.append(dict(row))

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
