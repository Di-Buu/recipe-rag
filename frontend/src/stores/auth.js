/**
 * 认证状态管理
 */

import { defineStore } from 'pinia'
import { authAPI } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: null,
    username: '',
    isNewUser: false,
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
  },

  actions: {
    /** 从 localStorage 恢复登录状态 */
    loadFromStorage() {
      this.token = localStorage.getItem('token')
      this.username = localStorage.getItem('username') || ''
      this.isNewUser = localStorage.getItem('isNewUser') === 'true'
    },

    /** 保存登录信息到 localStorage */
    _saveToStorage(token, username, isNewUser) {
      this.token = token
      this.username = username
      this.isNewUser = isNewUser
      localStorage.setItem('token', token)
      localStorage.setItem('username', username)
      localStorage.setItem('isNewUser', String(isNewUser))
    },

    /** 登录 */
    async login(username, password) {
      const { data } = await authAPI.login(username, password)
      this._saveToStorage(data.token, data.username, data.is_new_user)
      return data
    },

    /** 注册 */
    async register(username, password) {
      const { data } = await authAPI.register(username, password)
      this._saveToStorage(data.token, data.username, data.is_new_user)
      return data
    },

    /** 退出登录 */
    logout() {
      this.token = null
      this.username = ''
      this.isNewUser = false
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('isNewUser')
    },

    /** 标记为非新用户 */
    markNotNew() {
      this.isNewUser = false
      localStorage.setItem('isNewUser', 'false')
    },

    /** 修改密码 */
    async changePassword(oldPassword, newPassword) {
      await authAPI.changePassword(oldPassword, newPassword)
    },
  },
})
