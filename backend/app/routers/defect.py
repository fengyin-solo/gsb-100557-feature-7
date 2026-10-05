"""缺陷管理接口：维护设备缺陷，覆盖单条/批量分派处理、提交验收、关闭缺陷等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, BatchActionPayload, EntryPayload, PageResult
from app.services.defect import DefectService

router = APIRouter(prefix="/api/defect", tags=["缺陷管理"])

service = DefectService()

LIST_FIELDS = ["缺陷编号", "发现日期", "缺陷设备", "所属片区", "缺陷类别", "严重等级", "处理方案", "整改时限", "缺陷状态"]
STATUSES = ["待分派", "处理中", "已验收", "已关闭"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按缺陷编号检索"),
    status: str | None = Query(default=None, description="待分派、处理中、已验收、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按缺陷编号与状态过滤缺陷管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summary() -> dict[str, int]:
    """缺陷状态统计：缺陷列表与检修工作台共用这一份口径，两处读数一致。"""
    return service.summary()


@router.get("/teams")
def teams() -> dict[str, list[str]]:
    """运维队组与负责片区对照：只有负责该片区的队组能改动该片区缺陷。"""
    return service.teams()


@router.get("/acceptances")
def acceptances() -> dict[str, Any]:
    """验收结论台账：提交验收时落库，同设备同编号只留最早一条。"""
    records = service.list_acceptances()
    return {"total": len(records), "items": records}


@router.post("/batch")
def run_batch(payload: BatchActionPayload) -> dict[str, Any]:
    """框选多条缺陷一起分派/验收/关闭：逐条核对，打回的写明原因，其余照常执行。"""
    action = payload.action.strip()
    if action not in service.allowed_actions():
        raise HTTPException(status_code=400, detail=f"动作「{action}」不属于缺陷管理可执行范围")
    if not payload.ids:
        raise HTTPException(status_code=400, detail="请先勾选要处置的缺陷")
    result = service.run_batch_action(action, payload.ids, operator=payload.operator, team=payload.team)
    result["ok"] = result["rejected"] == 0
    result["message"] = f"共 {result['total']} 条：执行 {result['succeeded']} 条，打回 {result['rejected']} 条"
    return result


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出缺陷管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "defect", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条设备缺陷明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"设备缺陷 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条设备缺陷，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="设备缺陷已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条设备缺陷执行分派处理、提交验收、关闭缺陷；越级或无权限会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "值班管理员").strip()
    team = str(payload.values.get("team") or "").strip()
    entry, message = service.run_action(entry_id, action, operator=operator, team=team)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
