<script setup>
/**
 * 停留点列表 —— 纯展示组件，和 TrackList 一个规矩：
 * 自己不发请求，点击只往外抛事件。
 */
defineProps({
  stays: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  // 有没有选中轨迹（没选中时显示别的提示）
  hasTrack: { type: Boolean, default: false },
})

const emit = defineEmits(['focus'])

/** 秒 → "23 分钟" / "1 小时 5 分" */
function formatDuration(s) {
  if (s == null) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return h > 0 ? `${h} 小时 ${m} 分` : `${m} 分钟`
}

/** ISO → "19:12" */
function hhmm(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

/** 半径：小于 10 米显示一位小数，否则取整 */
function formatRadius(m) {
  if (m == null) return '—'
  return m < 10 ? `${m.toFixed(1)} 米` : `${Math.round(m)} 米`
}
</script>

<template>
  <div class="stay-list" data-testid="stay-list">
    <p v-if="loading" class="hint">正在分析停留点…</p>
    <p v-else-if="!hasTrack" class="hint">先选一条轨迹</p>
    <p v-else-if="stays.length === 0" class="hint">这条轨迹没有检测到停留</p>

    <ul v-else>
      <li v-for="s in stays" :key="s.seqStart">
        <button type="button" class="item" data-testid="stay-item" @click="emit('focus', s)">
          <span class="when">{{ hhmm(s.startTime) }} → {{ hhmm(s.endTime) }}</span>
          <span class="meta">
            {{ formatDuration(s.durationS) }} · 活动半径 {{ formatRadius(s.radiusM) }}
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.stay-list {
  /* 和轨迹列表平分面板剩余高度，各自独立滚动。
     flex-basis 用 0 的理由见 TrackList.vue 里的注释。 */
  flex: 1 1 0;
  min-height: var(--list-min, 88px);
  overflow-y: auto;
}

.hint {
  margin: 4px 0;
  font-size: 12px;
  color: #93a4bb;
}

ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

li + li {
  margin-top: 5px;
}

.item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 6px 9px;
  border: 1px solid rgba(255, 185, 94, 0.35);
  border-radius: 7px;
  background: rgba(255, 185, 94, 0.07);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.item:hover {
  border-color: rgba(255, 185, 94, 0.8);
  background: rgba(255, 185, 94, 0.18);
}

.when {
  font-size: 12px;
  color: #ffd08a;
}

.meta {
  font-size: 11px;
  color: #93a4bb;
}
</style>
