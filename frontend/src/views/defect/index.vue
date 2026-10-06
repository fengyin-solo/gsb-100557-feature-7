<template>
  <section class="page" data-module="defect">
    <header class="page-head">
      <div>
        <h2>缺陷管理</h2>
        <p class="page-desc">
          支持框选多条缺陷一起分派、一起提交验收；按「缺陷编号 + 缺陷设备」逐条核对，
          缺严重等级等不合格项单独打回，其余照常执行。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="openLedger('dispatch')">分派台账</button>
        <button class="btn" type="button" @click="openLedger('accept')">验收台账</button>
        <button class="btn" type="button" @click="exportRows">导出清单</button>
      </div>
    </header>

    <div class="team-hint">
      当前值班队组：<b>{{ session.team || '未选择（仅可查看）' }}</b
      ><template v-if="session.teamArea">，负责片区：{{ session.teamArea }}（顶栏可切换）</template>
      ；只有缺陷所在片区的运维队组能分派/提交验收，其他队组点开只能查看。
    </div>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>缺陷编号</span>
        <input v-model="keyword" placeholder="按缺陷编号检索" />
      </label>
      <label class="filter-item">
        <span>缺陷状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>所属片区</span>
        <select v-model="areaFilter">
          <option value="">全部</option>
          <option v-for="a in areas" :key="a" :value="a">{{ a }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>只看本队组可处理</span>
        <input v-model="onlyMine" type="checkbox" :disabled="!session.team" style="width:auto" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="selectableRows.length" class="bulk-bar">
      <span>已选 <span class="selected-count">{{ selected.size }}</span> 条（本页可勾选 {{ selectableRows.length }} 条）</span>
      <button class="btn" type="button" @click="selectAllPage">全选本页可操作</button>
      <button class="btn ghost" type="button" @click="selected.clear()">清空选择</button>
      <span class="spacer"></span>
      <button class="btn primary" type="button" :disabled="!selected.size" @click="openBatch('分派处理')">
        批量分派
      </button>
      <button class="btn primary" type="button" :disabled="!selected.size" @click="openAccept()">
        批量提交验收
      </button>
      <button class="btn" type="button" :disabled="!selected.size" @click="openBatch('关闭缺陷')">
        批量关闭
      </button>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="col-check">
            <input
              type="checkbox"
              :checked="pageAllSelected"
              :indeterminate.prop="selected.size > 0 && !pageAllSelected"
              @change="togglePageAll"
              title="全选/取消本页可操作条目"
            />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>所属片区</th>
          <th>责任队组</th>
          <th>操作与查看</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in rows"
          :key="String(row.id)"
          :class="{ 'row-readonly': row.只读 }"
        >
          <td class="col-check">
            <input
              v-if="isSelectable(row)"
              v-model="rowSelection[String(row.id)]"
              type="checkbox"
              @click="onCheckClick($event, index)"
              @change="syncSelection"
            />
            <span v-else title="非本队组片区，或当前状态不可操作">—</span>
          </td>
          <td>{{ row['缺陷编号'] }}</td>
          <td>{{ row['发现日期'] }}</td>
          <td>{{ row['缺陷设备'] }}</td>
          <td>{{ row['缺陷类别'] ?? '—' }}</td>
          <td>
            <span v-if="row['严重等级']" :class="severityClass(row['严重等级'])" class="tag">{{ row['严重等级'] }}</span>
            <span v-else class="tag tag-red" title="缺严重等级的条目会被单独打回">缺等级⚠</span>
          </td>
          <td>{{ row['处理方案'] || '—' }}</td>
          <td>{{ row['整改时限'] || '—' }}</td>
          <td><span :class="statusClass(row.status)" class="tag status-pill">{{ row.status }}</span></td>
          <td>{{ row['所属片区'] }}</td>
          <td>{{ row['责任队组'] || '未分派' }}</td>
          <td class="row-actions">
            <button v-if="row.可分派" class="link" type="button" @click="singleAction('分派处理', row)">分派</button>
            <button v-if="row.可验收" class="link" type="button" @click="singleAccept(row)">提交验收</button>
            <button v-if="row.可关闭" class="link" type="button" @click="singleAction('关闭缺陷', row)">关闭</button>
            <button class="link" type="button" @click="openDetail(row)">明细</button>
            <span v-if="row.只读" class="team-hint" title="非本队组片区，只能查看">只读</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 4" class="empty-state">暂无符合条件的缺陷</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条缺陷记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 批量分派 / 关闭确认 -->
    <div v-if="batchDialog.open" class="modal-mask" @click.self="batchDialog.open = false">
      <div class="modal">
        <div class="modal-head">
          <h3>{{ batchDialog.action }}（{{ batchDialog.items.length }} 条）</h3>
          <button class="modal-close" type="button" @click="batchDialog.open = false">×</button>
        </div>
        <div class="modal-body">
          <p class="team-hint">
            将逐条核对缺陷编号与缺陷设备：缺严重等级、状态越级、非本队组片区的条目会被单独打回并写明原因，
            其余条目照常执行。
          </p>
          <table class="data-table">
            <thead><tr><th>缺陷编号</th><th>缺陷设备</th><th>片区</th><th>严重等级</th><th>当前状态</th></tr></thead>
            <tbody>
              <tr v-for="item in batchDialog.items" :key="String(item.id)">
                <td>{{ item['缺陷编号'] }}</td>
                <td>{{ item['缺陷设备'] }}</td>
                <td>{{ item['所属片区'] }}</td>
                <td>
                  <span v-if="item['严重等级']">{{ item['严重等级'] }}</span>
                  <span v-else class="error-text">缺等级，将被打回</span>
                </td>
                <td>{{ item.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-foot">
          <button class="btn ghost" type="button" :disabled="submitting" @click="batchDialog.open = false">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitBatch">
            {{ submitting ? '执行中…' : `确认${batchDialog.action}` }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批量验收 -->
    <div v-if="acceptDialog.open" class="modal-mask" @click.self="acceptDialog.open = false">
      <div class="modal">
        <div class="modal-head">
          <h3>提交验收（{{ acceptDialog.items.length }} 条）· {{ session.team }}</h3>
          <button class="modal-close" type="button" @click="acceptDialog.open = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid" style="margin-bottom:12px">
            <label>
              验收结论
              <span class="radio-row" style="margin-top:4px">
                <label><input v-model="acceptDialog.conclusion" type="radio" value="通过" /> 验收通过</label>
                <label><input v-model="acceptDialog.conclusion" type="radio" value="不通过" /> 不通过（返工，停在处理中）</label>
              </span>
            </label>
            <label>
              验收说明
              <textarea v-model="acceptDialog.note" rows="2" placeholder="如：试运正常 / 仍有发热需返工"></textarea>
            </label>
          </div>
          <table class="data-table">
            <thead><tr><th>缺陷编号</th><th>缺陷设备</th><th>片区</th><th>严重等级</th><th>整改时限</th></tr></thead>
            <tbody>
              <tr v-for="item in acceptDialog.items" :key="String(item.id)">
                <td>{{ item['缺陷编号'] }}</td>
                <td>{{ item['缺陷设备'] }}</td>
                <td>{{ item['所属片区'] }}</td>
                <td>
                  <span v-if="item['严重等级']">{{ item['严重等级'] }}</span>
                  <span v-else class="error-text">缺等级，将被打回</span>
                </td>
                <td>{{ item['整改时限'] || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p class="team-hint" style="margin-top:8px">
            同一台设备的同一条缺陷重复提交验收，只认最早一条「通过」结论；已有结论的会直接沿用原判定，不重复受理。
          </p>
        </div>
        <div class="modal-foot">
          <button class="btn ghost" type="button" :disabled="submitting" @click="acceptDialog.open = false">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitAccept">
            {{ submitting ? '提交中…' : '确认提交验收' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 逐条结果 -->
    <div v-if="resultDialog.open" class="modal-mask" @click.self="resultDialog.open = false">
      <div class="modal wide">
        <div class="modal-head">
          <h3>{{ resultDialog.action }} · 逐条核对结果</h3>
          <button class="modal-close" type="button" @click="resultDialog.open = false">×</button>
        </div>
        <div class="modal-body">
          <div :class="resultDialog.data?.rejected ? 'result-summary has-reject' : 'result-summary all-ok'">
            {{ resultDialog.data?.message }}
          </div>
          <table class="data-table result-table">
            <thead><tr><th style="width:70px">结果</th><th>缺陷编号</th><th>缺陷设备</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="(item, idx) in resultDialog.data?.results ?? []" :key="idx">
                <td>
                  <span v-if="item.ok" class="result-ok">✓ 受理</span>
                  <span v-else class="result-bad">✗ 打回</span>
                </td>
                <td>{{ item['缺陷编号'] }}</td>
                <td>{{ item['缺陷设备'] }}</td>
                <td>{{ item.message }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-foot">
          <button class="btn primary" type="button" @click="resultDialog.open = false">知道了</button>
        </div>
      </div>
    </div>

    <!-- 缺陷明细 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <div class="modal-head">
          <h3>缺陷明细 · {{ detail['缺陷编号'] }}</h3>
          <button class="modal-close" type="button" @click="detail = null">×</button>
        </div>
        <div class="modal-body">
          <dl class="kv-list">
            <dt>缺陷设备</dt><dd>{{ detail['缺陷设备'] }}</dd>
            <dt>所属片区</dt><dd>{{ detail['所属片区'] }}（{{ detail['归属队组'] }}）</dd>
            <dt>严重等级</dt>
            <dd>
              <span v-if="detail['严重等级']" :class="severityClass(detail['严重等级'])" class="tag">{{ detail['严重等级'] }}</span>
              <span v-else class="tag tag-red">缺严重等级（打回原因：{{ detail['打回原因'] || '补录后重新提交' }}）</span>
            </dd>
            <dt>当前状态</dt><dd>{{ detail.status }}（待分派 → 处理中 → 已验收 → 已关闭，不可越级）</dd>
            <dt>处理方案</dt><dd>{{ detail['处理方案'] || '—' }}</dd>
            <dt>整改时限</dt><dd>{{ detail['整改时限'] || '—' }}</dd>
            <dt>责任队组</dt><dd>{{ detail['责任队组'] || '未分派' }}</dd>
            <dt>验收结论</dt>
            <dd>
              <span :class="detail['验收结论'] === '不通过' ? 'tag tag-red' : 'tag tag-green'" class="tag">
                {{ detail['验收结论'] || '暂无' }}
              </span>
              <span v-if="detail['验收时间']" class="team-hint">（{{ detail['验收人'] }} · {{ detail['验收时间'] }}）</span>
            </dd>
            <dt>操作权限</dt><dd>{{ detail.只读 ? '当前队组仅可查看，不能改动' : '当前队组可操作' }}</dd>
          </dl>

          <h4 style="margin:14px 0 4px;font-size:13px">分派轨迹（谁派的）</h4>
          <div class="trace-box">
            <div v-if="!detail['分派轨迹']?.length" class="team-hint">暂无分派记录</div>
            <div v-for="(t, i) in detail['分派轨迹']" :key="i" class="trace-line">
              {{ t['分派时间'] }} 分派给 <b>{{ t['分派队组'] }}</b>（{{ t['所属片区'] }}），整改时限 {{ t['整改时限'] }}
            </div>
          </div>

          <h4 style="margin:14px 0 4px;font-size:13px">验收轨迹（卡在哪、结论是什么）</h4>
          <div class="trace-box">
            <div v-if="!detail['验收轨迹']?.length" class="team-hint">暂无验收记录</div>
            <div v-for="(t, i) in detail['验收轨迹']" :key="i" class="trace-line">
              {{ t['验收时间'] }} {{ t['验收队组'] }} 提交验收，结论：
              <b :class="t['验收结论'] === '通过' ? 'result-ok' : 'result-bad'">{{ t['验收结论'] }}</b>
              <template v-if="t['验收说明']">（{{ t['验收说明'] }}）</template>
            </div>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 台账 -->
    <div v-if="ledgerDialog.open" class="modal-mask" @click.self="ledgerDialog.open = false">
      <div class="modal wide">
        <div class="modal-head">
          <h3>{{ ledgerDialog.title }}</h3>
          <button class="modal-close" type="button" @click="ledgerDialog.open = false">×</button>
        </div>
        <div class="modal-body">
          <div class="tabs">
            <button
              class="tab"
              :class="{ active: ledgerDialog.kind === 'dispatch' }"
              type="button"
              @click="switchLedger('dispatch')"
            >分派台账</button>
            <button
              class="tab"
              :class="{ active: ledgerDialog.kind === 'accept' }"
              type="button"
              @click="switchLedger('accept')"
            >验收台账</button>
            <input v-model="ledgerKeyword" placeholder="按缺陷编号/设备检索" @keyup.enter="loadLedger" style="margin-left:12px;padding:4px 8px" />
            <button class="btn" type="button" @click="loadLedger">检索</button>
          </div>
          <table v-if="ledgerDialog.kind === 'dispatch'" class="data-table">
            <thead><tr><th>分派时间</th><th>缺陷编号</th><th>缺陷设备</th><th>片区</th><th>分派队组</th><th>整改时限</th></tr></thead>
            <tbody>
              <tr v-for="item in ledgerDialog.items" :key="item.id">
                <td>{{ item['分派时间'] }}</td><td>{{ item['缺陷编号'] }}</td><td>{{ item['缺陷设备'] }}</td>
                <td>{{ item['所属片区'] }}</td><td><b>{{ item['分派队组'] }}</b></td><td>{{ item['整改时限'] }}</td>
              </tr>
              <tr v-if="!ledgerDialog.items.length"><td colspan="6" class="empty-state">暂无记录</td></tr>
            </tbody>
          </table>
          <table v-else class="data-table">
            <thead><tr><th>验收时间</th><th>缺陷编号</th><th>缺陷设备</th><th>片区</th><th>验收队组</th><th>结论</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="item in ledgerDialog.items" :key="item.id">
                <td>{{ item['验收时间'] }}</td><td>{{ item['缺陷编号'] }}</td><td>{{ item['缺陷设备'] }}</td>
                <td>{{ item['所属片区'] }}</td><td><b>{{ item['验收队组'] }}</b></td>
                <td>
                  <span :class="item['验收结论'] === '通过' ? 'tag tag-green' : 'tag tag-red'" class="tag">
                    {{ item['验收结论'] }}
                  </span>
                </td>
                <td>{{ item['验收说明'] || '—' }}</td>
              </tr>
              <tr v-if="!ledgerDialog.items.length"><td colspan="7" class="empty-state">暂无记录</td></tr>
            </tbody>
          </table>
        </div>
        <div class="modal-foot">
          <button class="btn primary" type="button" @click="ledgerDialog.open = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { AREA_TEAMS, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>
type BatchResult = {
  ok: boolean
  action: string
  message: string
  total: number
  succeeded: number
  rejected: number
  results: { 缺陷编号: string; 缺陷设备: string; ok: boolean; message: string; status?: string; 重复提交?: boolean }[]
}

const ENDPOINT = '/api/defect'
const session = useSessionStore()

const columns = ['缺陷编号', '发现日期', '缺陷设备', '缺陷类别', '严重等级', '处理方案', '整改时限', '缺陷状态']
const statuses = ['待分派', '处理中', '已验收', '已关闭']
const areas = AREA_TEAMS.map((item) => item.area)

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const areaFilter = ref('')
const onlyMine = ref(false)
const submitting = ref(false)

const stats = ref([
  { label: '待分派', value: 0 },
  { label: '处理中', value: 0 },
  { label: '已验收', value: 0 },
  { label: '已关闭', value: 0 },
])

/** 当前队组 + 当前状态下可勾选的行：待分派可分派、处理中可验收、已验收可关闭。 */
function isSelectable(row: Row): boolean {
  return Boolean(session.team && !row.只读 && (row.可分派 || row.可验收 || row.可关闭))
}

const selectableRows = computed(() => rows.value.filter(isSelectable))
const rowSelection = reactive<Record<string, boolean>>({})

const selected = reactive<Set<number>>(new Set())
const lastClickedIndex = ref<number | null>(null)

const pageAllSelected = computed(
  () => selectableRows.value.length > 0 && selectableRows.value.every((row) => selected.has(Number(row.id))),
)

function onCheckClick(event: MouseEvent, index: number) {
  // Shift 连选：框选一段连续的可操作条目
  if (event.shiftKey && lastClickedIndex.value !== null) {
    const [from, to] = [lastClickedIndex.value, index].sort((a, b) => a - b)
    const willCheck = !selected.has(Number(rows.value[index].id))
    for (let i = from; i <= to; i += 1) {
      const row = rows.value[i]
      if (!isSelectable(row)) continue
      if (willCheck) selected.add(Number(row.id))
      else selected.delete(Number(row.id))
    }
  }
  lastClickedIndex.value = index
}

function syncSelection() {
  rows.value.forEach((row) => {
    const id = Number(row.id)
    if (rowSelection[id]) selected.add(id)
    else selected.delete(id)
  })
}

function togglePageAll() {
  if (pageAllSelected.value) {
    selectableRows.value.forEach((row) => selected.delete(Number(row.id)))
    selectableRows.value.forEach((row) => { rowSelection[Number(row.id)] = false })
  } else {
    selectableRows.value.forEach((row) => {
      selected.add(Number(row.id))
      rowSelection[Number(row.id)] = true
    })
  }
}

function selectAllPage() {
  selectableRows.value.forEach((row) => {
    selected.add(Number(row.id))
    rowSelection[Number(row.id)] = true
  })
}

function severityClass(level: unknown): string {
  const text = String(level ?? '')
  if (text === '危急') return 'tag tag-red'
  if (text === '严重') return 'tag tag-orange'
  return 'tag tag-blue'
}

function statusClass(status: unknown): string {
  return {
    待分派: 'tag tag-gray',
    处理中: 'tag tag-blue',
    已验收: 'tag tag-green',
    已关闭: 'tag tag-dark',
  }[String(status)] ?? 'tag tag-gray'
}

function teamQuery(): string {
  return session.team ? `team=${encodeURIComponent(session.team)}` : ''
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  areaFilter.value = ''
  onlyMine.value = false
  void reload()
}

function exportRows() {
  const query = teamQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value) params.set('keyword', keyword.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  const area = onlyMine.value && session.teamArea ? session.teamArea : areaFilter.value
  if (area) params.set('area', area)
  if (session.team) params.set('team', session.team)
  params.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error('设备缺陷列表读取失败')
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
    // 清掉已不在列表中的勾选项
    const ids = new Set(rows.value.map((row) => Number(row.id)))
    Array.from(selected).forEach((id) => { if (!ids.has(id)) selected.delete(id) })
    Object.keys(rowSelection).forEach((id) => { if (!ids.has(Number(id))) delete rowSelection[id] })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷管理列表读取失败'
  }
  void loadWorkbench()
}

async function loadWorkbench() {
  try {
    const qs = teamQuery()
    const response = await request(`${ENDPOINT}/workbench${qs ? `?${qs}` : ''}`)
    if (!response.ok) return
    const payload = await response.json()
    stats.value = statuses.map((status) => ({ label: status, value: payload.counts[status] ?? 0 }))
  } catch {
    // 统计卡片失败不影响列表
  }
}

// ---------- 批量动作 ----------

const batchDialog = reactive({ open: false, action: '分派处理', items: [] as Row[] })
const acceptDialog = reactive({ open: false, items: [] as Row[], conclusion: '通过', note: '' })
const resultDialog = reactive<{ open: boolean; action: string; data: BatchResult | null }>({
  open: false,
  action: '',
  data: null,
})

function selectedRows(): Row[] {
  return rows.value.filter((row) => selected.has(Number(row.id)))
}

function openBatch(action: string) {
  if (!session.team) {
    errorMessage.value = '请先在顶栏选择值班队组；未选择队组时只能查看'
    return
  }
  const picked = selectedRows()
  if (!picked.length) return
  batchDialog.action = action
  batchDialog.items = picked
  batchDialog.open = true
}

function openAccept() {
  if (!session.team) {
    errorMessage.value = '请先在顶栏选择值班队组；未选择队组时只能查看'
    return
  }
  const picked = selectedRows().filter((row) => row.可验收)
  if (!picked.length) {
    errorMessage.value = '勾选的条目中没有「处理中」可验收的缺陷'
    return
  }
  acceptDialog.items = picked
  acceptDialog.conclusion = '通过'
  acceptDialog.note = ''
  acceptDialog.open = true
}

async function postBatch(action: string, items: Record<string, unknown>[]) {
  submitting.value = true
  errorMessage.value = ''
  try {
    const qs = teamQuery()
    const response = await request(`${ENDPOINT}/batch/actions${qs ? `?${qs}` : ''}`, {
      method: 'POST',
      body: JSON.stringify({ action, items }),
    })
    if (!response.ok) throw new Error('批量动作未生效，请稍后重试')
    const data = (await response.json()) as BatchResult
    batchDialog.open = false
    acceptDialog.open = false
    resultDialog.open = true
    resultDialog.action = action
    resultDialog.data = data
    selected.clear()
    Object.keys(rowSelection).forEach((key) => { rowSelection[key] = false })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量操作失败'
  } finally {
    submitting.value = false
    void reload()
  }
}

function submitBatch() {
  void postBatch(
    batchDialog.action,
    batchDialog.items.map((row) => ({ 缺陷编号: row['缺陷编号'], 缺陷设备: row['缺陷设备'] })),
  )
}

function submitAccept() {
  void postBatch(
    '提交验收',
    acceptDialog.items.map((row) => ({
      缺陷编号: row['缺陷编号'],
      缺陷设备: row['缺陷设备'],
      验收结论: acceptDialog.conclusion,
      验收说明: acceptDialog.note,
    })),
  )
}

async function singleAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const qs = teamQuery()
    const response = await request(`${ENDPOINT}/${row.id}/actions${qs ? `?${qs}` : ''}`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '动作未生效')
    void reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

function singleAccept(row: Row) {
  selected.clear()
  Object.keys(rowSelection).forEach((key) => { rowSelection[key] = false })
  selected.add(Number(row.id))
  rowSelection[Number(row.id)] = true
  openAccept()
}

// ---------- 明细 ----------

const detail = ref<Record<string, any> | null>(null)

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const qs = teamQuery()
    const response = await request(`${ENDPOINT}/${row.id}${qs ? `?${qs}` : ''}`)
    if (!response.ok) throw new Error('缺陷明细读取失败')
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷明细读取失败'
  }
}

// ---------- 台账 ----------

const ledgerDialog = reactive({
  open: false,
  kind: 'dispatch' as 'dispatch' | 'accept',
  title: '分派台账',
  items: [] as Record<string, any>[],
})
const ledgerKeyword = ref('')

function openLedger(kind: 'dispatch' | 'accept') {
  ledgerDialog.open = true
  ledgerDialog.kind = kind
  ledgerKeyword.value = ''
  void loadLedger()
}

function switchLedger(kind: 'dispatch' | 'accept') {
  ledgerDialog.kind = kind
  ledgerKeyword.value = ''
  void loadLedger()
}

async function loadLedger() {
  const params = new URLSearchParams()
  if (ledgerKeyword.value) params.set('keyword', ledgerKeyword.value)
  const response = await request(`${ENDPOINT}/ledger/${ledgerDialog.kind}?${params.toString()}`)
  if (!response.ok) {
    errorMessage.value = '台账读取失败'
    return
  }
  const payload = await response.json()
  ledgerDialog.items = payload.items ?? []
  ledgerDialog.title = payload.ledger ?? ''
}

onMounted(reload)
</script>
