"""幂等初始化测试：重复初始化不能清掉/覆盖已有的测试记录。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.store import Store  # noqa: E402

SEED_FILE = BACKEND_DIR / "data" / "seed.json"


class MergeSeedTests(unittest.TestCase):
    def test_seed_file_loads(self) -> None:
        """共用的初始化数据文件可被加载。"""
        self.assertTrue(SEED_FILE.exists(), f"{SEED_FILE} 应存在")

    def test_repeated_init_keeps_existing_rows(self) -> None:
        """连续两次初始化：行数不变，第一次运行中改动的记录不被覆盖。"""
        store = Store()
        store.reload(replace=True)
        first_total = sum(len(store.rows(name)) for name in store.module_names())

        # 模拟运行期间人工/接口改了一条防雷元件测试记录
        from app.services.lightning import MODULE

        entry = store.find(MODULE, 2)
        self.assertIsNotNone(entry)
        entry["status"] = "已更换"
        entry["更换记录"] = "测试期间登记的更换记录，不应被初始化清掉"

        store.reload()  # 再次初始化：幂等，按 id 补齐
        second_total = sum(len(store.rows(name)) for name in store.module_names())
        self.assertEqual(first_total, second_total)

        kept = store.find(MODULE, 2)
        self.assertEqual(kept["status"], "已更换")
        self.assertIn("不应被初始化清掉", kept["更换记录"])

    def test_merge_only_fills_missing_ids(self) -> None:
        """merge_seed 只插入缺失 id，已存在的 id 不动；后补的新 id 能并入。"""
        store = Store()
        store.reload(replace=True)
        lightning = store.rows("lightning")
        original = {row["id"]: dict(row) for row in lightning}
        lightning[:] = [dict(row) for row in lightning if row["id"] != 3]  # 删掉一条模拟缺失
        lightning[0]["元件状态"] = "本地人工改过的状态"

        store.merge_seed({"lightning": list(original.values())})

        self.assertEqual(len(lightning), len(original))
        by_id = {row["id"]: row for row in lightning}
        self.assertEqual(by_id[1]["元件状态"], "本地人工改过的状态")  # 已有记录不覆盖
        self.assertEqual(by_id[3]["id"], 3)  # 缺失记录被补齐


class SeedFileContentTests(unittest.TestCase):
    """共用初始化数据里的防雷元件必须覆盖三种测试情形且字段完整。"""

    def setUp(self) -> None:
        self.store = Store()
        self.store.reload(replace=True)

    def test_lightning_scenarios_present(self) -> None:
        statuses = {row["status"] for row in self.store.rows("lightning")}
        for expected in ("泄露超标", "动作频繁", "已更换"):
            self.assertIn(expected, statuses, f"防雷元件初始化数据缺少情形：{expected}")

    def test_lightning_fields_complete(self) -> None:
        required = ["元件编号", "安装位置", "防护等级", "泄露电流", "动作次数", "测试日期", "更换记录"]
        for row in self.store.rows("lightning"):
            for field in required:
                self.assertTrue(str(row.get(field) or "").strip(), f"{row.get('元件编号')} 缺字段 {field}")


if __name__ == "__main__":
    unittest.main()
