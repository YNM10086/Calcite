/**
 * lib/density.js 的回归测试。
 *
 * 零依赖，只用 node 自带的 assert —— 和 check-playback / check-chart / check-hotspot 一个路子。
 * 跑法：node scripts/check-density.mjs
 */
import assert from 'node:assert/strict'
import {
  LADDER,
  pickCellSize,
  densityRatio,
  rampColor,
  legendMax,
  legendTicks,
  cellRect,
  formatCount,
  HOUR_PRESETS,
  METRIC_OPTIONS,
} from '../src/lib/density.js'

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

// ---------------------------------------------------------------- 阶梯与挑档
t('阶梯有 15 档，且从粗到细', () => {
  /*
   * 档数钉成 15 —— 必须和后端 `calcite.density.cell-ladder`
   * （backend/src/main/resources/application.yml）一模一样，多一档少一档都会 400。
   * 计划原文这里写的是 9：那是「最粗档还是 0.05°」的旧版本残留，
   * 阶梯补成 15 档（最粗 5°）修 400 bug 时漏改了这一个数字。
   */
  assert.equal(LADDER.length, 15)
  for (let i = 1; i < LADDER.length; i++) {
    assert.ok(LADDER[i] < LADDER[i - 1], `第 ${i} 档没有更细: ${LADDER}`)
  }
})

t('视野 0.16° 宽 → 0.002', () => {
  assert.equal(pickCellSize(0.16, 80), 0.002)
})

t('视野 0.01° 宽 → 0.0002', () => {
  assert.equal(pickCellSize(0.01, 80), 0.0002)
})

t('视野 4° 宽 → 0.05', () => {
  assert.equal(pickCellSize(4, 80), 0.05)
})

t('视野比最粗档还宽 → 退回最粗档，不返回 0 或负数', () => {
  /*
   * 兜底分支：只有"荒谬地宽"的视野才会走到这里。
   * 最粗档 5° × 目标 80 格 = 能覆盖 400°，而地球一圈也才 360° ——
   * 所以正常情况下永远走不到兜底。
   * 但它必须存在，否则 pickCellSize 会返回 -1，后面全部算错。
   */
  assert.equal(pickCellSize(1000, 80), 5)
})

t('任何视野挑出的档都不会超过目标格数（含全球视野）', () => {
  /*
   * ⚠️ 范围必须一路覆盖到【全球视野 360°】。
   * 如果阶梯最粗档不够粗（比如只到 0.05°），那么视野 > 0.05×80 = 4° 时就会退回最粗档、
   * 算出几百万个格子 —— 后端直接 400。而用户一打开地图就是全球视野。
   * 这个 bug 在写计划时真的发生过（阶梯配窄了），被执行的子代理抓出来。
   */
  for (const w of [0.005, 0.01, 0.05, 0.16, 0.5, 1, 4, 20, 90, 180, 360]) {
    const cell = pickCellSize(w, 80)
    assert.ok(w / cell <= 80 + 1e-9, `视野 ${w} 挑了 ${cell} → ${w / cell} 格`)
  }
})

// ---------------------------------------------------------------- 对数色阶
t('对数归一化：0 → 0，max → 1', () => {
  assert.equal(densityRatio(0, 100), 0)
  assert.equal(densityRatio(100, 100), 1)
})

t('对数归一化：中低值被明显拉开（这正是选对数而不是线性的理由）', () => {
  // 线性下 10/1000 = 0.01，几乎看不见；对数下应该 > 0.3
  const lin = 10 / 1000
  const log = densityRatio(10, 1000)
  assert.ok(lin < 0.02, '线性确实很小')
  assert.ok(log > 0.3, `对数应该明显更大，实得 ${log}`)
})

t('对数归一化：单调不减', () => {
  let prev = -1
  for (const v of [0, 1, 2, 5, 10, 50, 100, 1000]) {
    const r = densityRatio(v, 1000)
    assert.ok(r >= prev, `${v} 反而变小了`)
    prev = r
  }
})

t('max 为 0 或非法 → 全部返回 0，不产生 NaN', () => {
  assert.equal(densityRatio(5, 0), 0)
  assert.equal(densityRatio(5, null), 0)
  assert.ok(Number.isFinite(densityRatio(0, 0)))
})

t('value 超过 max → 夹到 1，不越界', () => {
  assert.equal(densityRatio(500, 100), 1)
})

t('归一化结果永远在 [0,1] 内', () => {
  for (const [v, m] of [[0, 1], [1, 1], [1e9, 1e9], [-5, 100], [3, 2]]) {
    const r = densityRatio(v, m)
    assert.ok(r >= 0 && r <= 1, `densityRatio(${v}, ${m}) = ${r}`)
  }
})

// ---------------------------------------------------------------- 图例
t('图例最大值取本次响应里的最大 value', () => {
  assert.equal(legendMax([{ value: 3 }, { value: 11 }, { value: 7 }]), 11)
})

