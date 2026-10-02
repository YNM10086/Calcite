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

/** 最大层级默认值。街道矢量图要 18 级才看得到建筑轮廓（16 级以下基本只有路网） */
export const DEFAULT_MAX_LEVEL = 18

/** 天地图瓦片子域 t0~t7 */
export const DEFAULT_SUBDOMAINS = ['0', '1', '2', '3', '4', '5', '6', '7']

/**
 * 两个图层：矢量底图（路网 + 高层级的建筑轮廓）与注记（路名/地名）。
 * 顺序即叠放顺序 —— 注记必须在底图**之上**，否则会被底图盖住。
 */
export const TIANDITU_LAYERS = [
  { layer: 'vec', name: '街道矢量底图' },
  { layer: 'cva', name: '注记（路名 / 地名）' },
]

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
 * @returns {Array<{layer: string, name: string, url: string, maximumLevel: number, subdomains: string[]}>}
 */
export function layerDescriptors(config) {
  if (!config || !config.enabled) return []
  const token = typeof config.token === 'string' ? config.token.trim() : ''
  if (token === '') return []          // 双保险：只有空白 = 没配（与后端同一口径）
  const maximumLevel = Number.isFinite(config.maxLevel) ? config.maxLevel : DEFAULT_MAX_LEVEL
  const subdomains = Array.isArray(config.subdomains) && config.subdomains.length > 0
    ? config.subdomains
    : DEFAULT_SUBDOMAINS
  return TIANDITU_LAYERS.map((l) => ({
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
