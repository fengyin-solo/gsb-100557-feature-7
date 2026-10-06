"""缺陷管理业务规则：批量受理、状态流转、片区权限与验收口径全部收在这里。

口径约定（只有这一份，路由层不做业务判断）：

1. 批量分派/验收逐条核对「缺陷编号 + 缺陷设备」，缺严重等级等不合格项单独打回，
   其余条目照常执行，互不连坐。
2. 状态只能按 待分派 → 处理中 → 已验收 → 已关闭 顺序流转，不能越级。
3. 只有缺陷所属片区对应的运维队组能改动该缺陷，其他队组只读。
4. 验收结论落库（缺陷验收台账）；同一台设备同一条缺陷重复提交验收，只认最早
   一条「通过」结论，重复提交直接沿用原判定、不再新增台账。验收不通过属返工，
   状态停在处理中，整改后允许再次提交。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "defect"
DISPATCH_LEDGER_MODULE = "defect_dispatch_ledger"
ACCEPT_LEDGER_MODULE = "defect_accept_ledger"

REQUIRED_FIELDS = ["缺陷编号", "发现日期", "缺陷设备", "所属片区"]
# 严重等级合法取值；批量受理时缺这一项的条目单独打回
SEVERITY_LEVELS = ["一般", "严重", "危急"]
STATUS_ORDER = ["待分派", "处理中", "已验收", "已关闭"]
# 动作与目标状态：提交验收只有结论为「通过」才推进，不通过停在处理中（返工）
ACTION_DISPATCH = "分派处理"
ACTION_ACCEPT = "提交验收"
ACTION_CLOSE = "关闭缺陷"
ACTION_TARGET = {ACTION_DISPATCH: "处理中", ACTION_CLOSE: "已关闭"}

# 片区与运维队组一一对应：只有本片区队组能提交验收/改动缺陷
AREA_TEAMS: dict[str, str] = {
    "南区": "南区运维班",
    "北区": "北区运维班",
    "东区": "东区运维班",
    "西区": "西区运维班",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class DefectService:
    # ---------- 列表与明细 ----------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        area: str | None = None,
        team: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("缺陷编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if area:
            rows = [row for row in rows if row.get("所属片区") == area]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self._view(row, team) for row in page_rows], total

    def get_entry(self, entry_id: int, *, team: str | None = None) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._view(row, team) if row else None

    def _owning_team(self, row: dict[str, Any]) -> str:
        """缺陷所在片区对应的运维队组；责任队组以片区映射为准。"""
        return AREA_TEAMS.get(str(row.get("所属片区") or ""), "")

    def _can_modify(self, row: dict[str, Any], team: str | None) -> bool:
        return bool(team) and self._owning_team(row) == team

    def _view(self, row: dict[str, Any], team: str | None = None) -> dict[str, Any]:
        """给前端的读视图：附带权限标记，外队组拿到的就是只读数据。"""
        view = dict(row)
        owner = self._owning_team(row)
        can_modify = self._can_modify(row, team)
        status = row.get("status")
        view["归属队组"] = owner
        view["可分派"] = can_modify and status == "待分派"
        view["可验收"] = can_modify and status == "处理中"
        view["可关闭"] = can_modify and status == "已验收"
        view["只读"] = not can_modify
        return view

    # ---------- 登记 ----------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        area = str(values.get("所属片区") or "").strip()
        if area not in AREA_TEAMS:
            return None, ["所属片区"]
        rows = store.rows(MODULE)
        code = str(values.get("缺陷编号") or "").strip()
        if any(str(row.get("缺陷编号") or "") == code for row in rows):
            return None, ["__duplicate__"]
        entry: dict[str, Any] = {"id": store.next_id(MODULE)}
        for field in ["缺陷编号", "发现日期", "缺陷设备", "缺陷类别", "严重等级", "处理方案", "整改时限", "所属片区"]:
            entry[field] = str(values.get(field) or "").strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = entry.get("严重等级") in ("严重", "危急")
        entry["缺陷状态"] = STATUS_ORDER[0]
        entry["责任队组"] = ""
        entry["验收结论"] = ""
        entry["验收人"] = ""
        entry["验收时间"] = ""
        entry["打回原因"] = ""
        rows.append(entry)
        store.save()
        return entry, []

    # ---------- 单条动作：直接复用批量口径，保证验收口径只有一份 ----------

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        team: str | None = None,
        conclusion: str = "通过",
        note: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"设备缺陷 {entry_id} 不存在或已归档"
        summary = self.batch_action(
            action,
            [{"缺陷编号": row.get("缺陷编号"), "缺陷设备": row.get("缺陷设备"),
              "验收结论": conclusion, "验收说明": note}],
            team=team,
        )
        result = summary["results"][0]
        if not result["ok"]:
            return None, result["message"]
        return store.find(MODULE, entry_id), result["message"]

    # ---------- 批量分派 / 批量验收 / 批量关闭 ----------

    def batch_action(
        self,
        action: str,
        items: list[dict[str, Any]],
        *,
        team: str | None = None,
    ) -> dict[str, Any]:
        if action not in (ACTION_DISPATCH, ACTION_ACCEPT, ACTION_CLOSE):
            return self._summary(action, [], "动作不属于缺陷管理可执行范围")
        if not items:
            return self._summary(action, [], "没有勾选任何缺陷条目")

        results: list[dict[str, Any]] = []
        # 同一次提交里（缺陷编号+缺陷设备）只认第一条，重复条目直接打回
        seen: set[tuple[str, str]] = set()
        with store.lock():
            for raw in items:
                code = str(raw.get("缺陷编号") or "").strip()
                device = str(raw.get("缺陷设备") or "").strip()
                result = self._apply_one(action, code, device, raw, team, seen)
                results.append(result)
            store.save()

        succeeded = sum(1 for item in results if item["ok"])
        rejected = len(results) - succeeded
        message = f"共提交 {len(results)} 条：成功 {succeeded} 条"
        if rejected:
            message += f"，打回 {rejected} 条（详见逐条结果）"
        return self._summary(action, results, message, succeeded, rejected)

    def _apply_one(
        self,
        action: str,
        code: str,
        device: str,
        raw: dict[str, Any],
        team: str | None,
        seen: set[tuple[str, str]],
    ) -> dict[str, Any]:
        def reject(reason: str) -> dict[str, Any]:
            return {"缺陷编号": code, "缺陷设备": device, "ok": False, "message": reason}

        if not code or not device:
            return reject("缺陷编号与缺陷设备必须逐条核对，该条信息不完整，单独打回")

        dedupe_key = (code, device)
        if dedupe_key in seen:
            return reject("同一台设备的同一条缺陷在本次提交中重复，只保留最早一条")
        seen.add(dedupe_key)

        row = self._find_by_code(code)
        if row is None:
            return reject(f"缺陷编号 {code} 在缺陷台账中不存在，核对不上，单独打回")
        if str(row.get("缺陷设备") or "") != device:
            return reject(
                f"缺陷设备与记录不符：提交为「{device}」，台账为「{row.get('缺陷设备')}」，单独打回"
            )

        # 权限：只有所在片区的运维队组能改动，其他队组只读
        if not self._can_modify(row, team):
            return reject(
                f"该缺陷属{row.get('所属片区')}（{self._owning_team(row)}），{team or '当前队组'}仅可查看，不能改动"
            )

        # 缺严重等级的条目单独打回，不影响同批其他条目
        severity = str(row.get("严重等级") or "").strip()
        if not severity:
            row["打回原因"] = "缺严重等级，无法判定处置优先级，请补录后重新提交"
            return reject("缺严重等级，单独打回：请先补录严重等级（一般/严重/危急）")
        if severity not in SEVERITY_LEVELS:
            return reject(f"严重等级「{severity}」不在允许口径（一般/严重/危急）内，单独打回")

        status = str(row.get("status") or "")
        if action == ACTION_DISPATCH:
            return self._do_dispatch(row, status)
        if action == ACTION_ACCEPT:
            return self._do_accept(row, status, raw)
        return self._do_close(row, status)

    def _do_dispatch(self, row: dict[str, Any], status: str) -> dict[str, Any]:
        if status != "待分派":
            return self._reject_skip(row, status, ACTION_DISPATCH)
        owner = self._owning_team(row)
        stamp = now_text()
        row["status"] = "处理中"
        row["缺陷状态"] = "处理中"
        row["责任队组"] = owner
        row["pending"] = True
        self._append_dispatch_ledger(row, owner, stamp)
        return self._ok(row, f"已分派给{owner}，状态进入处理中")

    def _do_accept(self, row: dict[str, Any], status: str, raw: dict[str, Any]) -> dict[str, Any]:
        # 同一台设备同一条缺陷已有「通过」结论：无论当前走到哪一步，重复提交都
        # 沿用最早一条判定，不改状态、不再新增台账（这条判断优先于状态顺序校验）
        prior = self._find_acceptance(row.get("缺陷编号"), row.get("缺陷设备"), verdict="通过")
        if prior is not None:
            return self._ok(
                row,
                f"重复提交验收，沿用最早一条结论（通过，{prior.get('验收时间')}），不再重复受理",
                duplicated=True,
            )

        if status != "处理中":
            return self._reject_skip(row, status, ACTION_ACCEPT)

        conclusion_raw = str(raw.get("验收结论") or "通过").strip()
        conclusion = "不通过" if conclusion_raw in ("不通过", "退回", "驳回") else "通过"
        note = str(raw.get("验收说明") or "").strip()
        team = self._owning_team(row)
        stamp = now_text()

        ledger_row = self._append_accept_ledger(row, team, conclusion, note, stamp)
        if conclusion == "通过":
            row["status"] = "已验收"
            row["缺陷状态"] = "已验收"
            row["pending"] = True
            row["验收结论"] = "通过"
            row["验收人"] = team
            row["验收时间"] = stamp
            row["打回原因"] = ""
            return self._ok(row, f"验收通过，状态进入已验收（验收台账 #{ledger_row['id']}）")

        # 验收不通过：结论落库，状态停在处理中，整改后可再次提交
        row["验收结论"] = "不通过"
        row["验收人"] = team
        row["验收时间"] = stamp
        row["打回原因"] = note or "验收不通过，需返工整改"
        return self._ok(row, "验收不通过，结论已落库，缺陷停在处理中待返工", verdict="不通过")

    def _do_close(self, row: dict[str, Any], status: str) -> dict[str, Any]:
        if status != "已验收":
            return self._reject_skip(row, status, ACTION_CLOSE)
        row["status"] = "已关闭"
        row["缺陷状态"] = "已关闭"
        row["pending"] = False
        return self._ok(row, "已关闭")

    def _reject_skip(self, row: dict[str, Any], status: str, action: str) -> dict[str, Any]:
        """状态顺序校验：只允许走到相邻的下一状态，越级直接拦下。"""
        allowed = {"分派处理": "待分派", "提交验收": "处理中", "关闭缺陷": "已验收"}[action]
        return {
            "缺陷编号": row.get("缺陷编号"),
            "缺陷设备": row.get("缺陷设备"),
            "ok": False,
            "message": f"当前状态为「{status}」，{action}要求前置状态为「{allowed}」，不能越级，单独打回",
        }

    # ---------- 台账 ----------

    def _append_dispatch_ledger(self, row: dict[str, Any], team: str, stamp: str) -> dict[str, Any]:
        ledger = store.rows(DISPATCH_LEDGER_MODULE)
        entry = {
            "id": store.next_id(DISPATCH_LEDGER_MODULE),
            "缺陷编号": row.get("缺陷编号"),
            "缺陷设备": row.get("缺陷设备"),
            "所属片区": row.get("所属片区"),
            "严重等级": row.get("严重等级"),
            "分派队组": team,
            "处理方案": row.get("处理方案"),
            "整改时限": row.get("整改时限"),
            "分派时间": stamp,
        }
        ledger.append(entry)
        return entry

    def _append_accept_ledger(
        self, row: dict[str, Any], team: str, conclusion: str, note: str, stamp: str
    ) -> dict[str, Any]:
        ledger = store.rows(ACCEPT_LEDGER_MODULE)
        entry = {
            "id": store.next_id(ACCEPT_LEDGER_MODULE),
            "缺陷编号": row.get("缺陷编号"),
            "缺陷设备": row.get("缺陷设备"),
            "所属片区": row.get("所属片区"),
            "严重等级": row.get("严重等级"),
            "验收队组": team,
            "验收结论": conclusion,
            "验收说明": note,
            "验收人": team,
            "验收时间": stamp,
        }
        ledger.append(entry)
        return entry

    def _find_acceptance(self, code: Any, device: Any, *, verdict: str | None = None) -> dict[str, Any] | None:
        for row in store.rows(ACCEPT_LEDGER_MODULE):
            if row.get("缺陷编号") != code or row.get("缺陷设备") != device:
                continue
            if verdict is None or row.get("验收结论") == verdict:
                return row
        return None

    def list_ledger(
        self, kind: str, *, keyword: str | None = None, team: str | None = None
    ) -> tuple[list[dict[str, Any]], str]:
        """查询分派/验收台账，谁派的、验收卡在谁这里都能查出来。"""
        if kind == "dispatch":
            module, label = DISPATCH_LEDGER_MODULE, "分派台账"
            actor_field = "分派队组"
            time_field = "分派时间"
        elif kind == "accept":
            module, label = ACCEPT_LEDGER_MODULE, "验收台账"
            actor_field = "验收队组"
            time_field = "验收时间"
        else:
            return [], "台账类型只支持 dispatch / accept"
        rows = store.rows(module)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("缺陷编号", ""))
                    or keyword in str(row.get("缺陷设备", ""))]
        if team:
            rows = [row for row in rows if row.get(actor_field) == team]
        rows = sorted(rows, key=lambda row: str(row.get(time_field, "")), reverse=True)
        return rows, label

    # ---------- 检修工作台（缺陷列表与检修待办共用这一份口径） ----------

    def workbench(self, *, team: str | None = None) -> dict[str, Any]:
        rows = store.rows(MODULE)
        counts = {status: 0 for status in STATUS_ORDER}
        todo_rows: list[dict[str, Any]] = []
        for row in rows:
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
            owner = self._owning_team(row)
            if status == "待分派":
                todo_type, todo_desc = "待派工", "等待分派到片区运维队组"
            elif status == "处理中":
                todo_type, todo_desc = "整改中", "队组处置缺陷，完成后提交验收"
            elif status == "已验收":
                todo_type, todo_desc = "待关闭", "验收已通过，待关闭归档"
            else:
                continue
            todo_rows.append({
                "缺陷编号": row.get("缺陷编号"),
                "检修设备": row.get("缺陷设备"),
                "所属片区": row.get("所属片区"),
                "责任队组": owner,
                "严重等级": row.get("严重等级"),
                "处理方案": row.get("处理方案"),
                "整改时限": row.get("整改时限"),
                "缺陷状态": status,
                "待办类型": todo_type,
                "待办说明": todo_desc,
                "本队组待办": owner == team if team else False,
            })
        my_rows = [item for item in todo_rows if item["本队组待办"]] if team else []
        return {
            "counts": counts,
            "未关闭总数": counts["待分派"] + counts["处理中"] + counts["已验收"],
            "待办总数": len(todo_rows),
            "本队组待办数": len(my_rows),
            "当前队组": team or "",
            "todos": my_rows if team else todo_rows,
        }

    # ---------- 小工具 ----------

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("缺陷编号") or "") == code:
                return row
        return None

    def _ok(
        self, row: dict[str, Any], message: str, *, verdict: str | None = None, duplicated: bool = False
    ) -> dict[str, Any]:
        return {
            "缺陷编号": row.get("缺陷编号"),
            "缺陷设备": row.get("缺陷设备"),
            "ok": True,
            "message": message,
            "status": row.get("status"),
            "验收结论": verdict,
            "重复提交": duplicated,
        }

    def _summary(
        self,
        action: str,
        results: list[dict[str, Any]],
        message: str,
        succeeded: int = 0,
        rejected: int = 0,
    ) -> dict[str, Any]:
        return {
            "ok": succeeded > 0,
            "action": action,
            "message": message,
            "total": len(results),
            "succeeded": succeeded,
            "rejected": rejected,
            "results": results,
        }
