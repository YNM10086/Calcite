// frontend/scripts/check-region.mjs
import assert from 'node:assert/strict'
import {
  DRAW_LIMIT, rectGeometry, polygonGeometry, pointGeometry, ringOf,
  sortItems, visibleItems, formatDistance, formatCount, formatDuration, spanText, emptyHint,
} from '../src/lib/region.js'

let ok = 0
let fail = 0
const fails = []
function t(name, fn) {
  try {
    fn()
    ok++
    console.log(`  ✓ ${name}`)
  } catch (e) {
    fail++
    fails.push(`${name} :: ${e.message}`)
    console.log(`  ✗ ${name}  ${e.message}`)
  }
}

t('rectGeometry 是闭合的 5 点外环', () => {
  const g = rectGeometry({ lon: 116.30, lat: 39.90 }, { lon: 116.40, lat: 40.00 })
  assert.equal(g.type, 'Polygon')
  assert.equal(g.coordinates[0].length, 5)
  assert.deepEqual(g.coordinates[0][0], g.coordinates[0][4])
})

t('rectGeometry 两个角的顺序无所谓', () => {
  const a = rectGeometry({ lon: 116.30, lat: 39.90 }, { lon: 116.40, lat: 40.00 })
  const b = rectGeometry({ lon: 116.40, lat: 40.00 }, { lon: 116.30, lat: 39.90 })
  assert.deepEqual(a.coordinates, b.coordinates)
})

t('rectGeometry 用经度当第一维、纬度当第二维', () => {
  const g = rectGeometry({ lon: 116.30, lat: 39.90 }, { lon: 116.40, lat: 40.00 })
  assert.deepEqual(g.coordinates[0][0], [116.30, 39.90])
})

t('polygonGeometry 自动闭合环', () => {
  const g = polygonGeometry([{ lon: 0, lat: 0 }, { lon: 1, lat: 0 }, { lon: 1, lat: 1 }])
  assert.equal(g.coordinates[0].length, 4)
  assert.deepEqual(g.coordinates[0][0], g.coordinates[0][3])
})

t('polygonGeometry 已经闭合时不重复加点', () => {
  const pts = [{ lon: 0, lat: 0 }, { lon: 1, lat: 0 }, { lon: 1, lat: 1 }, { lon: 0, lat: 0 }]
  assert.equal(polygonGeometry(pts).coordinates[0].length, 4)
})

t('polygonGeometry 少于 3 个点返回 null（调用方据此不查询）', () => {
  assert.equal(polygonGeometry([{ lon: 0, lat: 0 }, { lon: 1, lat: 1 }]), null)
})

t('pointGeometry 输出经纬度顺序', () => {
  assert.deepEqual(pointGeometry(116.32, 40.00).coordinates, [116.32, 40.00])
})

t('ringOf 兼容 Polygon 与 MultiPolygon', () => {
  assert.equal(ringOf({ type: 'Polygon', coordinates: [[[0, 0], [1, 0], [0, 0]]] }).length, 3)
  assert.equal(ringOf({ type: 'MultiPolygon', coordinates: [[[[0, 0], [1, 0], [0, 0]]]] }).length, 3)
})

t('ringOf 对空/异常输入返回空数组而不是抛异常', () => {
  assert.deepEqual(ringOf(null), [])
  assert.deepEqual(ringOf({ type: 'Point', coordinates: [0, 0] }), [])
})

t('sortItems 按 insidePointCount 降序再按 trackId 升序', () => {
  const items = [
    { trackId: 9, insidePointCount: 5 },
    { trackId: 3, insidePointCount: 5 },
    { trackId: 7, insidePointCount: 1 },
  ]
  assert.deepEqual(sortItems(items).map((i) => i.trackId), [3, 9, 7])
})

t('sortItems 不改原数组', () => {
  const items = [{ trackId: 2, insidePointCount: 1 }, { trackId: 1, insidePointCount: 2 }]
  const copy = JSON.parse(JSON.stringify(items))
  sortItems(items)
  assert.deepEqual(items, copy)
})

