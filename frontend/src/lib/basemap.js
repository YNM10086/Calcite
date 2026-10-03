/**
 * 在线底图的纯计算：把"样式"翻译成"Cesium 要的图层描述"，外加**显示期坐标转换**。
 *
 * 零依赖、不 import Vue / Cesium —— 所以能用 node 直接断言（见 scripts/check-basemap.mjs）。
 *
 * 目前只接**高德**两套样式（街道图 / 高清影像）：**不需要 key**，实测 z16 有建筑轮廓与中文路名、
 * z18 能看清单栋建筑与树木，适合演示时"贴近看清建筑"。
 *
 * ⚠️ 高德是 **GCJ-02（火星坐标）**，我们的轨迹是 WGS84（GPS 原始）。解决办法是
 * **显示期坐标转换**：把"要画在地球上的几何"整体 +delta（{@link wgs84ToGcj02} 与 `shift*` 系列），
 * 用户在地图上画出来的坐标再 −delta（{@link gcj02ToWgs84}）转回 WGS84 去查库。
 * 影像是 GCJ-02 切的、Cesium 按 WGS84 摆，几何也挪到同一坐标系 ⇒ **精确重合**，且与所在地无关。
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

/*
 * 📌 历史（2026-09-27 实测，两条路都试过、都到此为止）—— 留着是为了别再走一遍：
 *
 * 1. 把"世界矩形反向挪 delta"交给 `UrlTemplateImageryProvider.rectangle`：
 *    Cesium 构造时做 `Rectangle.intersection(options.rectangle, tilingScheme.rectangle)`，
 *    超出世界边界的部分**被裁掉**（实测 `west` 恒等于 -180、只有 `east` 保留偏移）
 *    ⇒ "平移"退化成"以世界西/南边缘为锚点的缩放"：北京只恢复约七成、**残余 ~150 米**。
 * 2. 改去挪**剖分方案**的墨卡托米制边界（更"正统"的那条）：**经度方向走不通** ——
 *    世界西边界本来就是 -180，任何向西平移都会越过 ±180，Cesium 归一化后矩形退化
 *    （实测构造出的 `provider.rectangle.west` 变成 +179.99），图层入地球时
 *    `Rectangle.intersection` 返回 undefined ⇒ 抛 `DeveloperError`、渲染直接停住。
 *
 * ⇒ 结论：**别碰影像，改几何**（见下面的 wgs84ToGcj02 / shift* 系列）。
 *    另外：`UrlTemplateImageryProvider` **不传 `rectangle` 时它就是 undefined**，
 *    图层入地球后 `Rectangle.intersection(瓦片, undefined)` 同样会抛错 —— 必须显式传。
 */

// ------------------------------------------------------------ 显示期坐标转换（真正解决问题的做法）

/**
 * WGS84 → GCJ-02（单个点）。**底图是 GCJ-02 时，所有要画在地球上的几何都要过这一下。**
 *
 * 为什么这才是对的做法：高德瓦片按 GCJ-02 切、Cesium 按 WGS84 摆，于是影像内容天然落在
 * "WGS84 + delta" 处；把**几何也 +delta**，两边就精确重合（不是"恢复七成"，是精确）。
 * 走"挪影像"那条路已经证明走不通（见上面的历史注释）。
 */
export function wgs84ToGcj02(lon, lat) {
  const { dLon, dLat } = gcj02Offset(lon, lat)
  return { lon: lon + dLon, lat: lat + dLat }
}

/**
 * GCJ-02 → WGS84（单个点）。用户在地图上画出来的坐标是**显示坐标**，
 * 拿去查库前必须转回真实的 WGS84，否则圈选/缓冲区会整体偏 delta。
 *
 * 近似逆：在 GCJ 点上再取一次 delta 减回去，残差 < 1 米（远小于演示精度）。
 */
export function gcj02ToWgs84(lon, lat) {
  const { dLon, dLat } = gcj02Offset(lon, lat)
  return { lon: lon - dLon, lat: lat - dLat }
}

/** 单个 `{lon, lat, ...}`（其余字段原样保留）；`on=false` 时原样返回 */
export function shiftPoint(p, on, toDisplay = true) {
  if (!on || !p || !Number.isFinite(p.lon) || !Number.isFinite(p.lat)) return p
  const q = toDisplay ? wgs84ToGcj02(p.lon, p.lat) : gcj02ToWgs84(p.lon, p.lat)
  return { ...p, lon: q.lon, lat: q.lat }
}

/** `[{lon, lat, ...}]`：轨迹点、停留点、密度格子都用这个形状 */
export function shiftPointList(list, on, toDisplay = true) {
  if (!on || !Array.isArray(list)) return list
  return list.map((p) => shiftPoint(p, on, toDisplay))
}

