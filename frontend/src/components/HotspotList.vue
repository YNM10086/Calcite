<script setup>
/**
 * 热点列表 —— 纯展示组件，和 StayPointList / TrackList 一个规矩：
 * 自己不发请求，点击只往外抛事件。
 * 状态（拉数据、排序键）都由 App.vue 持有。
 */
import { formatDuration, formatSpread, SORT_OPTIONS } from '../lib/hotspot.js'

defineProps({
  hotspots: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  sortBy: { type: String, default: 'trackCount' },
})

const emit = defineEmits(['focus', 'sort'])

/** 用户换了排序口径 → 上报，由 App 重新排序 */
function onSortChange(ev) {
  emit('sort', ev.target.value)
}
</script>

<template>
  <div class="hotspot-list" data-testid="hotspot-list">
    <div class="toolbar">
      <select :value="sortBy" data-testid="hotspot-sort" @change="onSortChange">
        <option v-for="o in SORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <span class="count">{{ hotspots.length }} 处</span>
    </div>

    <p v-if="loading" class="hint">正在分析热点…</p>
    <p v-else-if="error" class="hint bad">{{ error }}</p>
    <p v-else-if="hotspots.length === 0" class="hint">还没有识别到热点</p>

    <ul v-else>
      <li v-for="(h, i) in hotspots" :key="h.centerLat + ',' + h.centerLon">
        <button type="button" class="item" data-testid="hotspot-item" @click="emit('focus', h)">
          <span class="head">
            <span class="rank">#{{ i + 1 }}</span>
            <span class="visits">{{ h.visitCount }} 次</span>
            <span class="tracks">{{ h.trackCount }} 条轨迹</span>
          </span>
          <span class="meta">
            {{ formatDuration(h.totalDurationS) }} · 散布 {{ formatSpread(h.radiusM) }}
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.hotspot-list {
  /* 和轨迹列表平分面板剩余高度，各自独立滚动 */
  flex: 1 1 0;
  min-height: var(--list-min, 88px);
  overflow-y: auto;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.toolbar select {
  padding: 3px 6px;
  border: 1px solid rgba(255, 159, 10, 0.4);
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.9);
  color: #e7eef8;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.toolbar select:hover {
  border-color: rgba(255, 159, 10, 0.8);
}

.count {
  margin-left: auto;
  font-size: 11px;
  color: #93a4bb;
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
  margin-top: 5px;
}

.item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 6px 9px;
  border: 1px solid rgba(255, 159, 10, 0.35);
  border-radius: 7px;
  background: rgba(255, 159, 10, 0.07);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.item:hover {
  border-color: rgba(255, 159, 10, 0.8);
  background: rgba(255, 159, 10, 0.18);
}

.head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
}

.rank {
  font-weight: 700;
  color: #ffd08a;
}

.visits {
  color: #ff9f0a;
}

.tracks {
  color: #93a4bb;
}

.meta {
  font-size: 11px;
  color: #93a4bb;
}
</style>
