<script setup>
/**
 * 网格密度的图例与控制条 —— 纯展示组件，和 HotspotList / StayPointList 一个规矩：
 * 自己不发请求，交互只往外抛事件。状态由 App.vue 持有。
 */
import {
  rampColor,
  legendMax,
  legendTicks,
  densityRatio,
  formatCount,
  HOUR_PRESETS,
  METRIC_OPTIONS,
} from '../lib/density.js'
import { computed } from 'vue'

const props = defineProps({
  cells: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  scanned: { type: Object, default: () => ({ cells: 0, points: 0, tracks: 0 }) },
  cellSize: { type: Number, default: 0.002 },
  metric: { type: String, default: 'tracks' },
  hourPreset: { type: String, default: '' },
})

const emit = defineEmits(['metric', 'hour'])

const max = computed(() => legendMax(props.cells))
const ticks = computed(() => legendTicks(max.value))

/** 色带用 12 段拼出来（纯 CSS 渐变也行，但这样和后端/图例的取色函数完全一致） */
const rampStops = computed(() => {
  const n = 12
  const stops = []
  for (let i = 0; i <= n; i++) {
    stops.push(`${rampColor(i / n)} ${Math.round((i / n) * 100)}%`)
  }
  return stops.join(', ')
})

function onMetric(ev) {
  emit('metric', ev.target.value)
}
function onHour(ev) {
  emit('hour', ev.target.value)
}
</script>

<template>
  <div class="density-legend" data-testid="density-legend">
    <p v-if="loading" class="hint">正在统计网格…</p>
    <p v-else-if="error" class="hint bad">{{ error }}</p>

    <template v-else>
      <div class="row">
        <select :value="metric" data-testid="density-metric" @change="onMetric">
          <option v-for="o in METRIC_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <select :value="hourPreset" data-testid="density-hour" @change="onHour">
          <option v-for="p in HOUR_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>

      <!-- 图例色条：必须带绝对刻度（见设计文档「已知限制」） -->
      <div class="legend" data-testid="density-legend-bar">
        <div class="bar" :style="{ background: `linear-gradient(to right, ${rampStops})` }" />
        <div class="ticks">
          <span v-for="t in ticks" :key="t">{{ t }}</span>
        </div>
        <p class="maxline">
          最深 = <b>{{ formatCount(max) }}</b> {{ metric === 'points' ? '个点' : '条轨迹' }}
        </p>
      </div>

      <p class="stat" data-testid="density-stat">
        {{ formatCount(scanned.cells) }} 个格子 · {{ formatCount(scanned.points) }} 个点 ·
        格边长 {{ cellSize }}°
      </p>
      <p class="note">颜色只在同一视野内可比；跨视野请读上面的刻度</p>
    </template>
  </div>
</template>

<style scoped>
.density-legend {
  flex: 1 1 0;
  min-height: var(--list-min, 88px);
  overflow-y: auto;
}

.row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.row select {
  flex: 1;
  padding: 3px 6px;
  border: 1px solid rgba(255, 159, 10, 0.4);
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.9);
  color: #e7eef8;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.row select:hover {
  border-color: rgba(255, 159, 10, 0.8);
}

.legend {
  margin: 4px 0 8px;
}

.bar {
  height: 12px;
  border-radius: 3px;
  border: 1px solid rgba(127, 209, 255, 0.2);
}

.ticks {
  display: flex;
  justify-content: space-between;
  margin-top: 2px;
  font-size: 10px;
  color: #93a4bb;
}

.maxline {
  margin: 4px 0 0;
  font-size: 11px;
  color: #ffd08a;
}

.stat {
  margin: 0;
  font-size: 11px;
  color: #93a4bb;
}

.note {
  margin: 4px 0 0;
  font-size: 10px;
  color: #6b7a8d;
  line-height: 1.4;
}

.hint {
  margin: 4px 0;
  font-size: 12px;
  color: #93a4bb;
}

.bad {
  color: #ff9b9b;
}
</style>
