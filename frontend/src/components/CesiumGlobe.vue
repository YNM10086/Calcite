<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import {
  Cartesian3,
  Cartographic,
  ClockRange,
  ClockStep,
  Color,
  HeightReference,
  ImageryLayer,
  JulianDate,
  // Cesium 的 Math 别名：相机包围盒给的是弧度，往外传要换成度
  Math as CesiumMath,
  PolygonHierarchy,
  Rectangle,
  SampledPositionProperty,
  // 圈选的鼠标事件：Cesium 的输入不是 Vue 事件，必须自己注册、自己注销
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  TileMapServiceImageryProvider,
  VERSION,
  Viewer,
  buildModuleUrl,
} from 'cesium'
import { computeMultiplier, timeRange } from '../lib/playback.js'
// 热点的「大小 / 颜色」判断全在这个纯函数模块里，组件只负责画
import { hotspotColor, hotspotPixelSize } from '../lib/hotspot.js'
// 密度格子的「矩形 / 色阶」同样是纯函数，组件不自己算
import { cellRect, densityRatio, rampColor } from '../lib/density.js'
// 相似度的「颜色」同样是纯函数，组件不自己算
import { simColor } from '../lib/similarity.js'
// 圈选区域的轮廓：把后端回显的 GeoJSON 取成最外环。同样是纯函数，组件不自己算
import { ringOf } from '../lib/region.js'
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
  // 网格密度的格子（跨轨迹的全局结果）。传空数组时什么都不画
  densityCells: { type: Array, default: () => [] },
  // 本批格子的最大值，用来做对数色阶归一化
  densityMax: { type: Number, default: 1 },
  // 格边长（度），用来算每个格子的矩形
  densityCellSize: { type: Number, default: 0.002 },
  // 相似档：主线（单独画，要醒目）+ 匹配到的轨迹（按相似度上色）
  similarBaseline: { type: Object, default: null },
  similarTracks: { type: Array, default: () => [] },
  // 圈选档：后端回显的区域几何（GeoJSON Polygon / MultiPolygon）。null = 不画
  region: { type: Object, default: null },
  // 圈选档：命中轨迹，已经由 App 切成最多 DRAW_LIMIT 条 —— 地球不再自己截断。
  // 元素形状：{ trackId, points: [{ lon, lat }, ...], selected?: true }
  //   selected === true（App 在结果列表里点了某一条时传）→ 亮蓝 #7fd1ff、width 3，与其余橙线区分
  //   —— 这就是规格 6.4.2 的"点某一条 → 把它补画上去并高亮"，缺了它这个语义在本组件里表达不出来
  withinTracks: { type: Array, default: () => [] },
  // 绘制模式：idle | rect | polygon | buffer。
  // 只认这个 prop、自己不切状态：ESC / 切档 / 取消三条退出路径都由 App 收口，
  // 否则"地球以为还在画、App 以为已经结束"这种状态分叉迟早出现
  drawingMode: { type: String, default: 'idle' },
})

// 往外报当前时刻（毫秒时间戳），App 用它更新播放条；
// camera-move-end 是把 Cesium 的相机事件转出来的（见 onMounted），
// App 靠它决定"相机停稳了，按新视野重新查密度"
//
// draw-* 三个是绘制模式的结果（App 收到后就发起查询、并把 drawingMode 收回 idle）：
//   draw-rect    { west, south, east, north }
//   draw-polygon [{ lon, lat }, ...]
//   draw-buffer  { lon, lat }
const emit = defineEmits([
  'time-change',
  'camera-move-end',
  'draw-rect',
  'draw-polygon',
  'draw-buffer',
])

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

// 同理：密度格子也单独存。它同样是「跨轨迹」的全局结果，
// 所以和热点一样不能被 clearTrack() 清掉（理由见下面的 drawDensity）
let densityEntities = []

// 同理：相似轨迹（主线 + 匹配到的）也单独存。它同样是「跨轨迹」的结果
// （"当前这条 vs 别的轨迹"），所以也不进 clearTrack() 的清理范围 —— 见 drawSimilarity()
let similarEntities = []

