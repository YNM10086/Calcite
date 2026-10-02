// frontend/scripts/check-basemap.mjs
//
// 在线底图（天地图）的**纯逻辑**回归：URL 拼装、图层顺序、缺 key 时的行为。
// 这些都不碰浏览器、不碰网络 —— 拼接规则错了会直接表现为"瓦片 404/403"，而那种错在页面上
// 只表现为"地图没变"，非常难查；所以把它钉在纯函数这一层。
import assert from 'node:assert/strict'
import {
  DEFAULT_MAX_LEVEL, DEFAULT_STYLE, LEVEL_ZERO_TILES_X, LEVEL_ZERO_TILES_Y, TIANDITU_STYLES,
  tiandituUrlTemplate, tiandituTileUrl, layerDescriptors, styleOptions,
  missingTokenHint, basemapLabel,
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

// ---------------------------------------------------------------- URL 模板
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

t('用经纬度矩阵集 w（配 Cesium 的 GeographicTilingScheme）', () => {
  assert.match(tiandituUrlTemplate({ layer: 'vec', token: 'k' }), /TILEMATRIXSET=w/)
})

t('token 原样进模板（由后端运行时下发，不进构建产物）', () => {
  assert.match(tiandituUrlTemplate({ layer: 'vec', token: 'my-secret-key' }), /tk=my-secret-key/)
})

// ---------------------------------------------------------------- 具体瓦片（探针用）
t('具体瓦片 URL：子域与行列层级都被替换成真实数字', () => {
  const url = tiandituTileUrl({ layer: 'vec', token: 'k', subdomain: '3', level: 16, row: 1234, col: 5678 })
  assert.match(url, /^https:\/\/t3\.tianditu\.gov\.cn\//)
  assert.match(url, /TILEMATRIX=16&/)
  assert.match(url, /TILEROW=1234&/)
  assert.match(url, /TILECOL=5678&/)
  assert.doesNotMatch(url, /\{s\}|\{Tile/)
})

// ---------------------------------------------------------------- 图层描述（组件消费的东西）
t('没配 token ⇒ 一层都不给（关闭状态下零瓦片请求的根本保证）', () => {
  assert.deepEqual(layerDescriptors({ enabled: false, token: null, maxLevel: 18, subdomains: ['0'] }), [])
})

t('token 只有空白也当没配（与后端同一条口径，双保险）', () => {
  assert.deepEqual(layerDescriptors({ enabled: true, token: '   ', maxLevel: 18, subdomains: ['0'] }), [])
})

t('配了 token ⇒ 两层，且矢量底图在前、注记在后（注记要压在底图上面）', () => {
  const layers = layerDescriptors(withToken)
  assert.equal(layers.length, 2)
  assert.equal(layers[0].layer, 'vec')
  assert.equal(layers[1].layer, 'cva')
})

t('两层用同一个 token，且都带上了 {s} 占位与层级上限', () => {
  const layers = layerDescriptors(withToken)
  for (const l of layers) {
    assert.match(l.url, /tk=abc123/)
    assert.match(l.url, /\{s\}/)
    assert.equal(l.maximumLevel, 18)
  }
})

t('子域列表原样透传（组件要拿它配 subdomains）', () => {
  const layers = layerDescriptors({ ...withToken, subdomains: ['0', '1'] })
  assert.deepEqual(layers[0].subdomains, ['0', '1'])
})

t('maxLevel 缺失时用默认 18（低于 16 级看不到建筑轮廓）', () => {
  const layers = layerDescriptors({ enabled: true, token: 'k' })
  assert.equal(layers[0].maximumLevel, DEFAULT_MAX_LEVEL)
  assert.equal(DEFAULT_MAX_LEVEL, 18)
})

// ---------------------------------------------------------------- 剖分方案（踩过的坑，必须钉死）
t('⭐ 0 级必须是 1×1 瓦片（天地图 _w 的基准，不是 Cesium 默认的 2×1）', () => {
  // 写错的后果：列号大一倍 → 请求越界瓦片 → 天地图回「此级别下，该区域无影像」占位图，
  // 而且四个相距很远的城市返回逐字节相同的图；页面"看起来变了"，只看截图抓不到。
  assert.equal(LEVEL_ZERO_TILES_X, 1)
  assert.equal(LEVEL_ZERO_TILES_Y, 1)
})

// ---------------------------------------------------------------- 样式（街道 / 影像）
t('两套样式都在，默认是街道图', () => {
  const opts = styleOptions()
  assert.deepEqual(opts.map((o) => o.key), ['street', 'image'])
  assert.equal(DEFAULT_STYLE, 'street')
  assert.equal(TIANDITU_STYLES.street.layers[0].layer, 'vec')
  assert.equal(TIANDITU_STYLES.image.layers[0].layer, 'img')
})

t('街道样式 = vec + cva，上限 18', () => {
  const layers = layerDescriptors(withToken, 'street')
  assert.deepEqual(layers.map((l) => l.layer), ['vec', 'cva'])
  assert.equal(layers[0].maximumLevel, 18)
})

t('⭐ 影像样式 = img + cia，上限被压到 12（L13+ 天地图只给占位图）', () => {
  const layers = layerDescriptors(withToken, 'image')
  assert.deepEqual(layers.map((l) => l.layer), ['img', 'cia'])
  assert.equal(layers[0].maximumLevel, 12)
  assert.equal(TIANDITU_STYLES.image.maxLevel, 12)
})

t('没配 token 时，两种样式都返回空数组', () => {
  assert.deepEqual(layerDescriptors({ enabled: false, token: null }, 'street'), [])
  assert.deepEqual(layerDescriptors({ enabled: false, token: null }, 'image'), [])
})

t('样式键写错时退回默认样式（不抛异常、也不是空）', () => {
  const layers = layerDescriptors(withToken, '不存在的样式')
  assert.deepEqual(layers.map((l) => l.layer), ['vec', 'cva'])
})


// ---------------------------------------------------------------- 界面文案
t('缺 key 的提示要说清"没配置"和去哪看', () => {
  const hint = missingTokenHint()
  assert.match(hint, /未配置|没配/)
  assert.match(hint, /天地图/)
  assert.match(hint, /DEPLOY|部署/)
})

t('开关文案能区分两种状态', () => {
  assert.match(basemapLabel(false), /离线/)
  assert.match(basemapLabel(true), /天地图/)
})

console.log(`\n${ok} 项通过，${fail} 项失败`)
if (fail) {
  console.log('失败清单：')
  for (const f of fails) console.log('  - ' + f)
}
process.exitCode = fail === 0 ? 0 : 1
