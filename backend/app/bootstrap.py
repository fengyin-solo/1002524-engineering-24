"""防雷元件本地开发与数据初始化。

职责边界：
- 这里只负责「把同一份初始化数据装进内存/本地状态文件」与「自检环境」，
  不包含状态流转、必填校验等业务规则（那些仍在 app/services/lightning.py）。
- 初始化幂等：以业务键（元件编号）合并，重复执行只补缺，不会覆盖或清空
  已有的测试记录（id、status、测试日期等运行期改动原样保留）。
- 本地与线上共用 data/lightning_seed.json；该文件的 sha256 由自检接口返回，
  换机器部署后 hash 一致即可证明初始化数据一致。

命令行：python -m app.bootstrap          # 幂等初始化并打印结果
         python -m app.bootstrap --check  # 只自检，失败时退出码非 0
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from app.config import settings

MODULE = "lightning"
BUSINESS_KEY = "元件编号"
# 启动后自检必须能看到的四种情形
REQUIRED_SCENARIOS = ["防护有效", "泄露超标", "动作频繁", "已更换"]
# 服务运行必需的第三方包；标准库不在此列
REQUIRED_PACKAGES: dict[str, str] = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "pydantic": "pydantic",
}


# ---------------------------------------------------------------- 种子文件

def seed_sha256(seed_path: Path | None = None) -> str | None:
    """返回种子文件的 sha256；文件不存在时为 None。"""
    path = seed_path or settings.lightning_seed_path
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_canonical_seed(seed_path: Path | None = None) -> list[dict[str, Any]]:
    """读取规范种子文件。

    文件缺失或格式不对时抛 SeedError，由调用方归类为 data_missing；
    本函数不吞异常，保证「数据缺失」能被自检明确指出。
    """
    path = seed_path or settings.lightning_seed_path
    if not path.is_file():
        raise SeedError(f"初始化数据文件缺失：{path}", "data_missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SeedError(f"初始化数据文件无法解析（{path}）：{exc}", "data_missing") from exc
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise SeedError(f"初始化数据为空或缺少 rows：{path}", "data_missing")
    clean: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not str(row.get(BUSINESS_KEY, "")).strip():
            raise SeedError(f"初始化数据第 {index} 行缺少业务键「{BUSINESS_KEY}」", "data_missing")
        clean.append(dict(row))
    return clean


class SeedError(RuntimeError):
    """种子数据不可用；reason 固定为 data_missing，供自检归类。"""

    def __init__(self, message: str, reason: str = "data_missing") -> None:
        super().__init__(message)
        self.reason = reason


# ------------------------------------------------------------ 运行时状态

def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def load_runtime_rows(state_path: Path | None = None) -> list[dict[str, Any]]:
    """读取本地运行时状态；文件不存在（全新机器）时返回空列表。"""
    path = state_path or settings.lightning_state_path
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # 状态文件损坏不致命：当作没有本地记录处理，规范种子仍可装配
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else None
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def save_runtime_rows(
    rows: list[dict[str, Any]],
    *,
    seed_path: Path | None = None,
    state_path: Path | None = None,
) -> Path:
    """把当前防雷元件记录持久化到约定位置（原子写入，内容排序，跨机可比对）。"""
    target = state_path or settings.lightning_state_path
    payload = {
        "module": MODULE,
        "business_key": BUSINESS_KEY,
        "seed_sha256": seed_sha256(seed_path),
        "rows": rows,
    }
    _write_json_atomic(target, payload)
    return target


def merge_seed(
    existing: list[dict[str, Any]],
    canonical: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """幂等合并：已有的按业务键原样保留（测试记录不清不覆盖），只补缺失的种子行。

    返回 (合并后列表, 新增条数, 跳过条数)。种子行追加在已有记录之后，
    并给未占用的 id，避免与本地新建记录撞 id。
    """
    merged = [dict(row) for row in existing]
    seen_keys = {
        str(row.get(BUSINESS_KEY, "")).strip()
        for row in merged
        if str(row.get(BUSINESS_KEY, "")).strip()
    }
    next_id = max((int(row.get("id", 0) or 0) for row in merged), default=0)
    inserted = skipped = 0
    for row in canonical:
        key = str(row.get(BUSINESS_KEY, "")).strip()
        if key in seen_keys:
            skipped += 1
            continue
        fresh = dict(row)
        next_id = max(next_id + 1, int(fresh.get("id", 0) or 0))
        fresh["id"] = next_id
        merged.append(fresh)
        seen_keys.add(key)
        inserted += 1
    return merged, inserted, skipped


# ------------------------------------------------------------------ 自检

def check_dependencies(required: dict[str, str] | None = None) -> list[dict[str, str]]:
    """检查服务依赖是否装好；返回缺失项列表（import_name -> pip 安装名）。"""
    missing: list[dict[str, str]] = []
    for import_name, pip_name in (required or REQUIRED_PACKAGES).items():
        if importlib.util.find_spec(import_name) is None:
            missing.append({"package": import_name, "pip_name": pip_name})
    return missing


def run_selfcheck(
    current_rows: list[dict[str, Any]] | None = None,
    *,
    seed_path: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """自检：依赖缺失优先于数据缺失，两者各自给出明确原因。

    返回结构同时被 HTTP 接口与 CLI 使用：
    {ok, reason(null|dependency_missing|data_missing), dependencies, data:{...}}
    """
    missing_deps = check_dependencies()

    data_report: dict[str, Any] = {
        "module": MODULE,
        "seed_path": str(seed_path or settings.lightning_seed_path),
        "state_path": str(state_path or settings.lightning_state_path),
        "seed_sha256": None,
        "rows": 0,
        "scenarios_present": [],
        "scenarios_missing": list(REQUIRED_SCENARIOS),
        "message": "",
    }

    canonical: list[dict[str, Any]] = []
    data_message = ""
    try:
        canonical = load_canonical_seed(seed_path)
        data_report["seed_sha256"] = seed_sha256(seed_path)
    except SeedError as exc:
        data_message = str(exc)

    rows = current_rows if current_rows is not None else load_runtime_rows(state_path)
    data_report["rows"] = len(rows)
    present = sorted({str(row.get("status", "")) for row in rows if row.get("status")})
    data_report["scenarios_present"] = [s for s in REQUIRED_SCENARIOS if s in present]
    data_report["scenarios_missing"] = [s for s in REQUIRED_SCENARIOS if s not in present]

    reason: str | None = None
    messages: list[str] = []
    if missing_deps:
        reason = "dependency_missing"
        names = "、".join(item["pip_name"] for item in missing_deps)
        messages.append(f"依赖未装好：{names}，请在 backend 目录执行 pip install -r requirements.txt")
    if data_message:
        reason = reason or "data_missing"
        messages.append(data_message)
    elif not rows:
        reason = reason or "data_missing"
        messages.append("防雷元件记录为空：尚未初始化，请执行 python -m app.bootstrap")
    elif data_report["scenarios_missing"]:
        reason = reason or "data_missing"
        messages.append(
            "防雷元件初始化数据不完整，缺少情形："
            + "、".join(data_report["scenarios_missing"])
        )

    data_report["message"] = "；".join(m for m in messages if "依赖" not in m) or (
        "防雷元件记录已就绪" if not reason and not data_message else data_message
    )
    return {
        "ok": reason is None,
        "reason": reason,
        "message": "；".join(messages) or "自检通过：依赖齐全，防雷元件记录可读",
        "dependencies": {
            "required": list(REQUIRED_PACKAGES),
            "missing": missing_deps,
        },
        "data": data_report,
        "canonical_rows": len(canonical),
    }


# --------------------------------------------------------- 初始化（装配）

def materialize(
    *,
    seed_path: Path | None = None,
    state_path: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """执行一次幂等初始化：合并规范种子与本地已有记录。

    不依赖 store，便于命令行与单元测试直接调用；返回装配好的行与计数。
    """
    canonical = load_canonical_seed(seed_path)
    existing = load_runtime_rows(state_path)
    merged, inserted, skipped = merge_seed(existing, canonical)
    saved_to: Path | None = None
    if persist:
        saved_to = save_runtime_rows(
            merged, seed_path=seed_path, state_path=state_path
        )
    return {
        "rows": merged,
        "inserted": inserted,
        "skipped": skipped,
        "existed": len(existing),
        "total": len(merged),
        "state_path": saved_to,
        "seed_sha256": seed_sha256(seed_path),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="防雷元件数据初始化与自检")
    parser.add_argument("--check", action="store_true", help="只执行自检，不写数据")
    args = parser.parse_args()

    if args.check:
        report = run_selfcheck()
    else:
        result = materialize()
        report = run_selfcheck(result["rows"])
        report["init"] = {
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "total": result["total"],
            "state_path": str(result["state_path"]),
        }
        print(
            f"初始化完成：新增 {result['inserted']} 条，"
            f"已有记录保留 {result['existed']} 条（其中命中种子键跳过 {result['skipped']} 条），"
            f"当前共 {result['total']} 条 -> {result['state_path']}"
        )

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
