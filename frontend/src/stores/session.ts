import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '光伏电站运维管理平台',
    team: '运维一队',
    teams: {} as Record<string, string[]>,
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    teamRegions: (state) => state.teams[state.team] ?? [],
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setTeam(team: string) {
      this.team = team
    },
    setTeams(teams: Record<string, string[]>) {
      this.teams = teams
      if (!teams[this.team]) {
        this.team = Object.keys(teams)[0] ?? ''
      }
    },
  },
})
