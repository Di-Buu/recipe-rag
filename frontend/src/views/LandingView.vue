<template>
  <div class="landing-page">
    <!-- 装饰元素 -->
    <div class="landing-deco deco-1">🍳</div>
    <div class="landing-deco deco-2">🥗</div>
    <div class="landing-deco deco-3">🍜</div>
    <div class="landing-deco deco-4">🧁</div>

    <div class="landing-content">
      <div class="landing-icon">
        <el-icon :size="64" color="var(--color-text-inverse)"><Food /></el-icon>
      </div>
      <h1 class="landing-title">个性化食谱推荐系统</h1>
      <p class="landing-subtitle">让每一餐都有灵感，让健康饮食更简单</p>
      <div class="landing-actions">
        <el-button type="primary" size="large" round @click="goRegister">
          开始探索
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
        <p class="login-hint">
          已有账号？
          <router-link to="/login" class="login-link">登录</router-link>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from "vue-router";

const router = useRouter();

function goRegister() {
  router.push("/login?tab=register");
}
</script>

<style scoped>
.landing-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gradient-primary);
  padding: var(--space-6);
  position: relative;
  overflow: hidden;
}

/* 浮动食物装饰 */
.landing-deco {
  position: absolute;
  font-size: 48px;
  opacity: 0.15;
  pointer-events: none;
  animation: drift 8s ease-in-out infinite;
}

.deco-1 {
  top: 12%;
  left: 8%;
  font-size: 56px;
  animation-delay: 0s;
}

.deco-2 {
  top: 18%;
  right: 10%;
  font-size: 44px;
  animation-delay: -2s;
}

.deco-3 {
  bottom: 20%;
  left: 14%;
  font-size: 40px;
  animation-delay: -4s;
}

.deco-4 {
  bottom: 15%;
  right: 12%;
  font-size: 52px;
  animation-delay: -6s;
}

@keyframes drift {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  25% { transform: translateY(-12px) rotate(3deg); }
  75% { transform: translateY(8px) rotate(-2deg); }
}

.landing-content {
  text-align: center;
  color: var(--color-text-inverse);
  position: relative;
  z-index: 1;
}

.landing-icon {
  margin-bottom: var(--space-5);
  width: 88px;
  height: 88px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.landing-title {
  font-size: clamp(32px, 5vw, 48px);
  font-weight: 800;
  margin-bottom: var(--space-3);
  letter-spacing: 3px;
}

.landing-subtitle {
  font-size: clamp(15px, 2vw, 19px);
  opacity: 0.85;
  margin-bottom: var(--space-10);
  letter-spacing: 1px;
  font-weight: 300;
}

.landing-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
}

.landing-actions .el-button {
  min-width: 200px;
  height: 52px;
  font-size: 17px;
  font-weight: 600;
  background: var(--color-surface);
  color: var(--color-primary);
  border: none;
  letter-spacing: 1px;
}

.landing-actions .el-button:hover {
  background: var(--color-primary-bg);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.login-hint {
  font-size: 14px;
  opacity: 0.8;
}

.login-link {
  color: var(--color-text-inverse);
  text-decoration: underline;
  font-weight: 500;
}
</style>