// 相机停稳的回调。Cesium 的 addEventListener 不是自动回收的，
// 销毁组件时必须手动移除，否则 Cesium 会一直持有这个闭包
let cameraMoveEndHandler = null

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
  //
  // 密度格子（densityEntities）同理也【不】在这里清 —— 见 drawDensity()。
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
 * 画网格密度：每个格子一个矩形，颜色按对数色阶映射。
 *
 * ⚠️ 这里【不】把密度格子加进 clearTrack() 的清理范围 ——
 * 理由和热点一样：密度是跨轨迹的全局结果，不属于任何一条轨迹。
 * 而 clearTrack() 是由"轨迹点变了"触发的，在密度模式下切轨迹会把它误清掉。
 * 清理统一由 drawDensity() 自己负责（它开头就清一遍）。
 *
 * @param {Array}  cells    格子列表 [{ lon, lat, value }, ...]（lon/lat 是格中心）
 * @param {number} max      本批最大值，归一化用
 * @param {number} cellSize 格边长（度）
 */
function drawDensity(cells, max, cellSize) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return

  for (const e of densityEntities) v.entities.remove(e)
  densityEntities = []
  if (!cells || cells.length === 0) return

  for (const c of cells) {
    const r = cellRect(c.lon, c.lat, cellSize)
    const t = densityRatio(c.value, max)
    const entity = v.entities.add({
      rectangle: {
        coordinates: Rectangle.fromDegrees(r.west, r.south, r.east, r.north),
        // 半透明：格子之间会重叠视角，太实会把底图糊住
        material: Color.fromCssColorString(rampColor(t)).withAlpha(0.75),
        height: 0,
      },
    })
    densityEntities.push(entity)
  }
}

/**
 * 原始轨迹点 → Cesium 坐标数组。
 *
 * ⚠️ 为什么要这一层适配（计划里的 drawSimilarity 直接用了 t.positions，现状不是这样）：
 * 本项目从后端到地球传的一直是**原始点** `{ seq, recordedAt, lon, lat, elevationM }`
 * （见 TrackPointDto 与上面 points prop 的注释），坐标转换是**在组件内部**做的
 * —— drawTrack() 里就是这么干的。App.vue 组装 similarBaseline / similarTracks 时
 * 照的也是这个现状，给的并不是 Cartesian3 数组。
 * 所以按现状在组件里转，而不是反过来去改地球已有的数据结构。
 *
 * 两种输入都认：已经是 Cartesian3（有 x/y/z 三个数字）就直接用，是原始点就 fromDegrees 转。
 * 多认一种不会出错，还能让以后真传 Cartesian3 的调用方不必改代码。
 */
function toCartesians(list) {
  if (!Array.isArray(list)) return []
  return list.map((p) =>
    p && typeof p.x === 'number' && typeof p.y === 'number' && typeof p.z === 'number'
      ? p
      : Cartesian3.fromDegrees(p.lon, p.lat, p.elevationM ?? p.elevation ?? 0),
  )
}

/**
 * 画相似轨迹：主线用醒目的亮蓝粗线画在最上面，匹配到的按相似度上色叠在下面。
 *
 * ⚠️ 和热点/密度一样，这些实体【不】进 clearTrack() 的清理范围 ——
 * 相似是"当前选中轨迹 vs 别的轨迹"的结果，由选中轨迹变化驱动；
 * 而 clearTrack() 是由"轨迹点变了"触发的（drawTrack → clearTrack），两者会互相打架：
 * 在相似档里点另一条轨迹，points 变了、similarTracks 的引用却没变，
 * 实体被清掉而 watcher 不触发 → 表现为"叠画凭空消失"。
 * 清理统一由 drawSimilarity() 自己负责（它开头清一遍）；切出相似档时 App 传空值进来，watcher 触发 → 清空。
 *
 * 数据形状（按现状，见 App.vue 的组装）：
 *   baseline: { positions: [{ lon, lat, elevationM }, ...], ... }（也兼容 points 键）
 *   tracks:   [{ trackId, similarity, points: [{ lon, lat, elevationM }, ...] }, ...]
 */
