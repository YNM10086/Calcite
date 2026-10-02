// frontend/scripts/check-basemap.mjs
//
// 在线底图的**纯逻辑**回归：URL 拼装、剖分基准、样式、GCJ-02 补偿、缺 key 行为。
// 这些都不碰浏览器、不碰网络 —— 拼接规则错了会直接表现为"瓦片 404/403/占位图"，
// 而那种错在页面上只表现为"地图没变"，非常难查；所以把它钉在纯函数这一层。
import assert from 'node:assert/strict'
import {
  BASEMAP_STYLES, DEFAULT_MAX_LEVEL, DEFAULT_STYLE, LEVEL_ZERO_TILES_X, LEVEL_ZERO_TILES_Y,
  amapImageUrl, amapStreetUrl, basemapLabel, compensatedWorldRectangle, gcj02Offset,
  layerDescriptors, missingTokenHint, needsGcj02Compensation, styleOptions,
  tiandituTileUrl, tiandituUrlTemplate,
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

const withToken = {
  enabled: true, token: 'abc123', maxLevel: 18, subdomains: ['0', '1', '2', '3', '4', '5', '6', '7'],
}

// ---------------------------------------------------------------- 天地图 URL 模板
t('模板是 https，且带天地图的四个必要参数', () => {
  const url = tiandituUrlTemplate({ layer: 'vec', token: 'abc123' })
  assert.match(url, /^https:\/\//, '必须 https —— http 在 https 页面里会被浏览器拦掉')
  assert.match(url, /SERVICE=WMTS/)
  assert.match(url, /REQUEST=GetTile/)
  assert.match(url, /VERSION=1\.0\.0/)
  assert.match(url, /FORMAT=tiles/)
})

t('模板用 {s} 占位子域、用 Cesium 的 WMTS 变量占位行列与层级', () => {
  const url = tiandituUrlTemplate({ layer: 'vec', token: 'abc123' })
  assert.match(url, /^https:\/\/t\{s\}\.tianditu\.gov\.cn\//, '子域占位必须是 {s}')
  assert.match(url, /TILEMATRIX=\{TileMatrix\}/)
  assert.match(url, /TILEROW=\{TileRow\}/)
  assert.match(url, /TILECOL=\{TileCol\}/)
})

t('矢量底图与注记分别走 vec_w / cva_w 两套瓦片', () => {
  assert.match(tiandituUrlTemplate({ layer: 'vec', token: 'k' }), /\/vec_w\/wmts/)
  assert.match(tiandituUrlTemplate({ layer: 'vec', token: 'k' }), /LAYER=vec&/)
  assert.match(tiandituUrlTemplate({ layer: 'cva', token: 'k' }), /\/cva_w\/wmts/)
  assert.match(tiandituUrlTemplate({ layer: 'cva', token: 'k' }), /LAYER=cva&/)
})

t('用经纬度矩阵集 w（配 1×1 的 GeographicTilingScheme）', () => {
  assert.match(tiandituUrlTemplate({ layer: 'vec', token: 'k' }), /TILEMATRIXSET=w/)
})

t('token 原样进模板（由后端运行时下发，不进构建产物）', () => {
  assert.match(tiandituUrlTemplate({ layer: 'vec', token: 'my-secret-key' }), /tk=my-secret-key/)
})

t('具体瓦片 URL：子域与行列层级都被替换成真实数字', () => {
  const url = tiandituTileUrl({ layer: 'vec', token: 'k', subdomain: '3', level: 16, row: 1234, col: 5678 })
  assert.match(url, /^https:\/\/t3\.tianditu\.gov\.cn\//)
  assert.match(url, /TILEMATRIX=16&/)
  assert.match(url, /TILEROW=1234&/)
  assert.match(url, /TILECOL=5678&/)
  assert.doesNotMatch(url, /\{s\}|\{Tile/)
})

// ---------------------------------------------------------------- 剖分方案（踩过的坑）
t('⭐ 0 级必须是 1×1 瓦片（天地图 _w 的基准，不是 Cesium 默认的 2×1）', () => {
  assert.equal(LEVEL_ZERO_TILES_X, 1)
  assert.equal(LEVEL_ZERO_TILES_Y, 1)
})

// ---------------------------------------------------------------- 高德 URL
t('高德街道图/影像都是 Web Mercator 的 {z}/{x}/{y} 模板，带 {s} 子域', () => {
  for (const url of [amapStreetUrl(), amapImageUrl()]) {
    // 街道图主机是 webrd0{s}（web+rd），影像是 webst0{s}（web+st）—— 别把 rd 写成 r
    assert.match(url, /^https:\/\/web(rd|st)0\{s\}\.is\.autonavi\.com\//)
    assert.match(url, /x=\{x\}&y=\{y\}&z=\{z\}/)
  }
  assert.match(amapStreetUrl(), /style=7/)
  assert.match(amapImageUrl(), /style=6/)
})

// ---------------------------------------------------------------- GCJ-02 补偿
t('中国范围外不做偏移（标准算法的既定约定）', () => {
  assert.deepEqual(gcj02Offset(0, 0), { dLon: 0, dLat: 0 })
  assert.deepEqual(gcj02Offset(139.7, 35.7), { dLon: 0, dLat: 0 })   // 东京
  assert.deepEqual(gcj02Offset(-74.0, 40.7), { dLon: 0, dLat: 0 })   // 纽约
})

t('北京一带的偏移量在合理量级（约 0.002~0.008 度，且两轴都为正）', () => {
  const { dLon, dLat } = gcj02Offset(116.397, 39.909)
  assert.ok(dLon > 0.002 && dLon < 0.008, `dLon=${dLon} 应在 0.002~0.008 之间`)
  assert.ok(dLat > 0.001 && dLat < 0.008, `dLat=${dLat} 应在 0.001~0.008 之间`)
  // 0.005 度 ≈ 430 米（纬度方向），符合"火星坐标偏几百米"的常识
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

t('只有高德需要补偿，天地图不需要（CGCS2000≈WGS84）', () => {
  assert.equal(needsGcj02Compensation('amap-street'), true)
  assert.equal(needsGcj02Compensation('amap-image'), true)
  assert.equal(needsGcj02Compensation('tdt-street'), false)
  assert.equal(needsGcj02Compensation('tdt-image'), false)
})

// ---------------------------------------------------------------- 样式
t('四套样式都在，默认是免 key 的高德街道图', () => {
  assert.deepEqual(styleOptions().map((o) => o.key),
    ['amap-street', 'amap-image', 'tdt-street', 'tdt-image'])
  assert.equal(DEFAULT_STYLE, 'amap-street')
  assert.equal(BASEMAP_STYLES[DEFAULT_STYLE].needsToken, false)
  assert.equal(DEFAULT_MAX_LEVEL, 18)
})

t('⭐ 天地图影像样式的上限被压到 12（13 级及以上天地图只给占位图）', () => {
  const layers = layerDescriptors(withToken, 'tdt-image')
  assert.deepEqual(layers.map((l) => l.layer), ['img', 'cia'])
  assert.equal(layers[0].maximumLevel, 12)
})

// ---------------------------------------------------------------- 图层描述：天地图
t('天地图样式：kind=wmts、要 token；没配 token 时一层都不给', () => {
  assert.deepEqual(layerDescriptors({ enabled: false, token: null }, 'tdt-street'), [])
  assert.deepEqual(layerDescriptors(null, 'tdt-street'), [])
  assert.deepEqual(layerDescriptors({ enabled: true, token: '   ' }, 'tdt-street'), [])
  const layers = layerDescriptors(withToken, 'tdt-street')
  assert.equal(layers.length, 2)
  assert.deepEqual(layers.map((l) => l.layer), ['vec', 'cva'])
  assert.equal(layers[0].kind, 'wmts')
  assert.equal(layers[0].maximumLevel, 18)
  assert.ok(!layers[0].rectangle, '天地图不需要补偿矩形')
  assert.match(layers[0].url, /tk=abc123/)
})

// ---------------------------------------------------------------- 图层描述：高德
t('⭐ 高德样式**不需要任何配置**就能给出图层（后端没起、没配 key 都能用）', () => {
  const layers = layerDescriptors(null, 'amap-street')
  assert.equal(layers.length, 1)
  assert.equal(layers[0].kind, 'xyz')
  assert.match(layers[0].url, /webrd0\{s\}/)
  assert.equal(layers[0].maximumLevel, 18)
  assert.ok(Array.isArray(layers[0].rectangle) && layers[0].rectangle.length === 4)
})

t('高德图层带补偿矩形，且随参考点变化（在北京与在纽约不同）', () => {
  const beijing = layerDescriptors(null, 'amap-image', { lon: 116.397, lat: 39.909 })[0]
  const newYork = layerDescriptors(null, 'amap-image', { lon: -74.0, lat: 40.7 })[0]
  assert.notDeepEqual(beijing.rectangle, newYork.rectangle,
    '中国范围内要补偿、范围外不补偿，两者矩形必须不同')
  assert.deepEqual(newYork.rectangle, [-180, -85.05112878, 180, 85.05112878],
    '范围外应等于未偏移的世界矩形')
})

t('高德影像与街道走不同 URL', () => {
  assert.match(layerDescriptors(null, 'amap-street')[0].url, /style=7/)
  assert.match(layerDescriptors(null, 'amap-image')[0].url, /style=6/)
})

t('样式键写错时退回默认样式（不抛异常、也不是空）', () => {
  const layers = layerDescriptors(withToken, '不存在的样式')
  assert.equal(layers.length, 1)
  assert.equal(layers[0].kind, 'xyz')     // 默认样式是高德街道图
})

// ---------------------------------------------------------------- 界面文案
t('缺 key 的提示要说清"没配置"、去哪看，并指出免 key 的替代样式', () => {
  const hint = missingTokenHint()
  assert.match(hint, /未配置|没配/)
  assert.match(hint, /天地图/)
  assert.match(hint, /DEPLOY|部署/)
  assert.match(hint, /高德/, '要告诉用户可以先用免 key 的样式')
})

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