/** `[{..., points: [{lon, lat}]}]`：相似档的匹配轨迹、圈选档的命中轨迹 */
export function shiftTrackList(list, on, toDisplay = true) {
  if (!on || !Array.isArray(list)) return list
  return list.map((t) => (t && Array.isArray(t.points)
    ? { ...t, points: t.points.map((p) => shiftPoint(p, on, toDisplay)) }
    : t))
}

/**
 * 热点列表：**字段名是 `centerLon` / `centerLat`**（不是 lon/lat），
 * 所以不能套 {@link shiftPointList} —— 漏了这一条，热点圈就会单独偏出去。
 */
export function shiftHotspotList(list, on, toDisplay = true) {
  if (!on || !Array.isArray(list)) return list
  return list.map((h) => {
    if (!h || !Number.isFinite(h.centerLon) || !Number.isFinite(h.centerLat)) return h
    const q = toDisplay
      ? wgs84ToGcj02(h.centerLon, h.centerLat)
      : gcj02ToWgs84(h.centerLon, h.centerLat)
    return { ...h, centerLon: q.lon, centerLat: q.lat }
  })
}

/** GeoJSON 的 Polygon / MultiPolygon（坐标是 `[lon, lat]` 二元组） */
export function shiftGeoJson(geom, on, toDisplay = true) {
  if (!on || !geom) return geom
  const ring = (r) => r.map((c) => {
    const q = toDisplay ? wgs84ToGcj02(c[0], c[1]) : gcj02ToWgs84(c[0], c[1])
    return [q.lon, q.lat]
  })
  if (geom.type === 'Polygon') return { ...geom, coordinates: geom.coordinates.map(ring) }
  if (geom.type === 'MultiPolygon') {
    return { ...geom, coordinates: geom.coordinates.map((poly) => poly.map(ring)) }
  }
  return geom
}

/**
 * 视野包围盒 `{west, south, east, north}` 在两个坐标系之间换。
 *
 * 用途：密度档按视野查库。相机给的 bbox 是**真实 WGS84**，而格子是"按显示坐标画"的，
 * 所以查库前要把 bbox 按 −delta 挪一下（`toDisplay=false`），否则网格会整体偏出去。
 * delta 在同一屏内变化可忽略（10 公里内约 10 米），所以按中心取一次即可。
 */
export function shiftBbox(box, on, toDisplay = true) {
  if (!on || !box) return box
  const clon = (box.west + box.east) / 2
  const clat = (box.south + box.north) / 2
  const { dLon, dLat } = gcj02Offset(clon, clat)
  const s = toDisplay ? 1 : -1
  return {
    ...box,
    west: box.west + s * dLon,
    east: box.east + s * dLon,
    south: box.south + s * dLat,
    north: box.north + s * dLat,
  }
}

/** 这套样式是不是 GCJ-02（火星坐标）—— 只有它才需要上面的显示期转换 */
export function isGcj02Style(style) {
  return (BASEMAP_STYLES[style] ?? {}).gcj02 === true
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
    gcj02: true,                     // 火星坐标 ⇒ 画几何时要 +delta（见 wgs84ToGcj02）
    layers: [{ layer: 'amap-street', name: '高德街道图（建筑轮廓 + 路名）' }],
  },
  'amap-image': {
    key: 'amap-image',
    label: '高德·高清影像',
    maxLevel: DEFAULT_MAX_LEVEL,
    gcj02: true,
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
 * 描述形状：`{ key, kind: 'xyz', layer, name, url, maximumLevel, subdomains }`
 * —— 组件按 `kind` 选 provider（目前只有 Web Mercator 的 `{z}/{x}/{y}` 一种）。
 * **不含任何坐标补偿**：影像原样摆，坐标对齐交给显示期转换（见 {@link wgs84ToGcj02}）。
 *
 * @param {string} style 见 {@link BASEMAP_STYLES}
 */
export function layerDescriptors(style = DEFAULT_STYLE) {
  const spec = BASEMAP_STYLES[style] ?? BASEMAP_STYLES[DEFAULT_STYLE]
  return spec.layers.map((l) => ({
    key: spec.key + ':' + l.layer,
    kind: 'xyz',
    layer: l.layer,
    name: l.name,
    url: l.layer === 'amap-street' ? amapStreetUrl() : amapImageUrl(),
    maximumLevel: spec.maxLevel,
    subdomains: AMAP_SUBDOMAINS,
  }))
}

/** 开关按钮上的文案 */
export function basemapLabel(on) {
  return on ? '在线底图' : '离线底图'
}