function drawSimilarity(baseline, tracks) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return

  for (const e of similarEntities) v.entities.remove(e)
  similarEntities = []
  if (!baseline && (!tracks || tracks.length === 0)) return

  // 先画匹配的（细、按相似度上色），后画主线（粗、亮蓝）—— 后加的在上层。
  // 顺序反过来的话，高度重合的匹配轨迹会把主线整个盖住，就认不出基准是哪条了。
  for (const t of tracks || []) {
    const positions = toCartesians(t.points ?? t.positions)
    // 少于 2 个点连不成线
    if (positions.length < 2) continue
    similarEntities.push(
      v.entities.add({
        polyline: {
          positions,
          width: 3,
          material: Color.fromCssColorString(simColor(t.similarity)).withAlpha(0.85),
          clampToGround: false,
        },
      }),
    )
  }

  const basePositions = toCartesians(baseline && (baseline.points ?? baseline.positions))
  if (basePositions.length >= 2) {
    similarEntities.push(
      v.entities.add({
        polyline: {
          positions: basePositions,
          width: 6,
          // 主线用亮蓝 —— 和匹配轨迹的暖色系形成对比，一眼能分清谁是谁。
          // 不用"最红"那条：红色系已经被"相似度"占用，主线不是某个相似度、它是基准。
          material: Color.fromCssColorString('rgb(127,209,255)'),
          clampToGround: false,
        },
      }),
    )
  }
}

/* ============ 绘制模式（第五档「圈选」）============
 *
 * ⚠️ 最关键的一条：Cesium 默认【左键拖动 = 旋转地球】。
 * 不关掉的话，用户拉一个框的同时地球会跟着转，框就画歪了。
 * 所以进入绘制模式时 enableRotate = false，退出/取消/切档/卸载时必须恢复 true ——
 * 忘了恢复的表现是"地图坏了"（用户以为 bug，其实是状态泄漏）。
 *
 * 状态方向仍然是「父 → 子」：App 通过 drawingMode prop 决定画不画、画哪种，
 * 地球只负责注册/注销鼠标事件。这样 ESC、切档、取消三条退出路径在 App 侧收口，
 * 不需要在两边各写一遍 —— 那种写法必漏其一。
 *
 * ⚠️ 第二条纪律：**"画的过程"由地球自己表现，父组件只在动作完成时收到一次事件**。
 *   - 拖框中的矩形、"已画折线"、回到起点的高亮 → 全是地球本地的**预览实体**（固定 id，重绘先删旧）
 *   - `draw-rect` 只在【松手】时 emit 一次（载荷 = 最终矩形）
 *   - `draw-polygon` 只在【闭合】时 emit 一次（双击 / 点回起点）
 *   - `draw-buffer` 单击即 emit 一次
 * 为什么不能"每次 MOUSE_MOVE 都往上报"：父组件收到就会把 drawingMode 收回 'idle'
 * （它没法在拖动过程中持续改状态），于是这边 setDrawingMode('idle') → clearDrawHandler()
 * 当场销毁处理器，框只剩"按下点到第一次移动"那一小段。所以收敛点必须在松手。
 */

const drawHandler = ref(null)      // ScreenSpaceEventHandler；null = 当前没在绘制
const drawPoints = ref([])         // 多边形已加的点
let rectStart = null               // 拉框起点（屏幕坐标）
// 多边形已加点的【屏幕】坐标：只用来判断"鼠标回到起点附近了"（与经纬度无关，所以单独存一份）
let drawScreenPoints = []

// 预览实体的固定 id —— 拖动/逐点画的过程中不断重绘，结束时必须清掉（否则框会留在地图上）
const PREVIEW_RECT_ID = 'draw-preview-rect'
const PREVIEW_POLY_ID = 'draw-preview-polygon'
const PREVIEW_COLOR = '#ffd166'    // 与"后端回显的区域轮廓"同色系：暗示预览和最终区域是一回事
const CLOSE_PX = 12                // 屏幕像素：鼠标离起点这么近就算"回到起点"

// 合法绘制模式的白名单。⚠️ 必须白名单，不能只挡假值：
// mode = 'foo' / 'RECT' 这种"非空但不认识"的值一旦被当成"进入绘制"，enableRotate 就被关掉，
// 而下面那个 handler 一个动作都不会注册（三个 if 全不成立）→ 左键旋转再也回不来，
// 用户看到的就是"地图坏了"。不在这个列表里的一律按退出处理。
const DRAW_MODES = ['rect', 'polygon', 'buffer']

/** 统一开关「左键拖动旋转地球」。
 *  为什么包一层：所有恢复动作都走这一个出口，"漏掉某条退出路径"就只剩"忘了调用"一种可能 */
