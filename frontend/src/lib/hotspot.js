/**
 * 停留热点的纯计算模块。
 *
 * 这里只放「输入 → 输出」的函数，不碰 Vue、不碰 Cesium、不碰浏览器 API，
 * 所以可以用 node 直接跑测试（scripts/check-hotspot.mjs）。
 *
 * 组件里只负责把结果画出来，判断逻辑全在这里 —— 这样前端逻辑也有回归测试。
 */

/** 按「有几条不同轨迹来过」决定颜色：越多人来过越红 */
const COLOR_BY_TRACKS = [
  { min: 3, color: '#ff375f' }, // 3 条及以上：红
  { min: 2, color: '#ff9f0a' }, // 2 条：橙
  { min: 1, color: '#ffd60a' }, // 1 条：黄（同一个人常来）
]

const FALLBACK_COLOR = '#86868b'

/**
 * 轨迹条数 → 颜色。
 *
 * 为什么用「轨迹数」而不是「次数」上色：这两个是不同的问题。
 * 颜色回答"有多少不同的人来过"（公共地点），大小回答"被停留过几次"。
 * 实测数据里有个热点 visitCount=2 但 trackCount=1，用同一个通道就分不出来了。
 */
export function hotspotColor(trackCount) {
  if (!trackCount || trackCount < 1) return FALLBACK_COLOR
  for (const rule of COLOR_BY_TRACKS) {
    if (trackCount >= rule.min) return rule.color
  }
  return FALLBACK_COLOR
}

/**
 * 停留次数 → 点标记的像素大小。
 *
 * ⚠️ 单位是**屏幕像素**，不是米。原因是热点不是一块有明确边界的区域，
 * 如果按真实散布画（最小的只有 9.4 米），城市尺度下根本看不见。
 * 用屏幕像素还带来一个好处：它不对地理范围做任何暗示，不会误导。
 */
export function hotspotPixelSize(visitCount) {
  const n = Number(visitCount)
  if (!Number.isFinite(n) || n < 1) return 14
  return 14 + 6 * (n - 1)
}

/** 允许的排序键。和接口返回的字段名保持一致。 */
const SORT_KEYS = ['trackCount', 'visitCount', 'totalDurationS']

/**
 * 按指定口径排序（降序）。
 *
 * 返回**新数组**，不改动传入的数组 —— 调用方（App.vue）把它放在 computed 里，
 * 改原数组会让 Vue 的依赖追踪出问题。
 *
 * @param {Array} list    热点列表
 * @param {string} sortBy 排序键，未知值退回 'trackCount'
 */
export function sortHotspots(list, sortBy) {
  if (!Array.isArray(list) || list.length === 0) return []
  const key = SORT_KEYS.includes(sortBy) ? sortBy : 'trackCount'
  return [...list].sort((a, b) => (b[key] || 0) - (a[key] || 0))
}

/** 秒 → "29 分钟" / "1 小时 5 分" */
export function formatDuration(s) {
  if (s == null) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return h > 0 ? `${h} 小时 ${m} 分` : `${m} 分钟`
}

/** 米 → "9.4 米" / "58 米"。小于 10 米保留一位小数，否则取整 */
export function formatSpread(m) {
  if (m == null) return '—'
  return m < 10 ? `${m.toFixed(1)} 米` : `${Math.round(m)} 米`
}

/** 排序下拉的选项，供组件复用，避免选项和排序键两处各写一份 */
export const SORT_OPTIONS = [
  { value: 'trackCount', label: '按轨迹数' },
  { value: 'visitCount', label: '按次数' },
  { value: 'totalDurationS', label: '按时长' },
]
