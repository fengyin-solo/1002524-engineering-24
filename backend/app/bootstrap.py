"""启动前自检与幂等初始化。

两类问题分开报，退出码也不同，换机部署时一眼能看出是哪一类：
- 依赖没装好（fastapi / uvicorn / pydantic 导入失败）→ 退出码 2
- 初始化数据缺失或损坏（data/seed.json）        → 退出码 3
- 数据在但防雷元件场景不全                       → 退出码 4
全部通过 → 0。

用法：
    python -m app.bootstrap selfcheck   # 只自检，不改数据
    python -m app.bootstrap init        # 幂等初始化（按 id 补齐）后自检
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass

from app.config import settings
from app.store import store

EXIT_OK = 0
EXIT_DEPENDENCY = 2
EXIT_DATA_MISSING = 3
EXIT_DATA_INCOMPLETE = 4

# 运行时必须能导入的第三方包；提示语直接给出安装命令
REQUIRED_PACKAGES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "pydantic": "pydantic",
}

# 防雷元件必须覆盖的测试情形
LIGHTNING_SCENARIO_STATUSES = ["泄露超标", "动作频繁", "已更换"]
LIGHTNING_REQUIRED_FIELDS = ["元件编号", "安装位置", "防护等级", "泄露电流", "动作次数", "测试日期", "更换记录"]
LIGHTNING_MODULE = "lightning"


@dataclass
class CheckResult:
    name: str
    kind: str  # dependency | data
    ok: bool
    detail: str


def check_dependencies() -> list[CheckResult]:
    """逐个确认运行依赖已安装；缺失时给出 pip 安装提示，而不是一串 ImportError。"""
    results: list[CheckResult] = []
    for import_name, pip_name in REQUIRED_PACKAGES.items():
        spec = importlib.util.find_spec(import_name)
        if spec is None:
            results.append(CheckResult(
                name=f"依赖：{import_name}",
                kind="dependency",
                ok=False,
                detail=f"未安装，执行 .venv/bin/pip install -r requirements.txt（缺包 {pip_name}）",
            ))
        else:
            version = getattr(_safe_import(import_name), "__version__", "未知版本")
            results.append(CheckResult(
                name=f"依赖：{import_name}",
                kind="dependency",
                ok=True,
                detail=f"已安装（{version}）",
            ))
    return results


def _safe_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:  # 包存在但导入失败按已安装处理，具体报错交给启动日志
        return type("Stub", (), {"__version__": "未知版本"})()


def check_seed_file() -> CheckResult:
    """初始化数据文件是否存在且可解析。"""
    if store.init_error:
        return CheckResult(name="初始化数据", kind="data", ok=False, detail=store.init_error)
    return CheckResult(
        name="初始化数据",
        kind="data",
        ok=True,
        detail=f"已加载 {len(store.module_names())} 个模块（{settings.seed_file}）",
    )


def check_lightning() -> CheckResult:
    """防雷元件记录要覆盖泄露超标、动作频繁、已更换三种情形且字段完整。"""
    if store.init_error:
        return CheckResult(
            name="防雷元件样例",
            kind="data",
            ok=False,
            detail="初始化数据不可用，防雷元件记录无法校验",
        )
    rows = store.rows(LIGHTNING_MODULE)
    if not rows:
        return CheckResult(
            name="防雷元件样例",
            kind="data",
            ok=False,
            detail="防雷元件记录为空，请确认初始化数据是否正确",
        )

    statuses = {str(row.get("status")) for row in rows}
    missing_statuses = [s for s in LIGHTNING_SCENARIO_STATUSES if s not in statuses]
    incomplete: list[str] = []
    for row in rows:
        code = row.get("元件编号", f"id={row.get('id')}")
        for field in LIGHTNING_REQUIRED_FIELDS:
            if not str(row.get(field) or "").strip():
                incomplete.append(f"{code} 缺字段「{field}」")

    problems = []
    if missing_statuses:
        problems.append("缺少情形：" + "、".join(missing_statuses))
    if incomplete:
        problems.append("；".join(incomplete))
    if problems:
        return CheckResult(
            name="防雷元件样例",
            kind="data",
            ok=False,
            detail="；".join(problems),
        )
    return CheckResult(
        name="防雷元件样例",
        kind="data",
        ok=True,
        detail=f"共 {len(rows)} 条，已覆盖泄露超标 / 动作频繁 / 已更换三种情形",
    )


def run_checks() -> dict[str, object]:
    checks = check_dependencies() + [check_seed_file(), check_lightning()]
    return {
        "ok": all(item.ok for item in checks),
        "checks": [asdict(item) for item in checks],
    }


def init_idempotent() -> dict[str, int]:
    """幂等初始化：按 id 补齐缺失记录，保留已有测试记录。返回初始化前后行数。"""
    before = {name: len(store.rows(name)) for name in store.module_names()}
    store.reload()
    after = {name: len(store.rows(name)) for name in store.module_names()}
    added = sum(after.get(name, 0) - before.get(name, 0) for name in after)
    return {"added_rows": added, "total_rows": sum(after.values()), "total_modules": len(after)}


def _print_report(report: dict[str, object]) -> None:
    for item in report["checks"]:
        mark = "PASS" if item["ok"] else "FAIL"
        print(f"[{mark}] {item['name']}：{item['detail']}")
    print("自检结论：" + ("全部通过" if report["ok"] else "存在失败项，见上方 FAIL"))


def _exit_code(report: dict[str, object]) -> int:
    """优先级：依赖缺失(2) > 初始化数据缺失/损坏(3) > 防雷样例不全(4)。"""
    failed = [c for c in report["checks"] if not c["ok"]]
    if any(c["kind"] == "dependency" for c in failed):
        return EXIT_DEPENDENCY
    if any(c["name"] == "初始化数据" for c in failed):
        return EXIT_DATA_MISSING
    if any(c["name"] == "防雷元件样例" for c in failed):
        return EXIT_DATA_INCOMPLETE
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="防雷元件本地开发：幂等初始化与启动前自检")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出自检结果")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init", help="幂等初始化（保留已有测试记录）后自检")
    sub.add_parser("selfcheck", help="只自检，不改数据")
    args = parser.parse_args(argv)

    if args.command == "init":
        summary = init_idempotent()
        if store.init_error:
            print(f"初始化未执行成功：{store.init_error}")
        else:
            print(
                f"初始化完成：新增 {summary['added_rows']} 条，"
                f"现有 {summary['total_rows']} 条 / {summary['total_modules']} 个模块（已有记录未覆盖、未删除）"
            )

    report = run_checks()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return EXIT_OK if report["ok"] else _exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