t('visibleItems 默认只给 20 条', () => {
  const many = Array.from({ length: 232 }, (_, i) => ({ trackId: i + 1, insidePointCount: 1 }))
  assert.equal(visibleItems(many).length, DRAW_LIMIT)
  assert.equal(visibleItems(many).length, 20)
})

t('visibleItems 少于上限时全给', () => {
  assert.equal(visibleItems([{ trackId: 1, insidePointCount: 1 }]).length, 1)
})

t('formatDistance 在 1km 附近切换单位', () => {
  assert.equal(formatDistance(850), '850 m')
  assert.equal(formatDistance(1500), '1.5 km')
  assert.equal(formatDistance(1234567.8), '1234.6 km')
})

// ⭐ 先取整再比阈值（本轮修复）：只比原始值时 999.6 落进"米"档、又被 round 成 `1000 m`，
// 而 1000 本身是 `1.0 km` —— 两个相邻的值给出自相矛盾的档位。
t('formatDistance 在 1000 附近自洽（先取整再比阈值）', () => {
  assert.equal(formatDistance(999.6), '1.0 km')
  assert.equal(formatDistance(1000), '1.0 km')
  assert.equal(formatDistance(999.4), '999 m')
  assert.equal(formatDistance(0), '0 m')
})

t('formatDistance 对 null/NaN 给破折号而不是 0', () => {
  assert.equal(formatDistance(null), '—')
  assert.equal(formatDistance(undefined), '—')
  assert.equal(formatDistance(NaN), '—')
})

// ⭐ bad() 现在也要求 typeof === 'number'（本轮修复）：字符串不再被算术悄悄用掉
// （`formatDistance('')` 修前得到 `'0 m'` —— 把"没有这个数"显示成真数据）。
t('formatDistance / formatCount 对字符串也给破折号（不被 Number() 吃掉）', () => {
  assert.equal(formatDistance(''), '—')
  assert.equal(formatDistance('850'), '—')
  assert.equal(formatCount('232'), '—')
  assert.equal(formatCount(''), '—')
})

t('formatCount 对 null 给破折号（Number(null)===0 这个坑）', () => {
  assert.equal(formatCount(232), '232')
  assert.equal(formatCount(0), '0')
  assert.equal(formatCount(null), '—')
  assert.equal(formatCount(undefined), '—')
})

// ⭐ 规格 6.5 的"时长"列（本轮新增导出）。分档 + 向下取整。
t('formatDuration 分档：秒 / 分钟 / 小时（向下取整，不越档）', () => {
  assert.equal(formatDuration(59), '59 秒')
  assert.equal(formatDuration(59.9), '59 秒')     // 四舍五入会变成 60 秒 → 越档
  assert.equal(formatDuration(60), '1 分钟')
  assert.equal(formatDuration(3599), '59 分钟')   // 四舍五入会变成 60 分钟 → 越档
  assert.equal(formatDuration(3600), '1 小时')
  assert.equal(formatDuration(3660), '1 小时 1 分')
  assert.equal(formatDuration(7320), '2 小时 2 分')
  assert.equal(formatDuration(0), '0 秒')
})

t('formatDuration 对非法值给破折号而不是 "0 秒"', () => {
  assert.equal(formatDuration(null), '—')
  assert.equal(formatDuration(undefined), '—')
  assert.equal(formatDuration(NaN), '—')
  assert.equal(formatDuration(Infinity), '—')
  assert.equal(formatDuration(-1), '—')
  assert.equal(formatDuration('3600'), '—')
})

t('spanText 只取日期部分', () => {
  assert.equal(spanText('2008-10-23T02:53:04Z', '2009-07-05T02:53:07Z'), '2008-10-23 → 2009-07-05')
})

t('spanText 缺任一端都给破折号', () => {
  assert.equal(spanText(null, '2009-07-05T02:53:07Z'), '—')
  assert.equal(spanText('2008-10-23T02:53:04Z', null), '—')
})

t('emptyHint 说明是空区域而不是报错', () => {
  assert.match(emptyHint(), /没有轨迹/)
})

console.log()
console.log(`${ok} 项通过，${fail} 项失败`)
if (fails.length) {
  console.log('失败明细：')
  for (const f of fails) console.log('  -', f)
  process.exit(1)
}