function rotateEnabled(on) {
  const v = viewer.value
  if (v && !v.isDestroyed()) v.screenSpaceCameraController.enableRotate = on
}

/** 屏幕坐标 → 经纬度；点在地球之外返回 null（否则会算出 NaN 坐标，一路传到后端） */
function pickLonLat(windowPosition) {
  const v = viewer.value
  if (!v) return null
  const cartesian = v.camera.pickEllipsoid(windowPosition, v.scene.globe.ellipsoid)
  if (!cartesian) return null
  const c = Cartographic.fromCartesian(cartesian)
  return { lon: CesiumMath.toDegrees(c.longitude), lat: CesiumMath.toDegrees(c.latitude) }
}

/** 清掉两个预览实体。绘制结束 / 取消 / 切档 / 进入别的模式 / 卸载都可能调它，
 *  viewer 已销毁时静默返回（用固定 id 重绘，所以清的时候不需要任何记账） */
function clearDrawPreview() {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  v.entities.removeById(PREVIEW_RECT_ID)
  v.entities.removeById(PREVIEW_POLY_ID)
}

/** 两个屏幕点的距离（像素）—— 判断"鼠标回到起点了"用 */
function screenDistance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** 拉框拖动中的预览：4 个角 + 回到起点的闭合段。每次调用先删旧再画新 */
function drawPreviewRect(a, b) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  v.entities.removeById(PREVIEW_RECT_ID)
  const west = Math.min(a.lon, b.lon)
  const east = Math.max(a.lon, b.lon)
  const south = Math.min(a.lat, b.lat)
  const north = Math.max(a.lat, b.lat)
  v.entities.add({
    id: PREVIEW_RECT_ID,
    polyline: {
      positions: Cartesian3.fromDegreesArray([
        west, south, east, south, east, north, west, north, west, south,
      ]),
      width: 2,
      material: Color.fromCssColorString(PREVIEW_COLOR),
    },
  })
}

/** 多边形的"已画折线"预览（规格 6.3：单击逐个加点、实时显示已画折线、回到起点时高亮）。
 *  橡皮筋：未闭合时把鼠标当前位置接在最后，用户能看到"下一段会画到哪"。
 *  回到起点附近（屏幕距离 ≤ CLOSE_PX）且已有 3 个点时改成高亮的闭合环
 *  —— 提示"再点一下就是一个区域了"（与 LEFT_CLICK 里"点回起点即闭合"配对）。 */
function drawPreviewPolygon(cursorWindow) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  v.entities.removeById(PREVIEW_POLY_ID)
  const pts = drawPoints.value
  if (pts.length === 0) return
  const closing = !!cursorWindow && pts.length >= 3 && drawScreenPoints.length > 0
    && screenDistance(cursorWindow, drawScreenPoints[0]) <= CLOSE_PX
  const ring = closing ? [...pts, pts[0]] : [...pts]
  const flat = ring.flatMap((p) => [p.lon, p.lat])
  if (!closing && cursorWindow) {
    const c = pickLonLat(cursorWindow) // 拾取不到（球外）就不接橡皮筋，不产生 NaN
    if (c) flat.push(c.lon, c.lat)
  }
  if (flat.length < 4) return // 少于 2 个顶点连不成线
  v.entities.add({
    id: PREVIEW_POLY_ID,
    polyline: {
      positions: Cartesian3.fromDegreesArray(flat),
      width: closing ? 4 : 2,
      material: Color.fromCssColorString(closing ? '#ffffff' : PREVIEW_COLOR),
    },
  })
}

/** 注销鼠标事件。
 *  destroy() 会连同它注册的全部动作一起注销，所以重复进入绘制模式不会叠加注册
 *  —— 前提是每次进入前都先 clear（setDrawingMode 开头就调它） */
function clearDrawHandler() {
  if (drawHandler.value) {
    drawHandler.value.destroy()
    drawHandler.value = null
  }
  rectStart = null
  drawPoints.value = []
  drawScreenPoints = []
  // ⚠️ 预览实体在这里一并清：取消 / 切档 / 进入别的模式 / 组件卸载都走这个函数，
  // 于是"每个出口都清预览"只需要维护这一处（卸载时它在 viewer.destroy() 之前被调用）
  clearDrawPreview()
}

