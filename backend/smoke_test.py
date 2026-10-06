# -*- coding: utf-8 -*-
"""缺陷批量分派/验收全流程冒烟测试：直接调服务层，UTF-8 可控。"""
import json
import sys

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def batch(action, items, team=None, **extra):
    body = {"action": action, "items": items, **extra}
    suffix = f"?team={team}" if team else ""
    r = client.post(f"/api/defect/batch/actions{suffix}", json=body)
    return r.status_code, r.json()


def get(path, team=None):
    suffix = f"&team={team}" if "?" in path and team else (f"?team={team}" if team else "")
    return client.get(path + suffix)


def result_map(resp):
    return {r["缺陷编号"]: r for r in resp["results"]}


print("== 初始工作台口径 ==")
wb = client.get("/api/defect/workbench").json()
check("初始计数 待分派=3", wb["counts"]["待分派"] == 3, wb["counts"])
check("初始计数 处理中=3", wb["counts"]["处理中"] == 3, wb["counts"])
check("初始计数 已验收=1", wb["counts"]["已验收"] == 1, wb["counts"])
check("初始计数 已关闭=1", wb["counts"]["已关闭"] == 1, wb["counts"])
check("未关闭总数=7", wb["未关闭总数"] == 7, wb)

# 检修待办与缺陷工作台同源
mwb = client.get("/api/maintenance/workbench").json()
check("检修工作台与缺陷工作台计数一致", mwb["counts"] == wb["counts"])

print("== 批量分派：1 条正常、1 条缺严重等级、1 条外片区 ==")
_, resp = batch("分派处理", [
    {"缺陷编号": "DEFE-0001", "缺陷设备": "1号逆变器 INVE-0001"},
    {"缺陷编号": "DEFE-0003", "缺陷设备": "1号汇流箱 COMB-0003"},
    {"缺陷编号": "DEFE-0002", "缺陷设备": "1号主变 TRAN-0001"},
], team="南区运维班")
rm = result_map(resp)
check("汇总 succeeded=1 rejected=2", (resp["succeeded"], resp["rejected"]) == (1, 2), resp)
check("正常项分派成功", rm["DEFE-0001"]["ok"] and rm["DEFE-0001"]["status"] == "处理中")
check("缺严重等级单独打回", (not rm["DEFE-0003"]["ok"]) and "严重等级" in rm["DEFE-0003"]["message"])
check("外片区越权被拦", (not rm["DEFE-0002"]["ok"]) and "北区" in rm["DEFE-0002"]["message"])

d1 = get("/api/defect/2", team="北区运维班").json()
check("被拦的北区缺陷仍为待分派", d1["status"] == "待分派", d1["status"])
d3 = client.get("/api/defect/3").json()
check("打回原因写明", "缺严重等级" in d3.get("打回原因", ""), d3)

print("== 缺陷编号/设备逐条核对 ==")
_, resp = batch("分派处理", [
    {"缺陷编号": "DEFE-0002", "缺陷设备": "错的设备"},
    {"缺陷编号": "DEFE-9999", "缺陷设备": "幽灵设备"},
], team="北区运维班")
rm = result_map(resp)
check("设备对不上打回", not rm["DEFE-0002"]["ok"] and "设备与记录不符" in rm["DEFE-0002"]["message"])
check("编号不存在打回", not rm["DEFE-9999"]["ok"] and "不存在" in rm["DEFE-9999"]["message"])

print("== 状态不能越级（待分派不能直接验收、处理中不能直接关闭）==")
_, resp = batch("提交验收", [
    {"缺陷编号": "DEFE-0002", "缺陷设备": "1号主变 TRAN-0001"},
], team="北区运维班")
rm = result_map(resp)
check("待分派越级验收被拦", not rm["DEFE-0002"]["ok"] and "不能越级" in rm["DEFE-0002"]["message"])
# 已关闭且历史有通过结论的，重复提交沿用原判定（过往验收沿用原有判定）
_, resp = batch("提交验收", [
    {"缺陷编号": "DEFE-0008", "缺陷设备": "关口表计 METE-0002"},
], team="西区运维班")
rm = result_map(resp)
check("已关闭历史通过：沿用原判定", rm["DEFE-0008"]["ok"] and rm["DEFE-0008"]["重复提交"])
_, resp = batch("关闭缺陷", [
    {"缺陷编号": "DEFE-0001", "缺陷设备": "1号逆变器 INVE-0001"},
], team="南区运维班")
rm = result_map(resp)
check("处理中直接关闭被拦", not rm["DEFE-0001"]["ok"] and "不能越级" in rm["DEFE-0001"]["message"])

print("== 外队组只读：南区班动东区的处理中缺陷 ==")
_, resp = batch("提交验收", [
    {"缺陷编号": "DEFE-0004", "缺陷设备": "2号储能电池组 ENER-0002"},
], team="南区运维班")
rm = result_map(resp)
check("外队组提交验收被拦", not rm["DEFE-0004"]["ok"] and "仅可查看" in rm["DEFE-0004"]["message"])

