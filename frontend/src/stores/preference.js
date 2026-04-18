/**
 * 用户偏好状态管理
 */

import { defineStore } from 'pinia'
import { preferenceAPI } from '../api'

export const usePreferenceStore = defineStore('preference', {
  state: () => ({
    preference: {
      exclude_ingredients: [],
      preferred_categories: [],
      nutrition_goals: [],
      difficulty_max: null,
      costtime_max: null,
    },
    loading: false,
    loaded: false,
  }),

  actions: {
    /** 从服务器获取当前偏好 */
    async fetchPreference() {
      this.loading = true
      try {
        const { data } = await preferenceAPI.get()
        this.preference = data
        this.loaded = true
      } catch {
        // 偏好获取失败不阻塞使用
      } finally {
        this.loading = false
      }
    },

    /** 保存偏好到服务器 */
    async savePreference(pref) {
      this.loading = true
      try {
        const { data } = await preferenceAPI.update(pref)
        this.preference = data
        this.loaded = true
      } finally {
        this.loading = false
      }
    },
  },
})
