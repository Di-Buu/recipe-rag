<template>
  <div class="onboarding-page">
    <div class="onboarding-card">
      <div class="onboarding-header">
        <el-icon :size="32" color="var(--color-primary)"><MagicStick /></el-icon>
        <h2>{{ stepTitles[currentStep] }}</h2>
        <p class="hint">{{ stepHints[currentStep] }}</p>
      </div>

      <!-- 步骤指示器 -->
      <div class="step-indicator">
        <div
          v-for="(_, idx) in stepTitles"
          :key="idx"
          class="step-dot"
          :class="{ active: idx === currentStep, done: idx < currentStep }"
        />
      </div>

      <!-- Step 0: 食材禁忌 -->
      <div v-show="currentStep === 0" class="step-content">
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
          >
            {{ item }}
          </el-check-tag>
        </div>
      </div>

      <!-- Step 1: 菜系 + 营养目标 -->
      <div v-show="currentStep === 1" class="step-content">
        <section class="pref-section">
          <h3 class="section-title">偏好菜系</h3>
          <div class="tag-group" v-if="categories.length">
            <el-check-tag
              v-for="cat in categories.slice(0, 12)"
              :key="cat"
              :checked="form.preferred_categories.includes(cat)"
              @change="toggleCategory(cat)"
            >
              {{ cat }}
            </el-check-tag>
          </div>
          <el-skeleton v-else :rows="1" animated />
        </section>

        <section class="pref-section">
          <h3 class="section-title">营养目标</h3>
          <div class="tag-group">
            <el-check-tag
              v-for="tag in nutritionOptions"
              :key="tag"
              :checked="form.nutrition_goals.includes(tag)"
              @change="toggleNutrition(tag)"
            >
              {{ tag }}
            </el-check-tag>
          </div>
        </section>
      </div>

      <!-- Step 2: 难度 + 耗时 -->
      <div v-show="currentStep === 2" class="step-content">
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
      </div>

      <!-- 操作按钮 -->
      <div class="onboarding-actions">
        <el-button v-if="currentStep === 0" size="large" @click="handleSkip">
          跳过，直接开始
        </el-button>
        <el-button v-else size="large" @click="currentStep--">
          <el-icon><ArrowLeft /></el-icon>
          上一步
        </el-button>

        <el-button
          v-if="currentStep < 2"
          type="primary"
          size="large"
          @click="currentStep++"
        >
          下一步
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
        <el-button
          v-else
          type="primary"
          size="large"
          :loading="saving"
          @click="handleSave"
        >
          保存并开始探索
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { usePreferenceStore } from '../stores/preference'
import { recipeAPI } from '../api'
import {
  COMMON_ALLERGENS,
  NUTRITION_OPTIONS,
  DIFFICULTY_OPTIONS,
  COSTTIME_OPTIONS,
} from '../constants/preferences'

const router = useRouter()
const authStore = useAuthStore()
const prefStore = usePreferenceStore()

const saving = ref(false)
const newExclude = ref('')
const categories = ref([])
const currentStep = ref(0)

const stepTitles = [
  '有什么不能吃的吗？',
  '你的口味偏好是？',
  '对难度和时间有要求吗？',
]
const stepHints = [
  '告诉我们您的食材禁忌，我们会在推荐时自动避开',
  '选择喜欢的菜系和营养目标，帮助我们精准推荐',
  '最后一步！设置好后即可开始探索（可随时在设置中修改）',
]

const form = ref({
  exclude_ingredients: [],
  preferred_categories: [],
  nutrition_goals: [],
  difficulty_max: null,
  costtime_max: null,
})

const commonAllergens = COMMON_ALLERGENS
const nutritionOptions = NUTRITION_OPTIONS
const difficultyOptions = DIFFICULTY_OPTIONS
const costtimeOptions = COSTTIME_OPTIONS

onMounted(async () => {
  try {
    const { data } = await recipeAPI.getFilterOptions()
    categories.value = data.categories.map((c) => c.value).slice(0, 20)
  } catch {
    // 静默处理
  }
})

function toggleExclude(item) {
  const idx = form.value.exclude_ingredients.indexOf(item)
  if (idx >= 0) form.value.exclude_ingredients.splice(idx, 1)
  else form.value.exclude_ingredients.push(item)
}

function removeExclude(item) {
  form.value.exclude_ingredients = form.value.exclude_ingredients.filter((i) => i !== item)
}

function addExclude() {
  const val = newExclude.value.trim()
  if (val && !form.value.exclude_ingredients.includes(val)) {
    form.value.exclude_ingredients.push(val)
  }
  newExclude.value = ''
}

function toggleCategory(cat) {
  const idx = form.value.preferred_categories.indexOf(cat)
  if (idx >= 0) form.value.preferred_categories.splice(idx, 1)
  else form.value.preferred_categories.push(cat)
}

function toggleNutrition(tag) {
  const idx = form.value.nutrition_goals.indexOf(tag)
  if (idx >= 0) form.value.nutrition_goals.splice(idx, 1)
  else form.value.nutrition_goals.push(tag)
}

async function handleSave() {
  saving.value = true
  try {
    await prefStore.savePreference(form.value)
    authStore.markNotNew()
    ElMessage.success('偏好已保存')
    router.push('/home')
  } catch (err) {
    ElMessage.error('保存失败，请重试')
  } finally {
    saving.value = false
  }
}

async function handleSkip() {
  // 跳过时也要标记非新用户
  try {
    await prefStore.savePreference(form.value)
  } catch {
    // 静默处理
  }
  authStore.markNotNew()
  router.push('/home')
}
</script>

<style scoped>
.onboarding-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-bg);
  padding: var(--space-6);
}

.onboarding-card {
  width: 100%;
  max-width: 580px;
  background: var(--color-surface);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  box-shadow: var(--shadow-lg);
}

.onboarding-header {
  text-align: center;
  margin-bottom: var(--space-4);
}

.onboarding-header h2 {
  margin-top: var(--space-2);
  font-size: 22px;
  color: var(--color-text-primary);
}

.hint {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin-top: var(--space-2);
}

/* 步骤指示器 */
.step-indicator {
  display: flex;
  justify-content: center;
  gap: var(--space-2);
  margin-bottom: var(--space-6);
}

.step-dot {
  width: 32px;
  height: 4px;
  border-radius: 2px;
  background: var(--color-border);
  transition: all var(--duration-normal) ease;
}

.step-dot.active {
  background: var(--color-primary);
  width: 48px;
}

.step-dot.done {
  background: var(--color-success);
}

/* 步骤内容 */
.step-content {
  min-height: 180px;
}

.pref-section {
  margin-bottom: var(--space-5);
}

.pref-section:last-child {
  margin-bottom: 0;
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
  margin-bottom: var(--space-2);
}

.quick-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.onboarding-actions {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-8);
  padding-top: var(--space-6);
  border-top: 1px solid var(--color-border);
}
</style>
