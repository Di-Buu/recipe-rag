<template>
  <router-view />
</template>

<script setup>
import { useAuthStore } from './stores/auth'

// 启动时从 localStorage 恢复登录状态
const authStore = useAuthStore()
authStore.loadFromStorage()
</script>

<style>
#app {
  min-height: 100vh;
}
</style>
