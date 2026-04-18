<template>
  <AppLayout>
    <div class="detail-page" v-if="recipe">
      <!-- 返回 -->
      <el-button text @click="router.back()" class="back-btn">
        <el-icon><ArrowLeft /></el-icon>
        返回
      </el-button>

      <!-- 顶部：标题+图片 -->
      <div class="detail-top">
        <div class="detail-info">
          <h1 class="recipe-title">{{ recipe.title }}</h1>
          <div class="recipe-meta">
            <el-tag>{{ recipe.category }}</el-tag>
            <DifficultyTag :level="recipe.difficulty" />
            <span class="meta-item" v-if="recipe.costtime">
              <el-icon><Clock /></el-icon>
              {{ recipe.costtime }}
            </span>
          </div>
          <div class="recipe-stats">
            <span><el-icon><View /></el-icon> {{ recipe.viewnum?.toLocaleString() }} 浏览</span>
            <span><el-icon><Star /></el-icon> {{ recipe.favnum?.toLocaleString() }} 收藏</span>
          </div>
          <div class="recipe-tags" v-if="recipe.tags?.length">
            <el-tag
              v-for="tag in recipe.tags"
              :key="tag"
              size="small"
              effect="plain"
              type="info"
            >
              {{ tag }}
            </el-tag>
          </div>
        </div>
        <div class="detail-thumb">
          <img v-if="recipe.thumb" :src="recipe.thumb" :alt="recipe.title" />
          <div v-else class="thumb-placeholder">
            <el-icon :size="48"><PictureFilled /></el-icon>
          </div>
        </div>
      </div>

      <!-- 简介 -->
      <section class="section" v-if="recipe.desc">
        <h2 class="section-title">
          <el-icon><EditPen /></el-icon>
          简介
        </h2>
        <p class="desc-text">{{ recipe.desc }}</p>
      </section>

      <!-- 营养概况 -->
      <section class="section" v-if="recipe.nutrition_summary">
        <h2 class="section-title">
          <el-icon><DataAnalysis /></el-icon>
          营养概况
        </h2>
        <div class="nutrition-grid">
          <NutritionBadge
            label="能量"
            :value="recipe.nutrition_summary.energy"
            unit="kcal"
            icon="🔥"
            color="var(--color-energy)"
          />
          <NutritionBadge
            label="蛋白质"
            :value="recipe.nutrition_summary.protein"
            unit="g"
            icon="💪"
            color="var(--color-protein)"
          />
          <NutritionBadge
            label="脂肪"
            :value="recipe.nutrition_summary.fat"
            unit="g"
            icon="🫒"
            color="var(--color-fat)"
          />
          <NutritionBadge
            label="碳水化合物"
            :value="recipe.nutrition_summary.carbs"
            unit="g"
            icon="🌾"
            color="var(--color-carbs)"
          />
        </div>
        <div class="nutrition-extra">
          <span v-if="recipe.nutrition_tags?.length">
            营养标签：
            <el-tag
              v-for="tag in recipe.nutrition_tags"
              :key="tag"
              size="small"
              type="success"
              effect="light"
              style="margin-right: 4px"
            >
              {{ tag }}
            </el-tag>
          </span>
          <span class="coverage" :title="'已匹配到营养数据库的食材占比，越高说明营养数据越准确'">
            食材匹配率：{{ (recipe.nutrition_coverage * 100).toFixed(0) }}%
          </span>
        </div>
      </section>

      <!-- 食材清单 -->
      <section class="section">
        <h2 class="section-title">
          <el-icon><Goods /></el-icon>
          食材清单
        </h2>
        <el-table :data="ingredientList" stripe style="width: 100%">
          <el-table-column prop="name" label="食材" min-width="120">
            <template #default="{ row }">
              <span :class="{ 'ingredient-header': row.isHeader }">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="用量" min-width="100" />
        </el-table>
      </section>

      <!-- 做法步骤 -->
      <section class="section" v-if="recipe.steps?.length">
        <h2 class="section-title">
          <el-icon><List /></el-icon>
          做法步骤
        </h2>
        <div class="steps-list">
          <div
            v-for="(step, idx) in recipe.steps"
            :key="idx"
            class="step-item"
          >
            <div class="step-num">{{ idx + 1 }}</div>
            <div class="step-content">
              <p>{{ cleanStepText(step) }}</p>
              <img
                v-if="recipe.step_pics?.[idx]"
                :src="recipe.step_pics[idx]"
                :alt="`步骤 ${idx + 1}`"
                class="step-img"
                loading="lazy"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- 小贴士 -->
      <section class="section" v-if="recipe.tip">
        <h2 class="section-title">
          <el-icon><InfoFilled /></el-icon>
          小贴士
        </h2>
        <p class="tip-text">{{ recipe.tip }}</p>
      </section>

      <!-- 视频 -->
      <section class="section" v-if="recipe.videourl">
        <h2 class="section-title">
          <el-icon><VideoCamera /></el-icon>
          视频
        </h2>
        <el-link :href="recipe.videourl" target="_blank" type="primary">
          观看视频
          <el-icon><Link /></el-icon>
        </el-link>
      </section>
    </div>

    <!-- 加载状态 -->
    <div class="loading-page" v-else-if="loading">
      <el-skeleton :rows="10" animated />
    </div>

    <!-- 错误状态 -->
    <div class="error-page" v-else>
      <el-empty description="食谱不存在或加载失败">
        <el-button type="primary" @click="router.push('/home')">返回首页</el-button>
      </el-empty>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'
