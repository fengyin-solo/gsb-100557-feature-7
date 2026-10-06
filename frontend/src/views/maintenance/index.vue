<template>
  <section class="page" data-module="maintenance">
    <header class="page-head">
      <div>
        <h2>检修计划管理</h2>
        <p class="page-desc">维护检修计划，围绕计划编号、检修设备、检修类别、计划开始做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检修计划</button>
        <button class="btn" type="button" @click="exportRows">导出检修计划清单</button>
      </div>
    </header>

    <!-- 检修待办工作台：数据直接来自缺陷服务，与缺陷列表页同一份口径 -->
    <div class="stat-row">
      <article v-for="item in defectStats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>
    <div class="bulk-bar" style="border-left-color:#b54708">
      <span>检修待办工作台（缺陷处置联动）· 当前队组：<b>{{ session.team || '未选择' }}</b></span>
      <label class="team-hint">
        <input v-model="onlyMyTodos" type="checkbox" style="width:auto" :disabled="!session.team" />
        只看本队组待办
      </label>
      <button class="btn" type="button" @click="loadWorkbench">刷新待办</button>
      <span class="spacer"></span>
      <span class="team-hint">待办 {{ workbench.待办总数 ?? 0 }} 条 · 本队组 {{ workbench.本队组待办数 ?? 0 }} 条 · 未关闭缺陷 {{ workbench.未关闭总数 ?? 0 }} 条（与缺陷列表同源）</span>
    </div>
    <table class="data-table" style="margin-bottom:18px">
      <thead>
        <tr>
          <th>缺陷编号</th><th>检修设备</th><th>片区</th><th>责任队组</th><th>严重等级</th>
          <th>处理方案</th><th>整改时限</th><th>缺陷状态</th><th>待办</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, idx) in todos" :key="`${item['缺陷编号']}-${idx}`">
          <td>{{ item['缺陷编号'] }}</td>
          <td>{{ item['检修设备'] }}</td>
          <td>{{ item['所属片区'] }}</td>
          <td>
            <b>{{ item['责任队组'] }}</b>
            <span v-if="session.team && item['本队组待办']" class="tag tag-green" style="margin-left:4px">本队组</span>
          </td>
          <td>
            <span :class="item['严重等级'] === '危急' ? 'tag tag-red' : item['严重等级'] === '严重' ? 'tag tag-orange' : 'tag tag-blue'" class="tag">
              {{ item['严重等级'] || '缺等级' }}
            </span>
          </td>
          <td>{{ item['处理方案'] || '—' }}</td>
          <td>{{ item['整改时限'] || '—' }}</td>
          <td>
            <span :class="{
              'tag tag-gray': item['缺陷状态'] === '待分派',
              'tag tag-blue': item['缺陷状态'] === '处理中',
              'tag tag-green': item['缺陷状态'] === '已验收',
            }" class="tag">{{ item['缺陷状态'] }}</span>
          </td>
          <td>{{ item['待办类型'] }}（{{ item['待办说明'] }}）</td>
        </tr>
        <tr v-if="!todos.length">
          <td colspan="9" class="empty-state">暂无检修待办（所有缺陷均已关闭）</td>
        </tr>
      </tbody>
    </table>

    <h3 style="font-size:15px;margin:0 0 8px">检修计划</h3>
    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检修计划数据，可先登记检修计划</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检修计划记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>
type TodoRow = Record<string, string | number | boolean | null>

const session = useSessionStore()
const ENDPOINT = '/api/maintenance'
const DEFECT_STATUS = ['待分派', '处理中', '已验收', '已关闭']
const columns = ["计划编号", "检修设备", "检修类别", "计划开始", "计划结束", "责任人", "安全措施", "计划状态"]
const actions = ["提交审批", "开始执行", "确认完工"]
const statuses = ["待审批", "已批复", "执行中", "已完工"]
const stats = ref([{"label": "待审批计划", "value": 0}, {"label": "执行中计划", "value": 0}, {"label": "本月完工数", "value": 0}])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

// 检修待办：与缺陷列表共用 DefectService.workbench 同一份数据
const workbench = ref<Record<string, any>>({})
const onlyMyTodos = ref(true)
const todos = computed<TodoRow[]>(() => (workbench.value.todos ?? []) as TodoRow[])
const defectStats = computed(() =>
  DEFECT_STATUS.map((status) => ({ label: `缺陷·${status}`, value: workbench.value.counts?.[status] ?? 0 })),
)

async function loadWorkbench() {
  try {
    const params = new URLSearchParams()
    if (onlyMyTodos.value && session.team) params.set('team', session.team)
    const response = await request(`${ENDPOINT}/workbench?${params.toString()}`)
    if (!response.ok) throw new Error('检修待办读取失败')
    workbench.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检修待办读取失败'
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检修计划登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('检修计划动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检修计划操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('检修计划列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检修计划列表读取失败'
  }
  void loadWorkbench()
}

onMounted(() => {
  void reload()
})
</script>

