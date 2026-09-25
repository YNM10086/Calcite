// Task 9 行为级自检：不启动 Vite，直接用 compiler-sfc 把 CesiumGlobe.vue 编译成 JS，
// 把 'vue' / 'cesium' 换成替身，然后真跑一遍 setup()。
//
// 覆盖（含主控 2026-09-25 裁定后的新契约：拉框收敛点在 LEFT_UP + 本地预览）：
//   ① enableRotate 的每一条出口（退出/取消/切档/无效值/卸载，且卸载恢复在 destroy 之前）
//   ② 事件处理器可逆（切档时旧的被 destroy，不叠加注册）
//   ③ 点在球外不产生 NaN 坐标（不 emit、不推进点数、不画预览）
//   ④ 三个 emit 的载荷形状 + 收敛点（拖动期间 0 次 emit；松手/闭合/单击各 1 次）
//   ⑤ 预览实体（矩形 / 多边形折线）在每个出口都被清掉
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'

const { hooks } = await import('./vue-stub.mjs')
const { ScreenSpaceEventType, handlers, reset, seq, state } = await import('./cesium-stub.mjs')
// 事件载荷**必须**用替身的 clickAt/moveTo/... —— 它们复刻 Cesium 的"模块级单例事件对象"
//    （同一个对象每次被改写）。写 `{ position: { x, y } }` 字面量每次都是新对象，
//    "组件把 m.position 存进数组"这类缺陷就永远测不出来（2026-09-25 三角形事故）。
const { clickAt, dblClickAt, downAt, moveTo, upAt } = await import('./cesium-stub.mjs')

// ⚠️ 路径**从自身位置推**（不要写死 E:/…）：这样换机器 / 换盘符也能跑
const ROOT = fileURLToPath(new URL('..', import.meta.url)).replace(/\\/g, '/').replace(/\/+$/, '')
const { compileScript, parse } = await import(
  pathToFileURL(`${ROOT}/frontend/node_modules/vue/compiler-sfc/index.mjs`).href)
const SFC = `${ROOT}/frontend/src/components/CesiumGlobe.vue`
const OUT = `${ROOT}/.tmp/task9-compiled.mjs`

const { descriptor } = parse(readFileSync(SFC, 'utf8'), { filename: SFC })
let code = compileScript(descriptor, { id: 'task9' }).content
code = code
  .replace(/from 'vue'/g, "from './vue-stub.mjs'")
  .replace(/from 'cesium'/g, "from './cesium-stub.mjs'")
  .replace(/^\s*import 'cesium\/Build\/Cesium\/Widgets\/widgets\.css'\s*$/m, '')
  .replace(/from '\.\.\/lib\/([\w-]+)\.js'/g, (_m, n) => `from 'file:///${ROOT}/frontend/src/lib/${n}.js'`)
writeFileSync(OUT, code)

const comp = (await import('./task9-compiled.mjs')).default

let pass = 0
let fail = 0
function check(name, cond, extra = '') {
  if (cond) { pass += 1; console.log(`OK   ${name}`) } else { fail += 1; console.log(`FAIL ${name} ${extra}`) }
}
const keys = (o) => Object.keys(o).sort().join(',')
const { LEFT_DOWN, LEFT_UP, LEFT_CLICK, LEFT_DOUBLE_CLICK, MOUSE_MOVE } = ScreenSpaceEventType
const RECT_ID = 'draw-preview-rect'
const POLY_ID = 'draw-preview-polygon'

// ---- 挂载：故意给上 region / withinTracks，验证挂载时就画 ----
reset()
const emits = []
const props = {
  points: [], loop: true, stayPoints: [], hotspots: [], densityCells: [],
  densityMax: 1, densityCellSize: 0.002, similarBaseline: null, similarTracks: [],
  region: { type: 'Polygon', coordinates: [[[116.2, 39.8], [116.6, 39.8], [116.6, 40.2], [116.2, 40.2], [116.2, 39.8]]] },
  withinTracks: [
    { trackId: 7, points: [{ lon: 116.3, lat: 39.85 }, { lon: 116.4, lat: 39.9 }, { lon: 116.5, lat: 39.95 }] },
    { trackId: 9, points: [{ lon: 116.3, lat: 39.85 }] }, // 只有 1 个点 → 应被跳过
  ],
  drawingMode: 'idle',
}
let exposed = {}
const ctx = comp.setup(props, {
  expose: (o) => { exposed = o },
  emit: (name, payload) => emits.push({ name, payload }),
})
hooks.mounted.forEach((f) => f())
const ents = ctx.viewer.value.entities // 捕获引用：卸载后 ctx.viewer.value 会变 null

