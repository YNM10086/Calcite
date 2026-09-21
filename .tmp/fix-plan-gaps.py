# -*- coding: utf-8 -*-
r"""计划自查发现的四处修正。

① 【路径穿越风险】safeFileName("..") 原样返回 ".." —— resolve 之后会跑到【上一级目录】。
   必须把 "." 和 ".." 当成危险值处理。顺带修那条写得莫名其妙的测试。

② 【性能/正确性】findNameConflict 用 findRecent(500) 当全表查 —— 只看了最新 500 条。
   改成给 TrackRepository 加一个 findFirstByName 派生查询。

③ 【编译不过】replaceInPlace 用了 trackPointRepository.deleteByTrackId(id)，但那个方法没声明。
   必须显式加到接口里（Spring Data 派生删除，但方法得先声明）。

④ 【计划不合格】Task 6 的 DataManager 只给了注释骨架 —— writing-plans 明确要求
   "代码步骤必须给出真实代码"。把三个关键函数（删除 / 改名 / 冲突处理）补成真代码。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-plan-gaps.py
"""
import io
import sys

P = "docs/superpowers/plans/2026-09-21-data-management.md"

EDITS = []

# ---------- ① safeFileName 处理 . 和 .. ----------
EDITS.append((
    """        String s = raw.replaceAll("[\\\\\\\\/:*?\\"<>|\\\\s]+", "_");
        if (s.length() > 80) {""",
    """        String s = raw.replaceAll("[\\\\\\\\/:*?\\"<>|\\\\s]+", "_");
        // ⚠️ "." 和 ".." 是【路径穿越】—— resolve 之后会跑到上一级目录。
        // 它们不包含上面那组非法字符，所以必须单独挡。
        if (s.equals(".") || s.equals("..")) {
            return "unnamed";
        }
        if (s.length() > 80) {""",
))

# ---------- ① 修那条莫名其妙的测试 ----------
EDITS.append((
    """        assertEquals("__", TrackExporter.safeFileName("..").replace(".", "_"));""",
    """        // ⚠️ "." 和 ".." 是路径穿越 —— 必须挡掉，不能原样当文件名
        assertEquals("unnamed", TrackExporter.safeFileName("."));
        assertEquals("unnamed", TrackExporter.safeFileName(".."));""",
))

# ---------- ② findNameConflict 改用派生查询 ----------
EDITS.append((
    """/** 库里有没有另一条同名轨迹（没有就返回 empty） */
    public java.util.Optional<Long> findNameConflict(String name, Long excludeTrackId) {
        return trackRepository.findRecent(org.springframework.data.domain.PageRequest.of(0, 500))
                .stream()
                .filter(t -> t.getName().equals(name))
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId)
                .findFirst();
    }""",
    """/**
     * 库里有没有另一条同名轨迹（没有就返回 empty）。
     *
     * <p>用派生查询 {@code findFirstByName} 而不是"把前 500 条拉回来在内存里筛" ——
     * 后者只看了最新的 500 条，是有边界 bug 的写法。
     */
    public java.util.Optional<Long> findNameConflict(String name, Long excludeTrackId) {
        return trackRepository.findFirstByName(name)
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId);
    }""",
))

# ---------- ③ 声明 deleteByTrackId + findFirstByName ----------
EDITS.append((
    """- [ ] **Step 1: 给 `TrackController` 注入 `TrackEditService` 并加两个端点**""",
    """- [ ] **Step 0: 给两个仓储补两个方法（否则编译不过）**

`TrackRepository` 加：

```java
    /**
     * 按名字找一条轨迹（同名检测用）。
     *
     * <p>Spring Data 的派生查询 —— 方法名翻译成 SQL 的 {@code WHERE name = ? LIMIT 1}。
     */
    Optional<Track> findFirstByName(String name);
```

`TrackPointRepository` 加：

```java
    /**
     * 删掉某条轨迹的全部点（"替换"时先清空旧的）。
     *
     * <p>派生删除：Spring Data 会翻译成 {@code DELETE FROM track_point WHERE track_id = ?}。
     * <b>为什么不用 {@code track_pointRepository.deleteAll(points)}</b>：
     * 那会把几万个实体一个个查出来再删 —— 慢得多，而且内存里要放 1 万多个对象。
     */
    void deleteByTrackId(Long trackId);
```

> ⚠️ 派生删除方法**必须加 `@Transactional`**（在调用它的 service 方法上已经有）。

- [ ] **Step 1: 给 `TrackController` 注入 `TrackEditService` 并加两个端点**""",
))