print("== 本队组批量验收：DEFE-0007 通过、DEFE-0004 东区班通过 ==")
_, resp = batch("提交验收", [
    {"缺陷编号": "DEFE-0007", "缺陷设备": "1号逆变器 INVE-0001", "验收结论": "通过", "验收说明": "驱动板更换后试运正常"},
], team="南区运维班")
rm = result_map(resp)
check("南区缺陷验收通过", rm["DEFE-0007"]["ok"] and rm["DEFE-0007"]["status"] == "已验收")
_, resp = batch("提交验收", [
    {"缺陷编号": "DEFE-0004", "缺陷设备": "2号储能电池组 ENER-0002", "验收结论": "通过"},
], team="东区运维班")
check("东区缺陷验收通过", result_map(resp)["DEFE-0004"]["status"] == "已验收")

print("== 验收不通过：返工停在处理中，结论落库 ==")
_, resp = batch("提交验收", [
    {"缺陷编号": "DEFE-0005", "缺陷设备": "1号升压站 BOOS-0001", "验收结论": "不通过", "验收说明": "端子仍有发热"},
], team="北区运维班")
rm = result_map(resp)
check("不通过停在处理中", rm["DEFE-0005"]["ok"] and rm["DEFE-0005"]["status"] == "处理中")
al = client.get("/api/defect/ledger/accept").json()
check("不通过结论已落库", any(x["缺陷编号"] == "DEFE-0005" and x["验收结论"] == "不通过" for x in al["items"]))
# 整改后再次提交，通过
_, resp = batch("提交验收", [
    {"缺陷编号": "DEFE-0005", "缺陷设备": "1号升压站 BOOS-0001", "验收结论": "通过", "验收说明": "复紧后温度正常"},
], team="北区运维班")
check("返工后可再次验收通过", result_map(resp)["DEFE-0005"]["status"] == "已验收")

print("== 重复提交验收：同设备同缺陷已有通过结论，沿用最早一条 ==")
_, resp1 = batch("提交验收", [
    {"缺陷编号": "DEFE-0007", "缺陷设备": "1号逆变器 INVE-0001", "验收结论": "通过"},
], team="南区运维班")
_, resp2 = batch("提交验收", [
    {"缺陷编号": "DEFE-0007", "缺陷设备": "1号逆变器 INVE-0001", "验收结论": "不通过"},
], team="南区运维班")
m1, m2 = result_map(resp1)["DEFE-0007"], result_map(resp2)["DEFE-0007"]
check("重复提交提示沿用原判定", m1["重复提交"] and m2["重复提交"] and "沿用最早一条" in m2["message"])
al = client.get("/api/defect/ledger/accept").json()
n7_pass = [x for x in al["items"] if x["缺陷编号"] == "DEFE-0007" and x["验收结论"] == "通过"]
check("通过台账只有最早一条", len(n7_pass) == 1, n7_pass)
d7 = client.get("/api/defect/7").json()
check("状态仍是已验收，不被不通过冲掉", d7["status"] == "已验收")

print("== 顺序走完：已验收 -> 已关闭 ==")
d7 = client.get("/api/defect/7").json()
check("关闭前为已验收", d7["status"] == "已验收")
_, resp = batch("关闭缺陷", [
    {"缺陷编号": "DEFE-0007", "缺陷设备": "1号逆变器 INVE-0001"},
], team="南区运维班")
check("关闭成功", result_map(resp)["DEFE-0007"]["status"] == "已关闭")

print("== 同一批次内重复条目只留第一条（用东区 DEFE-0004）==")
_, resp = batch("关闭缺陷", [
    {"缺陷编号": "DEFE-0004", "缺陷设备": "2号储能电池组 ENER-0002"},
    {"缺陷编号": "DEFE-0004", "缺陷设备": "2号储能电池组 ENER-0002"},
], team="东区运维班")
check("同批第二条打回", resp["succeeded"] == 1 and "重复" in resp["results"][1]["message"])

print("== 台账：谁派的、谁验的可查 ==")
dl = client.get("/api/defect/ledger/dispatch").json()
check("分派台账有 DEFE-0001 且队组为南区",
      any(x["缺陷编号"] == "DEFE-0001" and x["分派队组"] == "南区运维班" for x in dl["items"]))
al = client.get("/api/defect/ledger/accept").json()
check("验收台账包含通过/不通过两类",
      {"通过", "不通过"} <= {x["验收结论"] for x in al["items"]})

print("== 列表权限标记 ==")
rows = get("/api/defect?status=处理中", team="南区运维班").json()["items"]
# DEFE-0003 打回后仍是待分派；处理中里南区自己的应为可验收，外区的只读
for row in rows:
    if row["所属片区"] == "南区":
        check(f"{row['缺陷编号']} 本区可验收", row["可验收"] and not row["只读"])
    else:
        check(f"{row['缺陷编号']} 外区只读", row["只读"] and not row["可验收"])

print("== 无队组（游客）只读 ==")
_, resp = batch("分派处理", [
    {"缺陷编号": "DEFE-0002", "缺陷设备": "1号主变 TRAN-0001"},
])
check("无队组不能改动", not result_map(resp)["DEFE-0002"]["ok"])

print(f"\n结果：{PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
