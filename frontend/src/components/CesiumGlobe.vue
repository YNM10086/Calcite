<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import {
  Cartesian3,
  ClockRange,
  ClockStep,
  Color,
  HeightReference,
  ImageryLayer,
  JulianDate,
  Rectangle,
  SampledPositionProperty,
  TileMapServiceImageryProvider,
  VERSION,
  Viewer,
  buildModuleUrl,
} from 'cesium'
import { computeMultiplier, timeRange } from '../lib/playback.js'
// 热点的「大小 / 颜色」判断全在这个纯函数模块里，组件只负责画
import { hotspotColor, hotspotPixelSize } from '../lib/hotspot.js'
// Cesium 自带的控件样式，必须引入，否则地球上的控件会散架
import 'cesium/Build/Cesium/Widgets/widgets.css'

/**
 * 三维地球。父组件通过 :points 传轨迹点进来，这个组件负责把它们画成线，
 * 并在有完整时间信息时，用 Cesium 的时钟驱动一个白色标记沿轨迹移动。
 *
 * 数据方向始终是「父 → 子」，地球自己不请求接口，
 * 这样"谁在加载数据"永远只有一个地方（App.vue），出问题好定位。
 */
const props = defineProps({
  // 轨迹点数组：[{ seq, recordedAt, lon, lat, elevationM, speedMps }, ...]
  points: { type: Array, default: () => [] },
  // 循环开关：播到终点跳回起点（true）还是停在终点（false）
  loop: { type: Boolean, default: true },
  // 停留点数组（StayPointDto 列表）
  stayPoints: { type: Array, default: () => [] },
  // 热点列表（跨轨迹聚类的结果）。和 stayPoints 一样是「给数据就画，不给就不画」
  hotspots: { type: Array, default: () => [] },
})

// 往外报当前时刻（毫秒时间戳），App 用它更新播放条
const emit = defineEmits(['time-change'])

// 地球容器：Cesium 会接管这个 div
const container = ref(null)
// 用 shallowRef：Viewer 是庞大的非响应式对象，不能让 Vue 深度代理它
const viewer = shallowRef(null)
const ready = ref(false)
const message = ref('正在初始化 Cesium…')

// 给实体固定 id，方便重复绘制时先删旧的（否则会越画越多）
const LINE_ID = 'calcite-track-line'
const START_ID = 'calcite-track-start'
const END_ID = 'calcite-track-end'
const MOVER_ID = 'calcite-track-mover' // 沿轨迹移动的白色标记

// 停留圆圈的数量不固定（一条轨迹可能有好几段停留），所以用数组记着，
// 重画时逐个删掉 —— 不能用固定 id
let stayEntities = []

// 同理：热点的数量也不固定，而且和 stayEntities 分开存 ——
// 两者生命周期不同（可能只画热点不画停留点），混在一个数组里会互相误删
let hotspotEntities = []

// 时刻往外发的节流：最多每 100ms 一次，避免每帧都触发父组件重渲染
let lastEmitMs = 0
// Cesium 的 addEventListener 会返回移除函数，卸载时要调
let removeTickListener = null

/** 清掉上一条轨迹 */
function clearTrack() {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  for (const id of [LINE_ID, START_ID, END_ID, MOVER_ID]) {
    const entity = v.entities.getById(id)
    if (entity) v.entities.remove(entity)
  }
  for (const e of stayEntities) v.entities.remove(e)
  stayEntities = []
  // ⚠️ 这里【故意不清】hotspotEntities。
  //
  // clearTrack() 是由「轨迹点变了」触发的（drawTrack → clearTrack），而热点是
  // 【跨轨迹】的全局结果、不属于任何一条轨迹。如果在热点模式下点另一条轨迹：
  // points 变了、hotspots 的引用却没变 —— 热点会被清掉但它的 watcher 不触发、
  // 于是不会重画，表现为"热点凭空消失"。
  //
  // 热点的清理统一由 drawHotspots() 自己负责（它开头就清一遍）；
  // 切出热点模式时 App 会传空数组进来，watcher 触发 → 清空。
}

/**
 * 画停留点。
 *
 * 每段停留画一个半透明圆 —— 圆的半径就是那段的「活动半径」，
 * 所以圆的大小直接表示"当时活动范围多大"。
 * 颜色深浅表示停留时长：停得越久越浓。
 */