# ---------- ④ 把 DataManager 的骨架补成真代码 ----------
EDITS.append((
    """```javascript
import { ref, computed } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import { formatPoints, formatLength, conflictText, deleteConfirmText } from '../lib/dataEdit.js'

const props = defineProps({
  tracks: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  sourceFilter: { type: String, default: '' },
  limit: { type: Number, default: 50 },
  /** 当前选中的轨迹 id（改名/删除要提示"你正在改的是哪条"） */
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['back', 'changed', 'filter', 'limit', 'focus'])

// ---- 弹窗状态：三种用途共用一个 ConfirmDialog ----
const dialog = ref({ open: false, kind: '', payload: null })

// ---- 改名 ----
const editingId = ref(null)
const editingName = ref('')

// ---- 上传 + 409 ----
const pendingFile = ref(null)

async function onDelete(id, name, points) { /* 打开删除确认 */ }
async function doDelete() { /* DELETE → emit('changed') */ }
async function onRename(id, name) { /* 进编辑态 */ }
async function saveRename() { /* PATCH → emit('changed') */ }
async function onUpload(ev) { /* POST；409 时打开冲突弹窗 */ }
async function resolveConflict(choice) { /* 用同一个 File 对象重提交 */ }
```""",
    """```javascript
import { ref, computed } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import { formatPoints, formatLength, conflictText, deleteConfirmText } from '../lib/dataEdit.js'

const props = defineProps({
  tracks: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  sourceFilter: { type: String, default: '' },
  limit: { type: Number, default: 50 },
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['back', 'changed', 'filter', 'limit', 'focus'])

// ---- 弹窗：一个 ConfirmDialog 服务三种用途（删除确认 / 同名冲突 / 错误提示）----
const dialog = ref({ open: false, kind: '', title: '', body: '', confirmText: '', danger: false })
const dialogPayload = ref(null)

function openDialog(kind, title, body, confirmText, danger, payload) {
  dialog.value = { open: true, kind, title, body, confirmText, danger }
  dialogPayload.value = payload ?? null
}
function closeDialog() {
  dialog.value = { ...dialog.value, open: false }
  dialogPayload.value = null
}

/* ============================ 改名（行内编辑） ============================ */
const editingId = ref(null)
const editingName = ref('')
const busy = ref(false)

function startRename(t) {
  editingId.value = t.id
  editingName.value = t.name
}
function cancelRename() {
  editingId.value = null
  editingName.value = ''
}
async function saveRename() {
  const id = editingId.value
  const name = editingName.value.trim()
  if (!id || !name) return cancelRename()
  busy.value = true
  try {
    const res = await fetch(`/api/tracks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) {
      const msg = res.status === 400 ? '名字不合法（不能为空、不能超过 200 字）' : `HTTP ${res.status}`
      throw new Error(msg)
    }
    cancelRename()
    emit('changed')          // 让 App 去刷新（后端已经清了相似度缓存）
  } catch (e) {
    openDialog('error', '改名失败', String(e.message), '知道了', false)
  } finally {
    busy.value = false
  }
}

/* ============================ 删除 ============================ */
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
      // 500 多半是回收站写不进去 —— 后端【拒绝删除】了，轨迹还在
      throw new Error(data.message || `删除失败（HTTP ${res.status}）。轨迹没有被删除。`)
    }
    closeDialog()
    emit('changed')
    // 把回收站路径告诉用户 —— 他当场就知道东西在哪
    openDialog('info', '已删除',
      `「${t.name}」已删除（${data.deletedPointCount} 个点）。\\n\\n回收站文件：\\n${data.recyclePath}`,
      '知道了', false)
  } catch (e) {
    closeDialog()
    openDialog('error', '删除失败', String(e.message), '知道了', false)
  } finally {
    busy.value = false
  }
}

/* ============================ 上传 + 同名冲突 ============================ */
const pendingFile = ref(null)
const uploading = ref(false)

async function onUpload(ev) {
  const file = ev.target.files?.[0]
  if (!file) return
  pendingFile.value = file
  await submitUpload('append', null)
  ev.target.value = ''            // 允许再次选同一个文件
}

/**
 * 提交上传。
 *
 * ⚠️ 用户选"替换"时【不需要重新选文件】—— pendingFile 还在内存里，
 * 直接用同一个 File 对象再提交一次即可。
 */
async function submitUpload(mode, replaceTrackId) {
  const file = pendingFile.value
  if (!file) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const params = new URLSearchParams({ mode })
    if (replaceTrackId != null) params.set('replaceTrackId', String(replaceTrackId))
    const res = await fetch(`/api/tracks/import?${params}`, { method: 'POST', body: fd })
    const data = await res.json().catch(() => ({}))

    if (res.status === 409) {
      // 让用户决定 —— 这正是"同名检测返回 409"的设计意图
      openDialog('conflict', '发现同名/同内容轨迹',
        conflictText(data), '替换它', false, data)
      return
    }
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`)

    pendingFile.value = null
    closeDialog()
    emit('changed')
    openDialog('info', '导入完成', `已处理：${data.name ?? ''}`, '知道了', false)
  } catch (e) {
    openDialog('error', '导入失败', String(e.message), '知道了', false)
  } finally {
    uploading.value = false
  }
}

/** 冲突弹窗上点"替换它" */
async function resolveConflict() {
  const body = dialogPayload.value
  if (body?.conflictType === 'SAME_CONTENT') {
    // 内容已经在了，没什么可替换的 —— 只提示
    closeDialog()
    return
  }
  closeDialog()
  await submitUpload('replace', body.existingTrackId)
}

/** 冲突弹窗上点"新增为另一条" */
async function resolveKeepBoth() {
  closeDialog()
  await submitUpload('append', null)
}

/* ============================ 弹窗按钮分发 ============================ */
function onDialogConfirm() {
  const kind = dialog.value.kind
  if (kind === 'delete') return doDelete()
  if (kind === 'conflict') return resolveConflict()
  closeDialog()
}
```""",
))

