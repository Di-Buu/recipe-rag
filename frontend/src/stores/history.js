/**
 * 推荐历史状态管理
 */

import { defineStore } from 'pinia'
import { historyAPI } from '../api'

export const useHistoryStore = defineStore('history', {
  state: () => ({
    items: [],
    loading: false,
    currentPage: 1,
    hasMore: true,
  }),

  actions: {
    /** 获取历史记录（指定页码） */
    async fetchHistory(page = 1) {
      this.loading = true
      try {
        const { data } = await historyAPI.list(page, 20)
        if (page === 1) {
          this.items = data
        } else {
          this.items.push(...data)
        }
        this.currentPage = page
        this.hasMore = data.length === 20
      } catch {
        // 静默处理
      } finally {
        this.loading = false
      }
    },

    /** 加载更多 */
    async loadMore() {
      if (this.hasMore && !this.loading) {
        await this.fetchHistory(this.currentPage + 1)
      }
    },

    /** 删除单条记录 */
    async deleteItem(id) {
      await historyAPI.delete(id)
      this.items = this.items.filter((item) => item.id !== id)
    },
  },
})
