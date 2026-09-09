# M1 速度 / 海拔曲线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Calcite 底部加一组与回放联动的速度/海拔双图——播放时游标跟着白点走，悬停显示读数，点击曲线跳到那一刻。

**Architecture:** 三层分工，与已完成的回放功能同构：`frontend/src/lib/chart.js` 是零依赖纯计算（可用 node 秒测），`frontend/src/components/SpeedChart.vue` 是纯展示组件（props 进、SVG 出），`frontend/src/App.vue` 是唯一的「大脑」（持有 `currentMs`，把曲线点击接到已有的 `seekTo`）。不引入任何图表库。

**Tech Stack:** Vue 3.5（`<script setup>`）、手写 SVG、`ResizeObserver`；验收用 node 内置 `assert` + Playwright + Pillow。

**设计依据:** `docs/superpowers/specs/2026-09-09-m1-speed-chart-design.md`（如与本计划冲突，以设计文档为准）

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `frontend/src/lib/chart.js` | 新建 | 纯计算：序列提取、范围、刻度、坐标映射、路径生成、插值、格式化。**不 import Vue / Cesium** |
| `frontend/scripts/check-chart.mjs` | 新建 | node 内置 `assert` 的回归检查，与 `check-playback.mjs` 同构 |
| `frontend/src/components/SpeedChart.vue` | 新建 | 纯展示：两张图 + 时间轴 + 游标 + 悬停提示 + 点击 |
| `frontend/src/App.vue` | 修改 | 引入组件、传 props、接 `@seek`、把 `.status` 上移 |
| `frontend/package.json` | 修改 | 加 `check:chart` 脚本 |
| `.tmp/check-chart-pixels.py` | 新建 | Playwright + Pillow 的真实浏览器验收 |

**任务依赖**：Task 1 → Task 2（同一个文件的第二批函数）→ Task 3 → Task 4 → Task 5 → Task 6。Task 7 可与 Task 6 并行。

---

## Task 1: `chart.js` 数值层（序列、范围、刻度）

**Files:**
- Create: `frontend/src/lib/chart.js`
- Create: `frontend/scripts/check-chart.mjs`

- [ ] **Step 1: 先写失败的检查脚本**

创建 `frontend/scripts/check-chart.mjs`：

```js
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
```

> 注意：这个脚本此刻就 import 了 Task 2 才实现的函数。这是**故意的**——它会立刻报 `SyntaxError: The requested module does not provide an export named 'pathOf'`，也就是 TDD 的「红」。

- [ ] **Step 2: 跑一次，确认失败**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
node scripts/check-chart.mjs
```

Expected: `SyntaxError`，提示 `chart.js` 不存在或缺少导出。**这就是预期的红。**

- [ ] **Step 3: 写 `chart.js` 的数值层**

创建 `frontend/src/lib/chart.js`：

```js
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
```

- [ ] **Step 4: 再跑一次（此时仍会红，因为 Task 2 的函数还没写）**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
node scripts/check-chart.mjs
```

Expected: 仍然 `SyntaxError`，缺 `pathOf` / `scaleX` / `scaleY` / `msAtX` / `valueAt` / `formatTick` / `formatValue`。**不要在这一步提交。**

---

## Task 2: `chart.js` 几何层（坐标映射、路径、插值、格式化）

**Files:**
- Modify: `frontend/src/lib/chart.js`（追加到文件末尾）

- [ ] **Step 1: 追加几何层函数**

在 `frontend/src/lib/chart.js` 末尾追加：

```js
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
```

- [ ] **Step 2: 跑检查，确认变绿**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
node scripts/check-chart.mjs
```

Expected:
```
...
37 项通过，0 项失败
```

如果哪一项红了，**改实现，不要改断言**（断言是设计文档里定死的契约）。

- [ ] **Step 3: 提交**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
git add frontend/src/lib/chart.js frontend/scripts/check-chart.mjs
git commit -m "feat(chart): 曲线纯计算层 + node 回归检查

- seriesOf 跳空值（Number(null)===0 的坑已避开）
- domainOf 退化保护、niceTicks 取整步长、timeTicks 首尾对齐
- scaleX/scaleY/msAtX 坐标映射、pathOf 路径、valueAt 线性插值
- 37 项断言全绿"
```

