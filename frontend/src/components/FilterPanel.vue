<template>
  <div class="filter-panel">
    <!-- 折叠头 -->
    <div
      class="filter-header"
      role="button"
      tabindex="0"
      @click="collapsed = !collapsed"
      @keydown.enter="collapsed = !collapsed"
    >
      <span class="filter-title">
        <el-icon><Filter /></el-icon>
        筛选条件
        <span v-if="activeFilterCount" class="filter-badge">{{ activeFilterCount }}</span>
      </span>
      <span class="header-actions">
        <el-button
          v-if="!collapsed"
          text size="small"
          @click.stop="handleReset"
        >
          重置
        </el-button>
        <el-icon class="collapse-icon" :class="{ 'is-collapsed': collapsed }">
          <ArrowUp />
        </el-icon>
      </span>
    </div>

    <div class="filter-body-wrapper" :class="{ 'is-collapsed': collapsed }">
      <div class="filter-body">
        <!-- 分类（cid） -->
        <div class="filter-section" v-if="options.categories?.length">
          <div class="section-label">分类</div>
          <el-input
            v-model="categorySearch"
            placeholder="搜索分类..."
            size="small"
            clearable
            class="section-search"
            :prefix-icon="Search"
          />
          <div class="tag-group">
            <el-check-tag
              v-for="cat in displayCategories"
              :key="cat.value"
              :checked="localFilters.categories.includes(cat.value)"
              @change="toggleCategory(cat.value)"
            >
              {{ cat.label }}
            </el-check-tag>
            <el-button
              v-if="!categorySearch && filteredCategories.length > FEATURED_COUNT"
              text size="small"
              @click="showAllCategories = !showAllCategories"
            >
              {{ showAllCategories ? '收起' : `展开全部(${filteredCategories.length})` }}
            </el-button>
          </div>
        </div>

        <!-- 关键词（zid） -->
        <div class="filter-section" v-if="options.keywords?.length">
          <div class="section-label">关键词</div>
          <el-input
            v-model="keywordSearch"
            placeholder="搜索关键词..."
            size="small"
            clearable
            class="section-search"
            :prefix-icon="Search"
          />
          <div class="tag-group">
            <el-check-tag
              v-for="kw in displayKeywords"
              :key="kw.value"
              :checked="localFilters.keywords.includes(kw.value)"
              @change="toggleKeyword(kw.value)"
            >
              {{ kw.label }}
            </el-check-tag>
            <el-button
              v-if="!keywordSearch && filteredKeywords.length > FEATURED_COUNT"
              text size="small"
              @click="showAllKeywords = !showAllKeywords"
            >
              {{ showAllKeywords ? '收起' : `展开全部(${filteredKeywords.length})` }}
            </el-button>
          </div>
        </div>

        <!-- 难度 -->
        <div class="filter-section" v-if="options.difficulties?.length">
          <div class="section-label">难度上限</div>
          <div class="tag-group">
            <el-check-tag
              :checked="localFilters.difficulty_max == null"
              @change="localFilters.difficulty_max = null"
            >
              不限
            </el-check-tag>
            <el-check-tag
              v-for="d in options.difficulties"
              :key="d.value"
              :checked="localFilters.difficulty_max === d.value"
              @change="toggleDifficulty(d.value)"
            >
              {{ d.label }}
            </el-check-tag>
          </div>
        </div>

        <!-- 耗时 -->
        <div class="filter-section" v-if="options.costtimes?.length">
          <div class="section-label">耗时上限</div>
          <div class="tag-group">
            <el-check-tag
              :checked="!localFilters.costtime_max"
              @change="localFilters.costtime_max = null"
            >
              不限
            </el-check-tag>
            <el-check-tag
              v-for="ct in options.costtimes"
              :key="ct.value"
              :checked="localFilters.costtime_max === ct.value"
              @change="toggleCosttime(ct.value)"
            >
              {{ ct.label }}
            </el-check-tag>
          </div>
        </div>

        <!-- 营养标签 -->
        <div class="filter-section" v-if="orderedNutritionTags.length">
          <div class="section-label">营养标签</div>
          <div class="tag-group">
            <el-check-tag
              v-for="tag in orderedNutritionTags"
              :key="tag"
              :checked="localFilters.nutrition_tags.includes(tag)"
              @change="toggleNutritionTag(tag)"
            >
              {{ tag }}
            </el-check-tag>
          </div>
        </div>

        <!-- 排除食材 -->
        <div class="filter-section">
          <div class="section-label">排除食材</div>
          <div class="quick-tags">
            <el-check-tag
              v-for="ing in commonExcludes"
              :key="ing"
              size="small"
              :checked="localFilters.exclude_ingredients.includes(ing)"
              @change="toggleExcludeQuick(ing)"
            >
              {{ ing }}
            </el-check-tag>
          </div>
          <div class="ingredient-tags">
            <el-tag
              v-for="ing in localFilters.exclude_ingredients"
              :key="ing"
              closable
              @close="removeExclude(ing)"
              type="danger"
              size="default"
            >
              {{ ing }}
            </el-tag>
            <el-input
              v-model="newExclude"
              placeholder="输入食材，回车添加"
              size="small"
              style="width: 160px"
              @keyup.enter="addExclude"
            />
          </div>
        </div>

        <!-- 包含食材 -->
        <div class="filter-section">
          <div class="section-label">包含食材</div>
          <div class="quick-tags">
            <el-check-tag
              v-for="ing in commonIncludes"
              :key="ing"
              size="small"
              :checked="localFilters.include_ingredients.includes(ing)"
              @change="toggleIncludeQuick(ing)"
            >
              {{ ing }}
            </el-check-tag>
          </div>
          <div class="ingredient-tags">
            <el-tag
              v-for="ing in localFilters.include_ingredients"
              :key="ing"
              closable
              @close="removeInclude(ing)"
              type="success"
              size="default"
            >
              {{ ing }}
            </el-tag>
            <el-input
              v-model="newInclude"
              placeholder="输入食材，回车添加"
              size="small"
              style="width: 160px"
              @keyup.enter="addInclude"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Search, ArrowUp } from '@element-plus/icons-vue'
