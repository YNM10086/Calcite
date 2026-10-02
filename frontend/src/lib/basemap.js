/**
 * 在线底图的纯计算：把"后端给的配置 + 当前样式"翻译成"Cesium 要的图层描述"。
 *
 * 零依赖、不 import Vue / Cesium —— 所以能用 node 直接断言（见 scripts/check-basemap.mjs）。
 *
 * ⚠️ 为什么这些拼接值得单独一层：
 *   瓦片 URL 拼错、剖分基准配错的表现都是"地图看起来没变 / 一片空白"（403/404/占位图静默不显示），
 *   在浏览器里极难定位。做成纯函数就能用断言钉住。
 *
 * 两类服务（都免装依赖、都走 https）：
 *   1. **天地图**（需 key）：WMTS，矩阵集 `w`（经纬度），CGCS2000≈WGS84，**无坐标偏移**。
 *      实测坑：`_w` 的 0 级是 **1×1**，而 Cesium GeographicTilingScheme 默认 2×1（见 LEVEL_ZERO_TILES_*）；
 *      影像(image)公开服务只到 12 级。
 *   2. **高德**（**不需要 key**）：Web Mercator 的 `{z}/{x}/{y}` 瓦片，实测 z16/z18 都有真图，
 *      街道图带建筑轮廓与路名、高清影像能看清单栋建筑。
 *      ⚠️ 代价：高德是 **GCJ-02（火星坐标）**，直接用会让 WGS84 轨迹整体偏 300~600 米
 *      —— 所以给它的图层描述带上补偿矩形（见 gcj02Offset / compensatedWorldRectangle）。
 */

/** 矩阵集：w = 经纬度（配 GeographicTilingScheme），c = 球面墨卡托 */
export const TILE_MATRIX_SET = 'w'

/**
 * ⚠️⚠️ 天地图 `_w` 的**0 级是 1×1**（每级 2^level × 2^level 方格网），
 * 而 Cesium `GeographicTilingScheme` 默认是 **2×1**（它的 d.ts 里默认值就写着 2/1）。
 *
 * 写错的后果极其隐蔽（2026-09-27 实测栽过）：列号算大一倍 ⇒ 每次都请求到"越界"的瓦片
 * ⇒ 天地图返回 **200 + 「此级别下，该区域无影像」占位图**，而且四个相距很远的城市
 * 返回**逐字节相同**的图 —— 页面看起来"确实变了"，所以只看截图/状态码是抓不到的。
 */
export const LEVEL_ZERO_TILES_X = 1
export const LEVEL_ZERO_TILES_Y = 1

/** 矢量图 18 级足够看到建筑轮廓 */
export const DEFAULT_MAX_LEVEL = 18

/** 天地图瓦片子域 t0~t7 */
export const DEFAULT_SUBDOMAINS = ['0', '1', '2', '3', '4', '5', '6', '7']

/** 高德瓦片子域（URL 里是 webrd0{s} / webst0{s}） */
export const AMAP_SUBDOMAINS = ['1', '2', '3', '4']

/** Web Mercator 覆盖的纬度上限（Cesium WebMercatorTilingScheme 用的就是这个值） */
const MERCATOR_MAX_LAT = 85.05112878

// ------------------------------------------------------------------ 天地图 WMTS

/** 天地图 WMTS 的 URL 模板（Cesium 的 `{s}` / `{TileMatrix}` / `{TileRow}` / `{TileCol}` 约定） */
export function tiandituUrlTemplate({ layer, style = 'default', token, matrixSet = TILE_MATRIX_SET }) {
  return 'https://t{s}.tianditu.gov.cn/' + layer + '_' + matrixSet + '/wmts'
    + '?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0'
    + '&LAYER=' + layer
    + '&STYLE=' + style
    + '&TILEMATRIXSET=' + matrixSet
    + '&FORMAT=tiles'
    + '&TILEMATRIX={TileMatrix}&TILEROW={TileRow}&TILECOL={TileCol}'
    + '&tk=' + token
}

/** 一张**具体**瓦片的 URL（不含占位符）—— 给探针与单测用 */
export function tiandituTileUrl({
  layer, style = 'default', token, subdomain = '0', matrixSet = TILE_MATRIX_SET, level, row, col,
}) {
  return tiandituUrlTemplate({ layer, style, token, matrixSet })
    .replace('{s}', String(subdomain))
    .replace('{TileMatrix}', String(level))
    .replace('{TileRow}', String(row))
    .replace('{TileCol}', String(col))
}