function drawStayPoints(stays) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return

  for (const e of stayEntities) v.entities.remove(e)
  stayEntities = []
  if (!stays || stays.length === 0) return

  // 用最长的那个停留做归一化，映射颜色深浅
  const maxDur = Math.max(...stays.map((s) => s.durationS || 0), 1)

  for (const s of stays) {
    // 半径至少给一点，否则完全静止的停留会小到看不见
    const radius = Math.max(s.radiusM || 0, 3)
    const ratio = Math.min(1, (s.durationS || 0) / maxDur)
    // 短的浅（alpha .15），长的浓（alpha .55）
    const alpha = 0.15 + 0.4 * ratio

    const entity = v.entities.add({
      position: Cartesian3.fromDegrees(s.lon, s.lat),
      ellipse: {
        // Cesium 的 ellipse 半径单位就是米，不用换算
        semiMajorAxis: radius,
        semiMinorAxis: radius,
        material: Color.ORANGE.withAlpha(alpha),
        outline: true,
        outlineColor: Color.ORANGE.withAlpha(0.9),
        outlineWidth: 2,
        height: 0,
      },
    })
    stayEntities.push(entity)
  }
}

/**
 * 画热点。
 *
 * 和停留点不一样：热点不是一块有明确边界的区域，所以**不画地理半径**，
 * 而是画一个屏幕像素大小的点标记 —— 否则最小的热点（真实散布只有 9.4 米）
 * 在城市尺度下根本看不见。
 *
 * 两个视觉通道各管一个维度，互不干扰：
 *   - 大小（pixelSize） ← visitCount  来过几次
 *   - 颜色（color）     ← trackCount  几条不同轨迹
 */
function drawHotspots(hotspots) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return

  for (const e of hotspotEntities) v.entities.remove(e)
  hotspotEntities = []
  if (!hotspots || hotspots.length === 0) return

  for (const h of hotspots) {
    const entity = v.entities.add({
      position: Cartesian3.fromDegrees(h.centerLon, h.centerLat),
      point: {
        // pixelSize 的单位就是屏幕像素，不做任何米/像素换算
        pixelSize: hotspotPixelSize(h.visitCount),
        color: Color.fromCssColorString(hotspotColor(h.trackCount)).withAlpha(0.75),
        outlineColor: Color.fromCssColorString(hotspotColor(h.trackCount)),
        outlineWidth: 2,
        // 贴地 + 不测深度，保证热点不会被地形或地球背面吞掉
        heightReference: HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    })
    hotspotEntities.push(entity)
  }
}

/**
 * 把轨迹点画到地球上
 * @param {Array} points 轨迹点
 */
function drawTrack(points) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return

  clearTrack()
  // 少于 2 个点连不成线
  if (!points || points.length < 2) return

  // 经纬度 → Cesium 的三维直角坐标。fromDegrees 内部会把经纬度投影到椭球体上
  const positions = points.map((p) =>
    Cartesian3.fromDegrees(p.lon, p.lat, p.elevationM ?? 0),
  )

  // 1) 轨迹线本体
  v.entities.add({
    id: LINE_ID,
    polyline: {
      positions,
      width: 5,
      // 不贴地：示例数据本身带高程，悬空画更稳，也不会被地形起伏吃掉
      clampToGround: false,
      material: Color.fromCssColorString('#7fd1ff'),
    },
  })

  // 2) 起点（绿）和终点（红），一眼看出行进方向
  v.entities.add({
    id: START_ID,
    position: positions[0],
    point: {
      pixelSize: 11,
      color: Color.fromCssColorString('#7ee0a6'),
      outlineColor: Color.fromCssColorString('#0a101a'),
      outlineWidth: 2,
    },
  })
  v.entities.add({
    id: END_ID,
    position: positions[positions.length - 1],
    point: {
      pixelSize: 11,
      color: Color.fromCssColorString('#ff9b9b'),
      outlineColor: Color.fromCssColorString('#0a101a'),
      outlineWidth: 2,
    },
  })

  // 3) 移动标记：位置不是固定值，而是"按时间查表"的属性。
  //    Cesium 每帧会根据当前时刻自动插值出经纬度，所以拖动进度条时不需要重建任何实体。
  const range = timeRange(points)
  if (range) {
    const positionProperty = new SampledPositionProperty()
    points.forEach((p) => {
      positionProperty.addSample(
        JulianDate.fromIso8601(p.recordedAt),
        Cartesian3.fromDegrees(p.lon, p.lat, p.elevationM ?? 0),
      )
    })

    v.entities.add({
      id: MOVER_ID,
      position: positionProperty,
      point: {
        pixelSize: 12,
        color: Color.WHITE,
        outlineColor: Color.fromCssColorString('#0a101a'),
        outlineWidth: 2,
      },
    })

    // 4) 配置时钟：范围 = 轨迹的时间范围，倍速 = 让整条轨迹约 60 秒播完
    const clock = v.clock
    clock.startTime = JulianDate.fromDate(new Date(range.startMs))
    clock.stopTime = JulianDate.fromDate(new Date(range.endMs))
    clock.currentTime = JulianDate.clone(clock.startTime)
    clock.clockStep = ClockStep.SYSTEM_CLOCK_MULTIPLIER
    clock.multiplier = computeMultiplier(range.startMs, range.endMs)
    clock.clockRange = props.loop ? ClockRange.LOOP_STOP : ClockRange.CLAMPED
    clock.shouldAnimate = false // 默认暂停，等用户点播放
  }
  // 时间信息不全（range 为 null）时只画线不建移动点，App 会把播放条置灰。
  // 注意这里用 if 包起来而不是 return——相机还是要飞到这条轨迹上。

  // 5) 相机飞到这条轨迹上方：先算经纬度极值得到包围盒，再交给 Cesium 自动定高度
  const lons = points.map((p) => p.lon)
  const lats = points.map((p) => p.lat)
  const padding = 0.01 // 单位是度，约 1.1 km，让线别贴着屏幕边缘
  v.camera.flyTo({
    destination: Rectangle.fromDegrees(
      Math.min(...lons) - padding,
      Math.min(...lats) - padding,
      Math.max(...lons) + padding,
      Math.max(...lats) + padding,
    ),
    duration: 1.5,
  })
}

