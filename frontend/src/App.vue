<script setup>
import { onMounted, ref } from 'vue'
import CesiumGlobe from './components/CesiumGlobe.vue'

// 页面加载后调用后端健康检查接口，验证前后端是否连通
const health = ref(null)
const error = ref('')

onMounted(async () => {
  try {
    const res = await fetch('/api/health')
    if (!res.ok) throw new Error('HTTP ' + res.status)
    health.value = await res.json()
  } catch (e) {
    error.value = e.message
  }
})
</script>

<template>
  <div class="app">
    <!-- 三维地球占满整个视口 -->
    <CesiumGlobe />

    <!-- 左上角浮层：标题 + 后端连通性 -->
    <aside class="panel">
      <h1>Calcite</h1>
      <p class="subtitle">Spring Boot 3 + Vue 3 + Cesium + PostGIS</p>

      <h2>后端连通性</h2>
      <p v-if="error" class="bad">❌ 未连接：{{ error }}</p>
      <ul v-else-if="health" class="ok">
        <li><span>状态</span>{{ health.status }}</li>
        <li><span>应用</span>{{ health.application }}</li>
        <li><span>数据库</span>{{ health.database }}</li>
        <li><span>PostGIS</span>{{ health.postgis }}</li>
      </ul>
      <p v-else class="muted">检查中…</p>
    </aside>
  </div>
</template>

<style scoped>
.app {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}

.panel {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 10;
  width: 300px;
  padding: 16px 18px;
  border: 1px solid rgba(127, 209, 255, 0.18);
  border-radius: 10px;
  background: rgba(10, 16, 26, 0.78);
  backdrop-filter: blur(6px);
  font-size: 14px;
  line-height: 1.6;
}

.panel h1 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 1px;
}

.panel h2 {
  margin: 14px 0 6px;
  font-size: 13px;
  color: #7fd1ff;
  font-weight: 600;
}

.subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #93a4bb;
}

.panel ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.panel li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 0;
  font-size: 13px;
}

.panel li span {
  color: #93a4bb;
}

.ok {
  color: #7ee0a6;
}

.bad {
  margin: 0;
  color: #ff9b9b;
}

.muted {
  margin: 0;
  color: #93a4bb;
}
</style>
