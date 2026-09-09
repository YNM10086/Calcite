// 曲线纯逻辑的回归检查：不依赖任何测试框架，node 直接跑
// 用法：在 frontend 目录执行  node scripts/check-chart.mjs
import assert from 'node:assert/strict'
import {
  domainOf,
  formatTick,
  formatValue,
  msAtX,
  niceTicks,
  pathOf,
  scaleX,
  scaleY,
  seriesOf,
  tickDigits,
  timeTicks,
  valueAt,
} from '../src/lib/chart.js'

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

const T0 = Date.UTC(2026, 8, 7, 23, 30, 0) // 07:30:00 本地
const iso = (ms) => new Date(ms).toISOString()

/* ============ seriesOf ============ */
console.log('seriesOf')
check('抽出非空值并按时间升序', () => {
  const pts = [
    { recordedAt: iso(T0 + 2000), speedMps: 3.2 },
    { recordedAt: iso(T0), speedMps: 3.0 },
    { recordedAt: iso(T0 + 4000), speedMps: 3.1 },
  ]
  const s = seriesOf(pts, 'speedMps')
  assert.equal(s.length, 3)
  assert.equal(s[0].value, 3.0)
  assert.equal(s[0].ms, T0)
  assert.equal(s[2].value, 3.1)
})
check('跳过 null / undefined / 空串', () => {
  const pts = [
    { recordedAt: iso(T0), speedMps: null },
    { recordedAt: iso(T0 + 1000), speedMps: undefined },
    { recordedAt: iso(T0 + 2000), speedMps: '' },
    { recordedAt: iso(T0 + 3000), speedMps: 3.5 },
  ]
  const s = seriesOf(pts, 'speedMps')
  assert.equal(s.length, 1)
  assert.equal(s[0].value, 3.5)
})
check('null 不能变成 0', () => {
  const s = seriesOf([{ recordedAt: iso(T0), speedMps: null }], 'speedMps')
  assert.equal(s.length, 0)
})
check('跳过缺时间戳的点', () => {
  const s = seriesOf([{ recordedAt: null, speedMps: 3 }, { recordedAt: iso(T0), speedMps: 4 }], 'speedMps')
  assert.equal(s.length, 1)
})
check('非数组输入返回空数组', () => {
  assert.deepEqual(seriesOf(null, 'speedMps'), [])
  assert.deepEqual(seriesOf(undefined, 'speedMps'), [])
})

/* ============ domainOf ============ */
console.log('domainOf')
check('上下各留 10% 空白', () => {
  const d = domainOf([10, 20])
  assert.equal(d.min, 9)
  assert.equal(d.max, 21)
})
check('所有值相同也要撑开', () => {
  const d = domainOf([3, 3, 3])
  assert.ok(d.max > d.min)
  assert.equal(d.min, 2.7)
  assert.equal(d.max, 3.3)
})
check('空数组返回 null', () => {
  assert.equal(domainOf([]), null)
  assert.equal(domainOf([null, undefined]), null)
})

/* ============ niceTicks ============ */
console.log('niceTicks')
check('海拔 30.4~49.6 给出 35/40/45', () => {
  assert.deepEqual(niceTicks(30.4, 49.6, 3), [35, 40, 45])
})
check('速度 2.86~3.34 给出 3 和 3.2', () => {
  assert.deepEqual(niceTicks(2.86, 3.34, 3), [3, 3.2])
})
check('范围非法返回空数组', () => {
  assert.deepEqual(niceTicks(5, 5), [])
  assert.deepEqual(niceTicks(5, 1), [])
  assert.deepEqual(niceTicks(undefined, 10), [])
})
check('刻度都是整步长的倍数，不出现浮点毛刺', () => {
  const ticks = niceTicks(0, 1, 4)
  for (const t of ticks) {
    assert.equal(t, Number(t.toFixed(6)), '刻度有浮点毛刺: ' + t)
  }
})

/* ============ timeTicks ============ */
console.log('timeTicks')
check('首尾正好落在两端', () => {
  const ticks = timeTicks(T0, T0 + 3000000, 6)
  assert.equal(ticks.length, 6)
  assert.equal(ticks[0], T0)
  assert.equal(ticks[5], T0 + 3000000)
})
check('范围非法返回空数组', () => {
  assert.deepEqual(timeTicks(T0, T0), [])
  assert.deepEqual(timeTicks(T0, T0 - 1), [])
})

