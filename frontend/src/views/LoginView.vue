<template>
  <div class="login-page">
    <div class="login-card">
      <!-- Logo -->
      <div class="login-header">
        <el-icon :size="36" color="var(--color-primary)"><Food /></el-icon>
        <h2>个性化食谱推荐系统</h2>
      </div>

      <!-- Tab 切换 -->
      <el-tabs v-model="activeTab" class="login-tabs" stretch>
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <!-- 表单 -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            show-password
            size="large"
          />
        </el-form-item>

        <el-form-item
          v-if="activeTab === 'register'"
          label="确认密码"
          prop="confirmPassword"
        >
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            :prefix-icon="Lock"
            show-password
            size="large"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleSubmit"
            style="width: 100%"
          >
            {{ activeTab === "login" ? "登录" : "注册" }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <router-link to="/" class="back-link">
          <el-icon><ArrowLeft /></el-icon>
          返回首页
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { User, Lock } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const activeTab = ref("login");
const loading = ref(false);
const formRef = ref(null);
const form = ref({
  username: "",
  password: "",
  confirmPassword: "",
});

// URL 参数控制初始 Tab
onMounted(() => {
  if (route.query.tab === "register") {
    activeTab.value = "register";
  }
});

// 切换 Tab 时清空表单
watch(activeTab, () => {
  form.value = { username: "", password: "", confirmPassword: "" };
  formRef.value?.clearValidate();
});

// 确认密码校验
const validateConfirm = (rule, value, callback) => {
  if (activeTab.value === "register" && value !== form.value.password) {
    callback(new Error("两次输入的密码不一致"));
  } else {
    callback();
  }
};

const rules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { min: 3, max: 20, message: "用户名 3-20 个字符", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, max: 50, message: "密码 6-50 个字符", trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: "请确认密码", trigger: "blur" },
    { validator: validateConfirm, trigger: "blur" },
  ],
};

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) return;

  loading.value = true;
  try {
    let data;
    if (activeTab.value === "login") {
      data = await authStore.login(form.value.username, form.value.password);
      ElMessage.success("登录成功");
    } else {
      data = await authStore.register(form.value.username, form.value.password);
      ElMessage.success("注册成功");
    }

    // 新用户跳转偏好引导，老用户跳首页
    if (data.is_new_user) {
      router.push("/onboarding");
    } else {
      router.push("/home");
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || "操作失败，请重试");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-bg);
  padding: var(--space-6);
}

.login-card {
  width: 100%;
  max-width: 420px;
  background: var(--color-surface);
  border-radius: var(--radius-xl);
  padding: var(--space-8) var(--space-8) var(--space-6);
  box-shadow: var(--shadow-lg);
}

.login-header {
  text-align: center;
  margin-bottom: var(--space-6);
}

.login-header h2 {
  margin-top: var(--space-2);
  font-size: 22px;
  color: var(--color-text-primary);
}

.login-tabs {
  margin-bottom: var(--space-4);
}

.login-footer {
  text-align: center;
  margin-top: var(--space-4);
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-tertiary);
  font-size: 13px;
  transition: color var(--duration-fast);
}

.back-link:hover {
  color: var(--color-primary);
}
</style>
