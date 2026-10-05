<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">光伏电站运维管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向光伏组件、逆变器、汇流箱、变压器、储能与升压站运行监视的集中式电站运维后台。</span>
        <span class="head-user">
          当前值班：{{ store.operator }} · {{ store.shiftLabel }} ·
          <label class="team-switch">
            运维队组
            <select :value="store.team" @change="onTeamChange">
              <option v-for="name in teamNames" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { fetchJson } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "光伏阵列", path: "/pv_array" }, { label: "逆变器监视", path: "/inverter" }, { label: "汇流箱检测", path: "/combiner_box" }, { label: "变压器监视", path: "/transformer" }, { label: "储能电池组", path: "/energy_storage" }, { label: "升压站监视", path: "/boosting_station" }, { label: "关口计量", path: "/meter" }, { label: "环境监测站", path: "/environment" }, { label: "组件清洗", path: "/cleaning" }, { label: "巡视检查", path: "/patrol" }, { label: "缺陷管理", path: "/defect" }, { label: "检修计划", path: "/maintenance" }, { label: "备品备件", path: "/spare_parts" }, { label: "告警事件", path: "/alarm" }, { label: "调度指令", path: "/dispatch" }, { label: "安全措施", path: "/safety" }, { label: "运维合同", path: "/contract" }, { label: "运行月报", path: "/report" }]

const teamNames = computed(() => Object.keys(store.teams))

function onTeamChange(event: Event) {
  store.setTeam((event.target as HTMLSelectElement).value)
}

onMounted(async () => {
  try {
    const teams = await fetchJson<Record<string, string[]>>('/api/defect/teams')
    store.setTeams(teams)
  } catch {
    store.setTeams({ 运维一队: ['东区'], 运维二队: ['西区'], 运维三队: ['南区'] })
  }
})
</script>
