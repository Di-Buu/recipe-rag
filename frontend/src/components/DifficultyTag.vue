<template>
  <el-tag :type="tagType" :size="size" effect="light" class="difficulty-tag">
    {{ text }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const DIFFICULTY_MAP = {
  0: { text: '简单', type: 'success' },
  1: { text: '一般', type: 'success' },
  2: { text: '较难', type: 'warning' },
  3: { text: '困难', type: 'danger' },
}

const props = defineProps({
  level: { type: Number, default: 0 },
  size: { type: String, default: 'default' },
})

const text = computed(() => DIFFICULTY_MAP[props.level]?.text || '未知')
const tagType = computed(() => DIFFICULTY_MAP[props.level]?.type || 'info')
</script>

<style scoped>
.difficulty-tag {
  font-weight: 500;
}
</style>
