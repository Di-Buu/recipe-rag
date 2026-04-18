/**
 * 路由配置
 *
 * 包含导航守卫：
 * - 未登录 → 登录页
 * - 已登录访问登录/封面 → 首页
 * - 新用户 → 偏好引导页
 */

import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Landing',
    component: () => import('../views/LandingView.vue'),
    meta: { guest: true },
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('../views/OnboardingView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/home',
    name: 'Home',
    component: () => import('../views/HomeView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/result',
    name: 'Result',
    component: () => import('../views/ResultView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/recipe/:id',
    name: 'RecipeDetail',
    component: () => import('../views/RecipeDetail.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/preference',
    name: 'Preference',
    component: () => import('../views/PreferenceView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/HistoryView.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 导航守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  const isNewUser = localStorage.getItem('isNewUser') === 'true'

  // 需要认证但未登录 → 登录页
  if (to.meta.requiresAuth && !token) {
    return next('/login')
  }

  // 已登录访问游客页面 → 首页
  if (to.meta.guest && token) {
    return next('/home')
  }

  // 已登录的新用户，访问非 onboarding 的认证页面 → 偏好引导
  if (token && isNewUser && to.meta.requiresAuth && to.name !== 'Onboarding') {
    return next('/onboarding')
  }

  next()
})

export default router