import { COMMON_EXCLUDES, COMMON_INCLUDES, NUTRITION_OPTIONS } from '../constants/preferences'

const FEATURED_COUNT = 18

const props = defineProps({
  modelValue: { type: Object, required: true },
  options: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue'])

const collapsed = ref(true)
const showAllCategories = ref(false)
const showAllKeywords = ref(false)
const categorySearch = ref('')
const keywordSearch = ref('')
const newExclude = ref('')
const newInclude = ref('')

const commonExcludes = COMMON_EXCLUDES
const commonIncludes = COMMON_INCLUDES

// 营养标签固定顺序，与偏好设置页面保持一致
const orderedNutritionTags = computed(() => {
  const available = props.options.nutrition_tags || []
  const ordered = NUTRITION_OPTIONS.filter(t => available.includes(t))
  const rest = available.filter(t => !NUTRITION_OPTIONS.includes(t))
  return [...ordered, ...rest]
})

const localFilters = ref({ ...props.modelValue })

// 防止 watch 循环：外部更新时不触发 emit
let updatingFromParent = false

watch(
  () => props.modelValue,
  (val) => {
    updatingFromParent = true
    localFilters.value = { ...val }
    nextTick(() => { updatingFromParent = false })
  },
  { deep: true },
)

watch(
  localFilters,
  (val) => {
    if (!updatingFromParent) {
      emit('update:modelValue', { ...val })
    }
  },
  { deep: true },
)

// 计算当前激活的筛选条件数
const activeFilterCount = computed(() => {
  const f = localFilters.value
  let count = 0
  if (f.categories?.length) count += f.categories.length
  if (f.keywords?.length) count += f.keywords.length
  if (f.difficulty_max != null) count++
  if (f.costtime_max != null) count++
  if (f.nutrition_tags?.length) count += f.nutrition_tags.length
  if (f.exclude_ingredients?.length) count += f.exclude_ingredients.length
  if (f.include_ingredients?.length) count += f.include_ingredients.length
  return count
})

// 分类：搜索时显示匹配项，否则显示 top N 或全部
const filteredCategories = computed(() => {
  const cats = props.options.categories || []
  if (categorySearch.value) {
    const q = categorySearch.value.toLowerCase()
    return cats.filter(c => c.label.toLowerCase().includes(q))
  }
  return cats
})

const displayCategories = computed(() => {
  if (categorySearch.value) return filteredCategories.value
  return showAllCategories.value
    ? filteredCategories.value
    : filteredCategories.value.slice(0, FEATURED_COUNT)
})

// 关键词：同分类逻辑
const filteredKeywords = computed(() => {
  const kws = props.options.keywords || []
  if (keywordSearch.value) {
    const q = keywordSearch.value.toLowerCase()
    return kws.filter(k => k.label.toLowerCase().includes(q))
  }
  return kws
})

const displayKeywords = computed(() => {
  if (keywordSearch.value) return filteredKeywords.value
  return showAllKeywords.value
    ? filteredKeywords.value
    : filteredKeywords.value.slice(0, FEATURED_COUNT)
})

function toggleCategory(val) {
  const list = localFilters.value.categories
  const idx = list.indexOf(val)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(val)
}

function toggleKeyword(val) {
  const list = localFilters.value.keywords
  const idx = list.indexOf(val)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(val)
}

function toggleDifficulty(val) {
  localFilters.value.difficulty_max =
    localFilters.value.difficulty_max === val ? null : val
}

function toggleCosttime(val) {
  localFilters.value.costtime_max =
    localFilters.value.costtime_max === val ? null : val
}

function toggleNutritionTag(tag) {
  const tags = localFilters.value.nutrition_tags
  const idx = tags.indexOf(tag)
  if (idx >= 0) tags.splice(idx, 1)
  else tags.push(tag)
}

function toggleExcludeQuick(ing) {
  const list = localFilters.value.exclude_ingredients
  const idx = list.indexOf(ing)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(ing)
}

function toggleIncludeQuick(ing) {
  const list = localFilters.value.include_ingredients
  const idx = list.indexOf(ing)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(ing)
}

function addExclude() {
  const val = newExclude.value.trim()
  if (val && !localFilters.value.exclude_ingredients.includes(val)) {
    localFilters.value.exclude_ingredients.push(val)
  }
  newExclude.value = ''
}

function removeExclude(ing) {
  localFilters.value.exclude_ingredients =
    localFilters.value.exclude_ingredients.filter((i) => i !== ing)
}

function addInclude() {
  const val = newInclude.value.trim()
  if (val && !localFilters.value.include_ingredients.includes(val)) {
    localFilters.value.include_ingredients.push(val)
  }
  newInclude.value = ''
}

function removeInclude(ing) {
  localFilters.value.include_ingredients =
    localFilters.value.include_ingredients.filter((i) => i !== ing)
}

function handleReset() {
  localFilters.value = {
    categories: [],
    keywords: [],
    difficulty_max: null,
    costtime_max: null,
    nutrition_tags: [],
    exclude_ingredients: [],
    include_ingredients: [],
  }
}
</script>

<style scoped>
.filter-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-5);
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
  border-radius: var(--radius-md);
}

.filter-header:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.filter-title {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text-primary);
}

.filter-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--color-primary);
  color: var(--color-text-inverse);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.collapse-icon {
  transition: transform 0.25s ease;
  color: var(--color-text-secondary);
}

.collapse-icon.is-collapsed {
  transform: rotate(180deg);
}

.filter-body {
  padding-top: var(--space-3);
}

/* 折叠动画：grid-template-rows 实现平滑高度过渡 */
.filter-body-wrapper {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows 0.3s ease;
  overflow: hidden;
}

.filter-body-wrapper.is-collapsed {
  grid-template-rows: 0fr;
}

.filter-body-wrapper > .filter-body {
  min-height: 0;
  overflow: hidden;
}

.filter-section {
  margin-bottom: var(--space-3);
}

.filter-section:last-child {
  margin-bottom: 0;
}

.section-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}

.section-search {
  margin-bottom: var(--space-2);
  max-width: 240px;
}

.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
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
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}
</style>