// 父组件换了一条轨迹 → 先停表，再重画（drawTrack 内部会把时钟重置到起点）
watch(
  () => props.points,
  (points) => {
    const v = viewer.value
    if (v && !v.isDestroyed()) v.clock.shouldAnimate = false
    drawTrack(points)
  },
)

// 循环开关变化 → 只改时钟的取值方式，不用重画
watch(
  () => props.loop,
  (on) => {
    const v = viewer.value
    if (!v || v.isDestroyed()) return
    v.clock.clockRange = on ? ClockRange.LOOP_STOP : ClockRange.CLAMPED
  },
)

// 停留点变化 → 重画圆圈
watch(
  () => props.stayPoints,
  (stays) => {
    if (ready.value) drawStayPoints(stays)
  },
  { deep: true },
)

// 热点变化 → 重画点标记
watch(
  () => props.hotspots,
  (hotspots) => {
    if (ready.value) drawHotspots(hotspots)
  },
  { deep: true },
)

onMounted(() => {
  // 1) 底图：Cesium 自带的离线世界地图 NaturalEarthII
  //    不需要联网、不需要任何 access token，打开就有画面
  const baseLayer = ImageryLayer.fromProviderAsync(
    TileMapServiceImageryProvider.fromUrl(
      buildModuleUrl('Assets/Textures/NaturalEarthII'),
    ),
  )

  // 2) 创建 Viewer。关掉所有用不到的控件，只留地球本身
  const v = new Viewer(container.value, {
    baseLayer,
    baseLayerPicker: false, // 用 baseLayer 时必须关掉
    geocoder: false, // 地址搜索（依赖 Cesium ion）
    homeButton: false,
    sceneModePicker: false, // 2D/3D 切换
    navigationHelpButton: false,
    animation: false, // 左下角时钟
    timeline: false, // 底部时间轴（我们自己做了播放条，用不上 Cesium 自带的）
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
  })

  // 3) 初始视角：从高空俯视北京（后面 GeoLife 轨迹数据就在这一带）
  v.camera.setView({
    destination: Cartesian3.fromDegrees(116.4, 39.9, 12000000),
  })

  viewer.value = v
  ready.value = true
  message.value = `Cesium ${VERSION} 已就绪`

  // 时钟每帧都会 tick，我们只按节流往外报，避免父组件每帧重渲染
  removeTickListener = v.clock.onTick.addEventListener(() => {
    const now = Date.now()
    if (now - lastEmitMs < 100) return
    lastEmitMs = now
    emit('time-change', JulianDate.toDate(v.clock.currentTime).getTime())
  })

  // 万一父组件在挂载前就已经有点了，补画一次
  drawTrack(props.points)
  drawStayPoints(props.stayPoints)
  drawHotspots(props.hotspots)
})

onBeforeUnmount(() => {
  // 释放 WebGL 资源，否则热更新时会不断泄漏
  if (removeTickListener) {
    removeTickListener()
    removeTickListener = null
  }
  if (viewer.value && !viewer.value.isDestroyed()) viewer.value.destroy()
  viewer.value = null
})