/** 切换绘制模式。idle / 空值 / 非法模式 / 地球还没就绪 → 只做收尾（关掉事件 + 恢复左键旋转） */
function setDrawingMode(mode) {
  // 先收尾旧的：既防重复注册，也保证切档（rect → polygon）时不会两套事件同时活着
  clearDrawHandler()
  const v = viewer.value
  if (!v || v.isDestroyed() || !DRAW_MODES.includes(mode)) {
    rotateEnabled(true) // 出口 ①：退出 / 取消 / 切档 / 非法模式（幂等，从没关过也没关系）
    return
  }
  rotateEnabled(false) // ⭐ 画之前先关掉左键旋转，否则拉框时地球跟着转

  const h = new ScreenSpaceEventHandler(v.scene.canvas)

  if (mode === 'rect') {
    h.setInputAction((m) => {
      rectStart = m.position
      clearDrawPreview() // 上一笔理论上已被清；这里保险起见，保证新的一次拖动从干净状态开始
    }, ScreenSpaceEventType.LEFT_DOWN)
    // 拖动中【只画本地预览、绝不 emit】—— 父组件一收到就会把模式收回 idle（见本节顶部注释）
    h.setInputAction((m) => {
      if (!rectStart) return // 没按下就动鼠标 = 只是在看地图，不产生框
      // 两端都拾取；任一端落在地球外这一帧就不画，不要用半个合法值凑出一个框
      const a = pickLonLat(rectStart)
      const b = pickLonLat(m.endPosition)
      if (!a || !b) return
      drawPreviewRect(a, b)
    }, ScreenSpaceEventType.MOUSE_MOVE)
    // ⭐ 收敛点在【松手】：整次拖动只 emit 一次，载荷是最终矩形
    h.setInputAction((m) => {
      const a = rectStart ? pickLonLat(rectStart) : null
      const b = pickLonLat(m.position)
      rectStart = null
      clearDrawPreview() // 松手先撤掉预览，随后画上的是"后端回显的区域"（region prop）
      if (!a || !b) return // 任一为空 → 这次作废、不 emit（宁可少查一次，也不要畸形的框）
      emit('draw-rect', {
        west: Math.min(a.lon, b.lon), east: Math.max(a.lon, b.lon),
        south: Math.min(a.lat, b.lat), north: Math.max(a.lat, b.lat),
      })
    }, ScreenSpaceEventType.LEFT_UP)
  }

  if (mode === 'polygon') {
    h.setInputAction((m) => {
      const p = pickLonLat(m.position)
      if (!p) return // 点到地球之外 → 忽略这次点击（不要往点列里塞 NaN）
      // 规格 6.3「点回起点」= 闭合：已有 3 个点又点在起点附近，就当闭合，不再加点
      if (drawPoints.value.length >= 3 && drawScreenPoints.length > 0
        && screenDistance(m.position, drawScreenPoints[0]) <= CLOSE_PX) {
        emit('draw-polygon', drawPoints.value)
        drawPoints.value = []
        drawScreenPoints = []
        clearDrawPreview()
        return
      }
      drawPoints.value = [...drawPoints.value, p]
      drawScreenPoints = [...drawScreenPoints, m.position]
      drawPreviewPolygon() // 本地预览：把已画的折线显示出来（不 emit）
    }, ScreenSpaceEventType.LEFT_CLICK)
    // 鼠标移动：橡皮筋 + 回到起点时高亮，同样是纯本地表现，不 emit
    h.setInputAction((m) => { drawPreviewPolygon(m.endPosition) }, ScreenSpaceEventType.MOUSE_MOVE)
    h.setInputAction(() => {
      // 少于 3 个点围不成面：不发事件，由 App 侧提示
      if (drawPoints.value.length >= 3) emit('draw-polygon', drawPoints.value)
      drawPoints.value = []
      drawScreenPoints = []
      clearDrawPreview()
    }, ScreenSpaceEventType.LEFT_DOUBLE_CLICK)
  }

  if (mode === 'buffer') {
    h.setInputAction((m) => {
      const p = pickLonLat(m.position)
      if (p) emit('draw-buffer', p)
    }, ScreenSpaceEventType.LEFT_CLICK)
  }

  drawHandler.value = h
}

