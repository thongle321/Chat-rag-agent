import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueRouter from 'vue-router/vite'
import ui from '@nuxt/ui/vite'

export default defineConfig({
  plugins: [
    vueRouter({
      dts: 'src/route-map.d.ts'
    }),
    vue(),
    ui({
      autoImport: {
        imports: ['vue', 'vue-router', '@vueuse/core'],
      },
      ui: {
        colors: {
          primary: 'blue',
          neutral: 'slate'
        }
      }
    })
  ],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
