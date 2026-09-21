/**
 * lib/dataEdit.js 的回归测试。零依赖，只用 node 自带的 assert。
 * 跑法：node scripts/check-data-edit.mjs
 */
import assert from 'node:assert/strict'
import { formatPoints, formatLength, conflictText, deleteConfirmText } from '../src/lib/dataEdit.js'

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

t('点数格式化', () => {
  assert.equal(formatPoints(456), '456 个点')
  assert.equal(formatPoints(0), '0 个点')
  assert.equal(formatPoints(null), '—')
})

t('长度格式化（米 → 公里）', () => {
  assert.equal(formatLength(715), '715 米')
  assert.equal(formatLength(14948), '14.9 km')
  assert.equal(formatLength(null), '—')
})

// ---------------------------------------------------------------- 同名冲突文案
t('同名冲突文案带上两边的点数', () => {
  const s = conflictText({
    conflictType: 'SAME_NAME', existingName: '资料一',
    existingPointCount: 456, newPointCount: 623,
  })
  assert.ok(s.includes('资料一'), s)
  assert.ok(s.includes('456'), s)
  assert.ok(s.includes('623'), s)
})

t('同内容冲突文案说清"已经在库里了"', () => {
  const s = conflictText({
    conflictType: 'SAME_CONTENT', existingName: '资料一',
    existingPointCount: null, newPointCount: null,
  })
  assert.ok(s.includes('资料一'), s)
  assert.ok(s.includes('已经'), s)
})

t('冲突文案对缺字段兜底，不显示 undefined', () => {
  const s = conflictText({})
  assert.ok(!s.includes('undefined'), s)
  assert.ok(!s.includes('null'), s)
})

/*
 * ⚠️ 补的（计划原文没有这一条）：
 * 计划原文的「缺字段」用例传的是**空对象**（字段是 undefined），
 * 而真正会漏的是 **null** —— 后端 `TrackConflictResponse.newPointCount` 的
 * Javadoc 明写「解析失败时为 null」，也就是这个 null 是**真实会发生**的。
 * 判据必须是 `!s.includes('null')`：一旦拼出"（null 个点）"，比不显示还糟 ——
 * 用户会以为程序坏了，而不是"这个数还不知道"。
 */
t('冲突文案对 null 字段兜底（后端 newPointCount 解析失败就是 null）', () => {
  const s = conflictText({
    conflictType: 'SAME_NAME', existingName: '资料一',
    existingPointCount: null, newPointCount: null,
  })
  assert.ok(!s.includes('null'), s)
  assert.ok(!s.includes('undefined'), s)
  assert.ok(s.includes('资料一'), s)
  assert.ok(s.includes('未知'), s) // 缺的数要明说"未知"，不能静默变成 0
})

// ---------------------------------------------------------------- 删除确认文案
t('删除确认文案必须写出真实点数', () => {
  const s = deleteConfirmText('资料一', 456)
  assert.ok(s.includes('资料一'), s)
  assert.ok(s.includes('456'), s)
  assert.ok(s.includes('不可恢复') || s.includes('回收站'), s)
})

t('删除确认文案对缺名字兜底', () => {
  const s = deleteConfirmText(null, 0)
  assert.ok(!s.includes('undefined'), s)
  assert.ok(!s.includes('null'), s)
})

/**
 * 这条防的是"用户以为删了就没了" ——
 * 文案里必须告诉他"东西去哪了、要怎么找回来"，否则他会因为害怕而不敢用。
 */
t('删除确认文案必须告诉用户去哪找回来', () => {
  const s = deleteConfirmText('资料一', 456)
  assert.ok(s.includes('回收站') || s.includes('导出') || s.includes('重新导入'), s)
})

/*
 * ⚠️ 补的两条（计划原文没有）：
 *
 * 1) 上一条用的是 `||`，只钉住"最后那句里至少有一个词" —— 两行退路删掉一行它照样绿。
 *    而「回收站」和「重新导入」是**两条不同的退路**（本地文件 / 原始文件），
 *    少一条就等于少一条退路，所以这里用 `&&` 钉死。
 * 2) 点数为 null 时也不能拼出 "null 个轨迹点"（与 conflictText 同一个坑）。
 */
t('删除确认文案必须同时给出「回收站」和「重新导入」两条退路', () => {
  const s = deleteConfirmText('资料一', 456)
  assert.ok(s.includes('回收站'), s)
  assert.ok(s.includes('重新导入'), s)
})

t('删除确认文案对 null 点数兜底（不能写出 "null 个轨迹点"）', () => {
  const s = deleteConfirmText('资料一', null)
  assert.ok(!s.includes('null'), s)
  assert.ok(!s.includes('undefined'), s)
  assert.ok(s.includes('资料一'), s)
})

console.log('')
console.log(`${pass} 项通过，${fails.length} 项失败`)
if (fails.length) {
  fails.forEach((f) => console.log('  - ' + f))
  process.exit(1)
}
