<script setup>
/**
 * 轨迹列表 —— 纯展示组件（"哑组件"）
 *
 * 它自己不发请求：数据由父组件 App.vue 传进来，点击时只往外抛一个事件。
 * 这样做的好处是数据流单向、好调试：
 *   App 拿数据 → 传给 TrackList 显示 → 用户点了 → TrackList 喊一声 → App 去处理
 *
 * ⚠️ 上传表单（添加数据）**已经不在这里了**，搬到了 DataManager.vue。
 * 原因：上传会往库里写数据，而"写数据"的那几个动作（添加 / 替换 / 改名 / 删除）
 * 现在是同一个视图里的一组操作，它们的加载态、错误提示、同名冲突弹窗是共用的 ——
 * 留在列表里会出现"列表能写数据、别处也能写数据"两套互不知情的状态。
 * 这里只留一个入口按钮，点了往外抛 `openDataManager`。
 */
const props = defineProps({
  // 轨迹列表（来自 GET /api/tracks）
  tracks: { type: Array, default: () => [] },
  // 当前选中的轨迹 id，用于高亮
  selectedId: { type: Number, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  // 筛选条件：状态由父组件 App.vue 持有，这里只负责回显 + 上报
  sourceFilter: { type: String, default: '' },
  limit: { type: Number, default: 50 },
  total: { type: Number, default: 0 },
})

// 告诉父组件"用户点了哪条" / "用户改了筛选条件" / "用户要进数据编辑视图"
const emit = defineEmits(['select', 'filter', 'openDataManager'])

/** 来源变了 → 上报（带上当前的条数限制） */
function onSourceChange(ev) {
  emit('filter', { source: ev.target.value, limit: props.limit })
}

/** 条数限制变了 → 上报（带上当前的来源） */
function onLimitChange(ev) {
  emit('filter', { source: props.sourceFilter, limit: Number(ev.target.value) })
}

/** 米 → 人看得懂的距离 */
function formatDistance(m) {
  if (m == null) return '—'
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`
}

/** 秒 → "X 小时 Y 分" / "Y 分钟" */
function formatDuration(s) {
  if (s == null) return '—'
  const hours = Math.floor(s / 3600)
  const minutes = Math.round((s % 3600) / 60)
  return hours > 0 ? `${hours} 小时 ${minutes} 分` : `${minutes} 分钟`
}

/** ISO 时间字符串 → 本地时间。后端给的是 UTC（结尾 Z），浏览器会自动换算成东八区 */
function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="track-list">
    <!-- 进数据编辑视图的入口（原来这里是"导入轨迹"的文件选择器）。
         上传表单连同它的请求逻辑一起搬去了 DataManager.vue，见文件头注释。 -->
    <div class="open-bar">
      <button
        type="button"
        class="open-btn"
        data-testid="open-data-manager"
        @click="emit('openDataManager')"
      >数据编辑</button>
      <span class="open-hint">添加 / 替换 / 改名 / 删除</span>
    </div>

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

    <ul v-else>
      <li v-for="track in tracks" :key="track.id">
        <button
          type="button"
          class="item"
          :class="{ active: track.id === selectedId }"
          @click="emit('select', track.id)"
        >
          <span class="name">
            {{ track.name }}
            <span v-if="track.id === selectedId" class="badge">已加载</span>
          </span>
          <span class="meta">
            {{ formatDistance(track.distanceM) }} · {{ formatDuration(track.durationS) }} ·
            {{ track.pointCount }} 点
          </span>
          <span class="time">{{ formatTime(track.startTime) }}</span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.track-list {
  /* 弹性高度：面板是纵向 flex，两个列表平分剩下的空间，各自独立滚动。
     flex-basis 用 0（不是 auto）才能"平分剩余空间"而不是"按内容大小分"，
     否则轨迹多的时候会把停留点区块挤没。 */
  flex: 1 1 0;
  min-height: var(--list-min, 88px);
  overflow-y: auto;
}

.hint {
  margin: 4px 0;
  font-size: 12px;
  color: #93a4bb;
}

.bad {
  color: #ff9b9b;
}

ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

li + li {
  margin-top: 6px;
}

.item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 7px 9px;
  border: 1px solid rgba(127, 209, 255, 0.16);
  border-radius: 7px;
  background: rgba(127, 209, 255, 0.05);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.item:hover {
  border-color: rgba(127, 209, 255, 0.45);
  background: rgba(127, 209, 255, 0.12);
}

.item.active {
  border-color: #7fd1ff;
  background: rgba(127, 209, 255, 0.2);
}

.name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #e7eef8;
}

.badge {
  padding: 0 5px;
  border-radius: 4px;
  background: #7fd1ff;
  color: #0a101a;
  font-size: 10px;
  line-height: 15px;
}

.meta,
.time {
  font-size: 11px;
  color: #93a4bb;
}

/* 入口按钮（原来放上传表单的位置）——样式沿用被搬走的 .import-btn */
.open-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.open-btn {
  padding: 5px 12px;
  border: 1px solid rgba(127, 209, 255, 0.45);
  border-radius: 7px;
  background: rgba(127, 209, 255, 0.12);
  color: inherit;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.open-btn:hover {
  background: rgba(127, 209, 255, 0.25);
}

.open-hint {
  font-size: 11px;
  color: #93a4bb;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
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

.count {
  margin-left: auto;
  font-size: 11px;
  color: #93a4bb;
}
</style>
