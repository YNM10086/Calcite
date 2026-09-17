/**
 * lib/hotspot.js 的回归测试。
 *
 * 零依赖，只用 node 自带的 assert —— 和 check-playback.mjs / check-chart.mjs 一个路子。
 * 跑法：node scripts/check-hotspot.mjs
 */
import assert from 'node:assert/strict'
import {
  hotspotColor,
  hotspotPixelSize,
  sortHotspots,
  formatDuration,
  formatSpread,
  SORT_OPTIONS,
} from '../src/lib/hotspot.js'

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

// ---------------------------------------------------------------- 颜色映射
t('1 条轨迹 → 黄色', () => {
  assert.equal(hotspotColor(1), '#ffd60a')
})

t('2 条轨迹 → 橙色', () => {
  assert.equal(hotspotColor(2), '#ff9f0a')
})

t('3 条轨迹 → 红色', () => {
  assert.equal(hotspotColor(3), '#ff375f')
})

t('5 条轨迹 → 仍是红色（封顶，不会越界）', () => {
  assert.equal(hotspotColor(5), '#ff375f')
})

t('0 或空值 → 兜底灰色，不抛异常', () => {
  assert.equal(hotspotColor(0), '#86868b')
  assert.equal(hotspotColor(null), '#86868b')
  assert.equal(hotspotColor(undefined), '#86868b')
})

// ---------------------------------------------------------------- 点大小映射
t('2 次 → 20 像素', () => {
  assert.equal(hotspotPixelSize(2), 20)
})

t('4 次 → 32 像素（比 2 次大，说明越大越热）', () => {
  assert.equal(hotspotPixelSize(4), 32)
})

t('点大小随次数单调不减', () => {
  const sizes = [1, 2, 3, 4, 5].map(hotspotPixelSize)
  for (let i = 1; i < sizes.length; i++) {
    assert.ok(sizes[i] >= sizes[i - 1], `第 ${i} 项变小了: ${sizes}`)
  }
})

t('次数为 0 / 空值 → 最小值兜底，不返回负数或 NaN', () => {
  assert.equal(hotspotPixelSize(0), 14)
  assert.equal(hotspotPixelSize(null), 14)
})

// ---------------------------------------------------------------- 排序
const SAMPLE = [
  { rank: 1, visitCount: 4, trackCount: 3, totalDurationS: 1730 },
  { rank: 2, visitCount: 3, trackCount: 3, totalDurationS: 1228 },
  { rank: 3, visitCount: 2, trackCount: 1, totalDurationS: 650 },
]

t('按轨迹数排序 → 3,3,1', () => {
  const r = sortHotspots(SAMPLE, 'trackCount').map((h) => h.trackCount)
  assert.deepEqual(r, [3, 3, 1])
})

t('按次数排序 → 4,3,2', () => {
  const r = sortHotspots(SAMPLE, 'visitCount').map((h) => h.visitCount)
  assert.deepEqual(r, [4, 3, 2])
})

t('按时长排序 → 1730,1228,650', () => {
  const r = sortHotspots(SAMPLE, 'totalDurationS').map((h) => h.totalDurationS)
  assert.deepEqual(r, [1730, 1228, 650])
})

t('排序不改动原数组（无副作用）', () => {
  const before = SAMPLE.map((h) => h.rank)
  sortHotspots(SAMPLE, 'totalDurationS')
  assert.deepEqual(SAMPLE.map((h) => h.rank), before)
})

t('未知排序键 → 退回按轨迹数，不抛异常', () => {
  const r = sortHotspots(SAMPLE, '不存在的键').map((h) => h.trackCount)
  assert.deepEqual(r, [3, 3, 1])
})

t('空数组 / null → 返回空数组', () => {
  assert.deepEqual(sortHotspots([], 'visitCount'), [])
  assert.deepEqual(sortHotspots(null, 'visitCount'), [])
})

// ---------------------------------------------------------------- 格式化
t('时长 1730 秒 → 29 分钟（1730/60 = 28.83 四舍五入）', () => {
  assert.equal(formatDuration(1730), '29 分钟')
})

t('时长 650 秒 → 11 分钟', () => {
  assert.equal(formatDuration(650), '11 分钟')
})

t('超过一小时显示小时+分钟', () => {
  assert.equal(formatDuration(3900), '1 小时 5 分')
})

t('空值给占位符', () => {
  assert.equal(formatDuration(null), '—')
  assert.equal(formatSpread(null), '—')
})

t('散布小于 10 米显示一位小数', () => {
  assert.equal(formatSpread(9.42), '9.4 米')
})

t('散布大于 10 米取整', () => {
  assert.equal(formatSpread(58.1), '58 米')
})

// ---------------------------------------------------------------- 排序选项一致性
/*
 * SORT_OPTIONS 是给面板下拉框用的。它的 value 会直接喂给 sortHotspots，
 * 一旦和 sortHotspots 认识的键写岔了，下拉框会**静默失效**（永远退回按轨迹数排），
 * 而其他测试全都还是绿的。所以这里必须把两者的耦合钉住。
 */
t('SORT_OPTIONS 的 value 都是 sortHotspots 认识的键', () => {
  const allowed = ['trackCount', 'visitCount', 'totalDurationS']
  for (const o of SORT_OPTIONS) {
    assert.ok(allowed.includes(o.value), `未知排序键: ${o.value}`)
  }
})

t('SORT_OPTIONS 覆盖全部三个口径，一个不少', () => {
  const values = SORT_OPTIONS.map((o) => o.value).sort()
  assert.deepEqual(values, ['totalDurationS', 'trackCount', 'visitCount'])
})

t('SORT_OPTIONS 每项都有中文标签', () => {
  for (const o of SORT_OPTIONS) {
    assert.ok(o.label && o.label.length > 0, `${o.value} 缺 label`)
  }
})

console.log('')
console.log(`${pass} 项通过，${fails.length} 项失败`)
if (fails.length) {
  fails.forEach((f) => console.log('  - ' + f))
  process.exit(1)
}
