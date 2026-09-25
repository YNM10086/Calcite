<script setup>
import { computed } from 'vue'
import { formatCount, formatDistance, formatDuration, spanText, emptyHint, DRAW_LIMIT }
  from '../lib/region.js'

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
          <!-- 规格 6.5：名字 / 来源 / 点在区域内多少个 / 里程 / 时长 —— 五项都要有 -->
          <span class="meta">
            <em>{{ it.insidePointCount }}</em> 点 ·
            {{ formatDistance(it.distanceM) }} ·
            {{ formatDuration(it.durationS) }} ·
            {{ it.source }}
          </span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
/* ⚠️ 布局契约（2026-09-25 最终审查修复轮 2，实测驱动）：
   ① `flex: 1 1 0` 与 `min-height: 0` **缺一不可**：
      · `flex-basis: 0` 让它在面板里只占**剩余空间**（而不是"内容多高就多高"）；
      · `min-height: 0` 覆盖 flex 子项的自动最小尺寸（min-content）—— 少了它，
        即使 `flex-shrink: 1` 也收缩不到内容高度以下。
   ② 它仍然是 `overflow: visible`：内部那几块**不可再收缩**的内容（统计卡 / 来源行 /
      提示行 / `.items` 的 `min-height`）一旦超出分到的空间，溢出部分照样算进
      `.panel` 的 `scrollHeight`，而 `.panel` 是 `overflow: hidden` → 被裁掉、用户点不到。
   ③ 实测（G 段"有结果"测量，3 条命中）：1366×660 溢出 **99px**、1600×600 溢出 **159px**，
      而清空面板后是 **0px** —— 说明差别全在"有结果时多出来的内容"，且与白名单无关
      （`.within-stats` 的 `flex-shrink` 实测一直是 `1`）。所以矮窗口下**必须让内容真的变小**，
      见下面的 media query。 */
.within-stats { display: flex; flex-direction: column; gap: 6px; flex: 1 1 0; min-height: 0; }
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

/* 矮窗口（1366×660 笔记本 / 1600×600 投影）：统计卡压紧、来源行让位给列表。
   ⚠️ 四个统计数字（条数 / 区域内点数 / 累计里程 / 时间跨度）一个不少，只是更紧凑；
     让位的是**来源分布**那一行（规格 6.5 的第五项，矮窗口下由列表里的 source 字段承担）。 */
@media (max-height: 660px) {
  .within-stats { gap: 4px; }
  .cards { gap: 3px; }
  .card { padding: 2px 5px; }
  .card b { font-size: 12px; line-height: 1.25; }
  .card span { font-size: 9px; line-height: 1.2; }
  .sources { display: none; }
  .tip { font-size: 10px; line-height: 1.35; }
  .items li { padding: 3px 6px; }
}

/* 更矮（1600×600 这类投影视口）：统计卡改成"数字 + 标签"同一行，再省一层行高。
   列表的 min-height 保持 40px 不动 —— 它是"至少能滚到一条"的底线，不靠压列表来凑零溢出。 */
@media (max-height: 620px) {
  .card { flex-direction: row; align-items: baseline; gap: 4px; }
  .card b { font-size: 11px; }
}
</style>