---

## Task 3: `package.json` 加检查脚本

**Files:**
- Modify: `frontend/package.json:10`

- [ ] **Step 1: 加一行脚本**

把 `frontend/package.json` 的 `scripts` 改成：

```json
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "check:playback": "node scripts/check-playback.mjs",
    "check:chart": "node scripts/check-chart.mjs"
  },
```

- [ ] **Step 2: 验证脚本能跑**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
npm run check:chart
```

Expected: 输出 `37 项通过，0 项失败`。

- [ ] **Step 3: 提交**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
git add frontend/package.json
git commit -m "chore: 加 check:chart 脚本"
```

---

## Task 4: `SpeedChart.vue` 骨架（两张图 + 时间轴 + 网格 + 空态）

**Files:**
- Create: `frontend/src/components/SpeedChart.vue`

- [ ] **Step 1: 写组件**

创建 `frontend/src/components/SpeedChart.vue`：

```vue
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import {
  domainOf,
  formatTick,
  formatValue,
  niceTicks,
  pathOf,
  scaleX,
  scaleY,
  seriesOf,
  tickDigits,
  timeTicks,
} from '../lib/chart.js'

const props = defineProps({
  /** 轨迹点，每个点要有 recordedAt / speedMps / elevationM */
  points: { type: Array, default: () => [] },
  /** 当前时刻（毫秒），由 App 从 Cesium 时钟同步过来 */
  currentMs: { type: Number, default: 0 },
  startMs: { type: Number, default: 0 },
  endMs: { type: Number, default: 0 },
})

/* ============ 尺寸常量（像素）============ */
const CHART_H = 56 // 单张图高度
const AXIS_H = 20 // 底部时间轴刻度行
const PAD_L = 46 // 左侧留白，放 Y 轴标签
const PAD_R = 12
const INNER = 6 // 图内上下留白
const PLOT_H = CHART_H - INNER * 2

/* ============ 容器宽度：量真实像素，避免拉伸变形 ============ */
const root = ref(null)
const width = shallowRef(0)
let ro = null
let measure = null

onMounted(() => {
  if (!root.value) return
  measure = () => {
    width.value = root.value ? root.value.clientWidth : 0
  }
  measure()
  if (typeof ResizeObserver === 'function') {
    ro = new ResizeObserver(measure)
    ro.observe(root.value)
  } else {
    window.addEventListener('resize', measure)
  }
})

onBeforeUnmount(() => {
  if (ro) {
    ro.disconnect()
    ro = null
  } else if (measure) {
    window.removeEventListener('resize', measure)
  }
  measure = null
})

/* ============ 数据序列 ============ */
const speed = computed(() => seriesOf(props.points, 'speedMps'))
const elev = computed(() => seriesOf(props.points, 'elevationM'))
const hasSpeed = computed(() => speed.value.length >= 2)
const hasElev = computed(() => elev.value.length >= 2)

/* ============ 坐标映射 ============ */
const plotW = computed(() => Math.max(0, width.value - PAD_L - PAD_R))
const xOf = computed(() => scaleX(props.startMs, props.endMs, PAD_L, plotW.value))

const speedDomain = computed(() => domainOf(speed.value.map((d) => d.value)))
const elevDomain = computed(() => domainOf(elev.value.map((d) => d.value)))
const speedY = computed(() => scaleY(speedDomain.value, INNER, PLOT_H))
const elevY = computed(() => scaleY(elevDomain.value, INNER, PLOT_H))

/* ============ 折线路径 ============ */
const speedPath = computed(() =>
  pathOf(speed.value, (d) => xOf.value(d.ms), (d) => speedY.value(d.value)),
)
const elevPath = computed(() =>
  pathOf(elev.value, (d) => xOf.value(d.ms), (d) => elevY.value(d.value)),
)

/* ============ 刻度 ============ */
const speedTicks = computed(() => niceTicks(speedDomain.value?.min, speedDomain.value?.max, 3))
const elevTicks = computed(() => niceTicks(elevDomain.value?.min, elevDomain.value?.max, 3))
const speedDigits = computed(() => tickDigits(speedTicks.value))
const elevDigits = computed(() => tickDigits(elevTicks.value))

/** 时间轴标签密度按宽度定：大约每 90px 一个 */
const timeTickList = computed(() =>
  timeTicks(props.startMs, props.endMs, Math.max(2, Math.floor(plotW.value / 90) + 1)),
)
</script>

<template>
  <div ref="root" class="chart" data-testid="speed-chart">
    <!-- ============ 速度图 ============ -->
    <div class="pane" :style="{ height: CHART_H + 'px' }">
      <svg
        class="layer"
        :width="Math.max(width, 1)"
        :height="CHART_H"
        data-testid="chart-speed"
      >
        <g v-for="t in speedTicks" :key="'sg' + t">
          <line :x1="PAD_L" :x2="PAD_L + plotW" :y1="speedY(t)" :y2="speedY(t)" class="grid" />
          <text :x="PAD_L - 6" :y="speedY(t) + 3" class="ylabel">
            {{ formatValue(t, speedDigits) }}
          </text>
        </g>
        <path v-if="hasSpeed" :d="speedPath" class="line speed" />
      </svg>
      <div class="unit speed-unit">速度 m/s</div>
      <div v-if="!hasSpeed" class="empty">这条轨迹没有速度数据</div>
    </div>

    <!-- ============ 海拔图 ============ -->
    <div class="pane" :style="{ height: CHART_H + 'px' }">
      <svg
        class="layer"
        :width="Math.max(width, 1)"
        :height="CHART_H"
        data-testid="chart-elevation"
      >
        <g v-for="t in elevTicks" :key="'eg' + t">
          <line :x1="PAD_L" :x2="PAD_L + plotW" :y1="elevY(t)" :y2="elevY(t)" class="grid" />
          <text :x="PAD_L - 6" :y="elevY(t) + 3" class="ylabel">
            {{ formatValue(t, elevDigits) }}
          </text>
        </g>
        <path v-if="hasElev" :d="elevPath" class="line elev" />
      </svg>
      <div class="unit elev-unit">海拔 m</div>
      <div v-if="!hasElev" class="empty">这条轨迹没有海拔数据</div>
    </div>

    <!-- ============ 时间轴 ============ -->
    <svg class="layer" :width="Math.max(width, 1)" :height="AXIS_H" data-testid="chart-axis">
      <g v-for="t in timeTickList" :key="'t' + t">
        <line :x1="xOf(t)" :x2="xOf(t)" y1="0" y2="4" class="grid" />
        <text :x="xOf(t)" :y="15" class="xlabel">{{ formatTick(t) }}</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.chart {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 46px;
  z-index: 15;
  border-top: 1px solid rgba(127, 209, 255, 0.18);
  background: rgba(10, 16, 26, 0.86);
  backdrop-filter: blur(6px);
  user-select: none;
}

.pane {
  position: relative;
}

.layer {
  display: block;
}

.grid {
  stroke: rgba(127, 209, 255, 0.12);
  stroke-width: 1;
}

.ylabel {
  fill: #93a4bb;
  font-size: 10px;
  text-anchor: end;
}

.xlabel {
  fill: #93a4bb;
  font-size: 10px;
  text-anchor: middle;
}

.line {
  fill: none;
  stroke-width: 2;
}

.speed {
  stroke: #7ee0a6;
}

.elev {
  stroke: #ffb95e;
}

.unit {
  position: absolute;
  top: 2px;
  right: 12px;
  font-size: 10px;
}

.speed-unit {
  color: #7ee0a6;
}

.elev-unit {
  color: #ffb95e;
}

.empty {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 11px;
  color: #93a4bb;
}
</style>
```

