<template>
  <AppLayout>
    <div class="home-page">
      <!-- 筛选面板 -->
      <FilterPanel v-model="filters" :options="filterOptions" />

      <!-- 搜索区域 -->
      <div class="search-area">
        <h2 class="search-heading">今天想吃点什么？</h2>
        <div class="search-bar">
          <el-input
            v-model="question"
            placeholder="描述你的口味偏好，例如：简单的低脂晚餐、下饭的川菜..."
            size="large"
            clearable
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button
            type="primary"
            size="large"
            :loading="recommendStore.loading"
            @click="handleSearch"
          >
            智能推荐
          </el-button>
        </div>

        <!-- 快捷标签 -->
        <div class="quick-tags">
          <span class="quick-label">热门搜索</span>
          <el-tag
            v-for="tag in quickTags"
            :key="tag"
            class="quick-tag"
            effect="plain"
            round
            tabindex="0"
            @click="quickSearch(tag)"
            @keydown.enter="quickSearch(tag)"
          >
            {{ tag }}
          </el-tag>
        </div>
      </div>

      <!-- 今日发现 -->
      <section class="discover-section">
        <div class="section-header">
          <h2>
            <el-icon><Compass /></el-icon>
            今日发现
          </h2>
          <el-button text @click="loadRandomRecipes">
            <el-icon><Refresh /></el-icon>
            换一批
          </el-button>
        </div>

        <div class="recipe-grid" v-if="randomRecipes.length">
          <RecipeCard
            v-for="recipe in randomRecipes"
            :key="recipe.did"
            :recipe="recipe"
          />
        </div>

        <div class="loading-area" v-else>
          <el-skeleton :rows="3" animated />
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import FilterPanel from '../components/FilterPanel.vue'
import RecipeCard from '../components/RecipeCard.vue'
import { useRecommendStore } from '../stores/recommend'
import { usePreferenceStore } from '../stores/preference'
import { recipeAPI } from '../api'

const router = useRouter()
const recommendStore = useRecommendStore()
const prefStore = usePreferenceStore()

const question = ref('')
const randomRecipes = ref([])
const filterOptions = ref({})
const filters = ref({
  categories: [],
  keywords: [],
  difficulty_max: null,
  costtime_max: null,
  nutrition_tags: [],
  exclude_ingredients: [],
  include_ingredients: [],
})

const quickTags = ['简单家常菜', '低脂高蛋白', '30分钟快手晚餐', '宝宝辅食', '减脂便当']

onMounted(async () => {
  // 并行加载：筛选选项、随机食谱、用户偏好
  const [optRes] = await Promise.all([
    recipeAPI.getFilterOptions().catch(() => ({ data: {} })),
    loadRandomRecipes(),
    prefStore.loaded ? Promise.resolve() : prefStore.fetchPreference(),
  ])
  filterOptions.value = optRes.data
  // 偏好 → 筛选面板（需在 filterOptions 加载后执行，以便验证有效性）
  applyPreferenceToFilters()
})

async function loadRandomRecipes() {
  try {
    const { data } = await recipeAPI.getRandom(6)
    randomRecipes.value = data
  } catch {
    // 静默处理
  }
}

function applyPreferenceToFilters() {
  const pref = prefStore.preference
  const opts = filterOptions.value

  // 验证 categories 是否在可选项中
  if (pref.preferred_categories?.length && opts.categories?.length) {
    const validCats = new Set(opts.categories.map(c => c.value))
    filters.value.categories = pref.preferred_categories.filter(c => validCats.has(c))
  }
  if (pref.exclude_ingredients?.length) {
    filters.value.exclude_ingredients = [...pref.exclude_ingredients]
  }
  if (pref.difficulty_max != null && pref.difficulty_max < 3) {
    filters.value.difficulty_max = pref.difficulty_max
  }
  if (pref.costtime_max) {
    filters.value.costtime_max = pref.costtime_max
  }
  // 验证 nutrition_tags 是否在可选项中
  if (pref.nutrition_goals?.length && opts.nutrition_tags?.length) {
    const validNut = new Set(opts.nutrition_tags.map(n => n.value))
    filters.value.nutrition_tags = pref.nutrition_goals.filter(n => validNut.has(n))
  } else if (pref.nutrition_goals?.length) {
    filters.value.nutrition_tags = [...pref.nutrition_goals]
  }
}

function handleSearch() {
  if (!question.value.trim()) {
    ElMessage.warning('请输入您想吃什么')
    return
  }

  // 构建过滤条件（清理空值，避免传无效参数）
  const queryFilters = {}
  if (filters.value.nutrition_tags?.length)
    queryFilters.nutrition_tags = filters.value.nutrition_tags
  if (filters.value.exclude_ingredients?.length)
    queryFilters.exclude_ingredients = filters.value.exclude_ingredients
  if (filters.value.include_ingredients?.length)
    queryFilters.include_ingredients = filters.value.include_ingredients
  if (filters.value.difficulty_max != null)
    queryFilters.difficulty_max = filters.value.difficulty_max
  if (filters.value.costtime_max != null)
    queryFilters.costtime_max = filters.value.costtime_max
  if (filters.value.categories?.length)
    queryFilters.categories = filters.value.categories
  if (filters.value.keywords?.length)
    queryFilters.keywords = filters.value.keywords

  // 提交查询并跳转结果页
  recommendStore.submitQuery(question.value.trim(), queryFilters)
  router.push('/result')
}

function quickSearch(tag) {
  question.value = tag
  handleSearch()
}
</script>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

/* 搜索区域提权 */
.search-area {
  background: var(--color-primary-bg);
  border-radius: var(--radius-xl);
  padding: var(--space-8) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.search-heading {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  text-align: center;
  margin: 0;
}

.search-bar {
  display: flex;
  gap: var(--space-3);
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
}

.search-bar .el-input {
  flex: 1;
}

.search-bar .el-input :deep(.el-input__wrapper) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.quick-tags {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  justify-content: center;
}

.quick-label {
  font-size: 13px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}

.quick-tag {
  cursor: pointer;
  transition: all var(--duration-fast);
}

.quick-tag:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.quick-tag:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* 今日发现 */
.discover-section {
  margin-top: var(--space-2);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.section-header h2 {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 18px;
  color: var(--color-text-primary);
}

.recipe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-5);
}

.loading-area {
  padding: var(--space-8);
}
</style>