t('图例最大值为空时兜底 1（不返回 0，避免除零）', () => {
  assert.equal(legendMax([]), 1)
  assert.equal(legendMax(null), 1)
})

t('图例刻度是升序、且在 1~max 之间', () => {
  const ticks = legendTicks(152)
  assert.ok(ticks.length >= 3)
  for (let i = 1; i < ticks.length; i++) {
    assert.ok(ticks[i] > ticks[i - 1], `刻度没升序: ${ticks}`)
  }
  assert.ok(ticks[0] >= 1)
  assert.ok(ticks[ticks.length - 1] <= 152)
})

t('图例刻度数量不会爆炸（最多 6 个）', () => {
  for (const m of [1, 5, 152, 14186, 1e6]) {
    assert.ok(legendTicks(m).length <= 6, `max=${m} 得到 ${legendTicks(m).length} 个刻度`)
  }
})

// ---------------------------------------------------------------- 格子矩形
t('格子矩形以中心 ± cellSize/2 展开', () => {
  /*
   * ⚠️ 这里用容差而不是严格相等 —— 计划原文写的是 assert.equal，但那个断言
   * **物理上无法通过**：116.296 + 0.001 在 IEEE754 里就是 116.29700000000001
   * （差 1.4e-14，因为 116.296 本身存不下）。
   * 实现是对的（契约就是 lon ± cellSize/2），错的是拿十进制字面量做严格相等。
   * 容差 1e-12 ≈ 0.1 微米，比任何真实需求都严，仍然钉得住
   * 「方向、半格、经纬别弄反」这三类真 bug；下一条测试用的也是同一个数。
   */
  const r = cellRect(116.296, 40.012, 0.002)
  const near = (actual, expected, name) => {
    assert.ok(Math.abs(actual - expected) < 1e-12, `${name}: ${actual} ≠ ${expected}`)
  }
  near(r.west, 116.295, 'west')
  near(r.east, 116.297, 'east')
  near(r.south, 40.011, 'south')
  near(r.north, 40.013, 'north')
})

t('格子矩形宽高都等于 cellSize', () => {
  const r = cellRect(116.296, 40.012, 0.002)
  assert.ok(Math.abs((r.east - r.west) - 0.002) < 1e-12)
  assert.ok(Math.abs((r.north - r.south) - 0.002) < 1e-12)
})

// ---------------------------------------------------------------- 格式化与选项
t('数量格式化', () => {
  assert.equal(formatCount(7), '7')
  assert.equal(formatCount(1234), '1,234')
  assert.equal(formatCount(286019), '286,019')
  assert.equal(formatCount(null), '—')
})

t('时段预设包含「全天」且小时范围合法', () => {
  const all = HOUR_PRESETS.find((p) => p.value === '')
  assert.ok(all, '必须有「全天」这一项')
  for (const p of HOUR_PRESETS) {
    if (p.hourFrom != null) {
      assert.ok(p.hourFrom >= 0 && p.hourFrom <= 23)
      assert.ok(p.hourTo >= p.hourFrom && p.hourTo <= 23)
    }
  }
})

t('时段预设里有早高峰 7-9', () => {
  const m = HOUR_PRESETS.find((p) => p.hourFrom === 7 && p.hourTo === 9)
  assert.ok(m, '场景 3 就是早高峰，必须有这一项')
})

t('口径选项就是 tracks / points 两个', () => {
  assert.deepEqual(METRIC_OPTIONS.map((o) => o.value).sort(), ['points', 'tracks'])
})

// ---------------------------------------------------------------- 色带取色
/*
 * rampColor 被 DensityLegend（图例色条）和 CesiumGlobe（每个格子的填充色）
 * 共同使用。如果它坏了，整张图会变成同一个颜色 —— 所以必须测。
 */
t('色带两端：t=0 是最浅、t=1 是最深', () => {
  const lo = rampColor(0)
  const hi = rampColor(1)
  assert.equal(lo, 'rgb(255,247,232)')
  assert.equal(hi, 'rgb(158,0,27)')
})

t('色带越深红色分量占比越高（保证"越热越红"）', () => {
  const mid = rampColor(0.5)
  assert.ok(mid.startsWith('rgb('), mid)
  // 深红那端的绿色分量应该明显低于浅色那端
  const g = (c) => Number(c.split(',')[1])
  assert.ok(g(rampColor(1)) < g(rampColor(0)), '深色端的绿分量应该更低')
})

t('色带在 [0,1] 之外也不崩，返回字符串', () => {
  for (const t of [-5, 0, 0.5, 1, 9, null, undefined, NaN]) {
    const c = rampColor(t)
    assert.ok(typeof c === 'string' && c.startsWith('rgb('), `t=${t} → ${c}`)
  }
})

console.log('')
console.log(`${pass} 项通过，${fails.length} 项失败`)
if (fails.length) {
  fails.forEach((f) => console.log('  - ' + f))
  process.exit(1)
}