/** 区域轮廓：画【后端回显的几何】而不是本地画的形状 ——
 *  这样"看到的圈 = 查的范围"对三种形状都成立（缓冲区尤其重要：
 *  本地只有一个中心点，真正的圆是后端按米算出来的 33 边形）。
 *
 * 和热点/密度/相似一样，它【不】进 clearTrack() 的清理范围：
 * 圈选是跨轨迹的结果，而 clearTrack() 是由"轨迹点变了"触发的，会被误清。 */
function drawRegion(region) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  // 用固定 id + removeById：区域每次都是整个换掉，不需要数组记账
  v.entities.removeById('within-region')
  v.entities.removeById('within-region-outline')
  if (!region) return
  const ring = ringOf(region)
  if (ring.length < 3) return // 退化几何（点/线）画不出面，直接跳过
  const positions = Cartesian3.fromDegreesArray(ring.flat())
  // 半透明面 + 实线边：面太实会把底下的轨迹线糊住，边线负责让轮廓一眼可见
  v.entities.add({
    id: 'within-region',
    polygon: {
      hierarchy: new PolygonHierarchy(positions),
      material: Color.fromCssColorString('#ffd166').withAlpha(0.12),
    },
  })
  v.entities.add({
    id: 'within-region-outline',
    polyline: { positions, width: 2, material: Color.fromCssColorString('#ffd166') },
  })
}

/** 命中轨迹：最多 DRAW_LIMIT 条（由调用方切好）。橙色半透明是"顺带命中"的底色，
 *  和"选中轨迹"的蓝色区分；但元素里带 `selected: true` 的那条要反过来抢眼 ——
 *  它是用户刚在列表里点过的那条，用亮蓝加粗（规格 6.4.2 的"补画并高亮"）。
 *
 *  ⚠️ 保持既有纪律：固定前缀 `within-track-` 先清后画、不进 clearTrack()（跨轨迹结果）。 */
function drawWithinTracks(tracks) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  // 数量不固定（列表里点一条就多一条），所以不用固定 id，按前缀清一遍
  for (const e of [...v.entities.values]) {
    if (typeof e.id === 'string' && e.id.startsWith('within-track-')) v.entities.remove(e)
  }
  for (const t of tracks) {
    if (!t.points || t.points.length < 2) continue // 少于 2 个点连不成线
    const positions = Cartesian3.fromDegreesArray(
      t.points.flatMap((p) => [p.lon, p.lat]))
    // 只有明确的 true 才算选中（undefined / 别的值都当没选中），免得父组件传了个对象也亮起来
    const selected = t.selected === true
    v.entities.add({
      id: `within-track-${t.trackId}`,
      polyline: {
        positions,
        // 选中的更粗更实：它要压过其它橙线，也要能被一眼从区域轮廓里认出来
        width: selected ? 3 : 2,
        material: Color.fromCssColorString(selected ? '#7fd1ff' : '#ff9f45')
          .withAlpha(selected ? 1 : 0.9),
      },
    })
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

// 密度格子变化 → 重画矩形。
// 三个 prop 一起看：App 换档时格子、最大值、格边长会同时变，
// 任何一个变了都要整批重画（颜色归一化依赖 max，尺寸依赖 cellSize）
watch(
  () => [props.densityCells, props.densityMax, props.densityCellSize],
  ([cells, max, cellSize]) => {
    if (ready.value) drawDensity(cells, max, cellSize)
  },
  { deep: true },
)

// 相似数据变化 → 重画叠线。
// 主线和匹配轨迹一起看：App 会先把主线给出来、匹配轨迹的点是逐条异步取回来的，
// 所以这个 watch 会被触发多次 —— 每次都以"当前拿到的全部"重画一遍（drawSimilarity 自己先清）
watch(
  () => [props.similarBaseline, props.similarTracks],
  ([b, ts]) => {
    if (ready.value) drawSimilarity(b, ts)
  },
  { deep: true },
)

// 绘制模式变化 → 注册/注销鼠标事件 + 开关左键旋转。
// ⚠️ 这是"画完地球转不动了"那个 bug 的唯一防线：App 每一次把模式收回 'idle'
// （松手画完 / 取消 / ESC / 切档 / 请求失败）都会走到这里，没有第二条出口
watch(() => props.drawingMode, (m) => setDrawingMode(m))

// 区域回显 → 重画轮廓（画的是后端给的几何，不是本地画的形状）
watch(() => props.region, () => {
  if (ready.value) drawRegion(props.region)
})

// 命中轨迹变化 → 重画橙线（App 每次都以"当前该画的全部"给过来，drawWithinTracks 自己先清）
watch(() => props.withinTracks, () => {
  if (ready.value) drawWithinTracks(props.withinTracks)
})

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

  // Cesium 的相机事件不是 Vue 事件，必须自己转出来 ——
  // App.vue 靠它决定"相机停稳了，该按新视野重新查密度了"。
  // 漏了这步，密度图就只会在切档时加载一次、缩放时永远不更新。
  cameraMoveEndHandler = () => emit('camera-move-end')
  v.camera.moveEnd.addEventListener(cameraMoveEndHandler)

  // 万一父组件在挂载前就已经有点了，补画一次
  drawTrack(props.points)
  drawStayPoints(props.stayPoints)
  drawHotspots(props.hotspots)
  // 密度和热点一样是独立的图层，挂载前父组件可能已经给了格子
  drawDensity(props.densityCells, props.densityMax, props.densityCellSize)
  // 相似叠画同理：父组件可能在地球建好之前就已经把数据给了
  drawSimilarity(props.similarBaseline, props.similarTracks)
  // 圈选的两个图层同理：区域与命中结果都可能在挂载前就已经拿到了
  drawRegion(props.region)
  drawWithinTracks(props.withinTracks)
})

