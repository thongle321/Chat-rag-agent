import './assets/css/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { routes as autoRoutes, handleHotUpdate } from 'vue-router/auto-routes'
import { createHead } from '@unhead/vue/client'
import ui from '@nuxt/ui/vue-plugin'
import App from './App.vue'

import DefaultLayout from './layouts/default.vue'
import PublicLayout from './layouts/public.vue'

const autoAdmin = autoRoutes.find(r => r.path === '/admin')
const loginChild = autoAdmin?.children?.find(c => c.path === 'login')
const adminChildren = (autoAdmin?.children || []).filter(c => c.path !== 'login')

const routes = [
  {
    path: '/',
    component: PublicLayout,
    children: autoRoutes.filter(r => r.path === '/')
  },
  {
    path: '/admin',
    component: DefaultLayout,
    children: adminChildren
  },
  // Standalone login — no sidebar layout
  loginChild ? { ...loginChild, path: '/admin/login' } : null,
  autoRoutes.find(r => r.path === '/:all(.*)')
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

app.mount('#app')

if (import.meta.hot) {
  handleHotUpdate(router)
}
