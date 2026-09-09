// 纯逻辑的回归测试：不依赖任何测试框架，node 直接跑
// 用法：在 frontend 目录执行  node scripts/check-playback.mjs
import assert from 'node:assert/strict'
import {
  canPlay,
  computeMultiplier,
  formatClock,
  progressOf,
  timeRange,
  toMs,
} from '../src/lib/playback.js'

let passed = 0
let failed = 0

function check(name, fn) {
  try {
    fn()
    passed++
    console.log('  \u2713 ' + name)
  } catch (e) {
    failed++
    console.error('  \u2717 ' + name + '\n      ' + e.message)
  }
}

const ISO_A = '2026-09-07T23:30:00Z'
const ISO_B = '2026-09-08T00:20:00Z' // 比 A 晚 50 分钟

console.log('toMs')
check('ISO 字符串转毫秒', () => {
  assert.equal(toMs(ISO_A), Date.UTC(2026, 8, 7, 23, 30, 0))
})
check('空值返回 null', () => {
  assert.equal(toMs(null), null)
  assert.equal(toMs(''), null)
})
check('解析不了返回 null', () => {
  assert.equal(toMs('不是时间'), null)
})

console.log('timeRange')
check('两个点给出范围', () => {
  const r = timeRange([{ recordedAt: ISO_A }, { recordedAt: ISO_B }])
  assert.equal(r.startMs, Date.UTC(2026, 8, 7, 23, 30, 0))
  assert.equal(r.endMs, Date.UTC(2026, 8, 8, 0, 20, 0))
})
check('顺序颠倒也能算出范围', () => {
  const r = timeRange([{ recordedAt: ISO_B }, { recordedAt: ISO_A }])
  assert.equal(r.startMs, Date.UTC(2026, 8, 7, 23, 30, 0))
})
check('少于两个点返回 null', () => {
  assert.equal(timeRange([{ recordedAt: ISO_A }]), null)
  assert.equal(timeRange([]), null)
  assert.equal(timeRange(null), null)
})
check('有点缺时间戳返回 null', () => {
  assert.equal(timeRange([{ recordedAt: ISO_A }, { recordedAt: null }]), null)
})
check('时间跨度为零返回 null', () => {
  assert.equal(timeRange([{ recordedAt: ISO_A }, { recordedAt: ISO_A }]), null)
})

console.log('canPlay')
check('时间齐全可以回放', () => {
  assert.equal(canPlay([{ recordedAt: ISO_A }, { recordedAt: ISO_B }]), true)
})
check('缺时间戳不能回放', () => {
  assert.equal(canPlay([{ recordedAt: ISO_A }, {}]), false)
})

console.log('computeMultiplier')
check('3000 秒轨迹 60 秒播完 = 50 倍', () => {
  const start = Date.UTC(2026, 8, 7, 23, 30, 0)
  const end = start + 3000 * 1000
  assert.equal(computeMultiplier(start, end, 60), 50)
})
check('范围非法时退回 1 倍', () => {
  assert.equal(computeMultiplier(100, 100), 1)
  assert.equal(computeMultiplier(200, 100), 1)
})

console.log('progressOf')
check('中点 = 0.5', () => {
  assert.equal(progressOf(1500, 1000, 2000), 0.5)
})
check('超出范围会被夹住', () => {
  assert.equal(progressOf(9999, 1000, 2000), 1)
  assert.equal(progressOf(1, 1000, 2000), 0)
})
check('范围非法时返回 0', () => {
  assert.equal(progressOf(5, 1000, 1000), 0)
})

console.log('formatClock')
check('毫秒转 HH:MM:SS（本地时区）', () => {
  assert.equal(formatClock(new Date(2026, 0, 2, 3, 4, 5).getTime()), '03:04:05')
})
check('空值给占位符', () => {
  assert.equal(formatClock(null), '--:--:--')
})

console.log('')
console.log(passed + ' 项通过，' + failed + ' 项失败')
if (failed > 0) process.exitCode = 1
