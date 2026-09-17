/**
 * 网格密度的纯计算模块。
 *
 * 这里只放「输入 → 输出」的函数，不碰 Vue、不碰 Cesium、不碰浏览器 API，
 * 所以可以用 node 直接跑测试（scripts/check-density.mjs）。
 */

/**
 * 格边长阶梯（度），**从粗到细**。
 *
 * ⚠️ 必须和后端 `calcite.density.cell-ladder` 完全一致 ——
 * 后端只接受这些值，传别的会 400。
 *
 * 为什么用固定档位而不是"按视野宽度实时算"：`ST_SnapToGrid` 的网格锚定在
 * 绝对坐标（cellSize 的整数倍）上。只要 cellSize 不变，拖动地图时格子**纹丝不动**；
 * 一旦 cellSize 变成任意小数，网格锚点跟着变，缩放时整个网格就会"抖"。
 *
 * 为什么最粗档必须是 5（而不是 0.05）：**能覆盖的最大视野宽度 = 最粗档 × 目标格数**。
 * 5° × 80 = 400° > 地球一圈 360°，所以任何视野（含全球视野）都挑得出档；
 * 若最粗档只有 0.05°（只能覆盖 4°），用户一打开地图就是全球视野，点「密度」直接 400。
 */
export const LADDER = [5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001]

/**
 * 按视野宽度挑一档：阶梯里 ≥ (视野宽度 ÷ 目标格数) 的最小那一档。
 * 视野比最粗档还宽时退回最粗档（宁可格子粗，也不要算出一堆格子）。
 */
export function pickCellSize(viewWidthDeg, targetAcross = 80) {
  const need = viewWidthDeg / targetAcross
  let best = -1
  for (const v of LADDER) {          // 从粗到细
    if (v >= need) best = v
    else break
  }
  return best > 0 ? best : LADDER[0]
}

/**
 * 对数归一化：value → [0, 1]。
 *
 * 为什么必须用对数而不是线性：实测数据极度偏斜（北京 0.002° 网格里
 * 轨迹条数中位数 2、最大 152；点数中位数 28、最大 14186）。
 * 线性色阶下"数值最小的那一半格子"平均深浅只有 0.008 —— 等于白纸，
 * 整条路网是看不见的。对数下是 0.153，结构立刻显出来。
 */
export function densityRatio(value, maxValue) {
  const v = Number(value)
  const m = Number(maxValue)
  if (!Number.isFinite(v) || !Number.isFinite(m) || m <= 0) return 0
  if (v <= 0) return 0
  const r = Math.log1p(v) / Math.log1p(m)
  return Math.max(0, Math.min(1, r))
}

/** 图例色带：浅米黄 → 深红（与热点色系一致） */
const RAMP = [
  [0.0, [0xff, 0xf7, 0xe8]],
  [0.25, [0xff, 0xd6, 0x8a]],
  [0.5, [0xff, 0x9f, 0x0a]],
  [0.75, [0xe8, 0x50, 0x1e]],
  [1.0, [0x9e, 0x00, 0x1b]],
]

/** t ∈ [0,1] → CSS 颜色字符串 */
export function rampColor(t) {
  const x = Math.max(0, Math.min(1, Number(t) || 0))
  for (let i = 0; i < RAMP.length - 1; i++) {
    const [a, ca] = RAMP[i]
    const [b, cb] = RAMP[i + 1]
    if (x <= b) {
      const k = b === a ? 0 : (x - a) / (b - a)
      const c = ca.map((v, j) => Math.round(v + (cb[j] - v) * k))
      return `rgb(${c[0]},${c[1]},${c[2]})`
    }
  }
  const last = RAMP[RAMP.length - 1][1]
  return `rgb(${last[0]},${last[1]},${last[2]})`
}

/** 图例的上限：取本次响应里的最大 value；空数据兜底 1（避免除零） */
export function legendMax(cells) {
  if (!Array.isArray(cells) || cells.length === 0) return 1
  let m = 0
  for (const c of cells) m = Math.max(m, Number(c.value) || 0)
  return m > 0 ? m : 1
}

/**
 * 图例刻度：在 1 ~ max 之间取几个"好读"的数。
 *
 * ⚠️ 图例必须写出**绝对刻度**。因为归一化用的是"本次响应的最大值"，
 * 所以颜色只在**同一视野内**可比；跨视野看绝对值只能靠读图例 ——
 * 这一点写进了设计文档的「已知限制」。
 */
export function legendTicks(maxValue) {
  const m = Math.max(1, Number(maxValue) || 1)
  const candidates = [1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000]
  const ticks = candidates.filter((v) => v <= m)
  if (ticks.length === 0 || ticks[ticks.length - 1] < m) ticks.push(m)
  // 最多 6 个：均匀抽稀
  if (ticks.length > 6) {
    const step = Math.ceil(ticks.length / 6)
    return ticks.filter((_, i) => i % step === 0)
  }
  return ticks
}

/** 格子中心 ± cellSize/2 → 矩形的四至 */
export function cellRect(lon, lat, cellSize) {
  const h = cellSize / 2
  return { west: lon - h, east: lon + h, south: lat - h, north: lat + h }
}

/** 数字加千分位 */
export function formatCount(n) {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  return Number(n).toLocaleString('en-US')
}

/** 时段预设。`value` 为空表示全天（不传 hourFrom/hourTo） */
export const HOUR_PRESETS = [
  { value: '', label: '全天', hourFrom: null, hourTo: null },
  { value: '7-9', label: '早高峰 7-9', hourFrom: 7, hourTo: 9 },
  { value: '10-16', label: '白天 10-16', hourFrom: 10, hourTo: 16 },
  { value: '17-22', label: '晚间 17-22', hourFrom: 17, hourTo: 22 },
]

/** 口径选项。默认 tracks —— 场景 3 问的是"哪些路段人最多"，轨迹条数才对应"路段的繁忙度" */
export const METRIC_OPTIONS = [
  { value: 'tracks', label: '按轨迹数' },
  { value: 'points', label: '按点数' },
]
