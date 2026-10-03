// frontend/scripts/check-basemap.mjs
//
// 在线底图（高德）的**纯逻辑**回归：URL 拼装、显示期坐标转换、样式与图层描述。
// 这些都不碰浏览器、不碰网络 —— 拼接/换算错了的表现只是"地图看起来没变"或"轨迹整体偏几百米"，
// 在浏览器里极难定位；所以把它钉在纯函数这一层。
import assert from 'node:assert/strict'
import {
  AMAP_SUBDOMAINS, BASEMAP_STYLES, DEFAULT_MAX_LEVEL, DEFAULT_STYLE,
  amapImageUrl, amapStreetUrl, basemapLabel, gcj02Offset, gcj02ToWgs84, isGcj02Style,
  layerDescriptors, shiftBbox, shiftGeoJson, shiftHotspotList, shiftPointList,
  shiftTrackList, styleOptions, wgs84ToGcj02,
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

// ------------------------------------------------- 显示期坐标转换（真正对齐的做法）
t('⭐ wgs84ToGcj02：北京一带 +delta ≈ 555 米（东 533 / 北 156）', () => {
  const g = wgs84ToGcj02(116.397, 39.909)
  assert.ok(Math.abs(g.lon - (116.397 + 0.006244)) < 1e-5, `lon=${g.lon}`)
  assert.ok(Math.abs(g.lat - (39.909 + 0.001403)) < 1e-5, `lat=${g.lat}`)
  const mEast = (g.lon - 116.397) * 111320 * Math.cos((39.909 * Math.PI) / 180)
  const mNorth = (g.lat - 39.909) * 111320
  assert.ok(mEast > 450 && mEast < 600, `东向 ${mEast.toFixed(0)} 米`)
  assert.ok(mNorth > 100 && mNorth < 220, `北向 ${mNorth.toFixed(0)} 米`)
})

t('中国范围外不转换（纽约原样返回）', () => {
  const ny = wgs84ToGcj02(-74.0, 40.7)
  assert.ok(Math.abs(ny.lon + 74.0) < 1e-12 && Math.abs(ny.lat - 40.7) < 1e-12)
})

t('gcj02ToWgs84 是它的近似逆：往返误差 < 5 米', () => {
  const a = { lon: 116.397, lat: 39.909 }
  const g = wgs84ToGcj02(a.lon, a.lat)
  const back = gcj02ToWgs84(g.lon, g.lat)
  const m = Math.hypot((back.lon - a.lon) * 85400, (back.lat - a.lat) * 111320)
  assert.ok(m < 5, `往返误差 ${m.toFixed(2)} 米`)
})

t('shiftPointList：平移 lon/lat、其余字段保留；关掉时原样返回且不改原数据', () => {
  const pts = [{ seq: 1, lon: 116.397, lat: 39.909, speedMps: 3.2 }]
  const on = shiftPointList(pts, true)
  assert.equal(on[0].seq, 1)
  assert.equal(on[0].speedMps, 3.2)
  assert.ok(on[0].lon > 116.397 && on[0].lat > 39.909)
  assert.equal(shiftPointList(pts, false), pts, '关掉时应原样返回（省一次拷贝）')
  assert.equal(pts[0].lon, 116.397, '原始数据不能被就地改动')
})

t('⭐ shiftHotspotList：热点字段是 centerLon/centerLat（套 shiftPointList 会漏掉）', () => {
  const hs = [{ centerLon: 116.397, centerLat: 39.909, radiusM: 200, visits: 3 }]
  const on = shiftHotspotList(hs, true)
  assert.ok(on[0].centerLon > 116.397 && on[0].centerLat > 39.909, 'centerLon/Lat 应被平移')
  assert.equal(on[0].radiusM, 200)
  assert.equal(hs[0].centerLon, 116.397, '原数组不能被改')
})

t('shiftTrackList：嵌套的 points[] 一并平移（相似档 / 圈选档）', () => {
  const ts = [{ trackId: 7, similarity: 0.8, points: [{ lon: 116.4, lat: 39.9 }] }]
  const on = shiftTrackList(ts, true)
  assert.ok(on[0].points[0].lon > 116.4 && on[0].points[0].lat > 39.9)
  assert.equal(on[0].similarity, 0.8)
  assert.equal(ts[0].points[0].lon, 116.4, '原数据不能被改')
})

t('shiftGeoJson：Polygon / MultiPolygon 的 [lon,lat] 二元组都要平移', () => {
  const poly = { type: 'Polygon', coordinates: [[[116.3, 39.9], [116.4, 39.9], [116.4, 40.0], [116.3, 39.9]]] }
  assert.ok(shiftGeoJson(poly, true).coordinates[0][0][0] > 116.3)
  assert.equal(poly.coordinates[0][0][0], 116.3, '原对象不能被改')
  const multi = { type: 'MultiPolygon', coordinates: [[[[116.3, 39.9], [116.4, 39.9], [116.4, 40.0]]]] }
  assert.ok(shiftGeoJson(multi, true).coordinates[0][0][0][0] > 116.3)
})

t('shiftBbox：查库的视野包围盒按 −delta 挪回真实 WGS84', () => {
  const box = { west: 116.3, south: 39.8, east: 116.5, north: 40.0 }
  const t1 = shiftBbox(box, true, false)
  assert.ok(t1.west < box.west && t1.south < box.south, '−delta：往西/南挪')
  assert.ok(Math.abs((t1.east - t1.west) - (box.east - box.west)) < 1e-9, '宽度不变')
})

t('isGcj02Style：只有高德两套样式需要转换', () => {
  assert.equal(isGcj02Style('amap-street'), true)
  assert.equal(isGcj02Style('amap-image'), true)
  assert.equal(isGcj02Style('不存在的样式'), false)
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

t('图层描述里**不再有**补偿矩形（坐标对齐交给显示期转换）', () => {
  const layers = layerDescriptors('amap-image')
  assert.equal(layers[0].rectangle, undefined, '描述里不该再有补偿矩形')
  assert.equal(layers[0].kind, 'xyz')
  assert.equal(layers[0].maximumLevel, 18)
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
