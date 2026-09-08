import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// Cesium 的 Workers / Assets / Widgets / ThirdParty 不能被打包器处理，
// 必须原样拷贝到输出目录，再用 CESIUM_BASE_URL 告诉 Cesium 去哪里取。
const cesiumSource = 'node_modules/cesium/Build/Cesium'
const cesiumBaseUrl = 'cesiumStatic'
// 插件会保留匹配到的完整路径，这里算出需要剥掉的目录层数（node_modules/cesium/Build/Cesium = 4 层）
const stripBase = cesiumSource.split('/').length

// Vite 配置：前端开发服务器
export default defineConfig({
  define: {
    // 关键：Cesium 运行时用这个全局变量拼接 worker / 贴图 / 样式地址
    CESIUM_BASE_URL: JSON.stringify(`/${cesiumBaseUrl}`),
  },
  plugins: [
    vue(),
    viteStaticCopy({
      targets: [
        { src: `${cesiumSource}/ThirdParty`, dest: cesiumBaseUrl, rename: { stripBase } },
        { src: `${cesiumSource}/Workers`, dest: cesiumBaseUrl, rename: { stripBase } },
        { src: `${cesiumSource}/Assets`, dest: cesiumBaseUrl, rename: { stripBase } },
        { src: `${cesiumSource}/Widgets`, dest: cesiumBaseUrl, rename: { stripBase } },
      ],
    }),
  ],
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
