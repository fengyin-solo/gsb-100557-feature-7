"""缺陷管理接口：维护设备缺陷，覆盖批量分派、批量验收、关闭、台账与检修待办。

业务判断全部在 DefectService 里，路由层只负责取参、回包。
当前值班队组由请求头 X-Operator-Team 带入；不带队组时只能查看不能改动。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, BatchActionPayload, EntryPayload, PageResult
from app.services.defect import ACTION_CLOSE, ACTION_DISPATCH, ACTION_ACCEPT, AREA_TEAMS, DefectService

router = APIRouter(prefix="/api/defect", tags=["缺陷管理"])

service = DefectService()

LIST_FIELDS = ["缺陷编号", "发现日期", "缺陷设备", "缺陷类别", "严重等级", "处理方案", "整改时限", "缺陷状态"]
STATUSES = ["待分派", "处理中", "已验收", "已关闭"]


def _team(x_operator_team: str | None, team: str | None = None) -> str | None:
    """当前值班队组：优先取请求头 X-Operator-Team，也允许 team 查询参数带入。"""
    value = (x_operator_team or team or "").strip()
    return value or None


# 注意：静态路径必须排在 /{entry_id} 之前，否则会被当成缺陷 id
@router.get("/options")
def options() -> dict[str, Any]:
    """返回片区-队组映射、严重等级与状态口径，供前端切换队组与校验。"""
    return {
        "areas": [{"所属片区": area, "运维队组": team} for area, team in AREA_TEAMS.items()],
        "severity_levels": ["一般", "严重", "危急"],
        "statuses": STATUSES,
        "actions": [ACTION_DISPATCH, ACTION_ACCEPT, ACTION_CLOSE],
    }


@router.get("/workbench")
def workbench(
    x_operator_team: str | None = Header(default=None),
    team: str | None = Query(default=None, description="当前值班队组，与请求头二选一"),
) -> dict[str, Any]:
    """检修工作台数据：缺陷列表页与检修待办页共用同一份统计口径。"""
    return service.workbench(team=_team(x_operator_team, team))


@router.get("/ledger/{kind}")
def list_ledger(
    kind: str,
    keyword: str | None = Query(default=None, description="按缺陷编号/设备检索"),
    x_operator_team: str | None = Header(default=None),
    team: str | None = Query(default=None),
) -> dict[str, Any]:
    """查询分派台账（谁派的）或验收台账（卡在谁那里、结论是什么）。"""
    if kind not in ("dispatch", "accept"):
        raise HTTPException(status_code=400, detail="台账类型只支持 dispatch（分派）或 accept（验收）")
    rows, label = service.list_ledger(kind, keyword=keyword, team=_team(x_operator_team, team))
    return {"kind": kind, "ledger": label, "total": len(rows), "items": rows}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按缺陷编号检索"),
    status: str | None = Query(default=None, description="待分派、处理中、已验收、已关闭"),
    area: str | None = Query(default=None, description="按所属片区过滤"),
    page: int = 1,
    size: int = 200,
    x_operator_team: str | None = Header(default=None),
    team: str | None = Query(default=None, description="当前值班队组，与请求头二选一"),
) -> PageResult[dict]:
    """按缺陷编号、状态、片区过滤缺陷列表；返回里带每一条的可操作/只读标记。"""
    if size > 500:
        raise HTTPException(status_code=400, detail="每页最多 500 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, area=area, page=page, size=size, team=_team(x_operator_team, team)
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/batch/actions")
def batch_action(
    payload: BatchActionPayload,
    x_operator_team: str | None = Header(default=None),
    team: str | None = Query(default=None, description="当前值班队组，与请求头二选一"),
) -> dict[str, Any]:
    """框选多条一起分派/提交验收/关闭：逐条核对，不合格的单独打回，其余照常执行。"""
    return service.batch_action(payload.action, payload.items, team=_team(x_operator_team, team))


@router.get("/export")
def export_entries(
    x_operator_team: str | None = Header(default=None),
    team: str | None = Query(default=None),
) -> dict[str, Any]:
    """导出缺陷管理清单：返回当前全量数据（带权限标记）。"""
    items, total = service.list_entries(page=1, size=10000, team=_team(x_operator_team, team))
    return {"module": "defect", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(
    entry_id: int,
    x_operator_team: str | None = Header(default=None),
    team: str | None = Query(default=None),
) -> dict:
    """读取单条设备缺陷明细（含台账轨迹）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id, team=_team(x_operator_team, team))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"设备缺陷 {entry_id} 不存在或已归档")
    code, device = entry.get("缺陷编号"), entry.get("缺陷设备")
    dispatch_rows, _ = service.list_ledger("dispatch")
    accept_rows, _ = service.list_ledger("accept")
    entry["分派轨迹"] = [row for row in dispatch_rows if row.get("缺陷编号") == code and row.get("缺陷设备") == device]
    entry["验收轨迹"] = [row for row in accept_rows if row.get("缺陷编号") == code and row.get("缺陷设备") == device]
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条设备缺陷，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        if "__duplicate__" in missing:
            return ActionResult(ok=False, message="缺陷编号已存在，同一台设备的同一条缺陷不允许重复登记")
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="设备缺陷已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator_team: str | None = Header(default=None),
    team: str | None = Query(default=None, description="当前值班队组，与请求头二选一"),
) -> ActionResult:
    """对单条缺陷执行分派/验收/关闭；与批量动作共用同一份验收口径。"""
    values = payload.values
    action = str(values.get("action") or "").strip()
    conclusion = str(values.get("验收结论") or "通过").strip()
    note = str(values.get("验收说明") or "").strip()
    entry, message = service.run_action(
        entry_id, action, team=_team(x_operator_team, team), conclusion=conclusion, note=note
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
