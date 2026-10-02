// frontend/scripts/check-basemap.mjs
//
// 在线底图（高德）的**纯逻辑**回归：URL 拼装、GCJ-02 补偿、样式与图层描述。
// 这些都不碰浏览器、不碰网络 —— 拼接规则错了会直接表现为"瓦片 404/占位图"，
// 而那种错在页面上只表现为"地图没变"，非常难查；所以把它钉在纯函数这一层。
import assert from 'node:assert/strict'
import {
  AMAP_SUBDOMAINS, BASEMAP_STYLES, DEFAULT_MAX_LEVEL, DEFAULT_STYLE,
  amapImageUrl, amapStreetUrl, basemapLabel, compensatedWorldRectangle,
  gcj02Offset, layerDescriptors, styleOptions,
} from '../src/lib/basemap.js'

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

// ---------------------------------------------------------------- URL
t('两套样式都是 Web Mercator 的 {z}/{x}/{y} 模板，带 {s} 子域、都是 https', () => {
  for (const url of [amapStreetUrl(), amapImageUrl()]) {
    assert.match(url, /^https:\/\//, '必须 https —— http 在 https 页面里会被拦掉')
    // 街道图主机是 webrd0{s}（web+rd），影像是 webst0{s}（web+st）—— 别把 rd 写成 r
    assert.match(url, /^https:\/\/web(rd|st)0\{s\}\.is\.autonavi\.com\//)
    assert.match(url, /x=\{x\}&y=\{y\}&z=\{z\}/)
  }
})

t('街道图 style=7、影像 style=6，两者不混', () => {
  assert.match(amapStreetUrl(), /style=7/)
  assert.match(amapImageUrl(), /style=6/)
})

t('子域是 1~4（配 URL 里的 {s}）', () => {
  assert.deepEqual(AMAP_SUBDOMAINS, ['1', '2', '3', '4'])
})

// ---------------------------------------------------------------- GCJ-02 补偿
t('中国范围外不做偏移（标准算法的既定约定）', () => {
  assert.deepEqual(gcj02Offset(0, 0), { dLon: 0, dLat: 0 })
  assert.deepEqual(gcj02Offset(139.7, 35.7), { dLon: 0, dLat: 0 })   // 东京
  assert.deepEqual(gcj02Offset(-74.0, 40.7), { dLon: 0, dLat: 0 })   // 纽约
})

t('北京一带的偏移量在合理量级（约 0.002~0.008 度，两轴都为正）', () => {
  const { dLon, dLat } = gcj02Offset(116.397, 39.909)
  assert.ok(dLon > 0.002 && dLon < 0.008, `dLon=${dLon} 应在 0.002~0.008 之间`)
  assert.ok(dLat > 0.001 && dLat < 0.008, `dLat=${dLat} 应在 0.001~0.008 之间`)
  assert.ok(Math.abs(dLat) * 111000 > 100, '偏移应达到百米量级')
})

t('补偿矩形 = 世界矩形往反方向挪 delta（纬度取 Web Mercator 的 ±85.05）', () => {
  const [w, s, e, n] = compensatedWorldRectangle(116.397, 39.909)
  const { dLon, dLat } = gcj02Offset(116.397, 39.909)
  assert.ok(Math.abs(w - (-180 - dLon)) < 1e-12, '西边要往西挪 dLon')
  assert.ok(Math.abs(e - (180 - dLon)) < 1e-12)
  assert.ok(Math.abs(s - (-85.05112878 - dLat)) < 1e-9)
  assert.ok(Math.abs(n - (85.05112878 - dLat)) < 1e-9)
  assert.ok(e > w && n > s, '矩形必须有效')
})

// ---------------------------------------------------------------- 样式
t('两套样式都在，默认是街道图，且都不需要 key', () => {
  assert.deepEqual(styleOptions().map((o) => o.key), ['amap-street', 'amap-image'])
  assert.equal(DEFAULT_STYLE, 'amap-street')
  assert.equal(BASEMAP_STYLES[DEFAULT_STYLE].label, '高德·街道图')
  assert.equal(DEFAULT_MAX_LEVEL, 18)
})

// ---------------------------------------------------------------- 图层描述
t('街道样式：一层、kind=xyz、URL 是街道图、上限 18', () => {
  const layers = layerDescriptors('amap-street')
  assert.equal(layers.length, 1)
  assert.equal(layers[0].kind, 'xyz')
  assert.match(layers[0].url, /style=7/)
  assert.equal(layers[0].maximumLevel, 18)
  assert.deepEqual(layers[0].subdomains, AMAP_SUBDOMAINS)
})

t('影像样式：URL 是影像图', () => {
  const layers = layerDescriptors('amap-image')
  assert.equal(layers.length, 1)
  assert.match(layers[0].url, /webst0\{s\}/)
  assert.match(layers[0].url, /style=6/)
})

t('每种样式都带补偿矩形，且随参考点变化（北京与纽约不同）', () => {
  const beijing = layerDescriptors('amap-image', { lon: 116.397, lat: 39.909 })[0]
  const newYork = layerDescriptors('amap-image', { lon: -74.0, lat: 40.7 })[0]
  assert.equal(beijing.rectangle.length, 4)
  assert.notDeepEqual(beijing.rectangle, newYork.rectangle,
    '中国范围内要补偿、范围外不补偿，两者矩形必须不同')
  assert.deepEqual(newYork.rectangle, [-180, -85.05112878, 180, 85.05112878],
    '范围外应等于未偏移的世界矩形')
})

t('样式键写错时退回默认样式（不抛异常）', () => {
  const layers = layerDescriptors('不存在的样式')
  assert.equal(layers.length, 1)
  assert.match(layers[0].url, /style=7/, '应退回默认的街道图')
})

// ---------------------------------------------------------------- 界面文案
t('开关文案能区分两种状态', () => {
  assert.match(basemapLabel(false), /离线/)
  assert.match(basemapLabel(true), /在线/)
})

console.log(`\n${ok} 项通过，${fail} 项失败`)
if (fail) {
  console.log('失败清单：')
  for (const f of fails) console.log('  - ' + f)
}
process.exitCode = fail === 0 ? 0 : 1
