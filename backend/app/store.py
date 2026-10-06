"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

缺陷模块的缺陷主表、分派台账、验收台账会落到 backend/data/defect_state.json：
验收结论必须可追溯，服务重启后要沿用既往判定，不能回到示例数据。
真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any

from app.seed import SEED_ROWS

# 需要落库的表：缺陷主数据 + 分派/验收两本台账
PERSIST_MODULES = ("defect", "defect_dispatch_ledger", "defect_accept_ledger")
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_STATE_FILE = os.path.join(_DATA_DIR, "defect_state.json")


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        """从落库文件恢复缺陷相关表；文件不存在或损坏时沿用示例数据。"""
        if not os.path.exists(_STATE_FILE):
            return
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(saved, dict):
            return
        for module in PERSIST_MODULES:
            rows = saved.get(module)
            if isinstance(rows, list):
                self._tables[module] = [dict(row) for row in rows if isinstance(row, dict)]

    def save(self) -> None:
        """把缺陷相关表原子写回磁盘（先写临时文件再替换，避免半截文件）。"""
        os.makedirs(_DATA_DIR, exist_ok=True)
        with self._lock:
            payload = {module: self._tables.get(module, []) for module in PERSIST_MODULES}
            fd, tmp_path = tempfile.mkstemp(prefix="defect_state-", suffix=".json", dir=_DATA_DIR)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                os.replace(tmp_path, _STATE_FILE)
            except OSError:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

    def lock(self) -> threading.RLock:
        """批量动作期间持锁，保证多条缺陷的核对与流转是一个整体。"""
        return self._lock

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def next_id(self, module: str) -> int:
        return max((int(row.get("id", 0)) for row in self.rows(module)), default=0) + 1

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
