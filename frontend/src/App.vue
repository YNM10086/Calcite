<script setup>
import { computed, nextTick, onMounted, ref, shallowRef, watch } from 'vue'
import CesiumGlobe from './components/CesiumGlobe.vue'
import SpeedChart from './components/SpeedChart.vue'
import TrackList from './components/TrackList.vue'
import StayPointList from './components/StayPointList.vue'
import TrackPlayer from './components/TrackPlayer.vue'
import HotspotList from './components/HotspotList.vue'
import { canPlay, timeRange } from './lib/playback.js'
import { sortHotspots } from './lib/hotspot.js'

/* ============ 后端连通性 ============ */
const health = ref(null)
const healthError = ref('')

/** 页面上只显示版本号，完整构建串（msvc 那串）太长，塞进 title 悬浮提示 */
const pgShort = computed(() => (health.value?.database ?? '').split(' on ')[0])
const postgisShort = computed(() => (health.value?.postgis ?? '').split(' ')[0])
const healthTitle = computed(() =>
  health.value
    ? `${health.value.application} · ${health.value.database} · PostGIS ${health.value.postgis}`
    : '',
)
/** 标题后面那个小圆点：绿=通，红=断，灰=还不知道 */
const healthDotClass = computed(() =>
  healthError.value ? 'bad-dot' : health.value ? 'ok-dot' : '',
)

/* ============ 轨迹列表 ============ */
const tracks = ref([])
const tracksLoading = ref(true)
const tracksError = ref('')

/* ============ 选中的轨迹详情（含全部点）============ */
const selectedId = ref(null)
const detail = ref(null)
const detailLoading = ref(false)

/* ============ 回放 ============ */
// 地球组件的引用，用来调用它暴露的 play / pause / seekTo
const globe = ref(null)
const playing = ref(false)
const loop = ref(true)
// 每帧都在变的值用 shallowRef，避免 Vue 对它做深度代理
const currentMs = shallowRef(0)

/** 传给地球的轨迹点。detail 为空时给空数组，地球就什么都不画 */
const trackPoints = computed(() => detail.value?.points ?? [])

/** 这条轨迹的时间范围；缺时间信息时为 null */
const range = computed(() => timeRange(trackPoints.value))
const canPlayback = computed(() => canPlay(trackPoints.value))
const startMs = computed(() => range.value?.startMs ?? 0)
const endMs = computed(() => range.value?.endMs ?? 0)

/** 用于底部状态条 */
const selectedTrack = computed(() =>
  tracks.value.find((t) => t.id === selectedId.value) ?? null,
)

// 换轨迹 → 停止播放，进度回到起点
watch(trackPoints, (points) => {
  playing.value = false
  const r = timeRange(points)
  currentMs.value = r ? r.startMs : 0
})

/** 地球报来新时刻（已节流） */
function onTimeChange(ms) {
  currentMs.value = ms
  // 关掉循环时，Cesium 播到终点会自己停住，这里把 UI 的播放状态同步回来
  if (playing.value && !loop.value && ms >= endMs.value) {
    playing.value = false
    globe.value?.pause()
  }
}

/** 播放 / 暂停 */
function togglePlay() {
  if (!canPlayback.value) return
  playing.value = !playing.value
  if (playing.value) globe.value?.play()
  else globe.value?.pause()
}

/** 拖动进度条 */
function seekTo(ms) {
  currentMs.value = ms
  globe.value?.seekTo(ms)
}

/** 循环开关 */
function toggleLoop() {
  loop.value = !loop.value
}

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

/* ============ 列表筛选 ============ */
// 状态放在 App（唯一状态中心），TrackList 只负责回显 + 上报
const sourceFilter = ref('')
const limit = ref(50)
const tracksTotal = ref(0)

async function loadTracks() {
  tracksLoading.value = true
  tracksError.value = ''
  try {
    const params = new URLSearchParams()
    if (sourceFilter.value) params.set('source', sourceFilter.value)
    params.set('limit', String(limit.value))

    const res = await fetch('/api/tracks?' + params.toString())
    if (!res.ok) throw new Error('HTTP ' + res.status)
    // 接口返回的是 { total, items } —— total 是符合条件的总数，不只是本页条数
    const data = await res.json()
    tracks.value = data.items ?? []
    tracksTotal.value = data.total ?? tracks.value.length
  } catch (e) {
    tracksError.value = e.message
  } finally {
    tracksLoading.value = false
  }
}