- [ ] **Step 2: 构建，确认没有语法错误**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
$env:npm_config_cache = "E:\JAVA_IDEA_package\JAVA_Project\Calcite\.npm-cache"
cd frontend
npm run build
```

Expected: `✓ built in ...`（Cesium 的 chunk 体积警告是既有的，忽略）。

> 如果报 `spawn EPERM`：这是 Windows 沙箱挡住 Vite 探测网络盘，不是代码问题。用 `sandbox_permissions: danger-full-access` 重试同一条命令一次。

- [ ] **Step 3: 提交**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
git add frontend/src/components/SpeedChart.vue
git commit -m "feat(chart): SpeedChart 骨架 —— 双图 + 时间轴 + 网格 + 空态"
```

---

## Task 5: `SpeedChart.vue` 游标 + 悬停 + 点击

**Files:**
- Modify: `frontend/src/components/SpeedChart.vue`

- [ ] **Step 1: 在 `<script setup>` 里补上游标/悬停/点击逻辑**

在 `SpeedChart.vue` 的 `</script>` 之前（即 `timeTickList` 那段之后）追加：

```js
/* ============ 游标 ============ */
/** 游标 x：夹在绘图区内，避免超出两端 */
const playheadX = computed(() => {
  const x = xOf.value(props.currentMs)
  return Math.min(PAD_L + plotW.value, Math.max(PAD_L, x))
})

/** 游标与折线的交点 y —— 用插值，保证正好落在交叉处 */
const speedDotY = computed(() => {
  if (!hasSpeed.value) return null
  const v = valueAt(speed.value, props.currentMs)
  return v === null ? null : speedY.value(v)
})
const elevDotY = computed(() => {
  if (!hasElev.value) return null
  const v = valueAt(elev.value, props.currentMs)
  return v === null ? null : elevY.value(v)
})

/* ============ 悬停 / 点击 ============ */
const hoverX = ref(null)

const hoverMs = computed(() =>
  hoverX.value === null
    ? null
    : msAtX(hoverX.value, props.startMs, props.endMs, PAD_L, plotW.value),
)
const hoverSpeed = computed(() =>
  hoverMs.value === null ? null : valueAt(speed.value, hoverMs.value),
)
const hoverElev = computed(() =>
  hoverMs.value === null ? null : valueAt(elev.value, hoverMs.value),
)

/** 提示框位置：靠右时向左夹紧，避免溢出容器 */
const TIP_W = 176
const tipStyle = computed(() => {
  if (hoverX.value === null) return { display: 'none' }
  const maxLeft = Math.max(4, width.value - TIP_W - 4)
  const left = Math.min(Math.max(hoverX.value - TIP_W / 2, 4), maxLeft)
  return { left: left + 'px', width: TIP_W + 'px' }
})

function onMove(ev) {
  const rect = ev.currentTarget.getBoundingClientRect()
  hoverX.value = ev.clientX - rect.left
}

function onLeave() {
  hoverX.value = null
}

function onClick(ev) {
  const rect = ev.currentTarget.getBoundingClientRect()
  const ms = msAtX(ev.clientX - rect.left, props.startMs, props.endMs, PAD_L, plotW.value)
  emit('seek', Math.round(ms))
}
```

