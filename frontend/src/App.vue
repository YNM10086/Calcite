<script setup>
import { computed, nextTick, onMounted, ref, shallowRef, watch } from 'vue'
import CesiumGlobe from './components/CesiumGlobe.vue'
import SpeedChart from './components/SpeedChart.vue'
import TrackList from './components/TrackList.vue'
import StayPointList from './components/StayPointList.vue'
import TrackPlayer from './components/TrackPlayer.vue'
import HotspotList from './components/HotspotList.vue'
import DensityLegend from './components/DensityLegend.vue'
import SimilarityList from './components/SimilarityList.vue'
import DataManager from './components/DataManager.vue'
import { canPlay, timeRange } from './lib/playback.js'
import { sortHotspots } from './lib/hotspot.js'
import { pickCellSize, legendMax, HOUR_PRESETS } from './lib/density.js'
import { filterMatches } from './lib/similarity.js'

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
// 'stay' = 看某条轨迹的停留点；'hotspot' = 看全局热点；'density' = 看跨轨迹的网格密度；
// 'similar' = 看"和当前选中轨迹相似的那些轨迹"。
// 四者都会往地球上画画（圈 / 方格 / 线），同时画会糊在一起，所以做成互斥的四档。
const viewMode = ref('stay')
const hotspots = ref([])
const hotspotsLoading = ref(false)
const hotspotsError = ref('')
const hotspotSort = ref('trackCount')

/** 按当前口径排序后的热点（不改动 hotspots 本身） */
const sortedHotspots = computed(() => sortHotspots(hotspots.value, hotspotSort.value))

