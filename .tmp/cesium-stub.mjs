// Task 9 自检用：Cesium 1.145 的最小替身。只实现 CesiumGlobe.vue 真正触碰到的成员。
// 目的：在 node 里真跑一遍组件的 setup()，验证 enableRotate 的每条出口、事件处理器可逆、
// 以及"点在球外不产生 NaN 坐标"。
export const seq = []      // 事件顺序（用来断言"先恢复旋转、后销毁 viewer"）
export const handlers = [] // 每次 new ScreenSpaceEventHandler 都记下来
export const state = { enableRotate: true, destroyed: false, pick: null }

export function reset() {
  seq.length = 0
  handlers.length = 0
  state.enableRotate = true
  state.destroyed = false
  state.pick = null
}

export const ScreenSpaceEventType = {
  LEFT_DOWN: 0, LEFT_UP: 1, LEFT_CLICK: 2, LEFT_DOUBLE_CLICK: 3, MOUSE_MOVE: 15,
}

export class Cartesian2 {
  constructor(x = 0, y = 0) { this.x = x; this.y = y }
}

/* ⚠️⚠️ 鼠标事件对象是**模块级单例** —— 这是 Cesium 1.145 的真实形状，替身必须一样：
 *   · `CesiumUnminified/index.js:237297-237302` 定义 `mouseUpEvent` / `mouseClickEvent` 等模块级对象
 *     （`mouseDownEvent` / `mouseMoveEvent` / `mouseDblClickEvent` 同样是模块级）；
 *   · `cancelMouseEvent()`（:237303）每次 `Cartesian2.clone(position, mouseClickEvent.position)`
 *     —— 把新位置写进**同一个**对象再交给 handler。
 *   ⇒ handler 每次收到的 `m.position` 是**同一个 Cartesian2 实例**，`m.endPosition` 同理。
 *
 * 为什么替身要复刻：**2026-09-25 用户实测事故**「多边形选框只能是三角形」。
 *   组件把 `m.position` 原样存进 `drawScreenPoints` ⇒ 数组每一项都是同一个对象
 *   ⇒ 全都等于"最后一次点击的位置" ⇒ `screenDistance(本次点击, drawScreenPoints[0])` **恒为 0**
 *   ⇒ 第 4 次点击（哪怕离起点 566px）被判成"点回起点"闭合 ⇒ 只能画出三角形。
 *   旧替身让测试自己写 `{ position: { x, y } }` 字面量（每次都是新对象），
 *   于是这类"存引用"的写法在假环境里**永远看不出问题** —— 和 enableRotate 那次是同一类教训：
 *   替身的形状必须与运行时一致，否则夹具只证明了"在假环境里能跑"。
 */
const clickEvent = { position: new Cartesian2() }
const downEvent = { position: new Cartesian2() }
const upEvent = { position: new Cartesian2() }
const dblEvent = { position: new Cartesian2() }
const moveEvent = { startPosition: new Cartesian2(), endPosition: new Cartesian2() }

/** 单击（LEFT_CLICK）：**复用同一个对象**，复刻 Cesium 的 mouseClickEvent */
export function clickAt(x, y) {
  clickEvent.position.x = x
  clickEvent.position.y = y
  return clickEvent
}

/** 按下（LEFT_DOWN）：复刻 mouseDownEvent */
export function downAt(x, y) {
  downEvent.position.x = x
  downEvent.position.y = y
  return downEvent
}

/** 松手（LEFT_UP）：复刻 mouseUpEvent */
export function upAt(x, y) {
  upEvent.position.x = x
  upEvent.position.y = y
  return upEvent
}

/** 双击（LEFT_DOUBLE_CLICK）：复刻 mouseDblClickEvent */
export function dblClickAt(x, y) {
  dblEvent.position.x = x
  dblEvent.position.y = y
  return dblEvent
}

/** 鼠标移动（MOUSE_MOVE）：复刻 mouseMoveEvent（startPosition 与 endPosition 都在同一个对象上）*/
export function moveTo(x, y) {
  moveEvent.endPosition.x = x
  moveEvent.endPosition.y = y
  return moveEvent
}

export class ScreenSpaceEventHandler {
  constructor(canvas) {
    this.canvas = canvas
    this.actions = new Map()
    this.destroyed = false
    handlers.push(this)
  }

