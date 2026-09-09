<script setup>
import { computed, onMounted, ref } from 'vue'
import CesiumGlobe from './components/CesiumGlobe.vue'
import TrackList from './components/TrackList.vue'

/* ============ 后端连通性 ============ */
const health = ref(null)
const healthError = ref('')

/* ============ 轨迹列表 ============ */
const tracks = ref([])
const tracksLoading = ref(true)
const tracksError = ref('')

/* ============ 选中的轨迹详情（含全部点）============ */
const selectedId = ref(null)
const detail = ref(null)
const detailLoading = ref(false)

/** 传给地球的轨迹点。detail 为空时给空数组，地球就什么都不画 */
const trackPoints = computed(() => detail.value?.points ?? [])

/** 用于底部状态条 */
const selectedTrack = computed(() =>
  tracks.value.find((t) => t.id === selectedId.value) ?? null,
)

/** 页面加载时：拉健康检查 + 轨迹列表（两个请求互不依赖，可以并发） */
onMounted(() => {
  fetch('/api/health')
    .then((res) => {
      if (!res.ok) throw new Error('HTTP ' + res.status)
      return res.json()
    })
    .then((data) => (health.value = data))
    .catch((e) => (healthError.value = e.message))

  loadTracks()

  // 支持 ?track=1 直接打开某条轨迹（方便分享链接，也方便自动化验证）
  const wanted = Number(new URLSearchParams(window.location.search).get('track'))
  if (wanted > 0) selectTrack(wanted)
})

async function loadTracks() {
  tracksLoading.value = true
  tracksError.value = ''
  try {
    const res = await fetch('/api/tracks')
    if (!res.ok) throw new Error('HTTP ' + res.status)
    tracks.value = await res.json()
  } catch (e) {
    tracksError.value = e.message
  } finally {
    tracksLoading.value = false
  }
}

/**
 * 点列表里的一条轨迹
 * 再点一次同一条 = 取消选中（把线从地球上清掉）
 */
async function selectTrack(id) {
  if (selectedId.value === id) {
    selectedId.value = null
    detail.value = null
    return
  }

  selectedId.value = id
  detail.value = null
  detailLoading.value = true
  tracksError.value = ''
  try {
    // 详情接口会返回这条轨迹的全部点，前端才能连成线
    const res = await fetch(`/api/tracks/${id}`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    detail.value = await res.json()
  } catch (e) {
    tracksError.value = e.message
    selectedId.value = null
  } finally {
    detailLoading.value = false
  }
}
</script>

<template>
  <div class="app">
    <!-- 三维地球占满整个视口 -->
    <CesiumGlobe :points="trackPoints" />

    <!-- 左上角浮层：标题 + 后端连通性 + 轨迹列表 -->
    <aside class="panel">
      <h1>Calcite</h1>
      <p class="subtitle">Spring Boot 3 + Vue 3 + Cesium + PostGIS</p>

      <h2>后端连通性</h2>
      <p v-if="healthError" class="bad">❌ 未连接：{{ healthError }}</p>
      <ul v-else-if="health" class="ok">
        <li><span>状态</span>{{ health.status }}</li>
        <li><span>应用</span>{{ health.application }}</li>
        <li><span>数据库</span>{{ health.database }}</li>
        <li><span>PostGIS</span>{{ health.postgis }}</li>
      </ul>
      <p v-else class="muted">检查中…</p>

      <h2>轨迹列表</h2>
      <p class="tip">点一条轨迹，它会被画到地球上</p>
      <TrackList
        :tracks="tracks"
        :selected-id="selectedId"
        :loading="tracksLoading"
        :error="tracksError"
        @select="selectTrack"
      />
    </aside>

    <!-- 左下角状态条：当前地球上有几条轨迹、多少点 -->
    <div class="status" :class="{ live: trackPoints.length > 0 }">
      <template v-if="detailLoading">正在加载轨迹点…</template>
      <template v-else-if="detail">
        🛰 {{ detail.name }} · {{ detail.points.length }} 个点 ·
        {{ (detail.distanceM / 1000).toFixed(2) }} km
      </template>
      <template v-else>未选择轨迹</template>
    </div>
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
  width: 320px;
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

.tip {
  margin: 0 0 6px;
  font-size: 11px;
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

.status {
  position: absolute;
  bottom: 16px;
  left: 16px;
  z-index: 10;
  padding: 6px 12px;
  border: 1px solid rgba(127, 209, 255, 0.18);
  border-radius: 999px;
  background: rgba(10, 16, 26, 0.78);
  color: #93a4bb;
  font-size: 12px;
  backdrop-filter: blur(6px);
}

.status.live {
  border-color: rgba(127, 209, 255, 0.5);
  color: #7fd1ff;
}
</style>
