<template>
  <section class="page" data-module="defect">
    <header class="page-head">
      <div>
        <h2>缺陷管理</h2>
        <p class="page-desc">框选多条缺陷一起分派、一起提交验收；状态按 待分派→处理中→已验收→已关闭 顺序流转，不越级。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记设备缺陷</button>
        <button class="btn" type="button" @click="exportRows">导出缺陷管理清单</button>
      </div>
    </header>

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

    <div class="batch-bar">
      <span class="batch-count">已选 {{ selectedIds.length }} 条</span>
      <button class="btn primary" type="button" :disabled="!selectedIds.length" @click="runBatch('分派处理')">批量分派处理</button>
      <button class="btn primary" type="button" :disabled="!selectedIds.length" @click="runBatch('提交验收')">批量提交验收</button>
      <button class="btn" type="button" :disabled="!selectedIds.length" @click="runBatch('关闭缺陷')">批量关闭缺陷</button>
      <span class="batch-hint">逐条核对缺陷编号与缺陷设备，缺严重等级的单条打回，其余照常执行</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th><input type="checkbox" :checked="allChecked" @change="toggleAll" /></th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>分派人</th>
          <th>验收人</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>
            <input type="checkbox" :checked="selectedIds.includes(Number(row.id))" @change="toggleRow(row)" />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
          <td>{{ row.status }}</td>
          <td>{{ row['分派人'] || '—' }}</td>
          <td>{{ row['验收人'] || '—' }}</td>
          <td class="row-actions">
            <button
              v-if="nextAction(row) && canOperate(row)"
              class="link"
              type="button"
              @click="runAction(nextAction(row), row)"
            >
              {{ nextAction(row) }}
            </button>
            <span v-else-if="!canOperate(row)" class="muted-text">仅{{ row['所属片区'] || '所属片区' }}队组可操作</span>
            <span v-else class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 5" class="empty-state">暂无缺陷管理数据，可先登记设备缺陷</td>
        </tr>
      </tbody>
    </table>

    <div v-if="batchResults.length" class="batch-result">
      <p class="batch-result-title">{{ batchMessage }}</p>
      <ul>
        <li v-for="item in batchResults" :key="item.id" :class="item.ok ? 'ok-text' : 'error-text'">
          {{ item.ok ? '✓' : '✗' }} {{ item.message }}
        </li>
      </ul>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条缺陷管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>
type BatchResultItem = { id: number; ok: boolean; message: string }

const ENDPOINT = '/api/defect'
const columns = ["缺陷编号", "发现日期", "缺陷设备", "所属片区", "缺陷类别", "严重等级", "处理方案", "整改时限"]
const NEXT_ACTION: Record<string, string> = { '待分派': '分派处理', '处理中': '提交验收', '已验收': '关闭缺陷' }

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const summary = ref<Record<string, number>>({})
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const selectedIds = ref<number[]>([])
const batchResults = ref<BatchResultItem[]>([])
const batchMessage = ref('')

const stats = computed(() => [
  { label: '待分派', value: summary.value['待分派'] ?? 0 },
  { label: '处理中', value: summary.value['处理中'] ?? 0 },
  { label: '已验收', value: summary.value['已验收'] ?? 0 },
  { label: '已关闭', value: summary.value['已关闭'] ?? 0 },
])

const allChecked = computed(() => rows.value.length > 0 && rows.value.every((row) => selectedIds.value.includes(Number(row.id))))

function nextAction(row: Row): string {
  return NEXT_ACTION[String(row.status ?? '')] ?? ''
}

function canOperate(row: Row): boolean {
  return session.teamRegions.includes(String(row['所属片区'] ?? ''))
}

function toggleRow(row: Row) {
  const id = Number(row.id)
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function toggleAll() {
  selectedIds.value = allChecked.value ? [] : rows.value.map((row) => Number(row.id))
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '设备缺陷登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  batchResults.value = []
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, operator: session.operator, team: session.team } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message ?? '缺陷管理动作未生效，请稍后重试'
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷管理操作失败'
  }
}

async function runBatch(action: string) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/batch`, {
      method: 'POST',
      body: JSON.stringify({ action, ids: selectedIds.value, operator: session.operator, team: session.team }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail ?? '批量处置未生效，请稍后重试')
    }
    batchResults.value = payload.results ?? []
    batchMessage.value = payload.message ?? ''
    selectedIds.value = []
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量处置失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok) {
      throw new Error('设备缺陷列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      summary.value = await summaryResponse.json()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷管理列表读取失败'
  }
}

onMounted(reload)
</script>