同时把顶部 import 和 `defineEmits` 改成：

```js
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { formatClock } from '../lib/playback.js'
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
} from '../lib/chart.js'

const props = defineProps({
  /** 轨迹点，每个点要有 recordedAt / speedMps / elevationM */
  points: { type: Array, default: () => [] },
  /** 当前时刻（毫秒），由 App 从 Cesium 时钟同步过来 */
  currentMs: { type: Number, default: 0 },
  startMs: { type: Number, default: 0 },
  endMs: { type: Number, default: 0 },
})

const emit = defineEmits(['seek'])
```

- [ ] **Step 2: 把游标和交点插进两张图**

速度图里，在 `<path v-if="hasSpeed" ...>` **之前**插入游标（放前面 = 位于下层 = 永不遮挡数据线），在 `<path>` **之后**插入交点：

```html
        <!-- 游标画在数据线之前 → 位于下层 → 物理上不可能遮挡数据线 -->
        <line
          v-if="hasSpeed"
          :x1="playheadX"
          :x2="playheadX"
          y1="0"
          :y2="CHART_H"
          class="playhead"
          data-testid="chart-playhead"
        />
        <path v-if="hasSpeed" :d="speedPath" class="line speed" />
        <circle
          v-if="hasSpeed && speedDotY !== null"
          :cx="playheadX"
          :cy="speedDotY"
          r="2"
          class="dot"
        />
```

