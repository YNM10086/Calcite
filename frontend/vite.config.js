import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 配置：前端开发服务器
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 开发时把 /api 开头的请求转发给后端 8080，避免浏览器跨域（CORS）问题
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