check('挂载后 setDrawingMode 已 defineExpose', typeof exposed.setDrawingMode === 'function')
check('挂载后 getRotateEnabled 已 defineExpose（验收硬证据）', typeof exposed.getRotateEnabled === 'function')
check('挂载默认：enableRotate = true', state.enableRotate === true)
check('挂载默认：getRotateEnabled() === true', exposed.getRotateEnabled() === true)
// ⭐ 替身形状必须与 Cesium 1.145 运行时一致（否则 Task 11 那个 Critical 会再次溜过去）
check('④ 替身上 viewer 没有 screenSpaceCameraController，只有 viewer.scene 上有',
  ctx.viewer.value.screenSpaceCameraController === undefined
  && ctx.viewer.value.scene.screenSpaceCameraController !== undefined)
check('④ 走错路径（v.screenSpaceCameraController）确实会抛 —— 替身不再宽容', (() => {
  try {
    ctx.viewer.value.screenSpaceCameraController.enableRotate = false
    return false // 没抛 = 替身又把属性挂回 viewer 了
  } catch {
    return true
  }
})())
check('挂载即画 region（面+边线两个实体）',
  !!ents.getById('within-region') && !!ents.getById('within-region-outline'))
check('挂载即画命中轨迹（within-track-7 有、1 个点的 within-track-9 没有）',
  !!ents.getById('within-track-7') && !ents.getById('within-track-9'))
check('region 顶点数 = 5 点 × 2 = 10',
  ents.getById('within-region').polygon.hierarchy.positions.length === 10)
ctx.drawWithinTracks([{ trackId: 11, points: [{ lon: 1, lat: 1 }, { lon: 2, lat: 2 }] }])
check('重画命中轨迹：旧的 within-track-7 被清、新的 within-track-11 在',
  !ents.getById('within-track-7') && !!ents.getById('within-track-11'))
// selected: true（列表里点过的那条）→ 亮蓝加粗；其余维持橙色细线（规格 6.4.2）
ctx.drawWithinTracks([
  { trackId: 21, points: [{ lon: 3, lat: 3 }, { lon: 4, lat: 4 }], selected: true },
  { trackId: 22, points: [{ lon: 5, lat: 5 }, { lon: 6, lat: 6 }] },
  { trackId: 23, points: [{ lon: 7, lat: 7 }, { lon: 8, lat: 8 }], selected: 'yes' }, // 非 true → 不算选中
])
const sel = ents.getById('within-track-21')
const other = ents.getById('within-track-22')
const notBool = ents.getById('within-track-23')
check('③ selected:true 用亮蓝 #7fd1ff + width 3',
  sel.polyline.material.css === '#7fd1ff' && sel.polyline.width === 3,
  `${sel.polyline.material.css} / ${sel.polyline.width}`)
check('③ 未选中的仍是 #ff9f45 + width 2',
  other.polyline.material.css === '#ff9f45' && other.polyline.width === 2)
check('③ selected 只有明确 true 才算（"yes" 不亮）',
  notBool.polyline.material.css === '#ff9f45' && notBool.polyline.width === 2)
check('③ 选中的 alpha 更实（1 vs 0.9）',
  sel.polyline.material.alpha === 1 && other.polyline.material.alpha === 0.9)
check('③ 先清后画仍然生效（within-track-* 只剩这 3 条）',
  ents.values.filter((e) => typeof e.id === 'string' && e.id.startsWith('within-track-')).length === 3)
ctx.drawRegion(null)
check('drawRegion(null) 把区域两个实体都清掉',
  !ents.getById('within-region') && !ents.getById('within-region-outline'))

// 屏幕像素 → 经纬度（起止两端必须【各自拾取】才能得到真正的框）
const at = (x, y) => [110 + x / 1000, 35 + y / 1000]
const pickByPixel = (wp) => at(wp.x, wp.y)

