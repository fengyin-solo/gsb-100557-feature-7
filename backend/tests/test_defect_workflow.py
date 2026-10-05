"""缺陷批量处置回归验证：批量分派/验收、状态机、队组权限、验收幂等、口径一致性。

直接运行：python3 tests/test_defect_workflow.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name} {detail}")


print("== 1. 列表与统计口径 ==")
r = client.get("/api/defect", params={"size": 50}).json()
print("  缺陷总数:", r["total"])
s = client.get("/api/defect/summary").json()
print("  summary:", s)
check("summary 合计与列表 total 一致", s["合计"] == r["total"])
check("各状态之和等于合计", s["待分派"] + s["处理中"] + s["已验收"] + s["已关闭"] == s["合计"])

print("== 2. 批量分派：缺严重等级的单独打回，其余照常 ==")
# 1(东区,有待分派) 2(东区,待分派) 3(西区,缺严重等级) 8(南区,待分派)
resp = client.post("/api/defect/batch", json={
    "action": "分派处理", "ids": [1, 2, 3, 8], "operator": "值班管理员", "team": "运维一队",
}).json()
print(" ", resp["message"])
for item in resp["results"]:
    print("  ", item["id"], item["ok"], item["message"])
by_id = {item["id"]: item for item in resp["results"]}
check("东区1 分派成功", by_id[1]["ok"])
check("东区2 分派成功", by_id[2]["ok"])
check("西区3 缺严重等级被打回", not by_id[3]["ok"] and "严重等级" in by_id[3]["message"])
check("南区8 非本队组片区被打回", not by_id[8]["ok"] and "只能查看" in by_id[8]["message"])
e1 = client.get("/api/defect/1").json()
check("分派后状态=处理中", e1["status"] == "处理中")
check("分派人已记录", e1.get("分派人") == "值班管理员" and bool(e1.get("分派时间")))

print("== 3. 状态机：不能越级 ==")
resp = client.post("/api/defect/batch", json={
    "action": "关闭缺陷", "ids": [1], "operator": "值班管理员", "team": "运维一队",
}).json()
check("处理中→已关闭 越级被打回", not resp["results"][0]["ok"] and "越级" in resp["results"][0]["message"])
r = client.post("/api/defect/1/actions", json={"values": {"action": "关闭缺陷", "team": "运维一队"}}).json()
check("单条越级同样被拦", not r["ok"])

print("== 4. 批量提交验收：结论落库 ==")
before = client.get("/api/defect/acceptances").json()["total"]
resp = client.post("/api/defect/batch", json={
    "action": "提交验收", "ids": [1, 2], "operator": "值班管理员", "team": "运维一队",
}).json()
print(" ", resp["message"])
check("两条验收成功", resp["succeeded"] == 2, resp["results"])
after = client.get("/api/defect/acceptances").json()["total"]
check("验收台账新增 2 条", after - before == 2, f"before={before} after={after}")
e1 = client.get("/api/defect/1").json()
check("验收后状态=已验收", e1["status"] == "已验收")
check("验收人/结论已记录", e1.get("验收人") == "值班管理员" and e1.get("验收结论") == "验收通过")

print("== 5. 幂等：同设备同编号重复提交只留最早一条 ==")
# 新登记一条与 DEFE-0006 同编号同设备的缺陷，走到处理中再提交验收
r = client.post("/api/defect", json={"values": {
    "缺陷编号": "DEFE-0006", "发现日期": "2026-09-20", "缺陷设备": "5#逆变器",
    "所属片区": "东区", "严重等级": "一般",
}}).json()
new_id = r["entry"]["id"]
client.post(f"/api/defect/{new_id}/actions", json={"values": {"action": "分派处理", "team": "运维一队"}})
before = client.get("/api/defect/acceptances").json()["total"]
r = client.post(f"/api/defect/{new_id}/actions", json={"values": {"action": "提交验收", "team": "运维一队"}}).json()
print("  ", r["message"])
after = client.get("/api/defect/acceptances").json()["total"]
check("重复提交不新增验收记录", after == before, f"before={before} after={after}")
check("沿用原有判定", "沿用" in r["message"] and "验收通过" in r["message"])
check("状态仍流转为已验收", r["entry"]["status"] == "已验收")

print("== 6. 权限：别的队组只能查看 ==")
r = client.post("/api/defect/8/actions", json={"values": {"action": "分派处理", "team": "运维二队"}}).json()
check("运维二队不能动南区缺陷", not r["ok"] and "只能查看" in r["message"])
r = client.post("/api/defect/8/actions", json={"values": {"action": "分派处理", "team": "运维三队"}}).json()
check("运维三队可以分派南区缺陷", r["ok"], r["message"])

print("== 7. 检修工作台与缺陷列表同口径 ==")
wb = client.get("/api/maintenance/workbench").json()
s = client.get("/api/defect/summary").json()
check("工作台 defect_summary 与 summary 一致", wb["defect_summary"] == s,
      f'{wb["defect_summary"]} vs {s}')
todo_closed = [row for row in wb["defect_todo"] if row["status"] == "已关闭"]
check("待办明细不含已关闭", not todo_closed)
check("待办条数=合计-已关闭", len(wb["defect_todo"]) == s["合计"] - s["已关闭"])

print("== 8. 完整流转到关闭 ==")
for act in ["分派处理", "提交验收", "关闭缺陷"]:
    r = client.post("/api/defect/3/actions", json={"values": {"action": act, "team": "运维二队"}}).json()
check("缺严重等级的缺陷全程被拦", not r["ok"] and "严重等级" in r["message"], r["message"])
# 给 4(处理中,西区) 走 验收→关闭
r1 = client.post("/api/defect/4/actions", json={"values": {"action": "提交验收", "team": "运维二队"}}).json()
r2 = client.post("/api/defect/4/actions", json={"values": {"action": "关闭缺陷", "team": "运维二队"}}).json()
check("处理中→已验收→已关闭 顺序流转", r1["ok"] and r2["ok"] and r2["entry"]["status"] == "已关闭")
check("关闭后 pending=False", r2["entry"]["pending"] is False)

print()
if fails:
    print("FAILED:", fails)
    raise SystemExit(1)
print("ALL CHECKS PASSED")