// ------------------------------------------------------------------ 高德 XYZ

/** 高德街道图（矢量：建筑轮廓 + 路名 + 绿地水系） */
export function amapStreetUrl() {
  return 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7'
    + '&x={x}&y={y}&z={z}'
}

/** 高德高清卫星影像 */
export function amapImageUrl() {
  return 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}'
}

// ------------------------------------------------------------------ GCJ-02 偏移补偿

const GCJ_A = 6378245.0                 // 克拉索夫斯基椭球长半轴
const GCJ_EE = 0.00669342162296594323   // 偏心率平方

/** 中国大陆粗略范围之外不做偏移（标准 GCJ-02 算法的既定约定） */
function outOfChina(lon, lat) {
  return !(lon > 73.66 && lon < 135.05 && lat > 3.86 && lat < 53.55)
}

function transformLat(x, y) {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0
  ret += (20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin(y / 3.0 * Math.PI)) * 2.0 / 3.0
  ret += (160.0 * Math.sin(y / 12.0 * Math.PI) + 320 * Math.sin(y * Math.PI / 30.0)) * 2.0 / 3.0
  return ret
}

function transformLon(x, y) {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0
  ret += (20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin(x / 3.0 * Math.PI)) * 2.0 / 3.0
  ret += (150.0 * Math.sin(x / 12.0 * Math.PI) + 300.0 * Math.sin(x / 30.0 * Math.PI)) * 2.0 / 3.0
  return ret
}

/**
 * WGS84 → GCJ-02 的差值（度）。**纯函数、可断言**。
 *
 * 用途：高德的瓦片是按 GCJ-02 切的，Cesium 却按 WGS84 摆放 ⇒ 影像相对现实**整体偏了 delta**。
 * 把影像的覆盖矩形往**反方向**挪 delta，就能让它压回真实位置，我们的 WGS84 轨迹也就对齐了。
 *
 * ⚠️ 局限：delta 随地点缓慢变化，所以补偿是**近似**——同一城市内残差约百米量级，跨城市更大。
 * 这是本机没有天地图矢量服务时，为了"看得见建筑"付出的代价，文档里已写明。
 */
export function gcj02Offset(lon, lat) {
  if (outOfChina(lon, lat)) return { dLon: 0, dLat: 0 }
  const dLatRaw = transformLat(lon - 105.0, lat - 35.0)
  const dLonRaw = transformLon(lon - 105.0, lat - 35.0)
  const radLat = lat / 180.0 * Math.PI
  let magic = Math.sin(radLat)
  magic = 1 - GCJ_EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  return {
    dLat: (dLatRaw * 180.0) / ((GCJ_A * (1 - GCJ_EE)) / (magic * sqrtMagic) * Math.PI),
    dLon: (dLonRaw * 180.0) / (GCJ_A / sqrtMagic * Math.cos(radLat) * Math.PI),
  }
}

/**
 * 补偿后的"世界矩形"（度）：`[west, south, east, north]`。
 * 高德图层要用它当 `rectangle`，把整张影像从 GCJ-02 推回 WGS84。
 */
export function compensatedWorldRectangle(lon, lat) {
  const { dLon, dLat } = gcj02Offset(lon, lat)
  return [-180 - dLon, -MERCATOR_MAX_LAT - dLat, 180 - dLon, MERCATOR_MAX_LAT - dLat]
}

/** 这张底图是否需要 GCJ-02 补偿（只有高德需要） */
export function needsGcj02Compensation(style) {
  return (BASEMAP_STYLES[style] ?? {}).provider === 'amap'
}

// ------------------------------------------------------------------ 样式定义

/**
 * 四套样式。**默认高德街道图**：不需要 key、当下就能看清建筑轮廓与路名
 * （本机天地图 key 没开通矢量服务，默认选它演示才不会"打开一片空白"）。
 *
 * 天地图两套排在后面：等 key 开通矢量服务后，把 `DEFAULT_STYLE` 改成 `'tdt-street'` 即可
 * —— 它是**无坐标偏移**的正规选择。
 */
