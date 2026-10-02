/**
 * 在线底图的纯计算：把"样式"翻译成"Cesium 要的图层描述"。
 *
 * 零依赖、不 import Vue / Cesium —— 所以能用 node 直接断言（见 scripts/check-basemap.mjs）。
 *
 * 目前只接**高德**两套样式（街道图 / 高清影像）：**不需要 key**，实测 z16 有建筑轮廓与中文路名、
 * z18 能看清单栋建筑与树木，适合演示时"贴近看清建筑"。
 *
 * ⚠️ 高德是 **GCJ-02（火星坐标）**，我们的轨迹是 WGS84（GPS 原始），直接用会让轨迹整体偏
 * 300~600 米。所以给它的图层描述带上**补偿矩形**（见 gcj02Offset / compensatedWorldRectangle）：
 * 在影像的 `rectangle` 上反向挪 delta，把影像推回 WGS84 位置。
 * **这是近似** —— 偏移量随地点缓变，同城残差约百米量级、跨城市更大。已知限制，暂不再投入。
 *
 * 📌 曾经接过天地图（WMTS，坐标无偏移、更正规），但用户那把 key 没开通「矢量底图」服务
 *（`vec`/`cva` 任何层级都是 200 + 空白/占位图），公开影像又只到 12 级，2026-09-27 已整体移除。
 * 相关教训保留在 `_session_context.md`：`_w` 矩阵集 0 级是 1×1（不是 Cesium 默认的 2×1）、
 * 权限不足时**不报错**而是返回 200 + 全白/占位瓦片（"HTTP 200 ≠ 有内容"）。
 */

/** 矢量图 18 级足够看到建筑轮廓 */
export const DEFAULT_MAX_LEVEL = 18

/** 高德瓦片子域（URL 里是 webrd0{s} / webst0{s}） */
export const AMAP_SUBDOMAINS = ['1', '2', '3', '4']

/** Web Mercator 覆盖的纬度上限（Cesium WebMercatorTilingScheme 用的就是这个值） */
const MERCATOR_MAX_LAT = 85.05112878

// ------------------------------------------------------------------ 高德 XYZ

/** 高德街道图（矢量：建筑轮廓 + 路名 + 绿地水系） */
export function amapStreetUrl() {
  return 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7'
    + '&x={x}&y={y}&z={z}'
}

/** 高德高清卫星影像 */
export function amapImageUrl() {
  return 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}'
}

// ------------------------------------------------------------------ GCJ-02 偏移补偿

const GCJ_A = 6378245.0                 // 克拉索夫斯基椭球长半轴
const GCJ_EE = 0.00669342162296594323   // 偏心率平方

/** 中国大陆粗略范围之外不做偏移（标准 GCJ-02 算法的既定约定） */
function outOfChina(lon, lat) {
  return !(lon > 73.66 && lon < 135.05 && lat > 3.86 && lat < 53.55)
}

function transformLat(x, y) {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0
  ret += (20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin(y / 3.0 * Math.PI)) * 2.0 / 3.0
  ret += (160.0 * Math.sin(y / 12.0 * Math.PI) + 320 * Math.sin(y * Math.PI / 30.0)) * 2.0 / 3.0
  return ret
}

function transformLon(x, y) {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0
  ret += (20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin(x / 3.0 * Math.PI)) * 2.0 / 3.0
  ret += (150.0 * Math.sin(x / 12.0 * Math.PI) + 300.0 * Math.sin(x / 30.0 * Math.PI)) * 2.0 / 3.0
  return ret
}

/**
 * WGS84 → GCJ-02 的差值（度）。**纯函数、可断言**。
 *
 * 用途：高德的瓦片是按 GCJ-02 切的，Cesium 却按 WGS84 摆放 ⇒ 影像相对现实**整体偏了 delta**。
 * 把影像的覆盖矩形往**反方向**挪 delta，就能让它压回真实位置，我们的 WGS84 轨迹也就对齐了。
 */
export function gcj02Offset(lon, lat) {
  if (outOfChina(lon, lat)) return { dLon: 0, dLat: 0 }
  const dLatRaw = transformLat(lon - 105.0, lat - 35.0)
  const dLonRaw = transformLon(lon - 105.0, lat - 35.0)
  const radLat = lat / 180.0 * Math.PI
  let magic = Math.sin(radLat)
  magic = 1 - GCJ_EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  return {
    dLat: (dLatRaw * 180.0) / ((GCJ_A * (1 - GCJ_EE)) / (magic * sqrtMagic) * Math.PI),
    dLon: (dLonRaw * 180.0) / (GCJ_A / sqrtMagic * Math.cos(radLat) * Math.PI),
  }
}

/**
 * 补偿后的"世界矩形"（度）：`[west, south, east, north]`。
 * 高德图层用它当 `rectangle`，把整张影像从 GCJ-02 推回 WGS84。
 */
export function compensatedWorldRectangle(lon, lat) {
  const { dLon, dLat } = gcj02Offset(lon, lat)
  return [-180 - dLon, -MERCATOR_MAX_LAT - dLat, 180 - dLon, MERCATOR_MAX_LAT - dLat]
}

// ------------------------------------------------------------------ 样式定义

/**
 * 两套样式，都免 key。默认街道图（用户点名要"看得见建筑轮廓与路名"）。
 */
export const BASEMAP_STYLES = {
  'amap-street': {
    key: 'amap-street',
    label: '高德·街道图',
    maxLevel: DEFAULT_MAX_LEVEL,
    layers: [{ layer: 'amap-street', name: '高德街道图（建筑轮廓 + 路名）' }],
  },
  'amap-image': {
    key: 'amap-image',
    label: '高德·高清影像',
    maxLevel: DEFAULT_MAX_LEVEL,
    layers: [{ layer: 'amap-image', name: '高德高清影像' }],
  },
}

/** 默认样式 */
export const DEFAULT_STYLE = 'amap-street'

/** 给界面用的样式选项：`[{ key, label }]` */
export function styleOptions() {
  return Object.values(BASEMAP_STYLES).map((s) => ({ key: s.key, label: s.label }))
}

// ------------------------------------------------------------------ 图层描述

/**
 * 样式 → 组件要的图层描述数组。
 *
 * 描述形状：`{ key, kind: 'xyz', layer, name, url, maximumLevel, subdomains, rectangle }`
 * —— 组件按 `kind` 选 provider（目前只有 Web Mercator 的 `{z}/{x}/{y}` 一种）。
 *
 * @param {string} style 见 {@link BASEMAP_STYLES}
 * @param {{lon: number, lat: number}} [refPoint] 补偿参考点（一般传当前相机中心）
 */
export function layerDescriptors(style = DEFAULT_STYLE, refPoint = { lon: 116.397, lat: 39.909 }) {
  const spec = BASEMAP_STYLES[style] ?? BASEMAP_STYLES[DEFAULT_STYLE]
  const rect = compensatedWorldRectangle(refPoint.lon, refPoint.lat)
  return spec.layers.map((l) => ({
    key: spec.key + ':' + l.layer,
    kind: 'xyz',
    layer: l.layer,
    name: l.name,
    url: l.layer === 'amap-street' ? amapStreetUrl() : amapImageUrl(),
    maximumLevel: spec.maxLevel,
    subdomains: AMAP_SUBDOMAINS,
    rectangle: rect,                     // [w, s, e, n]：把 GCJ-02 影像推回 WGS84 位置
  }))
}

/** 开关按钮上的文案 */
export function basemapLabel(on) {
  return on ? '在线底图' : '离线底图'
}