/* ============ tickDigits ============ */
console.log('tickDigits')
check('步长 5 → 0 位小数', () => {
  assert.equal(tickDigits([35, 40, 45]), 0)
})
check('步长 0.2 → 1 位小数', () => {
  assert.equal(tickDigits([3, 3.2]), 1)
})
check('步长 2.5 → 1 位小数', () => {
  assert.equal(tickDigits([35, 37.5, 40]), 1)
})
check('刻度不足两个 → 0', () => {
  assert.equal(tickDigits([3]), 0)
  assert.equal(tickDigits([]), 0)
})

/* ============ scaleX ============ */
console.log('scaleX')
check('两端映射正确', () => {
  const x = scaleX(T0, T0 + 1000, 46, 1542)
  assert.equal(x(T0), 46)
  assert.equal(x(T0 + 1000), 1588)
})
check('中点线性', () => {
  const x = scaleX(T0, T0 + 1000, 46, 1542)
  assert.equal(x(T0 + 500), 817)
})
check('范围非法时全部落在 left', () => {
  const x = scaleX(T0, T0, 46, 1542)
  assert.equal(x(T0), 46)
  assert.equal(x(T0 + 999), 46)
})

/* ============ scaleY ============ */
console.log('scaleY')
check('最大值映射到顶端', () => {
  const y = scaleY({ min: 30, max: 50 }, 6, 44)
  assert.equal(y(50), 6)
})
check('最小值映射到底端', () => {
  const y = scaleY({ min: 30, max: 50 }, 6, 44)
  assert.equal(y(30), 50)
})
check('中间值映射到中间', () => {
  const y = scaleY({ min: 30, max: 50 }, 6, 44)
  assert.equal(y(40), 28)
})
check('domain 退化时返回中线', () => {
  const y = scaleY({ min: 5, max: 5 }, 6, 44)
  assert.equal(y(5), 28)
  assert.equal(scaleY(null, 6, 44)(1), 28)
})

/* ============ msAtX ============ */
console.log('msAtX')
check('左端 = startMs，右端 = endMs', () => {
  assert.equal(msAtX(46, T0, T0 + 1000, 46, 1542), T0)
  assert.equal(msAtX(1588, T0, T0 + 1000, 46, 1542), T0 + 1000)
})
check('中点 = 一半时长', () => {
  assert.equal(msAtX(817, T0, T0 + 1000, 46, 1542), T0 + 500)
})
check('超出绘图区被夹紧', () => {
  assert.equal(msAtX(0, T0, T0 + 1000, 46, 1542), T0)
  assert.equal(msAtX(99999, T0, T0 + 1000, 46, 1542), T0 + 1000)
})

/* ============ pathOf ============ */
console.log('pathOf')
check('两个点生成 M... L...', () => {
  const d = pathOf([{ ms: 0, value: 1 }, { ms: 1, value: 2 }], (s) => s.ms, (s) => s.value)
  assert.equal(d, 'M0,1 L1,2')
})
check('空序列返回空串', () => {
  assert.equal(pathOf([], () => 0, () => 0), '')
  assert.equal(pathOf(null, () => 0, () => 0), '')
})

/* ============ valueAt ============ */
console.log('valueAt')
check('中间值线性插值', () => {
  const s = [{ ms: 0, value: 0 }, { ms: 1000, value: 10 }]
  assert.equal(valueAt(s, 500), 5)
  assert.equal(valueAt(s, 250), 2.5)
})
check('超出两端取端点值', () => {
  const s = [{ ms: 0, value: 0 }, { ms: 1000, value: 10 }]
  assert.equal(valueAt(s, -100), 0)
  assert.equal(valueAt(s, 99999), 10)
})
check('空序列返回 null', () => {
  assert.equal(valueAt([], 0), null)
  assert.equal(valueAt(null, 0), null)
})

/* ============ formatTick ============ */
console.log('formatTick')
check('毫秒转 HH:MM（本地时区）', () => {
  assert.equal(formatTick(new Date(2026, 0, 2, 3, 4, 5).getTime()), '03:04')
})
check('非法输入返回空串', () => {
  assert.equal(formatTick(undefined), '')
})

/* ============ formatValue ============ */
console.log('formatValue')
check('固定小数位', () => {
  assert.equal(formatValue(3.14159, 2), '3.14')
  assert.equal(formatValue(41.6, 1), '41.6')
})
check('空值给破折号', () => {
  assert.equal(formatValue(null), '—')
  assert.equal(formatValue(undefined, 1), '—')
})

console.log('')
console.log(passed + ' 项通过，' + failed + ' 项失败')
if (failed > 0) process.exitCode = 1
