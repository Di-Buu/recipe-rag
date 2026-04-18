<template>
  <AppLayout>
    <div class="preference-page">
      <div class="page-header">
        <h1>
          <el-icon><Setting /></el-icon>
          饮食偏好设置
        </h1>
        <p class="page-desc">设置后每次查询自动应用（可在首页临时修改）</p>
      </div>

      <div class="pref-card" v-loading="prefStore.loading">
        <!-- 食材禁忌 -->
        <section class="pref-section">
          <h3 class="section-title">食材禁忌</h3>
          <div class="ingredient-tags">
            <el-tag
              v-for="ing in form.exclude_ingredients"
              :key="ing"
              closable
              @close="removeExclude(ing)"
              type="danger"
            >
              {{ ing }}
            </el-tag>
            <el-input
              v-model="newExclude"
              placeholder="输入食材名，回车添加"
              size="small"
              style="width: 180px"
              @keyup.enter="addExclude"
            />
          </div>
          <div class="quick-tags">
            <el-check-tag
              v-for="item in commonAllergens"
              :key="item"
              :checked="form.exclude_ingredients.includes(item)"
              @change="toggleExclude(item)"
              size="small"
            >
              {{ item }}
            </el-check-tag>
          </div>
        </section>

        <!-- 偏好分类 -->
        <section class="pref-section">
          <h3 class="section-title">偏好分类</h3>
          <div class="tag-group" v-if="categories.length">
            <el-check-tag
              v-for="cat in categories"
              :key="cat"
              :checked="form.preferred_categories.includes(cat)"
              @change="toggleItem(form.preferred_categories, cat)"
            >
              {{ cat }}
            </el-check-tag>
          </div>
          <el-skeleton v-else :rows="1" animated />
        </section>

        <!-- 营养目标 -->
        <section class="pref-section">
          <h3 class="section-title">营养目标</h3>
          <div class="tag-group">
            <el-check-tag
              v-for="tag in nutritionOptions"
              :key="tag"
              :checked="form.nutrition_goals.includes(tag)"
              @change="toggleItem(form.nutrition_goals, tag)"
            >
              {{ tag }}
            </el-check-tag>
          </div>
        </section>

        <!-- 难度上限 -->
        <section class="pref-section">
          <h3 class="section-title">难度上限</h3>
          <div class="tag-group">
            <el-check-tag
              v-for="d in difficultyOptions"
              :key="d.value"
              :checked="form.difficulty_max === d.value"
              @change="form.difficulty_max = d.value"
            >
              {{ d.label }}
            </el-check-tag>
          </div>
        </section>

        <!-- 耗时上限 -->
        <section class="pref-section">
          <h3 class="section-title">耗时上限</h3>
          <div class="tag-group">
            <el-check-tag
              v-for="ct in costtimeOptions"
              :key="ct.value"
              :checked="form.costtime_max === ct.value"
              @change="form.costtime_max = ct.value"
            >
              {{ ct.label }}
            </el-check-tag>
          </div>
        </section>

        <!-- 操作按钮 -->
        <div class="pref-actions">
          <el-button @click="handleReset">重置为默认</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">
            保存偏好
          </el-button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { usePreferenceStore } from '../stores/preference'
import { recipeAPI } from '../api'
import {
  COMMON_ALLERGENS,
  NUTRITION_OPTIONS,
  DIFFICULTY_OPTIONS,
  COSTTIME_OPTIONS,
} from '../constants/preferences'

const prefStore = usePreferenceStore()

const saving = ref(false)
const newExclude = ref('')
const categories = ref([])

const form = ref({
  exclude_ingredients: [],
  preferred_categories: [],
  nutrition_goals: [],
  difficulty_max: null,
  costtime_max: null,
})

const nutritionOptions = NUTRITION_OPTIONS
const difficultyOptions = DIFFICULTY_OPTIONS
const costtimeOptions = COSTTIME_OPTIONS

onMounted(async () => {
  // 加载筛选选项和当前偏好
  const [optRes] = await Promise.all([
    recipeAPI.getFilterOptions().catch(() => ({ data: {} })),
    prefStore.fetchPreference(),
  ])
  categories.value = (optRes.data.categories || []).map((c) => c.value).slice(0, 20)

  // 填入当前偏好
  const p = prefStore.preference
  form.value = {
    exclude_ingredients: [...(p.exclude_ingredients || [])],
    preferred_categories: [...(p.preferred_categories || [])],
    nutrition_goals: [...(p.nutrition_goals || [])],
    difficulty_max: p.difficulty_max ?? null,
    costtime_max: p.costtime_max || null,
  }
})

const commonAllergens = COMMON_ALLERGENS

function toggleItem(arr, val) {
  const idx = arr.indexOf(val)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(val)
}

function addExclude() {
  const val = newExclude.value.trim()
  if (val && !form.value.exclude_ingredients.includes(val)) {
    form.value.exclude_ingredients.push(val)
  }
  newExclude.value = ''
}

function removeExclude(item) {
  form.value.exclude_ingredients = form.value.exclude_ingredients.filter((i) => i !== item)
}

function toggleExclude(item) {
  const idx = form.value.exclude_ingredients.indexOf(item)
  if (idx >= 0) form.value.exclude_ingredients.splice(idx, 1)
  else form.value.exclude_ingredients.push(item)
}

function handleReset() {
  form.value = {
    exclude_ingredients: [],
    preferred_categories: [],
    nutrition_goals: [],
    difficulty_max: null,
    costtime_max: null,
  }
}

async function handleSave() {
  saving.value = true
  try {
    await prefStore.savePreference(form.value)
    ElMessage.success('偏好已保存')
  } catch {
    ElMessage.error('保存失败，请重试')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.preference-page {
  max-width: 700px;
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

.page-desc {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin-top: var(--space-1);
}

.pref-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
}

.pref-section {
  margin-bottom: var(--space-6);
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ingredient-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.quick-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-2);
}

.pref-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-6);
  padding-top: var(--space-6);
  border-top: 1px solid var(--color-border);
}
</style>
