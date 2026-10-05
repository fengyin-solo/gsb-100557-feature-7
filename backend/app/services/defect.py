"""缺陷管理业务规则：状态流转、批量处置、队组权限与验收口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "defect"
ACCEPTANCE_MODULE = "defect_acceptance"
REQUIRED_FIELDS = ["缺陷编号", "发现日期", "缺陷设备"]
OPTIONAL_FIELDS = ["所属片区", "缺陷类别", "严重等级", "处理方案", "整改时限"]
STATUS_ORDER = ["待分派", "处理中", "已验收", "已关闭"]
# 动作 → (前置状态, 目标状态)：状态只能沿 STATUS_ORDER 顺序流转，不允许越级
ACTION_RULES = {
    "分派处理": ("待分派", "处理中"),
    "提交验收": ("处理中", "已验收"),
    "关闭缺陷": ("已验收", "已关闭"),
}
# 运维队组 → 负责片区：只有负责该片区的队组才能改动该片区的缺陷，其余队组只能查看
TEAM_REGIONS = {
    "运维一队": ["东区"],
    "运维二队": ["西区"],
    "运维三队": ["南区"],
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class DefectService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("缺陷编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> dict[str, int]:
        """缺陷状态统计：缺陷列表与检修工作台共用这一份口径，保证两处读数一致。"""
        counts = {status: 0 for status in STATUS_ORDER}
        for row in store.rows(MODULE):
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
        return {**counts, "合计": len(store.rows(MODULE))}

    def teams(self) -> dict[str, list[str]]:
        return TEAM_REGIONS

    def allowed_actions(self) -> list[str]:
        return list(ACTION_RULES)

    def list_acceptances(self) -> list[dict[str, Any]]:
        return store.rows(ACCEPTANCE_MODULE)

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS + OPTIONAL_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["缺陷状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        operator: str = "值班管理员",
        team: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"设备缺陷 {entry_id} 不存在或已归档"
        ok, message = self._apply_action(entry, action, operator=operator, team=team)
        if not ok:
            return None, message
        return entry, message

    def run_batch_action(
        self,
        action: str,
        ids: list[int],
        *,
        operator: str = "值班管理员",
        team: str = "",
    ) -> dict[str, Any]:
        """框选多条一起处置：逐条核对逐条执行，打回的写明原因，不影响其余记录。"""
        results: list[dict[str, Any]] = []
        for entry_id in ids:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                results.append({
                    "id": entry_id,
                    "ok": False,
                    "message": f"设备缺陷 {entry_id} 不存在或已归档",
                })
                continue
            ok, message = self._apply_action(entry, action, operator=operator, team=team)
            results.append({
                "id": entry_id,
                "缺陷编号": entry.get("缺陷编号") or "",
                "缺陷设备": entry.get("缺陷设备") or "",
                "ok": ok,
                "message": message,
            })
        succeeded = sum(1 for item in results if item["ok"])
        return {
            "action": action,
            "total": len(results),
            "succeeded": succeeded,
            "rejected": len(results) - succeeded,
            "results": results,
        }

    def _apply_action(
        self,
        entry: dict[str, Any],
        action: str,
        *,
        operator: str,
        team: str,
    ) -> tuple[bool, str]:
        # 逐条核对：缺陷编号、缺陷设备缺一不可
        code = str(entry.get("缺陷编号") or "").strip()
        device = str(entry.get("缺陷设备") or "").strip()
        if not code:
            return False, "打回：缺陷编号缺失，核对不通过"
        if not device:
            return False, "打回：缺陷设备缺失，核对不通过"
        # 缺严重等级的那一条单独打回，写明原因，其余照常执行
        if not str(entry.get("严重等级") or "").strip():
            return False, f"打回：缺陷 {code}（{device}）缺少严重等级，请补录后再执行"
        if action not in ACTION_RULES:
            return False, f"动作「{action}」不属于缺陷管理可执行范围"
        expect, target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current != expect:
            return False, (
                f"打回：缺陷 {code} 当前为「{current}」，不能越级{action}，"
                f"状态须按 {'→'.join(STATUS_ORDER)} 顺序流转"
            )
        region = str(entry.get("所属片区") or "").strip()
        if region not in TEAM_REGIONS.get(team, []):
            return False, (
                f"打回：缺陷 {code} 属「{region or '未分区'}」，仅该片区运维队组可改动，"
                f"「{team or '未选队组'}」只能查看"
            )
        if action == "分派处理":
            entry["分派人"] = operator
            entry["分派时间"] = _now()
            entry["处理队组"] = team
            message = f"缺陷 {code} 已分派给「{team}」，分派人：{operator}"
        elif action == "提交验收":
            message = self._accept(entry, code, device, region, operator=operator, team=team)
        else:
            entry["关闭人"] = operator
            entry["关闭时间"] = _now()
            message = f"缺陷 {code} 已关闭，关闭人：{operator}"
        entry["status"] = target
        entry["缺陷状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        return True, message

    def _accept(
        self,
        entry: dict[str, Any],
        code: str,
        device: str,
        region: str,
        *,
        operator: str,
        team: str,
    ) -> str:
        """提交验收：结论落库；同设备同编号重复提交只留最早一条，沿用原有判定。"""
        existing = self._find_acceptance(code, device)
        if existing:
            entry["验收结论"] = existing["验收结论"]
            entry["验收人"] = existing["验收人"]
            entry["验收队组"] = existing["验收队组"]
            entry["验收时间"] = existing["验收时间"]
            return (
                f"缺陷 {code}（{device}）此前已验收，沿用 {existing['验收时间']} "
                f"由「{existing['验收队组']}」给出的判定「{existing['验收结论']}」，不重复登记"
            )
        records = store.rows(ACCEPTANCE_MODULE)
        record = {
            "id": max((int(row.get("id", 0)) for row in records), default=0) + 1,
            "缺陷编号": code,
            "缺陷设备": device,
            "所属片区": region,
            "验收结论": "验收通过",
            "验收人": operator,
            "验收队组": team,
            "验收时间": _now(),
        }
        records.append(record)
        entry["验收结论"] = record["验收结论"]
        entry["验收人"] = operator
        entry["验收队组"] = team
        entry["验收时间"] = record["验收时间"]
        return f"缺陷 {code}（{device}）验收通过，结论已落库（验收人：{operator}）"

    def _find_acceptance(self, code: str, device: str) -> dict[str, Any] | None:
        for row in store.rows(ACCEPTANCE_MODULE):
            if str(row.get("缺陷编号")) == code and str(row.get("缺陷设备")) == device:
                return row
        return None
