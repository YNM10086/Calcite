<script setup>
/**
 * 数据编辑视图 —— 添加 / 替换 / 改名 / 删除。
 *
 * 和 TrackList 的分工不同：TrackList 是**纯展示**组件（不发请求），
 * 而这里是**唯一会写数据的组件** —— 改名（PATCH）、删除（DELETE）、
 * 上传（POST import）都在这里发。理由：这三件事是同一个"事务"的三个动作，
 * 它们的加载态 / 错误提示 / 弹窗是共用的，拆到 App 里反而要把一堆中间状态往上提。
 * （App 仍然是**唯一的数据源**：本组件改完之后只喊一声 `changed`，由 App 去重新拉列表。）
 *
 * 只读的那部分（列表 + 来源/条数筛选 + 分页）**直接沿用 TrackList 那一套**：
 * 筛选状态由 App 持有、通过 prop 回显、改动时 emit `filter` 上报 ——
 * 不自造第二套，否则同一个列表在两处会有两种筛选行为。
 */
import { nextTick, ref } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import { conflictText, deleteConfirmText, formatLength, formatPoints } from '../lib/dataEdit.js'

const props = defineProps({
  tracks: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  selectedId: { type: Number, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  // 筛选条件：状态在 App 里，这里只回显 + 上报（与 TrackList 完全一致）
  sourceFilter: { type: String, default: '' },
  limit: { type: Number, default: 50 },
})

const emit = defineEmits(['back', 'changed', 'filter', 'focus'])

/** 来源的显示名 —— 后端给的是 geolife / gpx / sample */
const SOURCE_LABELS = { geolife: 'GeoLife', gpx: '我的 GPX', sample: '示例数据' }
function sourceLabel(s) {
  return SOURCE_LABELS[s] || s || '—'
}

/** 秒 → "X 小时 Y 分" / "Y 分钟"（与 TrackList 同一套写法） */
function formatDuration(s) {
  if (s == null) return '—'
  const hours = Math.floor(s / 3600)
  const minutes = Math.round((s % 3600) / 60)
  return hours > 0 ? `${hours} 小时 ${minutes} 分` : `${minutes} 分钟`
}

/** ISO 时间字符串 → 本地时间（后端给的是 UTC，浏览器自动换算成东八区） */
function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

/** 用户在筛选栏改了来源 / 条数 → 上报（形状与 TrackList 的 `filter` 事件一致） */
function onSourceChange(ev) {
  emit('filter', { source: ev.target.value, limit: props.limit })
}
function onLimitChange(ev) {
  emit('filter', { source: props.sourceFilter, limit: Number(ev.target.value) })
}

/* ==================== 一个弹窗，服务四种用途 ==================== */
/*
 * 删除确认 / 同名冲突 / 导入完成 / 出错，共用同一个 ConfirmDialog。
 *
 * ⚠️ **`kind` 决定按钮怎么接**，而其中只有 `cancel` 有一条约死的规矩：
 * `cancel` **永远只接 closeDialog** —— 因为 ConfirmDialog 的遮罩点击也抛 `cancel`，
 * 用户"点弹窗外面"必须等于"关掉弹窗"，绝不能等于"再上传一次"。
 * 冲突场景里那个"再上传一次"（新增为另一条）走的是**第三个按钮** `@alt`。
 */
const dialog = ref({
  open: false,
  kind: '',
  title: '',
  body: '',
  confirmText: '确定',
  cancelText: '取消',
  altText: '',
  danger: false,
})
/** 弹窗打开时携带的业务数据（要删的那条轨迹 / 409 的响应体） */
const dialogPayload = ref(null)

/**
 * 打开弹窗。
 *
 * @param kind        用途：'delete' | 'conflict' | 'info' | 'error'
 * @param title       标题
 * @param body        正文（可含换行）
 * @param confirmText 右侧主按钮文案
 * @param danger      主按钮是否标红（不可逆动作用）
 * @param payload     业务数据，见 dialogPayload
 * @param cancelText  左侧按钮文案；**传空串则不渲染**（提示类弹窗只留「知道了」）
 * @param altText     中间第三个按钮文案；传空串则不渲染
 */
function openDialog(kind, title, body, confirmText, danger, payload,
                    cancelText = '取消', altText = '') {
  dialog.value = { open: true, kind, title, body, confirmText, danger, cancelText, altText }
  dialogPayload.value = payload ?? null
}

function closeDialog() {
  dialog.value = { ...dialog.value, open: false }
  dialogPayload.value = null
}

/* ==================== 改名（行内编辑，不弹窗） ==================== */
/*
 * 为什么行内编辑而不是弹窗：改名是轻操作，弹窗太重；
 * 而且行内编辑能**看着那一行**改，不容易改错对象。
 */
const editingId = ref(null)
const editingName = ref('')
const renameInput = ref(null)
const busy = ref(false)

/**
 * 拿到输入框的真实 DOM（函数式模板 ref）。
 *
 * 为什么不用 `ref="renameInput"` 这种字符串写法：这个 input 在 `v-for` 里面，
 * Vue 3 会把 v-for 里的模板 ref **收集成数组**，取值要多套一层判断；
 * 函数式 ref 是逐个元素回调的，没有这个歧义。
 */
function setRenameInput(el) {
  if (el) renameInput.value = el
}

async function startRename(t) {
  editingId.value = t.id
  editingName.value = t.name
  // 等输入框真的进 DOM 之后再聚焦，否则拿到的是 null
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

function cancelRename() {
  editingId.value = null
  editingName.value = ''
}

/** 回车保存 / Esc 取消（Esc 走 cancelRename，不发请求） */
async function saveRename() {
  const id = editingId.value
  const name = editingName.value.trim()
  if (!id) return cancelRename()
  // 名字空着就当用户放弃 —— 让后端去报 400 只会让他多关一个弹窗
  if (!name) return cancelRename()

  busy.value = true
  try {
    const res = await fetch(`/api/tracks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) {
      const msg = res.status === 400
        ? '名字不合法（不能为空、不能超过 200 字）'
        : res.status === 404
          ? '这条轨迹已经不在了（可能被别处删掉了）'
          : `HTTP ${res.status}`
      throw new Error(msg)
    }
    cancelRename()
    emit('changed') // 让 App 去刷新（后端在改名时已经清了相似度缓存）
  } catch (e) {
    openDialog('error', '改名失败', String(e.message), '知道了', false, null, '')
  } finally {
    busy.value = false
  }
}

/* ==================== 删除 ==================== */
function askDelete(t) {
  openDialog('delete', '删除轨迹',
    deleteConfirmText(t.name, t.pointCount), '删除', true, t)
}

async function doDelete() {
  const t = dialogPayload.value
  if (!t) return closeDialog()

  busy.value = true
  try {
    const res = await fetch(`/api/tracks/${t.id}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (res.status === 404) throw new Error('这条轨迹已经不在了（可能被别处删掉了）')
    if (!res.ok) {
      /*
       * 500 只有一个来源：服务端**写不出回收站文件**。
       * 后端的设计是"导出失败就不删"（fail-safe），所以这时轨迹**原样还在** ——
       * 这句必须说清楚，否则用户会以为"删了一半"。
       *
       * 后端 500 的响应体里没有 message（Spring 默认 server.error.include-message=never），
       * 所以具体原因由这里补上，不能只丢一个 HTTP 500 给用户。
       */
      throw new Error(data.message
        || `删除失败（HTTP ${res.status}）。服务端把这条轨迹导出到回收站时出错了，`
         + '所以没有执行删除 —— 它仍然在库里。')
    }
    closeDialog()
    emit('changed')
    // 把回收站路径告诉用户 —— 他当场就知道东西在哪，需要时能找回来
    openDialog('info', '已删除',
      `「${t.name}」已删除（${data.deletedPointCount} 个点）。\n\n回收站文件：\n${data.recyclePath}`,
      '知道了', false, null, '')
  } catch (e) {
    closeDialog()
    openDialog('error', '删除失败', String(e.message), '知道了', false, null, '')
  } finally {
    busy.value = false
  }
}

/* ==================== 添加（上传）+ 同名冲突 ==================== */
const pendingFile = ref(null)
const uploading = ref(false)

/**
 * 上一次"因为同名被拦下来"的身份（轨 id + 文件指纹）。
 *
 * ⚠️ 这是**防死循环的兜底**，不是业务逻辑。
 * 「新增为另一条」现在已经会带 `allowSameName=true` 重新提交、后端必然放行
 * （见 submitUpload 的注释），所以同一个冲突**不会出现第二次**、这段护栏正常打不到。
 * 但它仍然留着，有两个理由：
 *   ① 它不影响正确路径 —— 第一次撞 409 时判据不相等，三个按钮照样齐；
 *   ② 万一连的是**没带 allowSameName 的旧版后端**，它还能把用户从死循环里捞出来
 *      （顶多少一个按钮、并说明原因，比"点了没反应"好）。
 * 另外 `.tmp/check-data-manager-sfc.mjs` §4b 用源码扫描钉住了这段结构，
 * 要删就得同时改那个脚本 —— 不在本次改动的文件范围内，故保持原样。
 */
let lastConflictKey = ''

async function onUpload(ev) {
  const file = ev.target.files?.[0]
  // 立刻清空 input，否则连续选同一个文件不会再触发 change
  ev.target.value = ''
  if (!file) return
  pendingFile.value = file
  lastConflictKey = '' // 换了文件就是一次全新的尝试
  await submitUpload('append', null)
}

/**
 * 提交上传。
 *
 * ⚠️ 用户选「替换它」时**不需要重新选文件** —— pendingFile 还在内存里，
 * 拿同一个 File 对象再提交一次即可（File 是不可变的，重发不会"用掉"它）。
 *
 * @param mode          'append'（新增）| 'replace'（替换）
 * @param replaceTrackId mode=replace 时要替换哪一条
 * @param allowSameName 用户是否**已经明确表态**"就要新增一条同名的"（默认 false）。
 *
 *   ⚠️ 这个参数是「新增为另一条」能走通的唯一开关，理由要说清楚：
 *   同名冲突是**两段式**交互 —— 第一次上传（false）后端返回 409 让用户选；
 *   用户看过那个 409、点「新增为另一条」之后重新提交时**必须**带 true。
 *   两次提交的 mode 都是 'append'、replaceTrackId 都是 null，
 *   后端只靠这两个值分不出"要不要拦"，于是每次都会返回同一个 409 ——
 *   用户就会在同一个弹窗里无限打转（曾经的真实 bug）。
 *   所以由前端在这里**显式声明意图**：首次上传 false、点过「新增为另一条」true。
 */
async function submitUpload(mode, replaceTrackId, allowSameName = false) {
  const file = pendingFile.value
  if (!file) return

  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const params = new URLSearchParams({ mode })
    if (replaceTrackId != null) params.set('replaceTrackId', String(replaceTrackId))
    // 只有用户明确选过「新增为另一条」才带上；不带时后端按 false 处理（首次上传照旧拦 409）
    if (allowSameName) params.set('allowSameName', 'true')

    const res = await fetch(`/api/tracks/import?${params}`, { method: 'POST', body: fd })
    const data = await res.json().catch(() => ({}))

    if (res.status === 409) {
      /*
       * 同名（或同内容）让用户自己决定 —— 这正是后端用 409 而不是 400 的用意。
       * 按钮排成「取消 / 新增为另一条 / 替换它」：
       * 其中**只有 cancel 会走 closeDialog**，所以点弹窗外面 = 什么都不做。
       */
      const sameContent = data.conflictType === 'SAME_CONTENT'

      /*
       * ⚠️ 死循环兜底（正常路径打不到，见 lastConflictKey 的注释）：
       *
       * 历史 bug 的成因写在这里，免得以后有人把 allowSameName 又删了：
       * 后端同名检测原来是 `if (conflict.isPresent() && !replace) throw 409`，
       * 而 mode=append 时 `replace` 恒为 false、`replaceTrackId` 恒为 null
       * （`findNameConflict(name, null)` 谁也排除不掉）——
       * 于是**同名 + 新增这条组合永远拿不到 200**，只会再返回一次一模一样的 409，
       * 用户点「新增为另一条」→ 弹窗关掉又原样弹回来，界面上也没说"这条路走不通"。
       *
       * 现在的正路是：点「新增为另一条」→ `submitUpload('append', null, true)`
       * → 后端拿到 allowSameName=true 放行 → 真的插进第二条同名轨迹。
       *
       * 万一（旧的 / 没更新的服务端）又撞回同一个冲突，就把第三个按钮撤掉并说明原因 ——
       * 但**仍然保留「替换它 / 取消」**：路可以少一条，不能把用户关在弹窗里。
       * （判据带上文件指纹：用户换了个文件重新上传时，要允许他再试一次。）
       */
      let canKeepBoth = true
      if (!sameContent) {
        const key = `${data.existingTrackId}|${file.name}|${file.size}|${file.lastModified}`
        if (key === lastConflictKey) {
          canKeepBoth = false
        } else {
          lastConflictKey = key
        }
      }

      openDialog('conflict',
        sameContent ? '这个文件已经在库里了' : '发现同名轨迹',
        conflictText(data) + (canKeepBoth ? '' :
          '\n\n⚠️ 后端目前不允许"同名新增" —— 再点一次还是会被同一个 409 拦下来。'
          + '\n想保留两份：先把文件里的轨迹名（或文件名）改掉，再重新上传。'),
        sameContent ? '知道了' : '替换它',
        false, data,
        sameContent ? '' : '取消',
        (sameContent || !canKeepBoth) ? '' : '新增为另一条')
      return
    }
    // 400 的响应体是 {"error": "..."}（ImportController 的异常处理器），不是 message
    if (!res.ok) throw new Error(data.message || data.error || `HTTP ${res.status}`)

    pendingFile.value = null
    lastConflictKey = ''
    closeDialog()
    emit('changed')
    openDialog('info', '导入完成', importSummary(data), '知道了', false, null, '')
  } catch (e) {
    openDialog('error', '导入失败', String(e.message), '知道了', false, null, '')
  } finally {
    uploading.value = false
  }
}

/**
 * 导入结果的一句话摘要。
 *
 * 为什么还要看 `skippedDuplicate`：上传一份**内容完全相同**的文件时后端是幂等的
 * （返回 200 + skippedDuplicate=true，一条新轨迹都没有），
 * 这时说"导入完成"会让用户以为库里多了一条 —— 必须明说"没有重复导入"。
 */
function importSummary(data) {
  if (data.skippedDuplicate) {
    return `这份内容已经在库里了（「${data.name}」），没有重复导入。`
  }
  const lines = [
    `已处理：${data.name ?? ''}`,
    `${formatPoints(data.pointCount)} · ${formatLength(data.distanceM)} · ${formatDuration(data.durationS)}`,
  ]
  if (data.outlierCount > 0) lines.push(`标记 ${data.outlierCount} 个疑似漂移点`)
  return lines.join('\n')
}

/** 冲突弹窗上点「替换它」（原地更新已有的那条，trackId 不变） */
async function resolveConflict() {
  const body = dialogPayload.value
  // 内容已经在库里了 —— 没什么可替换的，这个按钮此时根本不渲染，留着只是兜底
  if (body?.conflictType === 'SAME_CONTENT') return closeDialog()
  closeDialog()
  await submitUpload('replace', body.existingTrackId)
}

/**
 * 冲突弹窗上点「新增为另一条」（第三个按钮，不是 cancel）。
 *
 * ⚠️ 必须传 allowSameName=true：这是**用户本人的明确表态**（他已经看过 409、
 * 知道库里有一条同名的，仍然要保留两份）。不传的话后端只能按"首次上传"处理，
 * 又返回同一个 409 —— 弹窗关了又原样弹回来，点几次都一样。
 */
async function resolveKeepBoth() {
  closeDialog()
  await submitUpload('append', null, true)
}

/* ==================== 弹窗按钮分发 ==================== */
function onDialogConfirm() {
  const kind = dialog.value.kind
  if (kind === 'delete') return doDelete()
  if (kind === 'conflict') return resolveConflict()
  closeDialog() // info / error：只有一个「知道了」
}

/**
 * ⚠️ **遮罩点击也走这里**，所以这里只能关弹窗，不许发任何写请求。
 * 「新增为另一条」挂在 @alt 上（见模板），不在这儿。
 */
function onDialogCancel() {
  closeDialog()
}

function onDialogAlt() {
  if (dialog.value.kind === 'conflict') return resolveKeepBoth()
}
</script>

<template>
  <div class="data-manager" data-testid="data-manager">
    <!-- 顶部返回条：管理视图不属于任何分析档，所以要有一条退路 -->
    <div class="back-bar">
      <button
        type="button"
        class="back-btn"
        data-testid="data-manager-back"
        @click="emit('back')"
      >← 返回</button>
      <span class="title">数据编辑</span>
      <span class="count">共 {{ total }} 条</span>
    </div>

    <div class="import-bar">
      <label class="import-btn" :class="{ off: uploading }">
        {{ uploading ? '正在处理…' : '添加数据' }}
        <input
          type="file"
          accept=".gpx,.plt"
          hidden
          :disabled="uploading"
          data-testid="import-input"
          @change="onUpload"
        />
      </label>
      <span class="import-hint">支持 GPX / GeoLife .plt</span>
    </div>
    <p class="import-hint note">名字或内容重复时会问你：替换还是新增。</p>

    <!-- 筛选 / 分页：与 TrackList 同一套（状态在 App，这里只回显 + 上报） -->
    <div class="filter-bar">
      <select :value="sourceFilter" data-testid="source-filter" @change="onSourceChange">
        <option value="">全部来源</option>
        <option value="geolife">GeoLife</option>
        <option value="gpx">我的 GPX</option>
        <option value="sample">示例数据</option>
      </select>
      <select :value="limit" data-testid="limit-filter" @change="onLimitChange">
        <option :value="20">20 条</option>
        <option :value="50">50 条</option>
        <option :value="100">100 条</option>
        <option :value="500">500 条</option>
      </select>
      <span class="count">
        共 {{ total }} 条<template v-if="tracks.length < total"> · 显示前 {{ tracks.length }}</template>
      </span>
    </div>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-else-if="error" class="hint bad">❌ {{ error }}</p>
    <p v-else-if="tracks.length === 0" class="hint">还没有轨迹数据</p>

    <div v-else class="rows" data-testid="data-manager-rows">
      <div
        v-for="t in tracks"
        :key="t.id"
        class="row"
        :class="{ active: t.id === selectedId }"
        data-testid="dm-row"
        @click="emit('focus', t.id)"
      >
        <!-- 编辑态：原地变成输入框。按钮区在编辑时整块收起，避免误点 -->
        <div v-if="editingId === t.id" class="edit" @click.stop>
          <input
            :ref="setRenameInput"
            v-model="editingName"
            class="rename-input"
            type="text"
            maxlength="200"
            data-testid="rename-input"
            :disabled="busy"
            @keyup.enter="saveRename"
            @keyup.esc="cancelRename"
          />
          <span class="edit-hint">回车保存 · Esc 取消</span>
        </div>

        <template v-else>
          <div class="main">
            <span class="line1">
              <span class="name" :title="t.name">{{ t.name }}</span>
              <span class="src">{{ sourceLabel(t.source) }}</span>
              <span v-if="t.id === selectedId" class="badge">已加载</span>
            </span>
            <span class="meta">
              {{ formatPoints(t.pointCount) }} · {{ formatLength(t.distanceM) }} ·
              {{ formatDuration(t.durationS) }} · {{ formatTime(t.startTime) }}
            </span>
          </div>

          <div class="ops">
            <button
              type="button"
              class="op"
              title="改名"
              data-testid="dm-rename"
              :disabled="busy"
              @click.stop="startRename(t)"
            >✎</button>
            <button
              type="button"
              class="op danger"
              title="删除"
              data-testid="dm-delete"
              :disabled="busy"
              @click.stop="askDelete(t)"
            >🗑</button>
          </div>
        </template>
      </div>
    </div>

    <ConfirmDialog
      :open="dialog.open"
      :title="dialog.title"
      :body="dialog.body"
      :confirm-text="dialog.confirmText"
      :cancel-text="dialog.cancelText"
      :alt-text="dialog.altText"
      :danger="dialog.danger"
      @confirm="onDialogConfirm"
      @cancel="onDialogCancel"
      @alt="onDialogAlt"
    />
  </div>
</template>

<style scoped>
.data-manager {
  /* 与 .track-list 同一条规矩：flex-basis 用 0 才能"占满面板剩下的空间"。
     ⚠️ App.vue 的 .panel > div:not(...) 必须把 .data-manager 排除掉，
     否则它会被当成固定内容（flex: 0 0 auto），矮窗口下被面板裁掉。 */
  flex: 1 1 0;
  min-height: var(--list-min, 88px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.back-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  margin-bottom: 8px;
}

.back-btn {
  padding: 4px 10px;
  border: 1px solid rgba(127, 209, 255, 0.45);
  border-radius: 7px;
  background: rgba(127, 209, 255, 0.12);
  color: #e7eef8;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.back-btn:hover {
  background: rgba(127, 209, 255, 0.25);
}

.title {
  font-size: 13px;
  color: #7fd1ff;
  font-weight: 600;
}

.count {
  margin-left: auto;
  font-size: 11px;
  color: #93a4bb;
}

.import-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.import-btn {
  padding: 5px 12px;
  border: 1px solid rgba(127, 209, 255, 0.45);
  border-radius: 7px;
  background: rgba(127, 209, 255, 0.12);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.import-btn:hover {
  background: rgba(127, 209, 255, 0.25);
}

/* 上传中：不给再点（一次只处理一个文件，否则 pendingFile 会被后一个覆盖） */
.import-btn.off {
  opacity: 0.55;
  pointer-events: none;
}

.import-hint {
  font-size: 11px;
  color: #93a4bb;
}

.note {
  flex: 0 0 auto;
  margin: 4px 0 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  margin: 8px 0;
}

.filter-bar select {
  padding: 3px 6px;
  border: 1px solid rgba(127, 209, 255, 0.28);
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.9);
  color: #e7eef8;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.filter-bar select:hover {
  border-color: rgba(127, 209, 255, 0.55);
}

.hint {
  margin: 4px 0;
  font-size: 12px;
  color: #93a4bb;
}

.bad {
  color: #ff9b9b;
}

/* 只有行列表滚动，上面的返回条 / 添加区 / 筛选栏固定不动 */
.rows {
  flex: 1 1 0;
  min-height: 40px;
  overflow-y: auto;
}

.row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid rgba(127, 209, 255, 0.16);
  border-radius: 7px;
  background: rgba(127, 209, 255, 0.05);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.row + .row {
  margin-top: 6px;
}

.row:hover {
  border-color: rgba(127, 209, 255, 0.45);
  background: rgba(127, 209, 255, 0.12);
}

.row.active {
  border-color: #7fd1ff;
  background: rgba(127, 209, 255, 0.2);
}

.main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.line1 {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 13px;
  color: #e7eef8;
}

.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.src {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 4px;
  background: rgba(127, 209, 255, 0.18);
  color: #7fd1ff;
  font-size: 10px;
  line-height: 15px;
}

.badge {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 4px;
  background: #7fd1ff;
  color: #0a101a;
  font-size: 10px;
  line-height: 15px;
}

.meta {
  font-size: 11px;
  color: #93a4bb;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ops {
  display: flex;
  gap: 4px;
}

.op {
  width: 26px;
  height: 24px;
  border: 1px solid rgba(127, 209, 255, 0.32);
  border-radius: 6px;
  background: transparent;
  color: #e7eef8;
  font: inherit;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}

.op:hover {
  background: rgba(127, 209, 255, 0.2);
}

.op.danger {
  border-color: rgba(255, 90, 90, 0.5);
  color: #ffb3b3;
}

.op.danger:hover {
  background: rgba(255, 90, 90, 0.2);
}

.op:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.edit {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.rename-input {
  width: 100%;
  padding: 4px 6px;
  border: 1px solid #7fd1ff;
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.95);
  color: #e7eef8;
  font: inherit;
  font-size: 12px;
}

.edit-hint {
  font-size: 10px;
  color: #93a4bb;
}
</style>
