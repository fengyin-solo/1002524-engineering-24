"""自检分类测试：失败时要分清是依赖没装好还是初始化数据缺失。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import bootstrap  # noqa: E402
from app.store import Store  # noqa: E402


class DependencyCheckTests(unittest.TestCase):
    def test_missing_dependency_reported_as_dependency_kind(self) -> None:
        """找不到 fastapi 时结论必须归类为 dependency，并给出 pip 安装提示。"""
        with mock.patch.object(bootstrap.importlib.util, "find_spec", return_value=None):
            results = bootstrap.check_dependencies()
        self.assertTrue(any(not r.ok and r.kind == "dependency" for r in results))
        failed = [r for r in results if not r.ok]
        self.assertTrue(any("pip install" in r.detail for r in failed))


class LightningCheckTests(unittest.TestCase):
    def _store_with_rows(self, rows: list[dict]) -> Store:
        store = Store.__new__(Store)
        store.init_error = None
        store._tables = {"lightning": rows}
        return store

    def _full_row(self, status: str) -> dict:
        return {
            "id": abs(hash(status)) % 1000,
            "status": status,
            "元件编号": f"LIGH-{status}",
            "安装位置": "样例位置",
            "防护等级": "I级",
            "泄露电流": "12 μA",
            "动作次数": "0",
            "测试日期": "2026-09-10",
            "更换记录": "无",
        }

    def test_missing_scenario_fails_as_data(self) -> None:
        store = self._store_with_rows([self._full_row("防护有效")])
        with mock.patch.object(bootstrap, "store", store):
            result = bootstrap.check_lightning()
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "data")
        self.assertIn("动作频繁", result.detail)

    def test_all_scenarios_pass(self) -> None:
        rows = [self._full_row(s) for s in ("防护有效", "泄露超标", "动作频繁", "已更换")]
        store = self._store_with_rows(rows)
        with mock.patch.object(bootstrap, "store", store):
            result = bootstrap.check_lightning()
        self.assertTrue(result.ok, result.detail)

    def test_data_load_error_surfaces_as_data_problem(self) -> None:
        """seed.json 缺失时，防雷元件检查应说明数据不可用，而不是报依赖问题。"""
        store = Store.__new__(Store)
        store.init_error = "初始化数据文件缺失：/nonexistent/seed.json"
        store._tables = {}
        with mock.patch.object(bootstrap, "store", store):
            result = bootstrap.check_lightning()
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "data")


class ExitCodeTests(unittest.TestCase):
    def _report(self, names_kinds: list[tuple[str, str]]) -> dict:
        return {"ok": not names_kinds, "checks": [
            {"name": n, "kind": k, "ok": False, "detail": "x"} for n, k in names_kinds
        ]}

    def test_exit_codes_are_distinct(self) -> None:
        self.assertEqual(bootstrap._exit_code(self._report([("依赖：fastapi", "dependency")])), 2)
        self.assertEqual(bootstrap._exit_code(self._report([("初始化数据", "data")])), 3)
        self.assertEqual(bootstrap._exit_code(self._report([("防雷元件样例", "data")])), 4)
        self.assertEqual(bootstrap._exit_code({"ok": True, "checks": []}), 0)


class InitIdempotentTests(unittest.TestCase):
    def test_init_twice_adds_nothing_second_time(self) -> None:
        """对同一份 seed.json 连续初始化，第二次新增数必须为 0。"""
        payload = {"lightning": [
            {"id": 1, "status": "防护有效", "元件编号": "L1", "安装位置": "a",
             "防护等级": "x", "泄露电流": "1", "动作次数": "0",
             "测试日期": "2026-09-01", "更换记录": "无"},
            {"id": 2, "status": "泄露超标", "元件编号": "L2", "安装位置": "b",
             "防护等级": "x", "泄露电流": "90", "动作次数": "1",
             "测试日期": "2026-09-02", "更换记录": "无"},
            {"id": 3, "status": "动作频繁", "元件编号": "L3", "安装位置": "c",
             "防护等级": "x", "泄露电流": "20", "动作次数": "9",
             "测试日期": "2026-09-03", "更换记录": "无"},
            {"id": 4, "status": "已更换", "元件编号": "L4", "安装位置": "d",
             "防护等级": "x", "泄露电流": "5", "动作次数": "0",
             "测试日期": "2026-09-04", "更换记录": "2026-09-05 更换"},
        ]}
        fresh = Store.__new__(Store)
        fresh._tables = {}
        fresh.init_error = None
        with mock.patch.object(bootstrap, "store", fresh), \
                mock.patch("app.store.load_seed_rows", return_value=payload):
            first = bootstrap.init_idempotent()
            second = bootstrap.init_idempotent()
        self.assertGreater(first["total_rows"], 0)
        self.assertEqual(second["added_rows"], 0)
        self.assertEqual(first["total_rows"], second["total_rows"])


if __name__ == "__main__":
    unittest.main()