onBeforeUnmount(() => {
  // ⚠️ 必须排在 destroy() 之前：viewer 销毁后 camera 也没了，
  // 那时候再 removeEventListener 不但没意义，还可能直接报错
  if (cameraMoveEndHandler && viewer.value && !viewer.value.isDestroyed()) {
    viewer.value.camera.moveEnd.removeEventListener(cameraMoveEndHandler)
  }
  cameraMoveEndHandler = null

  // 释放 WebGL 资源，否则热更新时会不断泄漏
  if (removeTickListener) {
    removeTickListener()
    removeTickListener = null
  }
  // ⚠️ 绘制模式的两步收尾也必须排在 destroy() 之前：
  // 1) 事件处理器挂在 scene.canvas 上 —— viewer 没了就再没人能注销它
  // 2) 恢复左键旋转 —— 此时 screenSpaceCameraController 还活着；
  //    漏了这一条，用户在绘制中途切走页面（切档、热更新、路由离开）再回来，
  //    地球就再也拖不动了，看着像"地图坏了"
  clearDrawHandler()
  rotateEnabled(true) // 出口 ②：组件卸载
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
 * 取当前视野的包围盒（度）。密度模式靠它决定查哪一块。
 *
 * ⚠️ 三种"拿不到合法包围盒"的情况都必须返回 null，让调用方**跳过这次刷新**：
 *
 * 1. viewer 还没建好 / 已销毁
 * 2. `computeViewRectangle()` 返回 undefined —— 视角包含极点、或者看向太空时就是这样
 * 3. **视野跨了 180° 经线** —— 这时候 Cesium 给的矩形 `west > east`（它没有帮你做环绕），
 *    而后端校验"西必须小于东"，直接传下去会拿到 400。
 *    我们的数据在中国（116~121°E）碰不到，但用户把地球拖到太平洋就会踩到。
 *
 * 宁可少刷一次，也不要发一个注定 400 的请求。
 */
function getViewBbox() {
  const v = viewer.value
  if (!v || v.isDestroyed()) return null
  const rect = v.camera.computeViewRectangle()
  if (!rect) return null
  const west = CesiumMath.toDegrees(rect.west)
  const south = CesiumMath.toDegrees(rect.south)
  const east = CesiumMath.toDegrees(rect.east)
  const north = CesiumMath.toDegrees(rect.north)
  // 弧度值是 NaN（相机未就绪等）时也当拿不到
  if (![west, south, east, north].every(Number.isFinite)) return null
  // 跨 180° 经线：west >= east，后端会判非法
  if (east <= west) return null
  return { west, south, east, north }
}

/**
 * 暴露给父组件的七个方法。
 * 父组件通过 ref 调用，例如：globe.value.play()
 */
defineExpose({
  focusOn,
  /** 飞到能装下所有热点的位置 */
  fitBounds,
  /** 取当前视野包围盒（密度模式用） */
  getViewBbox,
  /** 切换绘制模式（'idle' 关闭）。绘制期间左键旋转被关掉，收尾一律走这里 */
  setDrawingMode,
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