海拔图里同样插入（游标不要 testid，避免重复；交点圆点保留）：

```html
        <line
          v-if="hasElev"
          :x1="playheadX"
          :x2="playheadX"
          y1="0"
          :y2="CHART_H"
          class="playhead"
        />
        <path v-if="hasElev" :d="elevPath" class="line elev" />
        <circle
          v-if="hasElev && elevDotY !== null"
          :cx="playheadX"
          :cy="elevDotY"
          r="2"
          class="dot"
        />
```

- [ ] **Step 3: 给两张 `<svg>` 挂鼠标事件**

速度图的 `<svg>` 标签改成：

```html
      <svg
        class="layer"
        :width="Math.max(width, 1)"
        :height="CHART_H"
        data-testid="chart-speed"
        @mousemove="onMove"
        @mouseleave="onLeave"
        @click="onClick"
      >
```

海拔图的 `<svg>` 标签同样加这三个事件（`data-testid="chart-elevation"` 不变）。

- [ ] **Step 4: 加悬停提示框到模板末尾**

在 `</div>` 之前（时间轴 `<svg>` 之后）插入：

```html
    <!-- ============ 悬停提示 ============ -->
    <div
      v-if="hoverX !== null"
      class="tip"
      :style="tipStyle"
      data-testid="chart-tooltip"
    >
      <span class="t">{{ hoverMs === null ? '—' : formatClock(hoverMs) }}</span>
      <span>速度 {{ formatValue(hoverSpeed, 2) }} m/s</span>
      <span>海拔 {{ formatValue(hoverElev, 1) }} m</span>
    </div>
```

- [ ] **Step 5: 加游标 / 交点 / 提示框的样式**

在 `<style scoped>` 末尾追加：

```css
.playhead {
  stroke: #ffffff;
  stroke-width: 1;
  stroke-dasharray: 4 3;
  opacity: 0.7;
}

.dot {
  fill: #ffffff;
}

.tip {
  position: absolute;
  top: 4px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 4px 8px;
  border: 1px solid rgba(127, 209, 255, 0.28);
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.92);
  color: #e7eef8;
  font-size: 11px;
  line-height: 1.5;
  pointer-events: none;
}

.tip .t {
  color: #7fd1ff;
}
```

- [ ] **Step 6: 构建确认无语法错误**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
$env:npm_config_cache = "E:\JAVA_IDEA_package\JAVA_Project\Calcite\.npm-cache"
cd frontend
npm run build
```

Expected: `✓ built in ...`

- [ ] **Step 7: 提交**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
git add frontend/src/components/SpeedChart.vue
git commit -m "feat(chart): 游标（2px 微点，画在数据线下层）+ 悬停读数 + 点击跳转"
```

---

## Task 6: `App.vue` 接线 + 布局上移

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: import 组件**

把 `frontend/src/App.vue:3-6` 改成：

```js
import CesiumGlobe from './components/CesiumGlobe.vue'
import SpeedChart from './components/SpeedChart.vue'
import TrackList from './components/TrackList.vue'
import TrackPlayer from './components/TrackPlayer.vue'
import { canPlay, timeRange } from './lib/playback.js'
```

- [ ] **Step 2: 在模板里挂上曲线**

在 `<TrackPlayer ...>` **之前**（即 `frontend/src/App.vue:186` 那行注释的位置）插入：

```html
    <!-- 底部速度/海拔曲线：游标与回放同步，点曲线跳转到那一刻 -->
    <SpeedChart
      v-if="detail && canPlayback"
      :points="trackPoints"
      :current-ms="currentMs"
      :start-ms="startMs"
      :end-ms="endMs"
      @seek="seekTo"
    />
```