// ---- 拉框：进入 / 拖动只画预览 / 松手才 emit ----
reset()
exposed.setDrawingMode('rect')
check('① 进入 rect：enableRotate = false', state.enableRotate === false)
check('① 进入 rect：getRotateEnabled() === false（走 scene 读得到）',
  exposed.getRotateEnabled() === false)
const h1 = handlers.at(-1)
check('① rect 注册 3 个动作（DOWN/MOVE/UP）—— 说明 rotateEnabled 没抛异常、函数跑到了注册',
  handlers.length === 1 && h1.actions.size === 3)

const n0 = emits.length
state.pick = pickByPixel
h1.fire(LEFT_DOWN, downAt(100, 100))
h1.fire(MOUSE_MOVE, moveTo(200, 200))
check('④ 拖动中 MOUSE_MOVE 不再 emit draw-rect（收敛点是松手）', emits.length === n0)
const pv1 = ents.getById(RECT_ID)
check('⑤ 拖动中创建了本地预览实体 draw-preview-rect（4 角 + 闭合 = 10 个数）',
  !!pv1 && pv1.polyline.positions.length === 10)
h1.fire(MOUSE_MOVE, moveTo(300, 400))
const pv2 = ents.getById(RECT_ID)
// 顶点顺序 = [w,s, e,s, e,n, w,n, w,s] → 下标 2 = east，下标 5 = north（松手那一端）
check('⑤ 预览随鼠标重绘（实体仍只有 1 个、顶点跟到新位置）',
  ents.values.filter((e) => e.id === RECT_ID).length === 1
  && pv2.polyline.positions[2] === at(300, 400)[0] && pv2.polyline.positions[5] === at(300, 400)[1],
  `${pv2.polyline.positions[2]} / ${pv2.polyline.positions[5]}`)
h1.fire(LEFT_UP, upAt(300, 400))
const rects = emits.filter((e) => e.name === 'draw-rect')
check('④ LEFT_UP 只 emit 一次 draw-rect', rects.length === 1, `实际 ${rects.length} 次`)
check('④ draw-rect 载荷 = 最终矩形 {west,south,east,north}（两端各自拾取、已归一化）',
  keys(rects[0].payload) === 'east,north,south,west'
  && rects[0].payload.west === at(100, 100)[0] && rects[0].payload.east === at(300, 400)[0]
  && rects[0].payload.south === at(100, 100)[1] && rects[0].payload.north === at(300, 400)[1],
  JSON.stringify(rects[0].payload))
check('⑤ LEFT_UP 后预览实体被清掉', !ents.getById(RECT_ID))
console.log(`NOTE 拉框收敛点：拖动 2 次 MOUSE_MOVE 期间 emit ${n0} 次（期望 0）+ LEFT_UP 后 ${rects.length} 次；`
  + `预览实体 拖动中=${!!pv1}、松手后=${!!ents.getById(RECT_ID)}`)

// ③ 球外：松手时任一端落空 → 不 emit、不留预览
const q = [[110.1, 35.1], null]
state.pick = () => q.shift() ?? null
h1.fire(LEFT_DOWN, downAt(100, 100))
h1.fire(MOUSE_MOVE, moveTo(200, 200))
check('③ 半个端点在球外 → 拖动中不画预览', !ents.getById(RECT_ID))
const n1 = emits.length
h1.fire(LEFT_UP, upAt(200, 200))
check('③ 松手时端点落空 → 不 emit，且没有残留预览',
  emits.length === n1 && !ents.getById(RECT_ID))

// ---- ② 切档：旧处理器 destroy + 预览清掉 + 不叠加 ----
state.pick = pickByPixel
h1.fire(LEFT_DOWN, downAt(100, 100))
h1.fire(MOUSE_MOVE, moveTo(250, 250))
check('⑤ 切档前预览在', !!ents.getById(RECT_ID))
exposed.setDrawingMode('polygon')
check('② 切档：旧处理器被 destroy 且动作已注销', h1.destroyed === true && h1.actions.size === 0)
check('⑤ 切档清掉了矩形预览', !ents.getById(RECT_ID))
const h2 = handlers.at(-1)
check('② 切档：只新增 1 个处理器（不叠加）', handlers.length === 2 && h2.actions.size === 3)
check('② 切档期间 enableRotate 仍为 false', state.enableRotate === false)

