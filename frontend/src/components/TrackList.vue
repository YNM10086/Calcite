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
})

// 告诉父组件"用户点了哪条"
const emit = defineEmits(['select'])

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
  max-height: 260px;
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
</style>
