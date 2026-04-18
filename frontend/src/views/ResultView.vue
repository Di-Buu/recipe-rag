<template>
  <AppLayout>
    <div class="result-page">
      <!-- 顶部信息栏 -->
      <div class="result-header">
        <el-button text @click="router.push('/home')">
          <el-icon><ArrowLeft /></el-icon>
          返回首页
        </el-button>
        <div class="query-info">
          <span class="query-text">"{{ recommendStore.query }}"</span>
          <span class="filter-summary" v-if="filterSummary">{{ filterSummary }}</span>
        </div>
      </div>

      <!-- 加载状态 -->
      <div class="loading-state" v-if="recommendStore.loading">
        <el-icon class="loading-icon is-loading" :size="32"><Loading /></el-icon>
        <p class="loading-text">正在为你搜寻美味食谱，请稍候…</p>
        <p class="loading-hint">通常需要 10~30 秒</p>
        <el-skeleton :rows="6" animated style="margin-top: 24px" />
      </div>

      <!-- 错误状态 -->
      <div class="error-state" v-else-if="recommendStore.error">
        <el-empty>
          <template #image>
            <span style="font-size: 56px">😔</span>
          </template>
          <template #description>
            <p class="error-title">推荐暂时遇到了问题</p>
            <p class="error-detail">{{ recommendStore.error }}</p>
            <p class="error-hint">你可以稍后重试，或查看历史记录中是否已有结果</p>
          </template>
          <div class="error-actions">
            <el-button type="primary" @click="router.push('/home')">重新提问</el-button>
            <el-button @click="router.push('/history')">查看历史</el-button>
          </div>
        </el-empty>
      </div>

      <!-- 结果展示（含流式生成中） -->
      <div class="result-content" v-else-if="recommendStore.answer || recommendStore.streaming">
        <!-- 左：LLM 回答 -->
        <div class="answer-panel">
          <h3 class="panel-title">
            <el-icon><ChatDotRound /></el-icon>
            智能推荐
          </h3>
          <div class="answer-body" v-html="renderedAnswer" />
          <span v-if="recommendStore.streaming" class="typing-cursor">▌</span>
        </div>

        <!-- 右：检索来源 -->
        <div class="source-panel">
          <h3 class="panel-title">
            <el-icon><Document /></el-icon>
            检索来源（{{ recommendStore.sources.length }}）
          </h3>
          <div class="source-list">
            <SourceCard
              v-for="source in recommendStore.sources"
              :key="source.recipe_id"
              :source="source"
            />
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div class="empty-state" v-else>
        <el-empty>
          <template #image>
            <span style="font-size: 56px">🍳</span>
          </template>
          <template #description>
            <p>还没有发起推荐，去首页告诉我你想吃什么吧</p>
          </template>
          <el-button type="primary" @click="router.push('/home')">去首页</el-button>
        </el-empty>
      </div>

      <!-- 底部操作 -->
      <div class="result-footer" v-if="recommendStore.answer">
        <el-button size="large" @click="router.push('/home')">
          <el-icon><ArrowLeft /></el-icon>
          重新提问
        </el-button>
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import AppLayout from '../components/AppLayout.vue'
import SourceCard from '../components/SourceCard.vue'
import { useRecommendStore } from '../stores/recommend'

const router = useRouter()
const recommendStore = useRecommendStore()

// Markdown 渲染（含 XSS 消毒）
const renderedAnswer = computed(() => {
  if (!recommendStore.answer) return ''
  const raw = marked(recommendStore.answer, { breaks: true })
  return DOMPurify.sanitize(raw)
})

// 筛选条件摘要
const filterSummary = computed(() => {
  const f = recommendStore.filters
  if (!f) return ''
  const parts = []
  if (f.categories?.length) parts.push(`分类: ${f.categories.join(', ')}`)
  if (f.keywords?.length) parts.push(`关键词: ${f.keywords.join(', ')}`)
  if (f.difficulty_max != null) parts.push(`难度≤${f.difficulty_max}`)
  if (f.costtime_max) parts.push(`耗时≤${f.costtime_max}分钟`)
  if (f.nutrition_tags?.length) parts.push(f.nutrition_tags.join(', '))
  return parts.length ? `筛选: ${parts.join(' | ')}` : ''
})
</script>

<style scoped>
.result-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.result-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.query-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.query-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.filter-summary {
  font-size: 13px;
  color: var(--color-text-tertiary);
}

/* 加载状态 */
.loading-state {
  text-align: center;
  padding: var(--space-12) 0;
  color: var(--color-text-secondary);
}

.loading-text {
  font-size: 15px;
  margin-bottom: var(--space-1);
}

.loading-hint {
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.loading-icon {
  color: var(--color-primary);
  margin-bottom: var(--space-3);
}

/* 错误状态 */
.error-state {
  padding: var(--space-12) 0;
}

.error-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.error-detail {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-1);
}

.error-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.error-actions {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

/* 结果区域：左右分栏 */
.result-content {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: var(--space-6);
  align-items: start;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 16px;
  color: var(--color-text-primary);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

/* 回答面板 */
.answer-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
}

.answer-body {
  font-size: 15px;
  line-height: 1.8;
  color: var(--color-text-primary);
}

.answer-body :deep(h1),
.answer-body :deep(h2),
.answer-body :deep(h3) {
  margin-top: var(--space-4);
  margin-bottom: var(--space-2);
  color: var(--color-text-primary);
}

.answer-body :deep(ul),
.answer-body :deep(ol) {
  padding-left: var(--space-5);
  margin-bottom: var(--space-3);
}

.answer-body :deep(li) {
  margin-bottom: var(--space-1);
}

.answer-body :deep(p) {
  margin-bottom: var(--space-3);
}

/* 来源面板 */
.source-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  position: sticky;
  top: calc(var(--navbar-height) + var(--space-6));
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* 底部 */
.result-footer {
  display: flex;
  justify-content: center;
  padding: var(--space-6) 0;
}

/* 流式输出光标 */
.typing-cursor {
  display: inline-block;
  color: var(--color-primary);
  font-weight: 700;
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@media (max-width: 1024px) {
  .result-content {
    grid-template-columns: 1fr;
  }

  .source-panel {
    position: static;
  }
}
</style>