// ---- 多边形：球外不计数 ----
state.pick = null
for (let i = 0; i < 3; i += 1) h2.fire(LEFT_CLICK, clickAt(i, i))
h2.fire(LEFT_DOUBLE_CLICK, dblClickAt(0, 0))
check('③ 球外点击不计数 → 不到 3 点不发事件（也不含 NaN）',
  emits.filter((e) => e.name === 'draw-polygon').length === 0)

// ---- 多边形：本地折线预览 / 橡皮筋 / 回到起点高亮 ----
state.pick = pickByPixel
h2.fire(LEFT_CLICK, clickAt(100, 100))
check('⑤ 只画了 1 个点时连不成线 → 不建预览实体', !ents.getById(POLY_ID))
h2.fire(LEFT_CLICK, clickAt(200, 100))
h2.fire(MOUSE_MOVE, moveTo(300, 200))
const lp1 = ents.getById(POLY_ID)
check('⑤ 折线预览 = 2 个已画点 + 橡皮筋（3 个顶点 = 6 个数）',
  !!lp1 && lp1.polyline.positions.length === 6)
check('⑤ 未回到起点时是普通色 #ffd166 / 宽 2',
  lp1.polyline.material.css === '#ffd166' && lp1.polyline.width === 2)
check('④ 多边形逐点期间不 emit', emits.filter((e) => e.name === 'draw-polygon').length === 0)

h2.fire(LEFT_CLICK, clickAt(400, 400)) // 第 3 个点
h2.fire(MOUSE_MOVE, moveTo(104, 104)) // 回到起点附近（≈5.7px ≤ 12px）
const lp2 = ents.getById(POLY_ID)
check('⑤ 回到起点：高亮闭合环（白色 / 宽 4 / 顶点数 = 已画 3 点 + 回起点 = 8 个数）',
  !!lp2 && lp2.polyline.material.css === '#ffffff' && lp2.polyline.width === 4
  && lp2.polyline.positions.length === 8)

const nPoly = emits.filter((e) => e.name === 'draw-polygon').length
h2.fire(LEFT_CLICK, clickAt(102, 102)) // 点回起点 = 闭合
const polys = emits.filter((e) => e.name === 'draw-polygon')
check('④ 点回起点即闭合：emit 一次 draw-polygon（不把那一下当成新顶点）',
  polys.length === nPoly + 1, `实际 +${polys.length - nPoly}`)
check('④ draw-polygon 载荷 = [{lon,lat},...] 三个点且全为有限数',
  Array.isArray(polys.at(-1).payload) && polys.at(-1).payload.length === 3
  && polys.at(-1).payload.every((p) => keys(p) === 'lat,lon'
    && Number.isFinite(p.lon) && Number.isFinite(p.lat)),
  JSON.stringify(polys.at(-1).payload))
check('⑤ 闭合后折线预览被清掉', !ents.getById(POLY_ID))

// 双击闭合这条路径同样只 emit 一次、同样清预览
for (const p of [[116.3, 39.9], [116.4, 39.95], [116.5, 40.0]]) {
  state.pick = p
  h2.fire(LEFT_CLICK, clickAt(1, 1))
}
check('⑤ 逐点期间折线预览在', !!ents.getById(POLY_ID))
h2.fire(LEFT_DOUBLE_CLICK, dblClickAt(1, 1))
check('④ 双击闭合：再 emit 一次 draw-polygon',
  emits.filter((e) => e.name === 'draw-polygon').length === nPoly + 2)
check('⑤ 双击闭合后折线预览被清掉', !ents.getById(POLY_ID))

/* ---- ⭐ 修复轮 7（2026-09-25 用户实测）：第 4 个点离起点很远时**绝不能闭合** ----
 * 因果链（真实 Cesium 的形状，见 cesium-stub.mjs 的 clickAt 注释）：
 *   `mouseClickEvent` 是**模块级单例**，`cancelMouseEvent()` 每次把新位置 clone 进**同一个对象**
 *   ⇒ handler 每次收到的 `m.position` 是同一个 Cartesian2 实例。
 *   组件若原样把它存进 `drawScreenPoints`，数组里每一项都等于"最后一次点击的位置"
 *   ⇒ `screenDistance(本次点击, drawScreenPoints[0])` **恒为 0**
 *   ⇒ 第 4 次点击（哪怕离起点 566px）也被判成"点回起点" ⇒ 用户看到的就是「多边形只能是三角形」。
 * ⚠️ 这里**必须**用替身的 clickAt（复用同一个对象）。写字面量 `{position:{x,y}}` 每次都是新对象，
 *    这条断言永远不会红 —— 浏览器验收脚本就是这么把这处缺陷放过去的（实测请求体只有 4 个坐标的三角形）。
 */
