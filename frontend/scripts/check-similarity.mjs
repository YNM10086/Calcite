/**
 * lib/similarity.js 的回归测试。零依赖，只用 node 自带的 assert。
 * 跑法：node scripts/check-similarity.mjs
 */
import assert from 'node:assert/strict'
import {
  SIM_FILTERS,
  simColor,
  simRatio,
  formatDays,
  formatPct,
  filterMatches,
} from '../src/lib/similarity.js'

let pass = 0
const fails = []

function t(name, fn) {
  try {
    fn()
    pass++
    console.log('  \u2713 ' + name)
  } catch (e) {
    fails.push(name + ' → ' + e.message)
    console.log('  \u2717 ' + name + '  ' + e.message)
  }
}

// ---------------------------------------------------------------- 归一化
t('相似度 0% → 0，100% → 1', () => {
  assert.equal(simRatio(0), 0)
  assert.equal(simRatio(100), 1)
})

t('相似度归一化夹在 [0,1] 内', () => {
  for (const v of [-10, 0, 50, 100, 150, null, undefined, NaN]) {
    const r = simRatio(v)
    assert.ok(r >= 0 && r <= 1, `simRatio(${v}) = ${r}`)
  }
})

t('相似度归一化是线性的（不是对数）', () => {
  // 相似度本身已经是 0~100 的百分比，不需要再压缩 —— 这和无界的密度计数不同
  assert.equal(simRatio(50), 0.5)
  assert.equal(simRatio(25), 0.25)
})

// ---------------------------------------------------------------- 颜色
t('相似度越高颜色越深红', () => {
  const g = (c) => Number(c.split(',')[1])
  assert.ok(g(simColor(100)) < g(simColor(0)), '高的绿分量应更低')
})

t('simColor 在极端输入下不崩，返回 rgb 字符串', () => {
  for (const v of [-5, 0, 50, 100, 999, null, NaN]) {
    const c = simColor(v)
    assert.ok(typeof c === 'string' && c.startsWith('rgb('), `simColor(${v}) → ${c}`)
  }
})

// ---------------------------------------------------------------- 日期差文案
t('相差 0 天显示「同一天」', () => {
  assert.equal(formatDays(0), '同一天')
})

t('相差 1 天显示「相差 1 天」', () => {
  assert.equal(formatDays(1), '相差 1 天')
  assert.equal(formatDays(19), '相差 19 天')
})

t('日期差为空或负数时兜底', () => {
  assert.equal(formatDays(null), '—')
  assert.equal(formatDays(undefined), '—')
  assert.equal(formatDays(NaN), '—')
})

// ---------------------------------------------------------------- 百分比文案
t('百分比保留一位小数', () => {
  assert.equal(formatPct(91.1), '91.1%')
  assert.equal(formatPct(100), '100%')
  assert.equal(formatPct(68.46), '68.5%')
})

t('百分比非法输入兜底', () => {
  assert.equal(formatPct(null), '—')
  assert.equal(formatPct(NaN), '—')
})

// ---------------------------------------------------------------- 筛选
const SAMPLE = [
  { trackId: 39, similarity: 91.1 },
  { trackId: 35, similarity: 84.3 },
  { trackId: 16, similarity: 69.9 },
  { trackId: 24, similarity: 69.4 },
  { trackId: 6, similarity: 63.0 },
  { trackId: 99, similarity: 12.0 },
]

t('筛选 >= 90% 只剩一条', () => {
  assert.deepEqual(filterMatches(SAMPLE, 90).map((m) => m.trackId), [39])
})

t('筛选 >= 50% 保留 5 条', () => {
  assert.equal(filterMatches(SAMPLE, 50).length, 5)
})

t('筛选 >= 0 全部保留', () => {
  assert.equal(filterMatches(SAMPLE, 0).length, SAMPLE.length)
})

t('筛选不会改动原数组', () => {
  const before = JSON.stringify(SAMPLE)
  filterMatches(SAMPLE, 90)
  assert.equal(JSON.stringify(SAMPLE), before)
})

t('筛选结果仍按相似度降序', () => {
  const out = filterMatches(SAMPLE, 0).map((m) => m.similarity)
  assert.deepEqual(out, [...out].sort((a, b) => b - a))
})

t('筛选遇到空数组或非法输入不崩', () => {
  assert.deepEqual(filterMatches([], 50), [])
  assert.deepEqual(filterMatches(null, 50), [])
  assert.deepEqual(filterMatches(SAMPLE, null), SAMPLE)
})

// ---------------------------------------------------------------- 筛选档位
t('筛选档位包含 90/70/50/全部 四档', () => {
  const vals = SIM_FILTERS.map((f) => f.value)
  assert.deepEqual(vals, [90, 70, 50, 0])
})

t('每个筛选档位都有中文标签', () => {
  for (const f of SIM_FILTERS) {
    assert.ok(f.label && f.label.length > 0, `档位 ${f.value} 缺标签`)
  }
})

t('默认档位是 50%（实测 15 条，既不空也不刷屏）', () => {
  const def = SIM_FILTERS.find((f) => f.value === 50)
  assert.ok(def, '必须有 50% 这一档')
})

console.log('')
console.log(`${pass} 项通过，${fails.length} 项失败`)
if (fails.length) {
  fails.forEach((f) => console.log('  - ' + f))
  process.exit(1)
}
