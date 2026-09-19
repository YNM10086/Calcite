<script setup>
/**
 * 轨迹相似度列表 —— 纯展示组件（和前几个列表一个规矩：不发请求，交互只往外抛事件）。
 */
import { computed } from 'vue'
import { SIM_FILTERS, simColor, formatDays, formatPct, filterMatches } from '../lib/similarity.js'

const props = defineProps({
  matches: { type: Array, default: () => [] },
  /** 主线的信息：{ name, pointCount, lengthM, compared } */
  baseline: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  /** 当前筛选档位（最低相似度） */
  filter: { type: Number, default: 50 },
})

const emit = defineEmits(['focus', 'filter'])

const shown = computed(() => filterMatches(props.matches, props.filter))

function onFilter(ev) {
  emit('filter', Number(ev.target.value))
}
function onPick(id) {
  emit('focus', id)
}
</script>

<template>
  <div class="similarity-list" data-testid="similarity-list">
    <p v-if="loading" class="hint">正在和 {{ baseline.compared ?? '…' }} 条轨迹比对…</p>
    <p v-else-if="error" class="hint bad">{{ error }}</p>

    <template v-else>
      <!-- 主线信息：让人知道"分母有多大" -->
      <p class="baseline" data-testid="similarity-baseline">
        以 <b>{{ baseline.name || '—' }}</b> 为主线 ·
        {{ baseline.pointCount ?? 0 }} 个点 ·
        {{ ((baseline.lengthM ?? 0) / 1000).toFixed(1) }} km
      </p>
      <p class="compared" data-testid="similarity-compared">
        和 {{ baseline.compared ?? 0 }} 条轨迹比过 · 容差 {{ baseline.toleranceM ?? 50 }} 米
      </p>

      <select :value="filter" data-testid="similarity-filter" @change="onFilter">
        <option v-for="f in SIM_FILTERS" :key="f.value" :value="f.value">{{ f.label }}</option>
      </select>

      <p v-if="matches.length === 0" class="hint" data-testid="similarity-empty">
        没有找到相似的轨迹 —— 这条轨迹可能和其它轨迹不在同一个区域。
      </p>
      <p v-else-if="shown.length === 0" class="hint" data-testid="similarity-none-in-filter">
        没有达到 {{ filter }}% 的轨迹，把筛选放宽试试。
      </p>

      <ul v-else class="list">
        <li
          v-for="m in shown"
          :key="m.trackId"
          class="item"
          data-testid="similarity-item"
          @click="onPick(m.trackId)"
        >
          <span class="pct" :style="{ color: simColor(m.similarity) }">
            {{ formatPct(m.similarity) }}
          </span>
          <span class="name">{{ m.name }}</span>
          <span class="meta">{{ (m.lengthM / 1000).toFixed(1) }} km · {{ formatDays(m.daysAway) }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.similarity-list {
  flex: 1 1 0;
  min-height: var(--list-min, 88px);
  overflow-y: auto;
}

.baseline,
.compared {
  margin: 0 0 4px;
  font-size: 11px;
  color: #93a4bb;
}

.baseline b {
  color: #e7eef8;
}

.similarity-list select {
  width: 100%;
  margin: 4px 0 8px;
  padding: 3px 6px;
  border: 1px solid rgba(255, 159, 10, 0.4);
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.9);
  color: #e7eef8;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: grid;
  grid-template-columns: 52px 1fr;
  grid-template-rows: auto auto;
  gap: 0 6px;
  padding: 5px 6px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 11px;
}

.item:hover {
  background: rgba(127, 209, 255, 0.1);
}

.pct {
  grid-row: span 2;
  align-self: center;
  font-size: 14px;
  font-weight: 600;
}

.name {
  color: #e7eef8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  color: #6b7a8d;
  font-size: 10px;
}

.hint {
  margin: 4px 0;
  font-size: 12px;
  color: #93a4bb;
  line-height: 1.5;
}

.bad {
  color: #ff9b9b;
}
</style>