# 冲突弹窗需要三个按钮 —— 补一句说明
EDITS.append((
    """- 同名 409 → 用 `ConfirmDialog` 显示 `conflictText(body)`，两个按钮「替换它」/「新增为另一条」""",
    """- 同名 409 → 用 `ConfirmDialog` 显示 `conflictText(body)`，两个按钮「替换它」/「新增为另一条」

> ⚠️ **`ConfirmDialog` 只有两个按钮**（取消 / 确定）。
> 冲突场景需要「替换它」和「新增为另一条」**两个都是正向选项** ——
> 所以 `DataManager` 里给 `ConfirmDialog` 传的 `cancelText` 用「新增为另一条」，
> 并把它的 `@cancel` 接到 `resolveKeepBoth()` 上（**不是** `closeDialog`）。
> 执行时按这个接法实现。""",
))


def main():
    with io.open(P, encoding="utf-8") as fh:
        t = fh.read()
    ok = True
    for old, new in EDITS:
        n = t.count(old)
        if n != 1:
            print(f"  [XX] 期望命中 1 次，实得 {n}：{old[:64]!r}")
            ok = False
            continue
        t = t.replace(old, new)
        print(f"  [OK] {old[:56]}…")
    if ok:
        with io.open(P, "w", encoding="utf-8", newline="") as fh:
            fh.write(t)
    print()
    print("全部修正完成" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
