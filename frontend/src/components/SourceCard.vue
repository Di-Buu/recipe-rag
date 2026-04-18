<template>
  <div class="source-card" role="link" tabindex="0" @click="goDetail" @keydown.enter="goDetail">
    <!-- 缩略图 -->
    <div class="source-thumb">
      <img v-if="source.thumb" :src="source.thumb" :alt="source.title" loading="lazy" />
      <div v-else class="thumb-placeholder">
        <el-icon><PictureFilled /></el-icon>
      </div>
    </div>

    <!-- 信息 -->
    <div class="source-info">
      <h4 class="source-title">{{ source.title }}</h4>

      <div class="source-meta">
        <span class="relevance">相关度: {{ (source.relevance * 100).toFixed(0) }}%</span>
        <span class="chunks">匹配: {{ source.matched_chunks }} 个子块</span>
      </div>

      <div class="source-detail">
        <DifficultyTag :level="source.difficulty" size="small" />
        <span v-if="source.costtime" class="costtime">
          <el-icon><Clock /></el-icon>{{ source.costtime }}
        </span>
      </div>

      <div class="source-tags" v-if="source.nutrition_tags?.length">
        <el-tag
          v-for="tag in source.nutrition_tags.slice(0, 2)"
          :key="tag"
          size="small"
          type="success"
          effect="light"
        >
          {{ tag }}
        </el-tag>
      </div>

      <el-button text type="primary" size="small" class="detail-link">
        查看详情
        <el-icon><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import DifficultyTag from './DifficultyTag.vue'

const props = defineProps({
  source: { type: Object, required: true },
})

const router = useRouter()

function goDetail() {
  router.push(`/recipe/${props.source.recipe_id}`)
}
</script>

<style scoped>
.source-card {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast);
}

.source-card:hover {
  border-color: var(--color-primary-light);
  box-shadow: var(--shadow-sm);
}

.source-card:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.source-thumb {
  width: 80px;
  height: 80px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--gradient-warm-bg);
}

.source-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
}

.source-info {
  flex: 1;
  min-width: 0;
}

.source-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-meta {
  display: flex;
  gap: var(--space-3);
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-1);
}

.source-detail {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.costtime {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.source-tags {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.detail-link {
  padding: 0;
  font-size: 12px;
}
</style>