> `@seek="seekTo"` 复用的就是进度条那一个函数（`App.vue:70-73`），所以点曲线和拖进度条行为完全一致。

- [ ] **Step 3: 把左下角状态条上移**

把 `frontend/src/App.vue:284` 的

```css
  bottom: 62px;
```

改成

```css
  bottom: 194px;
```

（46px 回放条 + 140px 曲线 + 8px 间隙）

- [ ] **Step 4: 构建**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
$env:npm_config_cache = "E:\JAVA_IDEA_package\JAVA_Project\Calcite\.npm-cache"
cd frontend
npm run build
```

Expected: `✓ built in ...`

- [ ] **Step 5: 人工看一眼**

确认开发服务器在跑（`http://localhost:5173`），浏览器打开 <http://localhost:5173/?track=1>：

- 底部应出现上下两张图（上绿下橙）
- 点播放，白色游标跟着走
- 鼠标移到图上，出现三行读数
- 点图的中间偏右，地球上的白点跳过去

**图是在浏览器里渲染的，PowerShell 只负责启动和检查。**

- [ ] **Step 6: 提交**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
git add frontend/src/App.vue
git commit -m "feat(chart): App 接线 —— 曲线与回放共用 seekTo，状态条上移"
```

---

## Task 7: Playwright + Pillow 真实浏览器验收

**Files:**
- Create: `.tmp/check-chart-pixels.py`

- [ ] **Step 1: 写验收脚本**

创建 `.tmp/check-chart-pixels.py`：

```python
"""曲线功能的真实浏览器验收：DOM 断言 + 像素分析。

为什么不用无头 Chrome 的 --virtual-time-budget 截图：
Cesium 的几何体在 web worker 里异步生成，虚拟时间会让截图提前结束、线还没画出来。
所以这里用 Playwright 真实等待。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-chart-pixels.py
"""
import asyncio
import re
import sys

from PIL import Image
from playwright.async_api import async_playwright

URL = "http://localhost:5173/?track=1"
VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/chart-shot.png"

# 曲线所在像素带（视口高 - 186 到 视口高 - 46），避免抓到地球上的白色移动点
BAND_TOP = VIEW_H - 186
BAND_BOTTOM = VIEW_H - 46

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


def count_pixels(img, predicate):
    px = img.load()
    n = 0
    for y in range(BAND_TOP, BAND_BOTTOM):
        for x in range(0, VIEW_W):
            r, g, b = px[x, y][:3]
            if predicate(r, g, b):
                n += 1
    return n