/** 用户改了筛选条件（来源或条数）→ 重新拉列表 */
function onFilterChange({ source, limit: newLimit }) {
  sourceFilter.value = source
  limit.value = newLimit
  loadTracks()
}

/* ============ 停留点 ============ */
const stays = ref([])
const staysLoading = ref(false)

/** 拉某条轨迹的停留点 */
async function loadStays(id) {
  staysLoading.value = true
  try {
    const res = await fetch(`/api/tracks/${id}/stay-points`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    stays.value = data.stays ?? []
  } catch (e) {
    stays.value = []
    tracksError.value = '停留点加载失败：' + e.message
  } finally {
    staysLoading.value = false
  }
}

/** 点停留点列表里的一条 → 地球飞过去 */
function focusStay(s) {
  globe.value?.focusOn(s.lon, s.lat, s.radiusM)
}

/* ============ 热点（跨轨迹）============ */
// 'stay' = 看某条轨迹的停留点；'hotspot' = 看全局热点。
// 两者都会往地球上画圈，同时画会糊在一起，所以做成互斥的两档。
const viewMode = ref('stay')
const hotspots = ref([])
const hotspotsLoading = ref(false)
const hotspotsError = ref('')
const hotspotSort = ref('trackCount')

/** 按当前口径排序后的热点（不改动 hotspots 本身） */
const sortedHotspots = computed(() => sortHotspots(hotspots.value, hotspotSort.value))

/** 切换模式：从"停留点"切到"热点"时才去拉数据（懒加载） */
async function switchMode(mode) {
  viewMode.value = mode
  if (mode === 'hotspot') {
    if (hotspots.value.length === 0) await loadHotspots()
    // 等 DOM 更新后相机再飞，否则地球可能还没拿到数据
    await nextTick()
    // 面板会盖住画布左侧。必须把这个比例告诉地球，否则热点包围盒会被居中，
    // 西边那个热点正好落在面板底下 —— 看起来像"只画出了一个热点"（实测踩过）。
    const panelEl = document.querySelector('.panel')
    const insetLeft = panelEl
      ? panelEl.getBoundingClientRect().right / window.innerWidth
      : 0
    globe.value?.fitBounds(sortedHotspots.value, insetLeft)
  }
}

/** 拉全部热点 */
async function loadHotspots() {
  hotspotsLoading.value = true
  hotspotsError.value = ''
  try {
    const res = await fetch('/api/analysis/hotspots')
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    hotspots.value = data.hotspots ?? []
  } catch (e) {
    hotspots.value = []
    hotspotsError.value = '热点加载失败：' + e.message
  } finally {
    hotspotsLoading.value = false
  }
}

/** 点热点列表里的一条 → 地球飞过去 */
function focusHotspot(h) {
  globe.value?.focusOn(h.centerLon, h.centerLat, Math.max(h.radiusM, 200))
}

/* ============ 轨迹导入 ============ */
const importing = ref(false)
const importMessage = ref('')

/**
 * 上传一个轨迹文件。
 *
 * 组件只负责"选文件"，请求统一由 App 发 —— 和 selectTrack 一样的规矩：
 * 子组件只显示 + 上报意图，状态和数据都由父组件管。
 */
async function importTrack(file) {
  importing.value = true
  importMessage.value = ''
  tracksError.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/tracks/import', { method: 'POST', body: form })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'HTTP ' + res.status)

    await loadTracks()
    if (data.skippedDuplicate) {
      importMessage.value = `这条轨迹已经导入过了（id=${data.id}）`
    } else {
      const mm = Math.floor(data.durationS / 60)
      const ss = String(data.durationS % 60).padStart(2, '0')
      importMessage.value =
        `导入成功：${data.name} · ${data.pointCount} 点 · ` +
        `${(data.distanceM / 1000).toFixed(2)} km · ${mm}分${ss}秒` +
        (data.outlierCount > 0 ? ` · 标记 ${data.outlierCount} 个疑似漂移点` : '')
    }
    // 无论是不是重复，都选中这条轨迹，让用户马上看到它
    await selectTrack(data.id)
  } catch (e) {
    importMessage.value = ''
    tracksError.value = '导入失败：' + e.message
  } finally {
    importing.value = false
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
    stays.value = []
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
    await loadStays(id)
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
    <CesiumGlobe
      ref="globe"
      :points="trackPoints"
      :loop="loop"
      :stay-points="viewMode === 'stay' ? stays : []"
      :hotspots="viewMode === 'hotspot' ? sortedHotspots : []"
      @time-change="onTimeChange"
    />

    <!-- 左上角浮层：标题 + 后端连通性 + 轨迹列表 -->
    <aside class="panel">
      <h1>Calcite<span class="dot" :class="healthDotClass" /></h1>
      <p class="subtitle">Spring Boot 3 + Vue 3 + Cesium + PostGIS</p>

      <!-- 后端连通性：原来是一个 h2 + 4 行列表，光这一块就占 160px，
           面板要塞下两个列表就不够了。压成一行，完整信息放 title 悬浮提示。 -->
      <p v-if="healthError" class="bad health-line">❌ 未连接：{{ healthError }}</p>
      <p v-else-if="health" class="ok health-line" :title="healthTitle">
        {{ health.status }} · {{ pgShort }} · PostGIS {{ postgisShort }}
      </p>
      <p v-else class="muted health-line">检查中…</p>

      <h2>轨迹列表</h2>
      <TrackList
        :tracks="tracks"
        :selected-id="selectedId"
        :loading="tracksLoading"
        :error="tracksError"
        :source-filter="sourceFilter"
        :limit="limit"
        :total="tracksTotal"
        @select="selectTrack"
        @import="importTrack"
        @filter="onFilterChange"
      />

      <p v-if="importing" class="tip">正在导入…</p>
      <p v-else-if="importMessage" class="import-ok">{{ importMessage }}</p>

      <!-- 停留点 / 热点 两档互斥：两者都会往地球上画圈，同时画会糊在一起 -->
      <div class="mode-switch" data-testid="mode-switch">
        <button
          type="button"
          :class="{ on: viewMode === 'stay' }"
          data-testid="mode-stay"
          @click="switchMode('stay')"
        >
          停留点
        </button>
        <button
          type="button"
          :class="{ on: viewMode === 'hotspot' }"
          data-testid="mode-hotspot"
          @click="switchMode('hotspot')"
        >
          热点
        </button>
      </div>

      <template v-if="viewMode === 'stay'">
        <h2>停留点<span v-if="stays.length"> （{{ stays.length }} 处）</span></h2>
        <StayPointList
          :stays="stays"
          :loading="staysLoading"
          :has-track="!!selectedId"
          @focus="focusStay"
        />
      </template>

      <template v-else>
        <h2>热点<span v-if="hotspots.length"> （{{ hotspots.length }} 处）</span></h2>
        <p class="tip">大小 = 停留次数 · 颜色 = 来过的轨迹条数</p>
        <HotspotList
          :hotspots="sortedHotspots"
          :loading="hotspotsLoading"
          :error="hotspotsError"
          :sort-by="hotspotSort"
          @focus="focusHotspot"
          @sort="hotspotSort = $event"
        />
      </template>

      <!-- 状态条：以前飘在左下角，但面板铺满左上角后会被压在面板底下
           （它 z-index 10、面板 20），所以收进面板底部当一行信息 -->
      <div class="status" :class="{ live: trackPoints.length > 0 }">
        <template v-if="detailLoading">正在加载轨迹点…</template>
        <template v-else-if="detail">
          🛰 {{ detail.name }} · {{ detail.points.length }} 个点 ·
          {{ (detail.distanceM / 1000).toFixed(2) }} km
        </template>
        <template v-else>未选择轨迹</template>
      </div>
    </aside>

    <!-- 底部速度/海拔曲线：游标与回放同步，点曲线跳转到那一刻 -->
    <SpeedChart
      v-if="detail && canPlayback"
      :points="trackPoints"
      :current-ms="currentMs"
      :start-ms="startMs"
      :end-ms="endMs"
      @seek="seekTo"
    />

    <!-- 底部回放控制条：选中轨迹后才出现 -->
    <TrackPlayer
      v-if="detail"
      :playing="playing"
      :current-ms="currentMs"
      :start-ms="startMs"
      :end-ms="endMs"
      :loop="loop"
      :disabled="!canPlayback"
      @toggle="togglePlay"
      @seek="seekTo"
      @toggle-loop="toggleLoop"
    />
  </div>
</template>

<style scoped>
.app {
  /* 底部那两块 UI 的高度，面板要停在它们上面。
     集中在这里定义，将来播放条改高度只需要改一个数。 */
  --gap: 12px;
  --chart-h: 133px;
  --player-h: 46px;
  /* 两个列表各自的最小高度，子组件通过 var() 取用。
     矮窗口下由下面的 media query 调小。 */
  --list-min: 88px;
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}

/* 矮窗口（1366×768 的笔记本视口只有 ~660px）：
   副标题属于锦上添花，让位给两个列表 */
@media (max-height: 660px) {
  .app {
    /* 60px 而不是 72px：热点模式比停留点模式多占了「切换开关 + 提示语 +
       排序工具栏」约 17px，72px 的下限会让面板在 600px 高的视口里溢出
       （实测 1600×600 溢出 17px，列表被顶出面板下边界）。
       注意 min-height 只是【地板】—— 有富余空间时 flex:1 仍会把列表撑大，
       所以调小它不会让正常视口下的列表变矮，只是矮窗口下不再溢出。 */
    --list-min: 60px;
  }

  .panel .subtitle {
    display: none;
  }
}

.panel {
  position: absolute;
  top: var(--gap);
  left: var(--gap);
  /* 铺满左上角：用 top + bottom 双向定位，而不是写死 max-height。
     这样面板高度自己跟着视口走，底部那条边永远停在曲线正上方。 */
  bottom: calc(var(--chart-h) + var(--player-h) + var(--gap));
  /* z-index 要高于底部曲线（.chart 是 15），否则面板伸进曲线区域时会被盖住、点不到
     —— 这个坑在浏览器验收时被 Playwright 抓到过 */
  z-index: 20;
  /* 原来固定 320px 太窄：「数据库」这种标签会被挤成两行、PostgreSQL 版本号也折行。
     给到 420px，同时留一个 vw 上限，窄屏上不至于把地球全挡掉。 */
  width: min(420px, 34vw);
  display: flex;
  flex-direction: column;
  /* 兜底：万一内容还是塞不下，宁可裁在面板里，也不许溢出去压住别的 UI
     （这就是之前「停留点滚动条刺出面板框」的成因） */
  overflow: hidden;
  padding: 16px 18px;
  border: 1px solid rgba(127, 209, 255, 0.18);
  border-radius: 10px;
  background: rgba(10, 16, 26, 0.78);
  backdrop-filter: blur(6px);
  font-size: 14px;
  line-height: 1.6;
}

.panel h1 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
  letter-spacing: 1px;
}

/* 标题后面的连通性小圆点 */
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #93a4bb;
}