  setInputAction(action, type) { this.actions.set(type, action) }

  destroy() {
    this.destroyed = true
    this.actions.clear() // 真实 Cesium 的 destroy 会注销全部动作
    seq.push('handler.destroy')
  }

  fire(type, payload) {
    const a = this.actions.get(type)
    return a ? a(payload) : 'NO_ACTION'
  }
}

const RAD = globalThis.Math.PI / 180
const mathShim = {
  toDegrees: (r) => r / RAD,
  toRadians: (d) => d * RAD,
}

export const Cartesian3 = {
  fromDegrees: (lon, lat, h) => [lon, lat, h ?? 0],
  fromDegreesArray: (coords) => coords,
}
export const Cartographic = {
  // 替身的 Cartesian 就是 [lon, lat]（度），这里换成弧度，让组件的 toDegrees 还原
  fromCartesian: (c) => ({ longitude: c[0] * RAD, latitude: c[1] * RAD }),
}
export { mathShim as Math }

export class PolygonHierarchy {
  constructor(positions) { this.positions = positions }
}

export const Color = {
  fromCssColorString: (css) => ({ css, withAlpha(a) { return { css, alpha: a } } }),
  WHITE: {}, ORANGE: { withAlpha: () => ({}) },
}

export const ClockRange = { LOOP_STOP: 1, CLAMPED: 0 }
export const ClockStep = { SYSTEM_CLOCK_MULTIPLIER: 3 }
export const HeightReference = { CLAMP_TO_GROUND: 1 }
export const ImageryLayer = { fromProviderAsync: () => ({}) }
export const TileMapServiceImageryProvider = { fromUrl: () => ({}) }
export const buildModuleUrl = (p) => p
export const VERSION = '1.145.0-stub'
export const Rectangle = { fromDegrees: (w, s, e, n) => ({ w, s, e, n }) }
export const JulianDate = {
  fromIso8601: (s) => new Date(s),
  fromDate: (d) => d,
  toDate: (j) => j,
  clone: (j) => j,
}
export class SampledPositionProperty { addSample() {} }

class FakeEntities {
  constructor() { this.list = [] }
  get values() { return this.list }
  getById(id) { return this.list.find((e) => e.id === id) }
  add(opts) { const e = { ...opts }; this.list.push(e); return e }
  remove(e) { const i = this.list.indexOf(e); if (i >= 0) this.list.splice(i, 1) }
  removeById(id) {
    const e = this.getById(id)
    if (!e) return false
    this.remove(e)
    return true
  }
}

export class Viewer {
  constructor(el, opts) {
    this.el = el
    this.opts = opts
    // ⚠️ 替身的形状必须与 **Cesium 1.145 运行时**一致：
    // screenSpaceCameraController 挂在 `scene` 上，viewer 上【没有】这个属性。
    // 以前替身把它直接挂在 viewer 上（= 顺着错误的源码写法造了个宽容的假环境），
    // 于是 Task 11 浏览器验收抓到的那个 Critical（点「拉框」抛 TypeError）从 53 项夹具里溜了过去。
    // 现在只保留 scene.screenSpaceCameraController —— 源码若写回 v.screenSpaceCameraController 会立刻抛。
    this.scene = {
      canvas: { stub: 'canvas' },
      globe: { ellipsoid: { stub: 'ellipsoid' } },
      screenSpaceCameraController: {
        get enableRotate() { return state.enableRotate },
        set enableRotate(v) { state.enableRotate = v; seq.push(`enableRotate=${v}`) },
      },
    }
    this.camera = {
      setView() {},
      flyTo() {},
      computeViewRectangle: () => null,
      // state.pick 可以是数组（每次都返回它），也可以是函数 —— 函数收到屏幕坐标，
      // 用来造"按像素映射经纬度"或"半个点在球外"的情形
      pickEllipsoid: (windowPosition) => (typeof state.pick === 'function' ? state.pick(windowPosition) : state.pick),
      moveEnd: { addEventListener() {}, removeEventListener() {} },
    }
    this.clock = {
      onTick: { addEventListener: () => () => {} },
      shouldAnimate: false,
      currentTime: null,
    }
    this.entities = new FakeEntities()
    this.isDestroyed = () => state.destroyed
    this.destroy = () => { state.destroyed = true; seq.push('viewer.destroy') }
  }
}
