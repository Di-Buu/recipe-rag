/**
 * API 请求封装
 *
 * 基于 Axios 封装统一的请求实例，包含：
 * - JWT Token 自动附加
 * - 401 响应自动跳转登录
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器：附加 JWT Token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一错误处理
http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      // 避免循环：不在登录页弹消息
      if (window.location.pathname !== '/login') {
        ElMessage.warning('登录已过期，请重新登录')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

// ==================== 认证 API ====================

export const authAPI = {
  register(username, password) {
    return http.post('/api/auth/register', { username, password })
  },
  login(username, password) {
    return http.post('/api/auth/login', { username, password })
  },
  changePassword(old_password, new_password) {
    return http.put('/api/auth/password', { old_password, new_password })
  },
}

// ==================== 食谱 API ====================

export const recipeAPI = {
  getDetail(id) {
    return http.get(`/api/recipe/${id}`)
  },
  getRandom(count = 6) {
    return http.get('/api/recipes/random', { params: { count } })
  },
  getFilterOptions() {
    return http.get('/api/filters/options')
  },
}

// ==================== 推荐 API ====================

export const recommendAPI = {
  query(question, filters = null) {
    return http.post('/api/recommend', { question, filters }, { timeout: 120000 })
  },

  /**
   * 流式推荐查询（SSE）
   * @returns {Promise<Response>} 原生 fetch Response，由调用方消费 SSE 事件
   */
  async queryStream(question, filters = null) {
    const token = localStorage.getItem('token')
    const resp = await fetch('/api/recommend/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question, filters }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    return resp
  },
}

// ==================== 偏好 API ====================

export const preferenceAPI = {
  get() {
    return http.get('/api/preference')
  },
  update(preference) {
    return http.put('/api/preference', preference)
  },
}

// ==================== 历史 API ====================

export const historyAPI = {
  list(page = 1, size = 20) {
    return http.get('/api/history', { params: { page, size } })
  },
  getDetail(id) {
    return http.get(`/api/history/${id}`)
  },
  delete(id) {
    return http.delete(`/api/history/${id}`)
  },
}

export default http
