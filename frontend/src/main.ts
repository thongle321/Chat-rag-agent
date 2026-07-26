import './assets/css/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { routes as autoRoutes, handleHotUpdate } from 'vue-router/auto-routes'
import { createHead } from '@unhead/vue/client'
import ui from '@nuxt/ui/vue-plugin'
import App from './App.vue'

import DefaultLayout from './layouts/default.vue'
import PublicLayout from './layouts/public.vue'

// ponytail: lazy import matches auto-router's dynamic imports
const NotFoundPage = () => import('./pages/404.vue')
// ponytail: /admin/login as standalone to avoid catch-all swallowing it
const AdminLogin = () => import('./pages/admin/login.vue')

const autoAdmin = autoRoutes.find(r => r.path === '/admin')
const adminChildren = (autoAdmin?.children || []).filter(c => c.path !== 'login' && c.path !== '')

const routes = [
  // Standalone login — before /admin to avoid catch-all
  { path: '/admin/login', component: AdminLogin },
  ...autoRoutes.filter(r => r.path !== '/admin'),
  {
    path: '/admin',
    component: DefaultLayout,
    children: [
      ...adminChildren,
      { path: ':pathMatch(.*)', redirect: '/404' }
    ]
  },
  { path: '/404', name: 'NotFound', component: NotFoundPage },
  { path: '/:all(.*)', redirect: '/404' }
]

const app = createApp(App)
const head = createHead()
const router = createRouter({
  history: createWebHistory(),
  routes
})

app.use(createPinia())
app.use(head)
app.use(router)
app.use(ui)

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (auth.token && !auth.user) {
    await auth.fetchUser()
  }
  if (to.path.startsWith('/admin') && to.path !== '/admin/login') {
    if (!auth.isAuthenticated) return '/admin/login'
  }
  if (to.path === '/admin/login' && auth.isAuthenticated) return '/admin/'
})

app.mount('#app')

if (import.meta.hot) {
  handleHotUpdate(router)
}