def white_median_x(img):
    px = img.load()
    xs = []
    for y in range(BAND_TOP, BAND_BOTTOM):
        for x in range(0, VIEW_W):
            r, g, b = px[x, y][:3]
            if r >= 230 and g >= 230 and b >= 230:
                xs.append(x)
    xs.sort()
    return xs[len(xs) // 2] if xs else None


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=True, args=["--no-sandbox"]
        )
        page = await browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})

        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        await page.goto(URL, wait_until="load")
        await page.wait_for_selector('[data-testid="speed-chart"]', timeout=30000)
        await page.wait_for_timeout(3000)

        # --- 1. 两条线都画了 ---
        d_speed = await page.eval_on_selector(
            '[data-testid="chart-speed"] path.line', "el => el.getAttribute('d')"
        )
        d_elev = await page.eval_on_selector(
            '[data-testid="chart-elevation"] path.line', "el => el.getAttribute('d')"
        )
        check("速度折线路径非空", d_speed and len(d_speed) > 100, "长度 " + str(len(d_speed or "")))
        check("海拔折线路径非空", d_elev and len(d_elev) > 100, "长度 " + str(len(d_elev or "")))

        # --- 2. 时间轴有刻度 ---
        axis_labels = await page.eval_on_selector_all(
            '[data-testid="chart-axis"] text', "els => els.map(e => e.textContent.trim())"
        )
        check("时间轴有 HH:MM 刻度", len(axis_labels) >= 3, str(axis_labels))

        # --- 3. 像素判据 ---
        await page.screenshot(path=SHOT)
        img = Image.open(SHOT).convert("RGB")
        green = count_pixels(img, lambda r, g, b: g >= 180 and r <= 150 and b <= 180)
        orange = count_pixels(img, lambda r, g, b: r >= 200 and 100 <= g <= 200 and b <= 130)
        check("绿色速度线像素 > 50", green > 50, "实得 " + str(green))
        check("橙色海拔线像素 > 50", orange > 50, "实得 " + str(orange))

        # --- 4. 游标会动 ---
        x1 = await page.eval_on_selector(
            '[data-testid="chart-playhead"]', "el => Number(el.getAttribute('x1'))"
        )
        await page.click('[data-testid="play-toggle"]')
        await page.wait_for_timeout(4000)
        x2 = await page.eval_on_selector(
            '[data-testid="chart-playhead"]', "el => Number(el.getAttribute('x1'))"
        )
        check("播放 4 秒后游标移动 > 20px", abs(x2 - x1) > 20, f"{x1:.0f} → {x2:.0f}")
        await page.click('[data-testid="play-toggle"]')

        # --- 5. 点击跳转 ---
        box = await page.eval_on_selector(
            '[data-testid="chart-speed"]',
            "el => { const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height} }",
        )
        plot_w = box["w"] - 46 - 12
        click_x = box["x"] + 46 + plot_w * 0.8
        click_y = box["y"] + box["h"] / 2
        await page.mouse.click(click_x, click_y)
        await page.wait_for_timeout(500)
        clock = await page.text_content('[data-testid="clock"]')
        check("点 80% 处时钟变成 08:10:00", clock.strip() == "08:10:00", "实得 " + repr(clock))

        # --- 6. 悬停读数 ---
        await page.mouse.move(click_x, click_y)
        await page.wait_for_timeout(300)
        tip = await page.text_content('[data-testid="chart-tooltip"]')
        check(
            "悬停提示含时刻/速度/海拔",
            bool(re.search(r"\d{2}:\d{2}:\d{2}", tip or ""))
            and "速度" in (tip or "")
            and "海拔" in (tip or ""),
            repr((tip or "").replace("\n", " ")),
        )

        # --- 7. 游标不遮挡数据线 ---
        await page.screenshot(path=SHOT)
        img2 = Image.open(SHOT).convert("RGB")
        x_now = await page.eval_on_selector(
            '[data-testid="chart-playhead"]', "el => Number(el.getAttribute('x1'))"
        )
        px = img2.load()
        colored = 0
        for y in range(BAND_TOP, BAND_BOTTOM):
            for x in range(int(x_now) - 2, int(x_now) + 3):
                if x < 0 or x >= VIEW_W:
                    continue
                r, g, b = px[x, y][:3]
                if (g >= 180 and r <= 150 and b <= 180) or (r >= 200 and 100 <= g <= 200 and b <= 130):
                    colored += 1
        check("游标穿过处仍有数据线颜色", colored > 0, "实得 " + str(colored))

        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
