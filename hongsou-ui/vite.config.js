import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag.includes('iconify-icon')
        }
      }
    })
  ],
  build: {
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (id.includes('vue') || id.includes('@vue')) {
            return 'vue-vendor'
          }

          if (id.includes('zrender')) {
            return 'zrender-vendor'
          }

          if (id.includes('echarts') || id.includes('vue-echarts')) {
            return 'charts-vendor'
          }

          if (id.includes('element-plus') || id.includes('@element-plus')) {
            return 'element-vendor'
          }

          return 'app-vendor'
        }
      }
    }
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