import DifficultyTag from '../components/DifficultyTag.vue'
import NutritionBadge from '../components/NutritionBadge.vue'
import { recipeAPI } from '../api'

const route = useRoute()
const router = useRouter()

const recipe = ref(null)
const loading = ref(true)

// 食材列表：合并食材名、用量，标记分类标题行
const ingredientList = computed(() => {
  if (!recipe.value) return []
  const names = recipe.value.ingredients_raw || []
  const qtys = recipe.value.quantities || []

  return names.map((name, idx) => {
    const trimmed = name.trim()
    const isHeader = /^[~～]/.test(trimmed) || /[:：]\s*$/.test(trimmed)
    return {
      name: isHeader ? trimmed.replace(/^[~～]+/, '').trim() : trimmed,
      quantity: qtys[idx] || '-',
      isHeader,
    }
  })
})

/** 去除步骤文本中用户写的前导序号，如 "1. " "2、" "③" 等 */
function cleanStepText(text) {
  if (!text) return ''
  return text.replace(/^\s*[\d①②③④⑤⑥⑦⑧⑨⑩]+\s*[.、．:：)\]）】]\s*/, '')
}

onMounted(async () => {
  try {
    const { data } = await recipeAPI.getDetail(route.params.id)
    recipe.value = data
  } catch {
    recipe.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.detail-page {
  max-width: 900px;
  margin: 0 auto;
}

.back-btn {
  margin-bottom: var(--space-4);
}

/* 顶部：左文右图 */
.detail-top {
  display: flex;
  gap: var(--space-6);
  margin-bottom: var(--space-6);
}

.detail-info {
  flex: 1;
}

.recipe-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.recipe-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.recipe-stats {
  display: flex;
  gap: var(--space-4);
  font-size: 14px;
  color: var(--color-text-secondary);
  margin-bottom: var(--space-3);
}

.recipe-stats span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.recipe-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.detail-thumb {
  width: 320px;
  height: 240px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--gradient-warm-bg);
}

.detail-thumb img {
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

/* 通用节区域 */
.section {
  margin-bottom: var(--space-8);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 18px;
  color: var(--color-text-primary);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-2);
  border-bottom: 2px solid var(--color-primary-bg);
}

.desc-text {
  font-size: 15px;
  line-height: 1.8;
  color: var(--color-text-secondary);
}

/* 营养概况 */
.nutrition-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.nutrition-extra {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.coverage {
  color: var(--color-text-tertiary);
}

/* 食材表 */
.ingredient-header {
  font-weight: 600;
  color: var(--color-text-primary);
}

.no-data {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

/* 步骤 */
.steps-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.step-item {
  display: flex;
  gap: var(--space-4);
}

.step-num {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
  flex-shrink: 0;
}

.step-content {
  flex: 1;
}

.step-content p {
  font-size: 15px;
  line-height: 1.7;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.step-img {
  max-width: 400px;
  border-radius: var(--radius-md);
}

.tip-text {
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-text-secondary);
  background: var(--color-primary-bg);
  padding: var(--space-4);
  border-radius: var(--radius-md);
}

/* 加载/错误 */
.loading-page,
.error-page {
  padding: var(--space-12) 0;
}

@media (max-width: 768px) {
  .detail-top {
    flex-direction: column-reverse;
  }

  .detail-thumb {
    width: 100%;
    height: 200px;
  }

  .nutrition-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
