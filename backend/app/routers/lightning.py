"""防雷元件接口：维护防雷元件，覆盖记录超标、安排测试、办理更换等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app import bootstrap
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.lightning import LightningService
from app.store import store

router = APIRouter(prefix="/api/lightning", tags=["防雷元件"])

service = LightningService()

LIST_FIELDS = ["元件编号", "安装位置", "防护等级", "泄露电流", "动作次数", "测试日期", "更换记录", "元件状态"]
STATUSES = ["防护有效", "泄露超标", "动作频繁", "已更换"]


@router.get("/selfcheck")
def selfcheck(response: Response) -> dict[str, Any]:
    """启动后自检：确认依赖已装好、防雷元件记录可读且四种情形齐全。

    失败时 HTTP 503，reason 明确区分：
    - dependency_missing：依赖没装好；
    - data_missing：数据缺失或初始化不完整。
    静态路径需声明在 /{entry_id} 之前，否则会被当成元件编号。
    """
    report = bootstrap.run_selfcheck(store.rows(bootstrap.MODULE))
    if not report["ok"]:
        response.status_code = 503
    return report


@router.post("/init", response_model=ActionResult)
def init_entries() -> ActionResult:
    """按同一份种子数据幂等初始化：只补缺，不清空、不覆盖已有测试记录。"""
    try:
        result = store.reinit_lightning()
    except bootstrap.SeedError as exc:
        return ActionResult(ok=False, message=str(exc))
    return ActionResult(
        ok=True,
        message=(
            f"初始化完成：新增 {result['inserted']} 条，"
            f"已有记录全部保留（命中种子键跳过 {result['skipped']} 条），共 {result['total']} 条"
        ),
    )


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出防雷元件清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "lightning", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按元件编号检索"),
    status: str | None = Query(default=None, description="防护有效、泄露超标、动作频繁、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按元件编号与状态过滤防雷元件列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条防雷元件明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"防雷元件 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条防雷元件，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="防雷元件已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条防雷元件执行记录超标、安排测试、办理更换；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