state.pick = pickByPixel
const nPolyBefore4 = emits.filter((e) => e.name === 'draw-polygon').length
for (const [x, y] of [[100, 100], [300, 100], [300, 300]]) {
  h2.fire(LEFT_CLICK, clickAt(x, y))
}
h2.fire(LEFT_CLICK, clickAt(500, 500)) // 第 4 个点：离起点 hypot(400,400) ≈ 566px ≫ CLOSE_PX=12
check('⭐ 第 4 个点离起点 566px → 不闭合、不 emit（多边形继续长）',
  emits.filter((e) => e.name === 'draw-polygon').length === nPolyBefore4,
  `实际多发了 ${emits.filter((e) => e.name === 'draw-polygon').length - nPolyBefore4} 次`)
h2.fire(LEFT_DOUBLE_CLICK, dblClickAt(500, 500))
const quadPayload = emits.filter((e) => e.name === 'draw-polygon').at(-1).payload
check('⭐ 四点闭合的载荷 = 4 个顶点（四边形，不是三角形）',
  Array.isArray(quadPayload) && quadPayload.length === 4,
  `顶点数=${Array.isArray(quadPayload) ? quadPayload.length : '—'}：${JSON.stringify(quadPayload)}`)

// ---- 缓冲区：单击即 emit ----
exposed.setDrawingMode('buffer')
const h3 = handlers.at(-1)
state.pick = [117.02, 25.03]
h3.fire(LEFT_CLICK, clickAt(5, 5))
const buf = emits.filter((e) => e.name === 'draw-buffer').at(-1)
check('④ draw-buffer 载荷 = {lon,lat}', keys(buf.payload) === 'lat,lon'
  && buf.payload.lon === 117.02 && buf.payload.lat === 25.03, JSON.stringify(buf.payload))

// ---- 出口 ①：退出绘制 / 取消 / 无效值 ----
exposed.setDrawingMode('idle')
check('① setDrawingMode(\'idle\')（= 画完 / 取消 / ESC / 切档）→ enableRotate 恢复 true',
  state.enableRotate === true)
check('① 退出后 getRotateEnabled() === true（硬证据，不是"间接推断"）',
  exposed.getRotateEnabled() === true)
check('① 退出时处理器被 destroy', h3.destroyed === true)
const nHandlers = handlers.length
exposed.setDrawingMode('')
exposed.setDrawingMode(null)
exposed.setDrawingMode('idle')
check('① 空值/无效值：不新建处理器，且 enableRotate 仍为 true',
  handlers.length === nHandlers && state.enableRotate === true)

// ⭐ 白名单：非空但"不认识"的模式绝不能被当成"进入绘制"
// （否则 enableRotate 被关掉、又不注册任何动作 → 左键旋转再也回不来 = 用户说的"地图坏了"）
for (const bad of ['foo', 'RECT', 'rectangle', 'idle ']) {
  exposed.setDrawingMode(bad)
  check(`① 非法模式 '${bad}'：enableRotate 保持 true 且不建 handler`,
    state.enableRotate === true && handlers.length === nHandlers,
    `enableRotate=${state.enableRotate} handlers=${handlers.length}/${nHandlers}`)
}
check('① 非法模式走完后 getRotateEnabled() === true',
  exposed.getRotateEnabled() === true)
// 非法模式之后状态没坏：仍能正常进入（false + 有 handler）、正常退出
exposed.setDrawingMode('rect')
check('① 非法模式之后再进 rect：enableRotate=false 且有 1 个新 handler',
  state.enableRotate === false && handlers.length === nHandlers + 1)
const hBad = handlers.at(-1)
exposed.setDrawingMode('idle')
check('① 再退出：enableRotate=true 且该 handler 被 destroy',
  state.enableRotate === true && hBad.destroyed === true)