export const BASEMAP_STYLES = {
  'amap-street': {
    key: 'amap-street',
    label: '高德·街道图',
    provider: 'amap',
    needsToken: false,
    maxLevel: 18,
    layers: [{ layer: 'amap-street', name: '高德街道图（建筑轮廓 + 路名）' }],
  },
  'amap-image': {
    key: 'amap-image',
    label: '高德·高清影像',
    provider: 'amap',
    needsToken: false,
    maxLevel: 18,
    layers: [{ layer: 'amap-image', name: '高德高清影像' }],
  },
  'tdt-street': {
    key: 'tdt-street',
    label: '天地图·街道图',
    provider: 'tianditu',
    needsToken: true,
    maxLevel: 18,
    layers: [
      { layer: 'vec', name: '街道矢量底图' },
      { layer: 'cva', name: '矢量注记（路名 / 地名）' },
    ],
  },
  'tdt-image': {
    key: 'tdt-image',
    label: '天地图·卫星影像',
    provider: 'tianditu',
    needsToken: true,
    // 实测：天地图**公开影像只到 12 级**，13 级及以上一律「此级别下，该区域无影像」占位图
    maxLevel: 12,
    layers: [
      { layer: 'img', name: '卫星影像底图' },
      { layer: 'cia', name: '影像注记' },
    ],
  },
}

/** 默认样式：不需要 key、当下就能看清建筑的那一套 */
export const DEFAULT_STYLE = 'amap-street'

/** 给界面用的样式选项：`[{ key, label, needsToken }]` */
export function styleOptions() {
  return Object.values(BASEMAP_STYLES).map((s) => ({
    key: s.key, label: s.label, needsToken: s.needsToken,
  }))
}

// ------------------------------------------------------------------ 图层描述

/**
 * 后端配置 + 样式 → 组件要的图层描述数组。
 *
 * 两类描述：
 *   - 天地图：`kind: 'wmts'`，需要 token，要求 `_w` 的 1×1 剖分
 *   - 高德：`kind: 'xyz'`，**不需要 token**，带 `rectangle`（GCJ-02 补偿）
 *
 * ⚠️ **天地图样式没配 key 时返回空数组**：这是"关闭状态下零瓦片请求"的根本保证，
 *    也是"没 key 就别发注定 403 的请求"的保证。高德样式不受此限。
 *
 * @param {{enabled?: boolean, token?: string|null, maxLevel?: number, subdomains?: string[]}} config
 * @param {string} style 见 {@link BASEMAP_STYLES}
 * @param {{lon: number, lat: number}} [refPoint] 补偿参考点（一般传当前相机中心）
 */
export function layerDescriptors(config, style = DEFAULT_STYLE, refPoint = { lon: 116.397, lat: 39.909 }) {
  const spec = BASEMAP_STYLES[style] ?? BASEMAP_STYLES[DEFAULT_STYLE]
  const token = config && typeof config.token === 'string' ? config.token.trim() : ''

  if (spec.needsToken) {
    if (!config || !config.enabled) return []
    if (token === '') return []          // 双保险：只有空白 = 没配（与后端同一口径）
    const configured = Number.isFinite(config.maxLevel) ? config.maxLevel : spec.maxLevel
    const maximumLevel = Math.min(spec.maxLevel, configured)
    const subdomains = Array.isArray(config.subdomains) && config.subdomains.length > 0
      ? config.subdomains
      : DEFAULT_SUBDOMAINS
    return spec.layers.map((l) => ({
      key: spec.key + ':' + l.layer,
      kind: 'wmts',
      layer: l.layer,
      name: l.name,
      url: tiandituUrlTemplate({ layer: l.layer, token }),
      maximumLevel,
      subdomains,
    }))
  }

  // 高德：免 key；两种样式的 URL 与层级上限都固定
  const rect = compensatedWorldRectangle(refPoint.lon, refPoint.lat)
  return spec.layers.map((l) => ({
    key: spec.key + ':' + l.layer,
    kind: 'xyz',
    layer: l.layer,
    name: l.name,
    url: l.layer === 'amap-street' ? amapStreetUrl() : amapImageUrl(),
    maximumLevel: spec.maxLevel,
    subdomains: AMAP_SUBDOMAINS,
    rectangle: rect,                     // [w, s, e, n]：把 GCJ-02 影像推回 WGS84 位置
  }))
}

/** 没配 key 时给用户看的一句提示（要指到具体文件，否则等于没说） */
export function missingTokenHint() {
  return '未配置天地图 key：把它填进 backend/src/main/resources/application-local.yml 的 '
    + 'calcite.map.tianditu-token（见 docs/DEPLOY.md「可选：开启天地图底图」）；'
    + '也可以先用「高德·街道图 / 高德·高清影像」这两套样式（不需要 key）。'
}

/** 开关按钮上的文案 */
export function basemapLabel(on) {
  return on ? '在线底图' : '离线底图'
}
