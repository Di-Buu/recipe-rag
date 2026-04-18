<template>
  <AppLayout>
    <div class="history-page">
      <div class="page-header">
        <h1>
          <el-icon><Clock /></el-icon>
          推荐历史
        </h1>
      </div>

      <!-- 历史列表 -->
      <div class="history-list" v-if="historyStore.items.length">
        <div
          v-for="item in historyStore.items"
          :key="item.id"
          class="history-item"
        >
          <div class="item-header">
            <div class="item-meta">
              <span class="item-time">
                <el-icon><Clock /></el-icon>
                {{ item.created_at }}
              </span>
              <el-tag size="small" type="info">{{ item.source_count }} 个来源</el-tag>
            </div>
            <el-button
              text
              type="danger"
              size="small"
              @click="handleDelete(item.id)"
            >
              <el-icon><Delete /></el-icon>
              删除
            </el-button>
          </div>

          <div class="item-question">
            Q: "{{ item.question }}"
          </div>

          <div class="item-filters" v-if="item.filters">
            <el-tag
              v-for="(val, key) in filterSummary(item.filters)"
              :key="key"
              size="small"
              type="info"
              effect="plain"
            >
              {{ val }}
            </el-tag>
          </div>

          <!-- 展开/收起回答 -->
          <div class="item-toggle">
            <el-button
              text
              size="small"
              @click="toggleExpand(item.id)"
            >
              <el-icon>
                <ArrowDown v-if="!expandedIds.has(item.id)" />
                <ArrowUp v-else />
              </el-icon>
              {{ expandedIds.has(item.id) ? '收起回答' : '展开回答' }}
            </el-button>
          </div>

          <!-- 展开的回答详情 -->
          <div class="item-detail" v-if="expandedIds.has(item.id)">
            <div v-if="detailLoading === item.id" class="detail-loading">
              <el-skeleton :rows="3" animated />
            </div>
            <div v-else-if="details[item.id]" class="detail-content">
              <div class="answer-rendered" v-html="renderMarkdown(details[item.id].answer)" />
            </div>
          </div>
        </div>

        <!-- 加载更多 -->
        <div class="load-more" v-if="historyStore.hasMore">
          <el-button
            :loading="historyStore.loading"
            @click="historyStore.loadMore()"
          >
            加载更多
          </el-button>
        </div>
      </div>

      <!-- 空状态 -->
      <el-empty v-else-if="!historyStore.loading">
        <template #image>
          <span style="font-size: 56px">📝</span>
        </template>
        <template #description>
          <p>还没有推荐记录，去首页探索美味食谱吧</p>
        </template>
        <el-button type="primary" @click="router.push('/home')">去首页</el-button>
      </el-empty>

      <!-- 加载状态 -->
      <div v-else class="loading-area">
        <el-skeleton :rows="5" animated />
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import AppLayout from '../components/AppLayout.vue'
import { useHistoryStore } from '../stores/history'
import { historyAPI } from '../api'

const router = useRouter()
const historyStore = useHistoryStore()

const expandedIds = ref(new Set())
const details = reactive({})
const detailLoading = ref(null)

onMounted(() => {
  historyStore.fetchHistory(1)
})

async function toggleExpand(id) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
    // 触发响应式更新
    expandedIds.value = new Set(expandedIds.value)
    return
  }

  // 加载详情
  if (!details[id]) {
    detailLoading.value = id
    try {
      const { data } = await historyAPI.getDetail(id)
      details[id] = data
    } catch {
      ElMessage.error('加载详情失败')
    } finally {
      detailLoading.value = null
    }
  }

  expandedIds.value.add(id)
  expandedIds.value = new Set(expandedIds.value)
}

async function handleDelete(id) {
  try {
    await ElMessageBox.confirm('确定删除这条推荐历史？', '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await historyStore.deleteItem(id)
    ElMessage.success('已删除')
  } catch {
    // 取消操作
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  const raw = marked(text, { breaks: true })
  return DOMPurify.sanitize(raw)
}

function filterSummary(filters) {
  if (!filters) return {}
  const result = {}
  if (filters.category) result.category = `分类: ${filters.category}`
  if (filters.difficulty_max) result.difficulty = `难度≤${filters.difficulty_max}`
  if (filters.costtime_max) result.costtime = `耗时≤${filters.costtime_max}分钟`
  if (filters.nutrition_tags?.length) result.nutrition = filters.nutrition_tags.join(', ')
  return result
}
</script>

<style scoped>
.history-page {
  max-width: 800px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: var(--space-6);
}

.page-header h1 {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 22px;
  color: var(--color-text-primary);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.history-item {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  transition: border-color var(--duration-fast);
}

.history-item:hover {
  border-color: var(--color-primary-light);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.item-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.item-time {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.item-question {
  font-size: 15px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.item-filters {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.item-toggle {
  margin-top: var(--space-2);
}

.item-detail {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border-light);
}

.detail-loading {
  padding: var(--space-4);
}

.answer-rendered {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.answer-rendered :deep(h1),
.answer-rendered :deep(h2),
.answer-rendered :deep(h3) {
  margin-top: var(--space-3);
  margin-bottom: var(--space-2);
  color: var(--color-text-primary);
}

.answer-rendered :deep(p) {
  margin-bottom: var(--space-2);
}

.answer-rendered :deep(ul),
.answer-rendered :deep(ol) {
  padding-left: var(--space-5);
}

.load-more {
  display: flex;
  justify-content: center;
  padding: var(--space-4);
}

.loading-area {
  padding: var(--space-8);
}
</style>
