"""防雷元件数据初始化与自检的单元测试（仅标准库，运行：python -m unittest discover -s tests）。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import bootstrap

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "lightning_seed.json"


class SeedDataTests(unittest.TestCase):
    def test_seed_covers_three_required_situations_plus_baseline(self) -> None:
        rows = bootstrap.load_canonical_seed(SEED_PATH)
        statuses = {row["status"] for row in rows}
        # 需求点名的三种情形：泄露电流超标、动作频繁、已更换
        for expected in ["泄露超标", "动作频繁", "已更换"]:
            self.assertIn(expected, statuses)
        # 另含一条正常基线
        self.assertIn("防护有效", statuses)

    def test_business_keys_unique_and_fields_complete(self) -> None:
        rows = bootstrap.load_canonical_seed(SEED_PATH)
        keys = [row[bootstrap.BUSINESS_KEY] for row in rows]
        self.assertEqual(len(keys), len(set(keys)))
        for row in rows:
            for field in ["id", "安装位置", "防护等级", "泄露电流", "动作次数", "测试日期"]:
                self.assertTrue(str(row.get(field, "")).strip(), f"{row.get('元件编号')} 缺字段 {field}")

    def test_sha256_is_stable(self) -> None:
        # 同一份文件多次读取哈希一致；换机部署对比该值即可确认初始化数据一致
        self.assertEqual(bootstrap.seed_sha256(SEED_PATH), bootstrap.seed_sha256(SEED_PATH))
        self.assertIsNone(bootstrap.seed_sha256(Path("/nonexistent/lightning_seed.json")))


class InitIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "lightning.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_fresh_init_materializes_all_seed_rows(self) -> None:
        result = bootstrap.materialize(seed_path=SEED_PATH, state_path=self.state)
        self.assertEqual(result["inserted"], 4)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["total"], 4)
        self.assertTrue(self.state.is_file())

    def test_reinit_does_not_clear_or_overwrite_existing_records(self) -> None:
        first = bootstrap.materialize(seed_path=SEED_PATH, state_path=self.state)
        self.assertEqual(first["inserted"], 4)
        # 模拟本地测试改动：把 LIGH-0002 标记为已更换、改测试日期，再新增一条本地记录
        rows = bootstrap.load_runtime_rows(self.state)
        for row in rows:
            if row["元件编号"] == "LIGH-0002":
                row["status"] = "已更换"
                row["测试日期"] = "2026-09-27"
        rows.append({
            "id": 99, "status": "防护有效", "pending": True, "abnormal": False,
            "元件编号": "LIGH-LOCAL-1", "安装位置": "本地临时测点", "防护等级": "II级",
            "泄露电流": "0.01mA", "动作次数": "0", "测试日期": "2026-09-27",
            "更换记录": "未更换", "元件状态": "本地新建",
        })
        bootstrap.save_runtime_rows(rows, seed_path=SEED_PATH, state_path=self.state)

        second = bootstrap.materialize(seed_path=SEED_PATH, state_path=self.state)
        # 重复初始化：一条都不再新增，本地改动与本地记录全部保留
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["skipped"], 4)
        self.assertEqual(second["total"], 5)
        after = {row["元件编号"]: row for row in second["rows"]}
        self.assertEqual(after["LIGH-0002"]["status"], "已更换")
        self.assertEqual(after["LIGH-0002"]["测试日期"], "2026-09-27")
        self.assertIn("LIGH-LOCAL-1", after)
        self.assertEqual(after["LIGH-LOCAL-1"]["元件状态"], "本地新建")

    def test_reinit_backfills_when_some_seed_rows_missing(self) -> None:
        # 模拟历史数据只有 2 条：再初始化只补缺，不清存量
        canonical = bootstrap.load_canonical_seed(SEED_PATH)
        bootstrap.save_runtime_rows(
            canonical[:2], seed_path=SEED_PATH, state_path=self.state
        )
        result = bootstrap.materialize(seed_path=SEED_PATH, state_path=self.state)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["total"], 4)

    def test_fresh_machine_state_is_deterministic(self) -> None:
        # 两台全新机器各自初始化：状态文件除路径无关内容外完全一致
        state_a = self.tmp / "a" / "lightning.json"
        state_b = self.tmp / "b" / "lightning.json"
        bootstrap.materialize(seed_path=SEED_PATH, state_path=state_a)
        bootstrap.materialize(seed_path=SEED_PATH, state_path=state_b)
        payload_a = json.loads(state_a.read_text(encoding="utf-8"))
        payload_b = json.loads(state_b.read_text(encoding="utf-8"))
        self.assertEqual(payload_a["rows"], payload_b["rows"])
        self.assertEqual(payload_a["seed_sha256"], payload_b["seed_sha256"])


class SelfcheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "lightning.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_selfcheck_passes_after_init(self) -> None:
        result = bootstrap.materialize(seed_path=SEED_PATH, state_path=self.state)
        report = bootstrap.run_selfcheck(
            result["rows"], seed_path=SEED_PATH, state_path=self.state
        )
        self.assertTrue(report["ok"], report["message"])
        self.assertIsNone(report["reason"])
        self.assertEqual(report["data"]["rows"], 4)
        self.assertEqual(report["data"]["scenarios_missing"], [])

    def test_selfcheck_reports_data_missing_with_empty_rows(self) -> None:
        report = bootstrap.run_selfcheck(
            [], seed_path=SEED_PATH, state_path=self.state
        )
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "data_missing")
        self.assertIn("尚未初始化", report["message"])

    def test_selfcheck_reports_data_missing_when_seed_file_absent(self) -> None:
        report = bootstrap.run_selfcheck(
            None,
            seed_path=self.tmp / "no_such_seed.json",
            state_path=self.state,
        )
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "data_missing")
        self.assertIn("初始化数据文件缺失", report["message"])

    def test_selfcheck_distinguishes_dependency_missing(self) -> None:
        rows = bootstrap.load_canonical_seed(SEED_PATH)
        report = bootstrap.run_selfcheck(
            rows,
            seed_path=SEED_PATH,
            state_path=self.state,
        )
        self.assertTrue(report["ok"])
        # 伪造一个不存在的依赖：必须归类为 dependency_missing 且给出 pip 安装名
        fake_required = {"definitely_not_installed_pkg_xyz": "definitely-not-installed-pkg-xyz"}
        missing = bootstrap.check_dependencies(fake_required)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["pip_name"], "definitely-not-installed-pkg-xyz")

    def test_selfcheck_reports_incomplete_scenarios(self) -> None:
        # 只有正常与超标两种情形时，应指出还缺动作频繁与已更换
        rows = [
            row for row in bootstrap.load_canonical_seed(SEED_PATH)
            if row["status"] in ("防护有效", "泄露超标")
        ]
        report = bootstrap.run_selfcheck(
            rows, seed_path=SEED_PATH, state_path=self.state
        )
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "data_missing")
        self.assertEqual(report["data"]["scenarios_missing"], ["动作频繁", "已更换"])


if __name__ == "__main__":
    unittest.main()
