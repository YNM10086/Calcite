/**
 * 数据管理的纯计算模块：格式化、文案拼装。
 *
 * 只放「输入 → 输出」的函数，不碰 Vue、不碰浏览器 API —— 所以能用 node 直接测
 * （scripts/check-data-edit.mjs）。
 */

/*
 * ⚠️ 本文件所有"数值 → 文案"的函数都遵守同一条铁律：**先挡 null/undefined，再判 NaN**。
 *
 * 为什么不能只写 `Number.isFinite(Number(v))`：`Number(null) === 0` 是**有限数**，
 * 它会让"这个值还不知道"静默变成"0" —— 后果不是格式难看，而是**说了一个错的事实**：
 *   - `formatPoints(null)` → '0 个点'（把"没数据"说成"空轨迹"）
 *   - `conflictText` 里 → '（null 个点）'（用户以为程序坏了）
 * 这个坑在 similarity.js 的 `formatDays` / `formatPct` 上已经踩过一次，
 * 兜底写法与 density.js 的 `formatCount` 保持一致。
 * 后端 `TrackConflictResponse.newPointCount` 的 Javadoc 明写"解析失败时为 null"，
 * 所以这些 null 分支**不是防御性编程，是真实会走到的路径**。
 */

/**
 * 点数文案。
 *
 * @param {number|null|undefined} n 点数
 * @returns {string} 例：`456 个点`；缺值返回 `—`
 */
export function formatPoints(n) {
  if (n == null) return '—'
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return `${v} 个点`
}

/**
 * 长度文案：小于 1 公里用米（取整），否则用公里（保留 1 位）。
 *
 * @param {number|null|undefined} m 长度（米）
 * @returns {string} 例：`715 米` / `14.9 km`；缺值返回 `—`
 */
export function formatLength(m) {
  if (m == null) return '—'
  const v = Number(m)
  if (!Number.isFinite(v)) return '—'
  if (v < 1000) return `${Math.round(v)} 米`
  return `${(v / 1000).toFixed(1)} km`
}

/**
 * 冲突响应里的一个点数 → 文案。
 *
 * ⚠️ 单独抽一个函数，是为了**两个字段各兜一次底**，
 * 而不是让调用处各写一遍 `Number.isFinite(...)`（那个写法挡不住 null，见文件头注释）。
 *
 * @param {number|null|undefined} v 后端给的原始值
 * @param {string} fallback 缺值时的文案（拼进句子里，必须读起来通顺）
 */
function pointCountText(v, fallback) {
  if (v == null) return fallback
  const n = Number(v)
  if (!Number.isFinite(n)) return fallback
  return `${n} 个点`
}

/**
 * 同名 / 同内容冲突的文案（HTTP 409 响应体 → 给用户看的一段话）。
 *
 * ⚠️ 每个字段都要兜底 —— 后端某个字段为 null 时，
 * 拼接出来会出现 "（null 个点）" 这种东西，比不显示还糟。
 *
 * 为什么要把两边的点数都摆出来：用户做决定时需要知道"要覆盖的是个什么东西"，
 * "已有『资料一』（456 个点），你上传的这份有 623 个点"比一句"已存在"有用得多。
 *
 * @param {object|null} body 后端的 `TrackConflictResponse`
 */
export function conflictText(body) {
  const b = body || {}
  // 名字用 `||` 兜底即可：空字符串也走兜底分支，符合"没名字"的语义
  const name = b.existingName || '（未知名称）'
  if (b.conflictType === 'SAME_CONTENT') {
    return `这个文件的内容已经作为「${name}」存在了 —— 库里不会有两份一模一样的轨迹。`
  }
  const oldN = pointCountText(b.existingPointCount, '（点数未知）')
  const newN = pointCountText(b.newPointCount, '（点数未知）')
  return `已有同名轨迹「${name}」（${oldN}）。你上传的这份有 ${newN}。`
}

/**
 * 删除确认弹窗的正文。
 *
 * ⚠️ **最后两句是故意的**：把"不可恢复"从一句恐吓变成**一个真实的操作指引** ——
 * 用户知道东西去哪了、怎么找回来，就不会因为害怕而不敢用这个功能。
 * 所以它们不是装饰，删掉就等于把这个功能变成一个让人不敢点的按钮
 * （check-data-edit.mjs 里有两条测试专门钉住"回收站"和"重新导入"缺一不可）。
 *
 * @param {string|null|undefined} name 轨迹名
 * @param {number|null|undefined} pointCount 点数
 */
export function deleteConfirmText(name, pointCount) {
  const n = name || '（未命名）'
  // 点数未知时**不能**写 "0 个"：那是在承诺"删掉 0 个点"，
  // 而事实是"要连带删掉一批点，只是数量还不知道" —— 宁可不说数字，也不能说错数字。
  const pts = pointCount == null ? NaN : Number(pointCount)
  const pointLine = Number.isFinite(pts)
    ? `会连带删除它的 ${pts} 个轨迹点。`
    : '会连带删除它名下的所有轨迹点。'
  return [
    `确定删除「${n}」？`,
    '',
    pointLine,
    '',
    '💡 删除前会自动导出到回收站目录，需要的话可以从那里找回来。',
    '   数据库里删掉后，也可以从原始文件重新导入。',
  ].join('\n')
}
