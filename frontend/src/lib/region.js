/**
 * 圈选功能的纯计算。零依赖、不 import Vue / Cesium —— 所以能用 node 直接断言。
 *
 * 这里只做「把界面上的点变成 GeoJSON」「把接口回来的数字变成人看的字符串」两件事。
 * ⚠️ 判定与统计的真相在【后端】，这里不重算任何空间关系。
 */

/** 地图上默认最多叠画多少条命中轨迹（统计与列表都是全量，这只是渲染取舍） */
export const DRAW_LIMIT = 20

/** 两个角点 → GeoJSON Polygon（闭合的 5 点外环）。顺序无所谓，内部会归一化。 */
export function rectGeometry(a, b) {
  const west = Math.min(a.lon, b.lon)
  const east = Math.max(a.lon, b.lon)
  const south = Math.min(a.lat, b.lat)
  const north = Math.max(a.lat, b.lat)
  return {
    type: 'Polygon',
    coordinates: [[
      [west, south], [east, south], [east, north], [west, north], [west, south],
    ]],
  }
}

/** 点序列 → GeoJSON Polygon（自动闭合）。少于 3 个点返回 null —— 调用方据此不发请求。 */
export function polygonGeometry(points) {
  if (!Array.isArray(points) || points.length < 3) return null
  const ring = points.map((p) => [p.lon, p.lat])
  const first = ring[0]
  const last = ring[ring.length - 1]
  if (first[0] !== last[0] || first[1] !== last[1]) ring.push([first[0], first[1]])
  return { type: 'Polygon', coordinates: [ring] }
}

export function pointGeometry(lon, lat) {
  return { type: 'Point', coordinates: [lon, lat] }
}

/** 取最外环：兼容后端可能回 Polygon 或 MultiPolygon（缓冲区永远是 Polygon） */
export function ringOf(geojson) {
  if (!geojson || !Array.isArray(geojson.coordinates)) return []
  if (geojson.type === 'Polygon') return geojson.coordinates[0] ?? []
  if (geojson.type === 'MultiPolygon') return geojson.coordinates[0]?.[0] ?? []
  return []
}

/** 后端已经排好序，这里做同样的排序 —— 用于本地乐观更新与测试（返回新数组，不改入参） */
export function sortItems(items) {
  return [...items].sort((a, b) =>
    (b.insidePointCount - a.insidePointCount) || (a.trackId - b.trackId))
}

/** 地图上该画哪几条：列表最前面的 DRAW_LIMIT 条 */
export function visibleItems(items, limit = DRAW_LIMIT) {
  return sortItems(items).slice(0, limit)
}

function bad(v) {
  return v === null || v === undefined || (typeof v === 'number' && !Number.isFinite(v))
}

export function formatDistance(m) {
  if (bad(m)) return '—'
  if (m < 1000) return `${Math.round(m)} m`
  return `${(m / 1000).toFixed(1)} km`
}

/** ⚠️ 不能直接 String(n)：Number(null) === 0 会写出 "0"（项目里踩过这个坑） */
export function formatCount(n) {
  if (bad(n)) return '—'
  return String(n)
}

export function spanText(earliest, latest) {
  if (!earliest || !latest) return '—'
  return `${earliest.slice(0, 10)} → ${latest.slice(0, 10)}`
}

export function emptyHint() {
  return '这块区域里没有轨迹穿过'
}
