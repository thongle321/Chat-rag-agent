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
import NotFoundPage from './pages/404.vue'
import AdminIndex from './pages/admin/index.vue'

const autoAdmin = autoRoutes.find(r => r.path === '/admin')
const loginChild = autoAdmin?.children?.find(c => c.path === 'login')
const adminChildren = (autoAdmin?.children || []).filter(c => c.path !== 'login')

const routes = [
  // Standalone login — before /admin to avoid catch-all
  loginChild ? { ...loginChild, path: '/admin/login' } : null,
  {
    path: '/',
    component: PublicLayout,
    children: autoRoutes.filter(r => r.path === '/')
  },
  {
    path: '/admin',
    component: DefaultLayout,
    children: [
      { path: '', component: AdminIndex },
      ...adminChildren,
      { path: ':pathMatch(.*)', redirect: '/404' }
    ]
  },
  { path: '/404', name: 'NotFound', component: NotFoundPage },
  { path: '/:all(.*)', redirect: '/404' }
].filter(Boolean)

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