/** 切换模式：四档（停留点 / 热点 / 密度 / 相似）。只有热点、密度、相似需要懒加载 */
async function switchMode(mode) {
  viewMode.value = mode
  if (mode === 'hotspot') {
    if (hotspots.value.length === 0) await loadHotspots()

    /*
     * ⚠️ 竞态防护：loadHotspots 是异步的（一次网络往返），用户完全可能在等待期间
     * 又点回「停留点」。如果不判这两下，挂起的这次调用恢复后会**照样**执行 fitBounds ——
     * 于是界面在停留点模式（地球上一个热点都不画），相机却飞去了热点区域，
     * 表现为"地球自己飘走了"。
     *
     * 这是最终代码审查抓到的确定性 bug（不依赖时序运气），
     * 而且讽刺的是：这个竞态正是"等 DOM 更新再飞相机"引入的。
     */
    if (viewMode.value !== 'hotspot') return

    // 等 DOM 更新后相机再飞，否则地球可能还没拿到数据
    await nextTick()
    if (viewMode.value !== 'hotspot') return

    // 面板会盖住画布左侧。必须把这个比例告诉地球，否则热点包围盒会被居中，
    // 西边那个热点正好落在面板底下 —— 看起来像"只画出了一个热点"（实测踩过）。
    const panelEl = document.querySelector('.panel')
    const insetLeft = panelEl
      ? panelEl.getBoundingClientRect().right / window.innerWidth
      : 0
    globe.value?.fitBounds(sortedHotspots.value, insetLeft)
    return
  }

  if (mode === 'density') {
    // 等地球把新的 prop 吃到、相机也稳定了，再按视野查
    await nextTick()
    if (viewMode.value !== 'density') return
    await loadDensity()
  }

  /*
   * 第四档「相似」：和密度一样是按需加载，所以只需要在这里【追加】一个分支。
   * 上面三个分支一个字都没动 —— 尤其是那两处 `viewMode.value !== 'xxx'` 的竞态守卫，
   * 它们是上一阶段修掉的确定性 bug（挂起的请求恢复后会错误地飞相机）。
   * 这里同样要守一次：loadSimilarity 有一次网络往返，用户可能在等待期间切走。
   * 注意密度分支结尾没有 return，会落到这里，但 mode 是 'density' 所以不会进这个 if。
   */
  if (mode === 'similar') {
    await nextTick()
    if (viewMode.value !== 'similar') return
    await loadSimilarity()
    return
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

/* ============ 网格密度（跨轨迹）============ */
const densityCells = ref([])
// 字段名必须和接口对得上：后端 DensityResponse.Scanned 是 maxTracks
// （单格里最多的轨迹条数），不是 tracks —— 名字故意带 max，免得被误读成全库轨迹数。
// 这里先给一份全零默认值，接口还没回来时图例上的统计行不会显示 undefined。
const densityScanned = ref({ cells: 0, points: 0, maxTracks: 0 })
const densityLoading = ref(false)
const densityError = ref('')
const densityCellSize = ref(0.002)
const densityMetric = ref('tracks')
const densityHourPreset = ref('')

/** 本批格子的最大值，给 Cesium 做对数色阶归一化 */
const densityMax = computed(() => legendMax(densityCells.value))

/** 防止"相机还在动、上一次请求还没回来"时乱序覆盖：只认最后一次请求 */
let densitySeq = 0

/**
 * 按当前视野查密度。
 *
 * 视野宽度决定格边长（从固定阶梯里挑一档），**只在跨档时才换格子** ——
 * 这样拖动地图时地面上的网格是纹丝不动的。
 */
async function loadDensity() {
  const box = globe.value?.getViewBbox()
  if (!box) return // 视角看太空/含极点 → 跳过这次
  const width = box.east - box.west
  const cell = pickCellSize(width, 80)

  const preset = HOUR_PRESETS.find((p) => p.value === densityHourPreset.value)
  const params = new URLSearchParams()
  params.set('bbox', [box.west, box.south, box.east, box.north].join(','))
  params.set('cellSize', String(cell))
  params.set('metric', densityMetric.value)
  if (preset && preset.hourFrom != null) {
    params.set('hourFrom', String(preset.hourFrom))
    params.set('hourTo', String(preset.hourTo))
  }

  const mine = ++densitySeq
  densityLoading.value = true
  densityError.value = ''
  try {
    const res = await fetch('/api/analysis/density?' + params.toString())
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    if (mine !== densitySeq) return // 已经有更新的请求了，丢弃这次结果
    densityCells.value = data.cells ?? []
    densityScanned.value = data.scanned ?? { cells: 0, points: 0, maxTracks: 0 }
    densityCellSize.value = data.cellSize ?? cell
  } catch (e) {
    if (mine !== densitySeq) return
    densityCells.value = []
    densityError.value = '密度加载失败：' + e.message
  } finally {
    // 只有最后一次请求才有资格关掉 loading，否则先发的请求回来就把转圈灭了
    if (mine === densitySeq) densityLoading.value = false
  }
}

/** 相机停稳后（App 里绑到 CesiumGlobe 的 camera-move-end 事件上） */
let densityTimer = null
function onCameraMoveEnd() {
  // 非密度档时相机事件是别的模式（比如热点 fitBounds）引起的，不该触发密度请求
  if (viewMode.value !== 'density') return
  // 相机停稳后还会抖一下，稍等片刻再查，避免连续拖动时打出一串请求
  clearTimeout(densityTimer)
  densityTimer = setTimeout(loadDensity, 400)
}

/** 用户换了口径 → 必须重新查：格子里的 value 是后端按 metric 选出来的那个字段 */
function onDensityMetric(m) {
  densityMetric.value = m
  loadDensity()
}

/** 用户换了时段 → 必须重新查（筛选是在 SQL 里做的，前端没有全量数据） */
function onDensityHour(v) {
  densityHourPreset.value = v
  loadDensity()
}

/* ============ 轨迹相似度（第四档）============ */
const similarityMatches = ref([])
/** 主线的元信息（name / pointCount / lengthM / compared / toleranceM），给列表当"分母"用 */
const similarityInfo = ref({})
const similarityLoading = ref(false)
const similarityError = ref('')
/**
 * 当前筛选档位（最低相似度）。
 *
 * ⚠️ 必须是 50 —— `SimilarityList` 的 `filter` prop 默认就是 50，
 * `<select>` 靠 `:value="filter"` 反查该选中哪一项。两边对不上时浏览器找不到匹配的
 * option，会渲染成**空白选中项**（下拉看着像没选，其实筛的是 50）。
 */
const similarityFilter = ref(50)

/** 防止"切轨迹时旧请求后回来盖掉新结果"——和热点/密度那套同一个问题 */
let similaritySeq = 0

/**
 * 主线的点（给地球画那条亮蓝粗线用）。
 *
 * 直接复用 `trackPoints`：它已经是**当前选中轨迹**的点，字段名就是地球要的
 * `{ lon, lat, elevationM }`，坐标转换在地球组件内部做，这里不必再转一次。
 */
const similarityBaselinePoints = computed(() => trackPoints.value)

/** 面板标题上要显示的条数（列表内部也会筛，这里只为统计） */
const similarityShownCount = computed(
  () => filterMatches(similarityMatches.value, similarityFilter.value).length,
)

/**
 * 地球上要叠画的匹配轨迹（只取前 N 条）。
 *
 * 为什么只画 10 条：再多在屏幕上也分不清哪条是哪条，反而把主线埋掉。
 */
const SIM_DRAW_TOP = 10
const similarityTracks = ref([])

/**
 * 取前 N 条匹配轨迹的点，给地球叠画用。
 *
 * 为什么要逐条取：`/api/analysis/similarity` 只返回**元数据**（相似度、长度、日期），
 * 不返回几何 —— 那是刻意的，否则一次响应要带上十几条轨迹的全部点。
 * 轨迹的点在 `GET /api/tracks/{id}` 里（返回 `TrackDetail`，含 `points` 字段）。
 */
async function loadSimilarityTracks(matches, seq) {
  const top = matches.slice(0, SIM_DRAW_TOP)
  const loaded = await Promise.all(top.map(async (m) => {
    try {
      const res = await fetch(`/api/tracks/${m.trackId}`)
      if (!res.ok) return null
      const d = await res.json()
      return { trackId: m.trackId, similarity: m.similarity, points: d.points ?? [] }
    } catch {
      return null            // 单条失败不影响其它条
    }
  }))
  if (seq !== similaritySeq) return          // 用户已经切走了，丢弃这批结果
  similarityTracks.value = loaded.filter(Boolean)
}

/**
 * 查相似度。主线就是**当前选中的轨迹**（本文件里那个变量叫 `selectedId`）。
 */
async function loadSimilarity() {
  const id = selectedId.value
  if (id == null) {
    /*
     * 没有主线 = 这一档什么都不该画。
     *
     * ⚠️ 同时要把 seq 推进一格：上一次请求（以及它拉点的 loadSimilarityTracks）
     * 可能还在路上，不推进的话它们回来时 `seq === similaritySeq` 依然成立，
     * 会把**上一条轨迹**的红线又画回地球 —— 表现为"取消选中后红线赖着不走"。
     */
    similaritySeq++
    similarityMatches.value = []
    similarityTracks.value = []
    similarityInfo.value = {}
    similarityError.value = ''
    similarityLoading.value = false
    return
  }

  const mine = ++similaritySeq
  similarityLoading.value = true
  similarityError.value = ''
  try {
    const res = await fetch(`/api/analysis/similarity?trackId=${id}&limit=200`)
    if (res.status === 404) throw new Error('这条轨迹不存在')
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    if (mine !== similaritySeq) return          // 已经有更新的请求了，丢弃
    similarityMatches.value = data.matches ?? []
    // 顺手把前 10 条的点也取回来给地球叠画（不阻塞列表显示，所以不 await）
    loadSimilarityTracks(similarityMatches.value, mine)
    similarityInfo.value = {
      name: data.name,
      pointCount: data.pointCount,
      lengthM: data.lengthM,
      compared: data.compared,
      toleranceM: data.toleranceM,
    }
  } catch (e) {
    if (mine !== similaritySeq) return
    similarityMatches.value = []
    // 出错时地球上的红线也必须清掉，否则会留下上一次查询的"幽灵轨迹"
    similarityTracks.value = []
    similarityError.value = '相似度查询失败：' + e.message
  } finally {
    if (mine === similaritySeq) similarityLoading.value = false
  }
}

/** 点列表里的一条 → 相机飞过去（复用地球暴露的 focusOn） */
async function focusSimilar(trackId) {
  let target = similarityTracks.value.find((t) => t.trackId === trackId)
  /*
   * 地球上只叠画了前 10 条（SIM_DRAW_TOP），点第 11 条及以后这里会找不到。
   * 直接 return 的话那些条目就是"点了没反应"的死条，所以缺哪条就单独去取一次。
   * 单次点击一次请求，代价可以接受。
   */
  if (!target) {
    try {
      const res = await fetch(`/api/tracks/${trackId}`)
      if (!res.ok) return
      const d = await res.json()
      target = { trackId, similarity: 0, points: d.points ?? [] }
    } catch {
      return
    }
  }
  if (!target.points || target.points.length === 0) return
  // 用轨迹中点（而不是起点）当目标：飞过去之后两边都能看在眼里
  const mid = target.points[Math.floor(target.points.length / 2)]
  globe.value?.focusOn(mid.lon, mid.lat, 500)
}

/* ============ 数据编辑视图 ============ */
/*
 * 面板有两个视图：
 *   'analysis' = 原来的四档分析（停留点 / 热点 / 密度 / 相似）
 *   'manage'   = 数据编辑（添加 / 替换 / 改名 / 删除）
 * 管理视图**不属于任何分析档**，所以它是整块替换（连四档切换那条一起换掉），
 * 而不是在某个档下面展开一块 —— 那样用户会以为"数据编辑"是第五个分析档。
 */
const panelView = ref('analysis')

function openDataManager() {
  panelView.value = 'manage'
}

function backToAnalysis() {
  panelView.value = 'analysis'
  // 回到分析视图时清空四档的本地状态 —— 管理视图里可能改过数据（见下）
  resetAnalysisState()
}

/**
 * 数据被改过（删除 / 改名 / 替换 / 新增）之后的统一刷新。
 *
 * ⚠️ 一条规则：**数据一改，四个分析功能的结果全部失效** —— 因为它们全都基于全库数据。
 * 后端那边的缓存已经在改的时候清了（StayPointCache / SimilarityCache），
 * 这里要清的是【前端已经拿到的旧结果】，否则切回分析档看到的还是改动前的数字。
 *
 * 为什么不"只清被改的那一条"：四个档里除了"停留点"以外都是跨轨迹的
 * （热点 / 密度 / 相似度全都要拿全库去比），改任何一条都可能影响别人 —— 宁可全清。
 */
function resetAnalysisState() {
  stays.value = []
  hotspots.value = []
  densityCells.value = []
  similarityMatches.value = []
  similarityTracks.value = []
  // 相似度的"分母"元信息（主线名字 / 比过多少条）也是旧数据，一并清掉
  similarityInfo.value = {}

  // 当前选中的轨迹可能已经被删了 —— 清掉选中，并切回「停留点」档。
  // 不清的话地球还画着一条已经不存在的轨迹、面板还写着它的名字（Review Focus 第 1 条）。
  if (selectedId.value != null && !tracks.value.some((t) => t.id === selectedId.value)) {
    selectedId.value = null
    detail.value = null
    viewMode.value = 'stay'
  }
  loadTracks()
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
    // 相似档下取消选中：主线没了，叠画的匹配轨迹也必须跟着清掉
    if (viewMode.value === 'similar') await loadSimilarity()
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

  /*
   * 相似档下换了主线（第四档的主线 = 当前选中的轨迹）必须重查。
   *
   * ⚠️ 位置放在点加载【之后】（try/finally 之外）：
   * 地球画主线靠的是 trackPoints ← detail.points，点还没到就查的话，
   * 匹配轨迹会先画出来、主线却还是空的，看起来像"只画了红线"。
   * 放在 finally 之后还有个好处：加载失败时 selectedId 已被清空，
   * 这里的 loadSimilarity() 会走"没有主线"分支，把上一次的红线一并清掉。
   */
  if (viewMode.value === 'similar') await loadSimilarity()
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
      :density-cells="viewMode === 'density' ? densityCells : []"
      :density-max="densityMax"
      :density-cell-size="densityCellSize"
      :similar-baseline="viewMode === 'similar' && similarityBaselinePoints.length
        ? { points: similarityBaselinePoints } : null"
      :similar-tracks="viewMode === 'similar' ? similarityTracks : []"
      @time-change="onTimeChange"
      @camera-move-end="onCameraMoveEnd"
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

      <h2 v-if="panelView === 'analysis'">轨迹列表</h2>
      <TrackList
        v-if="panelView === 'analysis'"
        :tracks="tracks"
        :selected-id="selectedId"
        :loading="tracksLoading"
        :error="tracksError"
        :source-filter="sourceFilter"
        :limit="limit"
        :total="tracksTotal"
        @select="selectTrack"
        @open-data-manager="openDataManager"
        @filter="onFilterChange"
      />

      <!-- 数据编辑视图：整块替换四档分析区（连下面那条四档切换一起换掉），
           因为管理视图不属于任何分析档。
           @changed = 数据被改过了 → 清掉四个分析档的旧结果并重新拉列表。
           @focus  = 点某一行 → 地球飞过去（知道自己在删哪条） -->
      <DataManager
        v-else
        :tracks="tracks"
        :total="tracksTotal"
        :selected-id="selectedId"
        :loading="tracksLoading"
        :error="tracksError"
        :source-filter="sourceFilter"
        :limit="limit"
        @back="backToAnalysis"
        @changed="resetAnalysisState"
        @filter="onFilterChange"
        @focus="selectTrack"
      />

      <!-- 四档分析区：管理视图下整块不渲染。
           ⚠️ 这三处 `panelView === 'analysis'` 必须一起加 ——
           最后一档原来是 `v-else`，而 `v-else` 在前面条件全不成立时也会渲染，
           漏掉它会让管理视图底下又多出一个「相似」面板。
           （没有用一个 <template> 包起来，是为了不动这 90 行原有的缩进。） -->
      <!-- 停留点 / 热点 / 密度 / 相似 四档互斥：四者都会往地球上画画（圈 / 方格 / 线），
           同时画会糊在一起 -->
      <div v-if="panelView === 'analysis'" class="mode-switch" data-testid="mode-switch">
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
        <button
          type="button"
          :class="{ on: viewMode === 'density' }"
          data-testid="mode-density"
          @click="switchMode('density')"
        >
          密度
        </button>
        <button
          type="button"
          :class="{ on: viewMode === 'similar' }"
          data-testid="mode-similar"
          @click="switchMode('similar')"
        >
          相似
        </button>
      </div>

      <template v-if="panelView === 'analysis' && viewMode === 'stay'">
        <h2>停留点<span v-if="stays.length"> （{{ stays.length }} 处）</span></h2>
        <StayPointList
          :stays="stays"
          :loading="staysLoading"
          :has-track="!!selectedId"
          @focus="focusStay"
        />
      </template>

      <template v-else-if="viewMode === 'hotspot'">
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

      <template v-else-if="viewMode === 'density'">
        <h2>密度<span v-if="densityCells.length"> （{{ densityCells.length }} 格）</span></h2>
        <p class="tip">颜色越红 = 这个格子里经过的轨迹越多</p>
        <DensityLegend
          :cells="densityCells"
          :loading="densityLoading"
          :error="densityError"
          :scanned="densityScanned"
          :cell-size="densityCellSize"
          :metric="densityMetric"
          :hour-preset="densityHourPreset"
          @metric="onDensityMetric"
          @hour="onDensityHour"
        />
      </template>

      <template v-else-if="viewMode === 'similar'">
        <h2>相似<span v-if="similarityMatches.length"> （{{ similarityShownCount }} 条）</span></h2>
        <p class="tip">越红 = 和主线重合得越多 · 主线是蓝色那条</p>
        <p v-if="selectedId == null" class="tip" data-testid="similarity-need-track">
          先在左边选一条轨迹，才能找和它相似的
        </p>
        <SimilarityList
          v-else
          :matches="similarityMatches"
          :baseline="similarityInfo"
          :loading="similarityLoading"
          :error="similarityError"
          :filter="similarityFilter"
          @filter="similarityFilter = $event"
          @focus="focusSimilar"
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

/* 面板里除列表以外的内容都不参与伸缩：
   空间不够时只压缩列表，标题和连通性信息不能被压扁。
   ⚠️ 每新增一个"要自己滚动的列表"都必须加进 :not(...)，否则它会被当成固定内容
   —— flex: 0 0 auto 下矮窗口里列表不滚动、直接被面板的 overflow:hidden 裁掉。
   .similarity-list 是第四档的列表，同一条规矩；
   .data-manager 是数据编辑视图（它自己内部还有一层 .rows 在滚动）。 */
.panel > h1,
.panel > h2,
.panel > p,
.panel > .mode-switch,
.panel > div:not(.track-list):not(.stay-list):not(.hotspot-list):not(.density-legend):not(.similarity-list):not(.data-manager) {
  flex: 0 0 auto;
}

/* 「停留点 / 热点 / 密度 / 相似」四档切换开关。
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
</style>
