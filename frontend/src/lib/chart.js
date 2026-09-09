/**
 * 速度/海拔曲线的纯计算逻辑。
 *
 * 和 playback.js 一样，这里刻意不 import Vue、也不 import Cesium —— 全是普通函数，
 * 所以可以直接用 node 跑断言（见 frontend/scripts/check-chart.mjs），不需要装测试框架。
 */

/**
 * 从一个轨迹点数组里抽出某个字段的非空序列，按时间升序。
 * null / undefined / 空串一律跳过 —— 特别注意 Number(null) === 0，
 * 不先判空的话「没有速度」会被画成「速度 0」。
 * @returns {Array<{ms:number,value:number}>}
 */
export function seriesOf(points, key) {
  if (!Array.isArray(points)) return []
  const out = []
  for (const p of points) {
    if (!p) continue
    const ms = Date.parse(p.recordedAt)
    if (!Number.isFinite(ms)) continue
    const raw = p[key]
    if (raw === null || raw === undefined || raw === '') continue
    const value = Number(raw)
    if (!Number.isFinite(value)) continue
    out.push({ ms, value })
  }
  out.sort((a, b) => a.ms - b.ms)
  return out
}

/**
 * Y 轴范围：上下各留 padRatio 的空白。
 * 所有值相同时强制撑开一个跨度，否则 scaleY 会除零。
 * @returns {{min:number,max:number}|null}
 */
export function domainOf(values, padRatio = 0.1) {
  if (!Array.isArray(values) || values.length === 0) return null
  let min = Infinity
  let max = -Infinity
  for (const v of values) {
    if (!Number.isFinite(v)) continue
    if (v < min) min = v
    if (v > max) max = v
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1
    return { min: min - pad, max: max + pad }
  }
  const pad = (max - min) * padRatio
  return { min: min - pad, max: max + pad }
}

/** 某个步长下，[min, max] 里能放下几个刻度 */
function tickCount(min, max, step) {
  const first = Math.ceil(min / step) * step
  if (first > max + step * 1e-9) return 0
  return Math.floor((max - first) / step + 1e-9) + 1
}

/**
 * 取整刻度：挑一个「好看的步长」，让刻度数量接近 count。
 * 步长只可能是 1 / 2 / 2.5 / 5 / 10 乘 10 的整数次幂，
 * 所以标签不会出现 37.4213 这种丑数字。
 */
export function niceTicks(min, max, count = 3) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return []
  const target = Math.max(2, count)
  const raw = (max - min) / target
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  const candidates = [1, 2, 2.5, 5, 10].map((m) => m * mag)
  let step = candidates[candidates.length - 1]
  for (const c of candidates) {
    const n = tickCount(min, max, c)
    if (n >= 2 && n <= target + 1) {
      step = c
      break
    }
  }
  const digits = Math.max(0, -Math.floor(Math.log10(step)) + 1)
  const out = []
  const first = Math.ceil(min / step) * step
  for (let v = first; v <= max + step * 1e-9; v += step) {
    out.push(Number(v.toFixed(digits)))
  }
  return out
}

/** 时间轴刻度：把 [startMs, endMs] 均分，首尾正好落在两端 */
export function timeTicks(startMs, endMs, count = 6) {
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return []
  const n = Math.max(2, Math.floor(count))
  const step = (endMs - startMs) / (n - 1)
  const out = []
  for (let i = 0; i < n; i++) out.push(Math.round(startMs + step * i))
  out[out.length - 1] = endMs
  return out
}

/** 刻度该保留几位小数：用 toFixed 逐位试，找到第一个能精确表示步长的位数 */
export function tickDigits(ticks) {
  if (!Array.isArray(ticks) || ticks.length < 2) return 0
  let minStep = Infinity
  for (let i = 1; i < ticks.length; i++) {
    minStep = Math.min(minStep, Math.abs(ticks[i] - ticks[i - 1]))
  }
  if (!Number.isFinite(minStep) || minStep <= 0) return 0
  for (let d = 0; d <= 6; d++) {
    if (Math.abs(Number(minStep.toFixed(d)) - minStep) < 1e-9) return d
  }
  return 6
}

/** 时间 → 像素 x。范围非法时所有点都落在 left */
export function scaleX(startMs, endMs, left, width) {
  const span = endMs - startMs
  if (!(span > 0) || !(width > 0)) return () => left
  return (ms) => left + ((ms - startMs) / span) * width
}

/** 数值 → 像素 y。注意屏幕 y 轴向下，所以大的值在上面 */
export function scaleY(domain, top, height) {
  if (!domain || !(domain.max > domain.min) || !(height > 0)) return () => top + height / 2
  const span = domain.max - domain.min
  return (v) => top + height - ((v - domain.min) / span) * height
}

/** 像素 x → 时间；超出绘图区会被夹到两端 */
export function msAtX(x, startMs, endMs, left, width) {
  if (!(width > 0) || !(endMs > startMs)) return startMs
  const ratio = (x - left) / width
  return startMs + Math.min(1, Math.max(0, ratio)) * (endMs - startMs)
}

function round2(v) {
  return Math.round(v * 100) / 100
}

/** 一串点 → SVG path 的 d 字符串 */
export function pathOf(series, xOf, yOf) {
  if (!Array.isArray(series) || series.length === 0) return ''
  const parts = []
  for (let i = 0; i < series.length; i++) {
    const x = xOf(series[i], i)
    const y = yOf(series[i], i)
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue
    parts.push((parts.length === 0 ? 'M' : 'L') + round2(x) + ',' + round2(y))
  }
  return parts.join(' ')
}

/**
 * 线性插值取某时刻的值。
 * 用它而不是「最近的真实点」，是为了让游标交点精确落在游标线与数据线的交叉处。
 * 超出两端取端点值；空序列返回 null。
 */
export function valueAt(series, ms) {
  if (!Array.isArray(series) || series.length === 0) return null
  if (series.length === 1) return series[0].value
  const first = series[0]
  const last = series[series.length - 1]
  if (!Number.isFinite(ms) || ms <= first.ms) return first.value
  if (ms >= last.ms) return last.value
  for (let i = 1; i < series.length; i++) {
    const a = series[i - 1]
    const b = series[i]
    if (ms <= b.ms) {
      const span = b.ms - a.ms
      if (!(span > 0)) return b.value
      return a.value + (b.value - a.value) * ((ms - a.ms) / span)
    }
  }
  return last.value
}

/** 毫秒时间戳 → "HH:MM"（时间轴标签用） */
export function formatTick(ms) {
  if (!Number.isFinite(ms)) return ''
  const d = new Date(ms)
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

/** 数值 → 固定小数位的字符串；空值显示破折号 */
export function formatValue(v, digits = 2) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return Number(v).toFixed(digits)
}
