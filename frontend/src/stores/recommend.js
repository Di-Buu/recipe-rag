/**
 * 推荐查询状态管理
 */

import { defineStore } from 'pinia'
import { recommendAPI } from '../api'

export const useRecommendStore = defineStore('recommend', {
  state: () => ({
    loading: false,
    streaming: false,
    answer: '',
    sources: [],
    query: '',
    filters: null,
    error: '',
  }),

  actions: {
    /** 流式推荐查询 */
    async submitQuery(question, filters = null) {
      this.loading = true
      this.streaming = false
      this.error = ''
      this.answer = ''
      this.sources = []
      this.query = question
      this.filters = filters

      try {
        const response = await recommendAPI.queryStream(question, filters)
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        this.loading = false
        this.streaming = true

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          // 保留最后一行（可能不完整）
          buffer = lines.pop() || ''

          let eventType = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              const data = line.slice(6)
              try {
                if (eventType === 'sources') {
                  this.sources = JSON.parse(data)
                } else if (eventType === 'token') {
                  this.answer += JSON.parse(data)
                } else if (eventType === 'error') {
                  this.error = JSON.parse(data)
                }
              } catch {
                // 解析失败，忽略
              }
              eventType = ''
            }
          }
        }
      } catch (err) {
        this.error = err.message || '推荐查询失败，请稍后重试'
      } finally {
        this.loading = false
        this.streaming = false
      }
    },

    /** 清除结果 */
    clearResult() {
      this.answer = ''
      this.sources = []
      this.query = ''
      this.filters = null
      this.error = ''
    },
  },
})