// ---- 出口 ①（取消）：预览也要清 ----
exposed.setDrawingMode('rect')
const h4a = handlers.at(-1)
state.pick = pickByPixel
h4a.fire(LEFT_DOWN, downAt(100, 100))
h4a.fire(MOUSE_MOVE, moveTo(220, 220))
check('④ 取消前预览在', !!ents.getById(RECT_ID))
check('④ 取消前 getRotateEnabled() === false', exposed.getRotateEnabled() === false)
exposed.setDrawingMode('idle') // 取消 / ESC / 切档
check('④ 取消：预览被清 + 处理器 destroy + enableRotate 恢复 true',
  !ents.getById(RECT_ID) && h4a.destroyed === true && state.enableRotate === true)
check('④ 取消后 getRotateEnabled() === true（硬证据）', exposed.getRotateEnabled() === true)

// ---- 出口 ②：组件卸载（清预览与恢复旋转都必须在 viewer.destroy() 之前）----
exposed.setDrawingMode('rect')
const h4 = handlers.at(-1)
h4.fire(LEFT_DOWN, downAt(100, 100))
h4.fire(MOUSE_MOVE, moveTo(260, 260))
check('卸载前：绘制中 enableRotate = false 且预览在',
  state.enableRotate === false && !!ents.getById(RECT_ID))
seq.length = 0
hooks.beforeUnmount.forEach((f) => f())
check('④ 卸载：清预览 + 恢复 true + destroy 处理器，且恢复排在 viewer.destroy() 之前',
  !ents.getById(RECT_ID) && state.enableRotate === true && h4.destroyed === true
  && seq.indexOf('enableRotate=true') !== -1 && seq.indexOf('viewer.destroy') !== -1
  && seq.indexOf('enableRotate=true') < seq.indexOf('viewer.destroy'),
  JSON.stringify(seq))
// 卸载后 viewer.value 已置 null → 只读方法按契约返回 null（"问不到了"），
// 因此"卸载后旋转恢复了"这条用替身状态 state.enableRotate 断言（真实浏览器里 viewer 已销毁）
check('④ 卸载后 getRotateEnabled() === null（viewer 已销毁，契约如此）',
  exposed.getRotateEnabled() === null)
console.log(`NOTE 卸载出口顺序：${JSON.stringify(seq)}；卸载后 getRotateEnabled()=${exposed.getRotateEnabled()}、`
  + `替身 enableRotate=${state.enableRotate}`)

/* ---- ⭐ 修复轮 6（A4）：挂载时 drawingMode 已经不是 'idle' ----
 * 因果链：`drawingMode` 的 watcher 只在**变化**时触发。父组件在 viewer 就绪之前就把模式设成
 * 'rect'（用户在挂载前点了「拉框」）时，那次变化发生在 setup 阶段、`viewer.value` 还是 null，
 * setDrawingMode 开头的守卫（`!v || v.isDestroyed()`）会把它**静默吃掉** —— 按钮亮着、
 * 地球却收不到任何鼠标事件、左键旋转也没关掉。
 * 修法：onMounted 末尾（viewer 与 ready 都就绪之后）补调一次 `setDrawingMode(props.drawingMode)`。
 * 这里用一个"挂载前 drawingMode 已是 rect"的实例钉住它 —— 去掉那行补调，两条都会红。
 */
reset()
const mountedBefore = hooks.mounted.length
let exposedRect = {}
comp.setup({ ...props, drawingMode: 'rect' }, {
  expose: (o) => { exposedRect = o },
  emit: () => {},
})
hooks.mounted.slice(mountedBefore).forEach((f) => f())
check('A4 挂载时 drawingMode 已是 rect → onMounted 补调生效：enableRotate=false 且新建 1 个 handler',
  state.enableRotate === false && handlers.length === 1,
  `enableRotate=${state.enableRotate} handlers=${handlers.length}（期望 false / 1）`)
check('A4 挂载时 drawingMode 已是 rect → getRotateEnabled() === false（硬证据）',
  exposedRect.getRotateEnabled() === false, String(exposedRect.getRotateEnabled && exposedRect.getRotateEnabled()))

console.log(`\nRESULT: ${pass} 通过 / ${fail} 失败`)
process.exitCode = fail === 0 ? 0 : 1
