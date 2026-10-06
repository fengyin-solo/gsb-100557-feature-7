# 光伏电站运维管理平台

面向光伏组件、逆变器、汇流箱、变压器、储能与升压站运行监视的集中式电站运维后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 光伏阵列 | `pv_array` | 光伏阵列 | 阵列编号、所属片区、组件型号 |
| 逆变器监视 | `inverter` | 逆变器 | 逆变器编号、品牌型号、额定功率 |
| 汇流箱检测 | `combiner_box` | 汇流箱 | 汇流箱编号、所属阵列、输入路数 |
| 变压器监视 | `transformer` | 变压器 | 变压器编号、电压等级、额定容量 |
| 储能电池组 | `energy_storage` | 储能电池组 | 电池组编号、电池类型、额定容量 |
| 升压站监视 | `boosting_station` | 升压站 | 升压站编号、进线电压、出线电压 |
| 关口计量 | `meter` | 关口表计 | 表计编号、计量点名称、表计精度 |
| 环境监测站 | `environment` | 环境监测站 | 站点编号、安装位置、辐照度 |
| 组件清洗 | `cleaning` | 清洗任务 | 任务编号、清洗区域、清洗方式 |
| 巡视检查 | `patrol` | 巡视记录 | 记录编号、巡视区域、巡视日期 |
| 缺陷管理 | `defect` | 设备缺陷 | 缺陷编号、发现日期、缺陷设备 |
| 检修计划 | `maintenance` | 检修计划 | 计划编号、检修设备、检修类别 |
| 备品备件 | `spare_parts` | 备件物料 | 备件编号、备件名称、规格型号 |
| 告警事件 | `alarm` | 告警事件 | 告警编号、告警来源、告警类型 |
| 调度指令 | `dispatch` | 调度指令单 | 指令编号、下发单位、指令类型 |
| 安全措施 | `safety` | 安全措施票 | 措施编号、措施类型、涉及设备 |
| 运维合同 | `contract` | 运维合同 | 合同编号、合同名称、签约甲方 |
| 运行月报 | `report` | 运行月报 | 月报编号、统计月份、发电量 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 设备缺陷：批量分派与统一验收

缺陷管理（`defect`）在通用骨架之上实现了一套完整的批量处置闭环，所有业务判断都收口在
`app/services/defect.py`，路由层不做判断，验收口径全局只有这一份：

- **框选批量操作**：缺陷列表支持勾选、Shift 连选、全选本页可操作条目，一次批量分派、
  批量提交验收、批量关闭。接口 `POST /api/defect/batch/actions`。
- **逐条核对、单独打回**：每条按「缺陷编号 + 缺陷设备」与台账核对；编号不存在、设备对
  不上、缺严重等级、状态越级、非本片区队组提交的条目单独打回并写明原因，同批其余条目
  照常执行，互不连坐。批量返回 `results` 逐条结果。
- **状态严格顺序**：待分派 → 处理中 → 已验收 → 已关闭，只允许走到相邻的下一状态，不能
  越级；验收「不通过」属返工，结论落库但状态停在处理中，整改后可再次提交。
- **片区队组权限**：片区与运维队组一一对应（南/北/东/西运维班），只有缺陷所在片区的队
  组能分派、提交验收、关闭，其他队组点开只读。当前值班队组由请求头 `X-Operator-Team`
  或查询参数 `team` 带入，顶栏可切换；不带队组时仅可查看。
- **重复提交沿用原判定**：同一台设备的同一条缺陷重复提交验收，只认最早一条「通过」结
  论，重复提交直接沿用、不再新增台账；同一次提交内的重复条目只留第一条。
- **结论落库**：缺陷主表、分派台账、验收台账原子写入 `backend/data/defect_state.json`，
  服务重启后恢复，过往验收沿用原有判定。
- **检修工作台同源**：检修计划页的「检修待办工作台」直接调用
  `DefectService.workbench()`（`GET /api/maintenance/workbench`），与缺陷列表页的
  `GET /api/defect/workbench` 是同一份数据，两处数字一致。
- **台账可查**：`GET /api/defect/ledger/dispatch`（谁派的）与
  `GET /api/defect/ledger/accept`（谁验的、结论、卡在哪个队组）。
- 后端冒烟测试：`cd backend && python3 smoke_test.py`。

