<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import {
  Cartesian3,
  ClockRange,
  ClockStep,
  Color,
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
 * 暴露给父组件的三个方法。
 * 父组件通过 ref 调用，例如：globe.value.play()
 */
defineExpose({
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
