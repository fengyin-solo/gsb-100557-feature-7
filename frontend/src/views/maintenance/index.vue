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

    <section class="workbench">
      <h3 class="workbench-title">检修工作台</h3>
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">缺陷待办合计</span>
          <strong class="stat-value">{{ defectTodo.length }}</strong>
        </article>
        <article v-for="item in defectStats" :key="item.label" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>缺陷编号</th>
            <th>缺陷设备</th>
            <th>所属片区</th>
            <th>严重等级</th>
            <th>状态</th>
            <th>分派人</th>
            <th>验收人</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in defectTodo" :key="String(row.id)">
            <td>{{ row['缺陷编号'] || '—' }}</td>
            <td>{{ row['缺陷设备'] || '—' }}</td>
            <td>{{ row['所属片区'] || '—' }}</td>
            <td>{{ row['严重等级'] || '—' }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row['分派人'] || '—' }}</td>
            <td>{{ row['验收人'] || '—' }}</td>
          </tr>
          <tr v-if="!defectTodo.length">
            <td colspan="7" class="empty-state">当前没有待办缺陷</td>
          </tr>
        </tbody>
      </table>
      <p class="workbench-note">缺陷待办与缺陷管理列表共用同一份统计口径，两处读数一致。</p>
    </section>

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

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/maintenance'
const columns = ["计划编号", "检修设备", "检修类别", "计划开始", "计划结束", "责任人", "安全措施", "计划状态"]
const actions = ["提交审批", "开始执行", "确认完工"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const defectSummary = ref<Record<string, number>>({})
const defectTodo = ref<Row[]>([])
const planSummary = ref<Record<string, number>>({})

const defectStats = computed(() => [
  { label: '待分派', value: defectSummary.value['待分派'] ?? 0 },
  { label: '处理中', value: defectSummary.value['处理中'] ?? 0 },
  { label: '已验收', value: defectSummary.value['已验收'] ?? 0 },
])

const stats = computed(() => [
  { label: '待审批计划', value: planSummary.value['待审批'] ?? 0 },
  { label: '执行中计划', value: planSummary.value['执行中'] ?? 0 },
  { label: '已完工计划', value: planSummary.value['已完工'] ?? 0 },
])

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
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message ?? '检修计划动作未生效，请稍后重试'
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
    const [listResponse, workbenchResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/workbench`),
    ])
    if (!listResponse.ok) {
      throw new Error('检修计划列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (workbenchResponse.ok) {
      const workbench = await workbenchResponse.json()
      defectSummary.value = workbench.defect_summary ?? {}
      defectTodo.value = workbench.defect_todo ?? []
      planSummary.value = workbench.plan_summary ?? {}
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检修计划列表读取失败'
  }
}

onMounted(reload)
</script>