```

- [ ] **Step 2: 确认服务在跑**

```powershell
Invoke-RestMethod http://localhost:8080/api/health | Select-Object status, postgis
(Invoke-WebRequest http://localhost:5173 -UseBasicParsing).StatusCode
```

Expected: `status: UP` / `postgis: 3.6...`，以及 `200`。

若任一没起来，先启动（后台任务）：

```powershell
# 后端
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" spring-boot:run
# 前端（另开一个后台任务）
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
npm run dev
```

- [ ] **Step 3: 跑验收**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
$env:PYTHONIOENCODING='utf-8'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
& "E:\python\python_address\python.exe" .tmp\check-chart-pixels.py
```

Expected: 10 项全部 `✓`，最后一行 `10 项通过，0 项失败`。

> 若报 `PermissionError: [WinError 5]`（Playwright 建管道被沙箱挡），用 `sandbox_permissions: danger-full-access` 重试同一条命令一次。
>
> 若某项红了：**先读截图确认是渲染问题还是断言问题**，不要直接放宽断言。

- [ ] **Step 4: 提交（脚本进 git，截图不进）**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
git add -f .tmp/check-chart-pixels.py
git commit -m "test(chart): Playwright + Pillow 验收脚本（9 项）"
```

---

## Task 8: 文档与记忆更新

**Files:**
- Modify: `_session_context.md`

- [ ] **Step 1: 在 `_session_context.md` 的 M1 段落补一段**

在 `### M1 回放（2026-09-09 完成）` 之后插入：

```markdown
### M1 速度/海拔曲线（2026-09-09 完成）

- 设计文档 `docs/superpowers/specs/2026-09-09-m1-speed-chart-design.md`
- `frontend/src/lib/chart.js` 纯计算（12 个导出函数，零依赖）
- `frontend/src/components/SpeedChart.vue` 上下双图，共用时间轴
- 游标 1px 半透明虚线 + 2px 微点，**画在数据线之前（下层）所以永不遮挡**
- 回归命令：`cd frontend; npm run check:chart`（37 项）
- 浏览器验收：`.tmp/check-chart-pixels.py`（10 项）
- 曲线点击复用 `App.vue` 的 `seekTo`，与进度条完全同源
- 不做：缩放/框选/导出/多轨迹对比/平滑滤波
```

- [ ] **Step 2: 全量回归（三个检查一起跑）**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
npm run check:playback
npm run check:chart
cd ..
$env:PYTHONIOENCODING='utf-8'
& "E:\python\python_address\python.exe" .tmp\check-chart-pixels.py
```

Expected: `17 项通过，0 项失败` / `37 项通过，0 项失败` / `10 项通过，0 项失败`。

- [ ] **Step 3: 提交**

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
git add _session_context.md
git commit -m "docs: 记录 M1 速度/海拔曲线完成情况与回归命令"
git log --oneline -6
git status --porcelain
```

Expected: 工作区干净；**不执行 `git push`**（用户明确要求只本地提交保留回滚退路）。

---

## 自查记录

**1. 设计文档覆盖检查**

| 设计文档章节 | 对应任务 |
|---|---|
| 一、目标（4 条） | Task 4（双图）+ Task 5（游标/悬停/点击） |
| 一、非目标（6 条） | 无任务（正确：就是不做） |
| 二、数据来源与空值 | Task 1（`seriesOf` 跳空）+ Task 4（空态文案） |
| 3.1 上下双图 | Task 4 |
| 3.2 横轴用时间 | Task 1（`timeTicks`）+ Task 2（`scaleX`） |
| 3.3 手写 SVG 零依赖 | 全计划（无新增依赖） |
| 3.4 ResizeObserver | Task 4 |
| 4.1 文件划分 | Task 1 / 4 / 6 |
| 4.2 数据流 | Task 6（`@seek="seekTo"`） |
| 4.3 纯函数清单（12 个） | Task 1（5 个）+ Task 2（7 个） |
| 5.1 尺寸与位置 | Task 4（常量）+ Task 6（状态条 194px） |
| 5.2 颜色 | Task 4（`<style>`） |
| 5.3 游标规范 | Task 5 |
| 5.4 testid | Task 4 + Task 5 |
| 六、交互 | Task 5 |
| 七、边界情况（8 条） | Task 1（退化保护）+ Task 4（空态）+ Task 6（`canPlayback` 门控） |
| 8.1 node 检查 | Task 1 / 2 / 3 |
| 8.2 浏览器验收 | Task 7 |

**2. 占位符扫描**：无 TBD / TODO / 「类似 Task N」/「加上适当的错误处理」。

**3. 命名一致性**：`seriesOf` / `domainOf` / `niceTicks` / `timeTicks` / `tickDigits` / `scaleX` / `scaleY` / `msAtX` / `pathOf` / `valueAt` / `formatTick` / `formatValue` —— Task 1、Task 2、Task 4、Task 5 中的调用名与定义名逐一核对一致；testid 与设计文档 §5.4 一致。
