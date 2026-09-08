<script setup>
import { ref, onMounted } from 'vue'

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
  <main>
    <h1>Calcite</h1>
    <p class="subtitle">Spring Boot 3 + Vue 3 + Cesium + PostGIS</p>

    <section class="card">
      <h2>后端连通性检查</h2>

      <p v-if="error" class="bad">
        ❌ 后端未连接：{{ error }}
      </p>
      <ul v-else-if="health" class="ok">
        <li><span>状态</span>{{ health.status }}</li>
        <li><span>应用</span>{{ health.application }}</li>
        <li><span>数据库</span>{{ health.database }}</li>
        <li><span>PostGIS</span>{{ health.postgis }}</li>
      </ul>
      <p v-else class="muted">检查中…</p>
    </section>
  </main>
</template>