.dot.ok-dot {
  background: #7ee0a6;
  box-shadow: 0 0 8px rgba(126, 224, 166, 0.8);
}

.dot.bad-dot {
  background: #ff9b9b;
  box-shadow: 0 0 8px rgba(255, 155, 155, 0.8);
}

.panel h2 {
  margin: 12px 0 6px;
  font-size: 13px;
  color: #7fd1ff;
  font-weight: 600;
}

/* 面板里除两个列表以外的内容都不参与伸缩：
   空间不够时只压缩列表，标题和连通性信息不能被压扁 */
.panel > h1,
.panel > h2,
.panel > p,
.panel > .mode-switch,
.panel > div:not(.track-list):not(.stay-list):not(.hotspot-list) {
  flex: 0 0 auto;
}

/* 「停留点 / 热点」两档切换开关。
   必须参与上面那条 flex: 0 0 auto（见选择器列表里的 .mode-switch），
   否则矮窗口下它会被 flex 收缩压成一条细缝，点都点不到。 */
.mode-switch {
  display: flex;
  flex: 0 0 auto;
  margin: 10px 0 0;
  border: 1px solid rgba(127, 209, 255, 0.45);
  border-radius: 6px;
  overflow: hidden;
}

.mode-switch button {
  flex: 1;
  padding: 5px 0;
  border: 0;
  background: transparent;
  color: #93a4bb;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.mode-switch button:hover {
  background: rgba(127, 209, 255, 0.12);
}

.mode-switch button.on {
  background: #7fd1ff;
  color: #0a101a;
  font-weight: 700;
}

/* 连通性压成一行后，别让它撑高 */
.health-line {
  margin: 6px 0 0;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  /* 收进面板底部当一行信息：不再是绝对定位的浮层了 */
  flex: 0 0 auto;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid rgba(127, 209, 255, 0.14);
  color: #93a4bb;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status.live {
  color: #7fd1ff;
}

.import-ok {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: #7ee0a6;
  word-break: break-all;
}
</style>
