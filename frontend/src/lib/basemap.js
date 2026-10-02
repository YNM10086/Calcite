/**
 * 在线底图（天地图）的纯计算：把"后端给的配置"翻译成"Cesium 要的图层描述"。
 *
 * 零依赖、不 import Vue / Cesium —— 所以能用 node 直接断言（见 scripts/check-basemap.mjs）。
 *
 * ⚠️ 为什么这些拼接值得单独一层：
 *   瓦片 URL 拼错的表现是"地图看起来没变化"（403/404 的瓦片静默不显示），
 *   在浏览器里极难定位。把它做成纯函数，就能用断言钉住。
 *
 * ⚠️ 投影：下面的矩阵集用 `w`（经纬度 / EPSG:4326）。
 *   因此组件里创建 provider 时必须配 `new GeographicTilingScheme()`；
 *   若哪天改回 `_c`（球面墨卡托），矩阵集与此处都要一起改成 `c` + `WebMercatorTilingScheme`。
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
 * 因此组件里必须显式 `new GeographicTilingScheme({ numberOfLevelZeroTilesX: 1, numberOfLevelZeroTilesY: 1 })`。
 */
export const LEVEL_ZERO_TILES_X = 1
export const LEVEL_ZERO_TILES_Y = 1

/** 矢量图看不到更多细节了；18 级足够看到建筑轮廓 */
export const DEFAULT_MAX_LEVEL = 18

/**
 * 两套样式。**默认街道图**（用户点名要"看得见建筑轮廓与路名"），影像作为备选。
 *
 * ⚠️ 影像层的上限刻意设成 12：实测（2026-09-27）天地图的**公开影像**在北京市区
 * **L13 及以上一律返回「此级别下，该区域无影像」占位图**，L12 一张瓦片约 10 公里 ——
 * 也就是说影像**看不清建筑**，能用来看大范围地貌。要"看见建筑"，得用矢量图。
 */
export const TIANDITU_STYLES = {
  street: {
    key: 'street',
    label: '街道图',
    maxLevel: 18,
    layers: [
      { layer: 'vec', name: '街道矢量底图' },
      { layer: 'cva', name: '矢量注记（路名 / 地名）' },
    ],
  },
  image: {
    key: 'image',
    label: '卫星影像',
    maxLevel: 12,
    layers: [
      { layer: 'img', name: '卫星影像底图' },
      { layer: 'cia', name: '影像注记' },
    ],
  },
}

/** 默认样式（也是用户在需求里点名的那种） */
export const DEFAULT_STYLE = 'street'

/** 给界面用的样式选项：`[{ key, label }]` */
export function styleOptions() {
  return Object.values(TIANDITU_STYLES).map((s) => ({ key: s.key, label: s.label }))
}

/** 天地图瓦片子域 t0~t7 */
export const DEFAULT_SUBDOMAINS = ['0', '1', '2', '3', '4', '5', '6', '7']

/**
 * 两个图层：矢量底图（路网 + 高层级的建筑轮廓）与注记（路名/地名）。
 * 顺序即叠放顺序 —— 注记必须在底图**之上**，否则会被底图盖住。
 *
 * @deprecated 用 {@link TIANDITU_STYLES}.street.layers —— 保留常量只是为了不破坏既有引用
 */
export const TIANDITU_LAYERS = TIANDITU_STYLES.street.layers

/**
 * 瓦片 URL 模板（给 Cesium 的 WebMapTileServiceImageryProvider 用）。
 *
 * 三个占位符是 Cesium 的 WMTS 约定：`{s}` 子域、`{TileMatrix}` 层级、`{TileRow}/{TileCol}` 行列。
 * @param {{layer: string, style?: string, token: string, matrixSet?: string}} o
 * @returns {string}
 */
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

/**
 * 一张**具体**瓦片的 URL（不含占位符）—— 给探针与单测用：
 * 在没有浏览器的情况下，直接 curl 它就能知道"key 有没有效、投影对不对、CORS 通不通"。
 * @param {{layer: string, style?: string, token: string, subdomain?: string,
 *          matrixSet?: string, level: number, row: number, col: number}} o
 * @returns {string}
 */
export function tiandituTileUrl({
  layer, style = 'default', token, subdomain = '0', matrixSet = TILE_MATRIX_SET, level, row, col,
}) {
  return tiandituUrlTemplate({ layer, style, token, matrixSet })
    .replace('{s}', String(subdomain))
    .replace('{TileMatrix}', String(level))
    .replace('{TileRow}', String(row))
    .replace('{TileCol}', String(col))
}

/**
 * 后端配置 → 组件要的图层描述数组。
 *
 * ⚠️ **没配 key 时返回空数组**：这是"关闭状态下零瓦片请求"的根本保证 ——
 * 组件拿到空数组就不会创建任何 provider，一行网络请求都不会发。
 *
 * @param {{enabled?: boolean, token?: string|null, maxLevel?: number, subdomains?: string[]}} config
 * @param {'street'|'image'} style 样式（见 {@link TIANDITU_STYLES}）
 * @returns {Array<{layer: string, name: string, url: string, maximumLevel: number, subdomains: string[]}>}
 */
export function layerDescriptors(config, style = DEFAULT_STYLE) {
  if (!config || !config.enabled) return []
  const token = typeof config.token === 'string' ? config.token.trim() : ''
  if (token === '') return []          // 双保险：只有空白 = 没配（与后端同一口径）
  const spec = TIANDITU_STYLES[style] ?? TIANDITU_STYLES[DEFAULT_STYLE]
  // 层级上限取"样式上限"与"后端配置上限"的较小者：
  // 影像样式必须压到 12，否则 L13+ 全是「此级别下，该区域无影像」占位图
  const configured = Number.isFinite(config.maxLevel) ? config.maxLevel : spec.maxLevel
  const maximumLevel = Math.min(spec.maxLevel, configured)
  const subdomains = Array.isArray(config.subdomains) && config.subdomains.length > 0
    ? config.subdomains
    : DEFAULT_SUBDOMAINS
  return spec.layers.map((l) => ({
    layer: l.layer,
    name: l.name,
    url: tiandituUrlTemplate({ layer: l.layer, token }),
    maximumLevel,
    subdomains,
  }))
}

/** 没配 key 时给用户看的一句提示（要指到具体文件，否则等于没说） */
export function missingTokenHint() {
  return '未配置天地图 key：把它填进 backend/src/main/resources/application-local.yml 的 '
    + 'calcite.map.tianditu-token（见 docs/DEPLOY.md「可选：开启天地图底图」）。'
}

/** 开关按钮上的文案 */
export function basemapLabel(on) {
  return on ? '天地图（街道）' : '离线底图'
}
