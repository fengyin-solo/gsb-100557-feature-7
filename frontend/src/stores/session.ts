import { defineStore } from 'pinia'

/** 片区与运维队组一一对应：只有本片区队组能改动片区内缺陷，其他队组只读。 */
export const AREA_TEAMS: { area: string; team: string }[] = [
  { area: '南区', team: '南区运维班' },
  { area: '北区', team: '北区运维班' },
  { area: '东区', team: '东区运维班' },
  { area: '西区', team: '西区运维班' },
]

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '光伏电站运维管理平台',
    // 当前值班队组；为空表示仅查看（游客），任何改动都会被后端拦下
    team: '南区运维班',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    /** 队组负责的片区，用于列表里直观展示权限范围。 */
    teamArea: (state) => AREA_TEAMS.find((item) => item.team === state.team)?.area ?? '',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setTeam(team: string) {
      this.team = team
    },
  },
})
