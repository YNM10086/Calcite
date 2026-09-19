/**
 * 轨迹相似度的纯计算模块。
 *
 * 只放「输入 → 输出」的函数，不碰 Vue、不碰 Cesium、不碰浏览器 API，
 * 所以能用 node 直接跑测试（scripts/check-similarity.mjs）。
 */
import { rampColor } from './density.js'

/**
 * 相似度 → [0, 1]。
 *
 * ⚠️ 这里是**线性**的，和密度那边的**对数**色阶不同 —— 因为两者性质不一样：
 * 密度是**无界计数**（中位数 2、最大 152，差 76 倍，线性下等于白纸）；
 * 而相似度本身已经是 **0~100 的百分比**，天然有界、分布也均匀（实测 91/84/70/63/…），
 * 再压一次反而看不出 91% 和 84% 的区别。
 */
export function simRatio(similarity) {
  const v = Number(similarity)
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(1, v / 100))
}

/**
 * 相似度 → 颜色。复用密度那套色带（越红越"热"），语义一致：
 * 越相似越红，一眼就能看出哪几条和主线重合。
 *
 * 为什么不自己再写一套色带：色带是"跨模块的视觉契约"，
 * 密度和相似度用同一个 rampColor 才能保证图例、格子、圆圈看起来是一套东西；
 * 复制一份出来早晚会两边不一致。
 */
export function simColor(similarity) {
  return rampColor(simRatio(similarity))
}

/**
 * 相差天数的文案。
 *
 * ⚠️ 必须先挡 null/undefined，再挡 NaN/负数 —— 计划原文只判了
 * `Number.isFinite`，但 `Number(null) === 0` 是有限数，会让"没有日期差"
 * 静默显示成「同一天」（把"缺数据"说成了"同一天"，是**错的事实**而不是错格式）。
 * 所以这里和 density.js 的 formatCount 用同一个写法：先 `== null` 兜底。
 */
export function formatDays(daysAway) {
  if (daysAway == null) return '—'
  const v = Number(daysAway)
  if (!Number.isFinite(v) || v < 0) return '—'
  if (v === 0) return '同一天'
  return `相差 ${v} 天`
}

/**
 * 百分比文案，保留一位小数（91.10 → '91.1%'，100.0 → '100%'）。
 *
 * 同样先挡 null/undefined：`Number(null) === 0` 会输出 '0%'，
 * 那是在断言"两条轨迹完全不相似"，而真实语义是"这个值还没算出来"。
 */
export function formatPct(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const r = Math.round(n * 10) / 10
  return (Number.isInteger(r) ? String(r) : r.toFixed(1)) + '%'
}

/**
 * 按最低相似度筛选。
 *
 * 返回**新数组**（不改动入参）—— 调用的地方是 Vue 的 computed，
 * 改动原数组会让缓存失效、白白触发重渲染。
 *
 * @param {Array} matches 匹配列表（已按相似度降序）
 * @param {number} minSimilarity 最低相似度（0 表示不过滤）
 */
export function filterMatches(matches, minSimilarity) {
  if (!Array.isArray(matches)) return []
  const min = Number(minSimilarity)
  if (!Number.isFinite(min) || min <= 0) return matches.slice()
  return matches.filter((m) => Number(m?.similarity) >= min)
}

/**
 * 界面上的筛选档位。
 *
 * 实测（track 20 对比 197 条）：≥90% 有 1 条、≥70% 有 3 条、≥50% 有 15 条。
 * 默认给 **50%** —— 既不空、也不至于刷屏。
 */
export const SIM_FILTERS = [
  { value: 90, label: '≥ 90%（几乎重合）' },
  { value: 70, label: '≥ 70%（大部分重合）' },
  { value: 50, label: '≥ 50%（有实质重合）' },
  { value: 0, label: '全部' },
]
