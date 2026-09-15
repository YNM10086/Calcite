<script setup>
/**
 * 轨迹列表 —— 纯展示组件（"哑组件"）
 *
 * 它自己不发请求：数据由父组件 App.vue 传进来，点击时只往外抛一个事件。
 * 这样做的好处是数据流单向、好调试：
 *   App 拿数据 → 传给 TrackList 显示 → 用户点了 → TrackList 喊一声 → App 去处理
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

// 告诉父组件"用户点了哪条" / "用户选了要导入的文件" / "用户改了筛选条件"
const emit = defineEmits(['select', 'import', 'filter'])

/** 来源变了 → 上报（带上当前的条数限制） */
function onSourceChange(ev) {
  emit('filter', { source: ev.target.value, limit: props.limit })
}

/** 条数限制变了 → 上报（带上当前的来源） */
function onLimitChange(ev) {
  emit('filter', { source: props.sourceFilter, limit: Number(ev.target.value) })
}

/** 用户选完文件 → 上报给父组件（组件自己不发请求，这是本组件的边界） */
function onFilePicked(ev) {
  const file = ev.target.files?.[0]
  if (file) emit('import', file)
  // 清空 input，否则连续选同一个文件不会再触发 change
  ev.target.value = ''
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
    <div class="import-bar">
      <label class="import-btn">
        导入轨迹
        <input
          type="file"
          accept=".gpx,.plt"
          hidden
          data-testid="import-input"
          @change="onFilePicked"
        />
      </label>
      <span class="import-hint">支持 GPX / GeoLife .plt</span>
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

.import-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
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

.import-hint {
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
