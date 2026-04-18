<template>
  <div class="nutrition-badge" :style="{ background: bgColor }">
    <div class="badge-icon">{{ icon }}</div>
    <div class="badge-info">
      <div class="badge-value">{{ displayValue }}</div>
      <div class="badge-label">{{ label }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], default: 0 },
  unit: { type: String, default: '' },
  icon: { type: String, default: '' },
  color: { type: String, default: 'var(--color-primary)' },
})

const displayValue = computed(() => {
  const val = typeof props.value === 'number' ? props.value.toFixed(1) : props.value
  return props.unit ? `${val} ${props.unit}` : val
})

// 将 hex 或 CSS 变量转为带透明度的背景色
const bgColor = computed(() => {
  const c = props.color
  // 如果是 CSS 变量引用，使用 color-mix 获得透明度
  if (c.startsWith('var(')) {
    return `color-mix(in srgb, ${c} 10%, transparent)`
  }
  // hex 颜色转 rgba
  const hex = c.replace('#', '')
  if (hex.length === 6) {
    const r = parseInt(hex.slice(0, 2), 16)
    const g = parseInt(hex.slice(2, 4), 16)
    const b = parseInt(hex.slice(4, 6), 16)
    return `rgba(${r}, ${g}, ${b}, 0.08)`
  }
  return c + '12'
})
</script>

<style scoped>
.nutrition-badge {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  min-width: 120px;
}

.badge-icon {
  font-size: 24px;
  line-height: 1;
}

.badge-info {
  display: flex;
  flex-direction: column;
}

.badge-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.badge-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
