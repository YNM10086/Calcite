/**
 * 回放的纯计算逻辑。
 *
 * 这里刻意不 import Vue、也不 import Cesium —— 全是普通函数，
 * 所以可以直接用 node 跑断言（见 frontend/scripts/check-playback.mjs），
 * 不需要装任何测试框架。
 */

/** 一条轨迹默认用多少秒播完。真实时长可能是几十分钟，所以不会等于真实时间 */
export const PLAY_SECONDS = 20

/**
 * ISO 时间字符串 → 毫秒时间戳
 * @param {string|null|undefined} iso
 * @returns {number|null} 解析不了就返回 null
 */
export function toMs(iso) {
  if (!iso) return null
  const ms = Date.parse(iso)
  return Number.isNaN(ms) ? null : ms
}

/**
 * 轨迹的时间范围
 * @param {Array} points 轨迹点，每个点要有 recordedAt
 * @returns {{startMs:number,endMs:number}|null} 点数不足、缺时间戳、跨度为零都返回 null
 */
export function timeRange(points) {
  if (!Array.isArray(points) || points.length < 2) return null
  const times = points.map((p) => toMs(p.recordedAt))
  if (times.some((t) => t === null)) return null
  const startMs = Math.min(...times)
  const endMs = Math.max(...times)
  if (endMs <= startMs) return null
  return { startMs, endMs }
}

/** 这条轨迹能不能回放 */
export function canPlay(points) {
  return timeRange(points) !== null
}

/**
 * Cesium 时钟的倍速：让整条轨迹在 playSeconds 秒内播完
 * @returns {number} 范围非法时退回 1
 */
export function computeMultiplier(startMs, endMs, playSeconds = PLAY_SECONDS) {
  if (!(endMs > startMs) || !(playSeconds > 0)) return 1
  return (endMs - startMs) / 1000 / playSeconds
}

/** 当前时刻在整条轨迹里的进度 0~1，超出范围会被夹住 */
export function progressOf(currentMs, startMs, endMs) {
  if (!(endMs > startMs)) return 0
  const ratio = (currentMs - startMs) / (endMs - startMs)
  return Math.min(1, Math.max(0, ratio))
}

/** 毫秒时间戳 → "HH:MM:SS"（浏览器本地时区） */
export function formatClock(ms) {
  if (ms == null || Number.isNaN(ms)) return '--:--:--'
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false })
}
