<script setup>
import { computed } from 'vue'
import { formatCount, formatDistance, spanText, emptyHint, DRAW_LIMIT } from '../lib/region.js'

const props = defineProps({
  stats: { type: Object, default: null },
  items: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  truncated: { type: Boolean, default: false },
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['select'])

const empty = computed(() => props.stats && props.total === 0)
const sources = computed(() => Object.entries(props.stats?.sourceCounts ?? {}))
const overDraw = computed(() => props.items.length > DRAW_LIMIT)
</script>

<template>
  <div class="within-stats" data-testid="within-stats">
    <p v-if="empty" class="empty" data-testid="within-empty">{{ emptyHint() }}</p>

    <template v-else-if="stats">
      <div class="cards">
        <div class="card"><b data-testid="stat-tracks">{{ formatCount(stats.trackCount) }}</b><span>条轨迹穿过</span></div>
        <div class="card"><b data-testid="stat-points">{{ formatCount(stats.pointCount) }}</b><span>个点在区域内</span></div>
        <div class="card"><b data-testid="stat-distance">{{ formatDistance(stats.distanceM) }}</b><span>累计里程</span></div>
        <div class="card wide">
          <b data-testid="stat-span">{{ spanText(stats.earliest, stats.latest) }}</b><span>时间跨度</span>
        </div>
      </div>

      <p class="sources" data-testid="stat-sources">
        <span v-for="[k, v] in sources" :key="k" class="src">{{ k }} {{ v }}</span>
      </p>

      <p v-if="truncated" class="tip" data-testid="within-truncated">
        共 {{ total }} 条，列表只显示前 {{ items.length }} 条
      </p>
      <p v-if="overDraw" class="tip" data-testid="within-draw-limit">
        地图上只画了前 {{ DRAW_LIMIT }} 条，点列表里的任意一条可把它画上去
      </p>

      <ul class="items">
        <li v-for="it in items" :key="it.trackId"
            :class="{ on: it.trackId === selectedId }"
            :data-testid="`within-item-${it.trackId}`"
            @click="emit('select', it.trackId)">
          <span class="name">{{ it.name }}</span>
          <span class="meta">
            <em>{{ it.insidePointCount }}</em> 点 ·
            {{ formatDistance(it.distanceM) }} ·
            {{ it.source }}
          </span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.within-stats { display: flex; flex-direction: column; gap: 6px; min-height: 0; }
.empty { margin: 4px 0; font-size: 12px; color: #f0b48a; }
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
.card {
  display: flex; flex-direction: column; padding: 4px 6px; border-radius: 4px;
  background: #16202b; border: 1px solid #22303d;
}
.card.wide { grid-column: 1 / -1; }
.card b { font-size: 14px; color: #cfe3f5; }
.card span { font-size: 10px; color: #8aa4bb; }
.sources { margin: 0; display: flex; gap: 6px; flex-wrap: wrap; }
.src { font-size: 11px; color: #8aa4bb; background: #16202b; border-radius: 3px; padding: 1px 5px; }
.tip { margin: 0; font-size: 11px; color: #f0b48a; line-height: 1.5; }
.items { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1 1 0; min-height: 40px; }
.items li {
  display: flex; flex-direction: column; gap: 1px; padding: 4px 6px; cursor: pointer;
  border-bottom: 1px solid #1b2733;
}
.items li:hover { background: #1b2733; }
.items li.on { background: #24405a; }
.name { font-size: 12px; color: #cfe3f5; }
.meta { font-size: 10px; color: #8aa4bb; }
.meta em { font-style: normal; color: #7ee0a6; }
</style>