/**
 * 把相机飞到某个点（停留点列表点击时用）。
 *
 * 为什么写成局部函数而不是 defineExpose 里的内联方法：
 * fitBounds 需要在内部按名字调用它，而对象字面量里的方法不是局部作用域里的函数，
 * 内联写会让 fitBounds 里报 focusOn is not defined。
 *
 * @param {number} lon 经度
 * @param {number} lat 纬度
 * @param {number} radiusM 停留的活动半径，用来决定飞多高
 */
function focusOn(lon, lat, radiusM) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  // 半径越大飞得越高；至少 600 米，不然贴着地面看不清周围
  const height = Math.max(600, (radiusM || 0) * 25)
  v.camera.flyTo({
    destination: Cartesian3.fromDegrees(lon, lat, height),
    duration: 1.0,
  })
}

/**
 * 把相机飞到能装下所有热点的位置（进入热点模式时用）。
 * 只有一个热点时退化成 focusOn。
 *
 * @param {Array}  items     热点列表
 * @param {number} insetLeft 画面左侧被浮层（面板）遮住的比例，0~0.5
 *
 * ⚠️ `insetLeft` 必须传，不能省。原因是实测踩到的：
 * Cesium 的 flyTo 会把矩形**居中**铺满整个画布，但左侧 432px 被面板盖着，
 * 于是西边那个热点正好落在面板底下 —— 看着像"只画出了一个热点"。
 * 把遮挡比例算进去，让包围盒只占右边没被遮的那一段。
 */
function fitBounds(items, insetLeft = 0) {
  const v = viewer.value
  if (!v || v.isDestroyed() || !items || items.length === 0) return

  if (items.length === 1) {
    focusOn(items[0].centerLon, items[0].centerLat, 300)
    return
  }

  let west = Math.min(...items.map((h) => h.centerLon))
  let east = Math.max(...items.map((h) => h.centerLon))
  let south = Math.min(...items.map((h) => h.centerLat))
  let north = Math.max(...items.map((h) => h.centerLat))

  // 纵向直接留 25% 余量
  const padLat = (north - south) * 0.25 || 0.002
  south -= padLat
  north += padLat

  // 横向：让包围盒只落在画面右边的 [p+margin, 1-margin] 这一段里。
  //   viewSpan = span / band            视野跨度要放大，才能把 span 塞进 band
  //   westEdge = west0 - (p+margin)*viewSpan
  //
  // 左侧为什么要额外加一个 margin：如果只按 p 算，最西边那个热点的【圆心】会正好
  // 落在面板边缘上，于是半个圆被面板压住。加了 margin 它的圆心才会退到面板右边。
  const p = Math.min(Math.max(insetLeft, 0), 0.5)
  const margin = 0.05
  const band = Math.max(0.2, 1 - p - 2 * margin)
  const span = (east - west) || 0.002
  const viewSpan = span / band
  const westEdge = west - (p + margin) * viewSpan
  west = westEdge
  east = westEdge + viewSpan

  v.camera.flyTo({
    destination: Rectangle.fromDegrees(west, south, east, north),
    duration: 1.2,
  })
}

/**
 * 暴露给父组件的五个方法。
 * 父组件通过 ref 调用，例如：globe.value.play()
 */
defineExpose({
  focusOn,
  /** 飞到能装下所有热点的位置 */
  fitBounds,
  /** 开始播放 */
  play() {
    const v = viewer.value
    if (!v || v.isDestroyed()) return
    v.clock.shouldAnimate = true
  },
  /** 暂停 */
  pause() {
    const v = viewer.value
    if (!v || v.isDestroyed()) return
    v.clock.shouldAnimate = false
  },
  /**
   * 跳到某个时刻。
   * 只改 clock.currentTime，不动任何实体——这是拖动进度条不卡的关键。
   * @param {number} ms 毫秒时间戳
   */
  seekTo(ms) {
    const v = viewer.value
    if (!v || v.isDestroyed()) return
    v.clock.currentTime = JulianDate.fromDate(new Date(ms))
    lastEmitMs = 0 // 拖动要立刻反馈，不等下一次节流窗口
    emit('time-change', ms)
  },
})
</script>

<template>
  <div class="globe">
    <div ref="container" class="globe-canvas"></div>
    <p v-if="!ready" class="globe-status">{{ message }}</p>
  </div>
</template>

<style scoped>
.globe {
  position: absolute;
  inset: 0;
}

.globe-canvas {
  width: 100%;
  height: 100%;
}

.globe-status {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  margin: 0;
  color: #93a4bb;
  pointer-events: none;
}

/* 隐藏左下角的数据版权栏，演示时画面更干净 */
.globe :deep(.cesium-widget-credits) {
  display: none;
}
</style>
