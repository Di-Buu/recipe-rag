<template>
  <div class="app-layout">
    <!-- 顶部导航栏 -->
    <header class="navbar">
      <div class="navbar-inner">
        <!-- 左：Logo -->
        <div
          class="navbar-brand"
          role="link"
          tabindex="0"
          @click="router.push('/home')"
          @keydown.enter="router.push('/home')"
        >
          <el-icon :size="24"><Food /></el-icon>
          <span class="brand-text">食谱智能推荐</span>
        </div>

        <!-- 中：导航链接 -->
        <nav class="navbar-nav">
          <router-link to="/home" class="nav-link" active-class="active">
            <el-icon><HomeFilled /></el-icon>
            <span>首页</span>
          </router-link>
          <router-link to="/preference" class="nav-link" active-class="active">
            <el-icon><Setting /></el-icon>
            <span>偏好设置</span>
          </router-link>
          <router-link to="/history" class="nav-link" active-class="active">
            <el-icon><Clock /></el-icon>
            <span>历史</span>
          </router-link>
        </nav>

        <!-- 右：用户菜单 -->
        <div class="navbar-user">
          <el-dropdown trigger="click" @command="handleUserCommand">
            <span class="user-trigger">
              <el-icon><User /></el-icon>
              <span>{{ authStore.username }}</span>
              <el-icon class="arrow"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">
                  <el-icon><Lock /></el-icon>修改密码
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </header>

    <!-- 内容区 -->
    <main class="main-content">
      <slot />
    </main>

    <!-- 修改密码对话框 -->
    <el-dialog v-model="pwdDialogVisible" title="修改密码" width="400px" :close-on-click-modal="false">
      <el-form :model="pwdForm" :rules="pwdRules" ref="pwdFormRef" label-width="80px">
        <el-form-item label="旧密码" prop="oldPassword">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="pwdForm.newPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdLoading" @click="handleChangePwd">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

// 修改密码
const pwdDialogVisible = ref(false)
const pwdLoading = ref(false)
const pwdFormRef = ref(null)
const pwdForm = ref({ oldPassword: '', newPassword: '' })
const pwdRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 50, message: '密码长度 6-50 字符', trigger: 'blur' },
  ],
}

function handleUserCommand(command) {
  if (command === 'password') {
    pwdForm.value = { oldPassword: '', newPassword: '' }
    pwdDialogVisible.value = true
  } else if (command === 'logout') {
    authStore.logout()
    router.push('/login')
    ElMessage.success('已退出登录')
  }
}

async function handleChangePwd() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return

  pwdLoading.value = true
  try {
    await authStore.changePassword(pwdForm.value.oldPassword, pwdForm.value.newPassword)
    ElMessage.success('密码修改成功')
    pwdDialogVisible.value = false
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '修改失败')
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--navbar-height);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  z-index: 100;
}

.navbar-inner {
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: 0 var(--space-6);
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.navbar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  color: var(--color-primary);
  font-weight: 600;
  font-size: 18px;
  transition: opacity var(--duration-fast);
}

.navbar-brand:hover {
  opacity: 0.85;
}

.navbar-brand:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: var(--radius-md);
}

.navbar-nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.nav-link {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: 14px;
  transition: all var(--duration-fast);
  text-decoration: none;
}

.nav-link:hover {
  color: var(--color-primary);
  background-color: var(--color-primary-bg);
}

.nav-link.active {
  color: var(--color-primary);
  background-color: var(--color-primary-bg);
  font-weight: 500;
}

.navbar-user {
  display: flex;
  align-items: center;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: 14px;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  transition: all var(--duration-fast);
}

.user-trigger:hover {
  color: var(--color-primary);
  background-color: var(--color-primary-bg);
}

.arrow {
  font-size: 12px;
}

.main-content {
  flex: 1;
  margin-top: var(--navbar-height);
  padding: var(--space-6);
  max-width: var(--content-max-width);
  width: 100%;
  margin-left: auto;
  margin-right: auto;
}
</style>
