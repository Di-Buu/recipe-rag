<template>
  <div
    class="recipe-card"
    role="link"
    tabindex="0"
    @click="goDetail"
    @keydown.enter="goDetail"
  >
    <!-- 缩略图 -->
    <div class="card-thumb">
      <img v-if="recipe.thumb" :src="recipe.thumb" :alt="recipe.title" loading="lazy" />
      <div v-else class="thumb-placeholder">
        <el-icon :size="32"><PictureFilled /></el-icon>
      </div>
    </div>

    <!-- 内容 -->
    <div class="card-body">
      <h3 class="card-title">{{ recipe.title }}</h3>

      <div class="card-meta">
        <DifficultyTag :level="recipe.difficulty" />
        <span class="meta-item" v-if="recipe.costtime">
          <el-icon><Clock /></el-icon>
          {{ recipe.costtime }}
        </span>
      </div>

      <!-- 营养标签 -->
      <div class="card-tags" v-if="recipe.nutrition_tags?.length">
        <el-tag
          v-for="tag in recipe.nutrition_tags.slice(0, 3)"
          :key="tag"
          size="small"
          type="success"
          effect="light"
        >
          {{ tag }}
        </el-tag>
      </div>

      <!-- 底部统计 -->
      <div class="card-stats">
        <span class="stat">
          <el-icon><View /></el-icon>
          {{ formatNum(recipe.viewnum) }}
        </span>
        <span class="stat">
          <el-icon><Star /></el-icon>
          {{ formatNum(recipe.favnum) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import DifficultyTag from './DifficultyTag.vue'

const props = defineProps({
  recipe: { type: Object, required: true },
})

const router = useRouter()

function goDetail() {
  router.push(`/recipe/${props.recipe.did}`)
}

function formatNum(num) {
  if (!num) return '0'
  if (num >= 10000) return (num / 10000).toFixed(1) + '万'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'k'
  return String(num)
}
</script>

<style scoped>
.recipe-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: transform var(--duration-normal) ease, box-shadow var(--duration-normal) ease;
}

.recipe-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.recipe-card:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.card-thumb {
  width: 100%;
  height: 180px;
  overflow: hidden;
  background: var(--gradient-warm-bg);
}

.card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--duration-slow) ease;
}

.recipe-card:hover .card-thumb img {
  transform: scale(1.05);
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
}

.card-body {
  padding: var(--space-3) var(--space-4);
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.4;
  min-height: 2.8em;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
  font-size: 13px;
  color: var(--color-text-secondary);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 2px;
}

.card-tags {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.card-stats {
  display: flex;
  gap: var(--space-4);
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.stat {
  display: flex;
  align-items: center;
  gap: 2px;
}
</style>
