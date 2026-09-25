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

/** 地图上该画哪几条：**排序后**最前面的 DRAW_LIMIT 条（先 sortItems，再取前 N） */
export function visibleItems(items, limit = DRAW_LIMIT) {
  return sortItems(items).slice(0, limit)
}

/*
 * 非法值判定（统一的"—"口径）。
 *
 * ⚠️ 必须要求 `typeof v === 'number'`：只挡 null/undefined/非有限数的话，
 * 字符串会走到下面的算术里 —— `formatDistance('')` 得 `'0 m'`、`formatCount('')` 得 `''`，
 * 把"没有这个数"显示成一个像真数据的值（本项目在 Number(null)===0 上已经踩过一次）。
 */
function bad(v) {
  return typeof v !== 'number' || !Number.isFinite(v)
}

export function formatDistance(m) {
  if (bad(m)) return '—'
  /*
   * ⚠️ 先取整、再拿取整后的值比阈值。
   * 只比原始值的话，999.6 会落进"米"档、又被 Math.round 显示成 `1000 m`，
   * 而 1000 本身显示 `1.0 km` —— 两个相邻的值给出自相矛盾的档位。
   */
  const rounded = Math.round(m)
  if (rounded < 1000) return `${rounded} m`
  return `${(rounded / 1000).toFixed(1)} km`
}

/** ⚠️ 不能直接 String(n)：Number(null) === 0 会写出 "0"（项目里踩过这个坑） */
export function formatCount(n) {
  if (bad(n)) return '—'
  return String(n)
}

/**
 * 秒 → 人看的时长（规格 6.5 的"时长"列：名字 / 来源 / 区域内点数 / 里程 / 时长）。
 *
 * 分档：< 60 秒 → `N 秒`；< 3600 秒 → `N 分钟`；再往上 → `N 小时` / `N 小时 M 分`。
 *
 * ⚠️ 一律**向下取整**（不是四舍五入）：3599 秒四舍五入成 60 分钟、
 * 59.6 秒四舍五入成 60 秒 —— 都越过了本该进位的那一档，读起来是错的。
 * ⚠️ 非法值（null / undefined / NaN / Infinity / 负数 / 字符串）沿用 bad() 的「—」口径，
 * **绝不变成 "0 秒"**。
 */
export function formatDuration(s) {
  if (bad(s) || s < 0) return '—'
  if (s < 60) return `${Math.floor(s)} 秒`
  if (s < 3600) return `${Math.floor(s / 60)} 分钟`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return m === 0 ? `${h} 小时` : `${h} 小时 ${m} 分`
}

export function spanText(earliest, latest) {
  if (!earliest || !latest) return '—'
  return `${earliest.slice(0, 10)} → ${latest.slice(0, 10)}`
}

export function emptyHint() {
  return '这块区域里没有轨迹穿过'
}
