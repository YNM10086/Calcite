<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { formatClock } from '../lib/playback.js'
import {
  domainOf,
  formatTick,
  formatValue,
  msAtX,
  niceTicks,
  pathOf,
  scaleX,
  scaleY,
  seriesOf,
  tickDigits,
  timeTicks,
  valueAt,
} from '../lib/chart.js'

const props = defineProps({
  /** 轨迹点，每个点要有 recordedAt / speedMps / elevationM */
  points: { type: Array, default: () => [] },
  /** 当前时刻（毫秒），由 App 从 Cesium 时钟同步过来 */
  currentMs: { type: Number, default: 0 },
  startMs: { type: Number, default: 0 },
  endMs: { type: Number, default: 0 },
})

const emit = defineEmits(['seek'])

/* ============ 尺寸常量（像素）============ */
const CHART_H = 56 // 单张图高度
const AXIS_H = 20 // 底部时间轴刻度行
const PAD_L = 46 // 左侧留白，放 Y 轴标签
const PAD_R = 12
const INNER = 6 // 图内上下留白
const PLOT_H = CHART_H - INNER * 2
const TIP_W = 176 // 悬停提示框宽度

/* ============ 容器宽度：量真实像素，避免拉伸变形 ============ */
const root = ref(null)
const width = shallowRef(0)
let ro = null
let measure = null

onMounted(() => {
  if (!root.value) return
  measure = () => {
    width.value = root.value ? root.value.clientWidth : 0
  }
  measure()
  if (typeof ResizeObserver === 'function') {
    ro = new ResizeObserver(measure)
    ro.observe(root.value)
  } else {
    window.addEventListener('resize', measure)
  }
})

onBeforeUnmount(() => {
  if (ro) {
    ro.disconnect()
    ro = null
  } else if (measure) {
    window.removeEventListener('resize', measure)
  }
  measure = null
})

/* ============ 数据序列 ============ */
const speed = computed(() => seriesOf(props.points, 'speedMps'))
const elev = computed(() => seriesOf(props.points, 'elevationM'))
const hasSpeed = computed(() => speed.value.length >= 2)
const hasElev = computed(() => elev.value.length >= 2)

/* ============ 坐标映射 ============ */
const plotW = computed(() => Math.max(0, width.value - PAD_L - PAD_R))
const xOf = computed(() => scaleX(props.startMs, props.endMs, PAD_L, plotW.value))

const speedDomain = computed(() => domainOf(speed.value.map((d) => d.value)))
const elevDomain = computed(() => domainOf(elev.value.map((d) => d.value)))
const speedY = computed(() => scaleY(speedDomain.value, INNER, PLOT_H))
const elevY = computed(() => scaleY(elevDomain.value, INNER, PLOT_H))

/* ============ 折线路径 ============ */
const speedPath = computed(() =>
  pathOf(speed.value, (d) => xOf.value(d.ms), (d) => speedY.value(d.value)),
)
const elevPath = computed(() =>
  pathOf(elev.value, (d) => xOf.value(d.ms), (d) => elevY.value(d.value)),
)

/* ============ 刻度 ============ */
const speedTicks = computed(() => niceTicks(speedDomain.value?.min, speedDomain.value?.max, 3))
const elevTicks = computed(() => niceTicks(elevDomain.value?.min, elevDomain.value?.max, 3))
const speedDigits = computed(() => tickDigits(speedTicks.value))
const elevDigits = computed(() => tickDigits(elevTicks.value))

/** 时间轴标签密度按宽度定：大约每 90px 一个 */
const timeTickList = computed(() =>
  timeTicks(props.startMs, props.endMs, Math.max(2, Math.floor(plotW.value / 90) + 1)),
)

/* ============ 游标 ============ */
/** 游标 x：夹在绘图区内，避免超出两端 */
const playheadX = computed(() => {
  const x = xOf.value(props.currentMs)
  return Math.min(PAD_L + plotW.value, Math.max(PAD_L, x))
})

/** 游标与折线的交点 y —— 用插值，保证正好落在交叉处 */
const speedDotY = computed(() => {
  if (!hasSpeed.value) return null
  const v = valueAt(speed.value, props.currentMs)
  return v === null ? null : speedY.value(v)
})
const elevDotY = computed(() => {
  if (!hasElev.value) return null
  const v = valueAt(elev.value, props.currentMs)
  return v === null ? null : elevY.value(v)
})

/* ============ 悬停 / 点击 ============ */
const hoverX = ref(null)

const hoverMs = computed(() =>
  hoverX.value === null ? null : msAtX(hoverX.value, props.startMs, props.endMs, PAD_L, plotW.value),
)
const hoverSpeed = computed(() =>
  hoverMs.value === null ? null : valueAt(speed.value, hoverMs.value),
)
const hoverElev = computed(() =>
  hoverMs.value === null ? null : valueAt(elev.value, hoverMs.value),
)

/** 提示框位置：靠右时向左夹紧，避免溢出容器 */
const tipStyle = computed(() => {
  if (hoverX.value === null) return { display: 'none' }
  const maxLeft = Math.max(4, width.value - TIP_W - 4)
  const left = Math.min(Math.max(hoverX.value - TIP_W / 2, 4), maxLeft)
  return { left: left + 'px', width: TIP_W + 'px' }
})

function onMove(ev) {
  const rect = ev.currentTarget.getBoundingClientRect()
  hoverX.value = ev.clientX - rect.left
}

function onLeave() {
  hoverX.value = null
}

function onClick(ev) {
  const rect = ev.currentTarget.getBoundingClientRect()
  const ms = msAtX(ev.clientX - rect.left, props.startMs, props.endMs, PAD_L, plotW.value)
  emit('seek', Math.round(ms))
}
</script>

<template>
  <div ref="root" class="chart" data-testid="speed-chart">
    <!-- ============ 速度图 ============ -->
    <div class="pane" :style="{ height: CHART_H + 'px' }">
      <svg
        class="layer"
        :width="Math.max(width, 1)"
        :height="CHART_H"
        data-testid="chart-speed"
        @mousemove="onMove"
        @mouseleave="onLeave"
        @click="onClick"
      >
        <g v-for="t in speedTicks" :key="'sg' + t">
          <line :x1="PAD_L" :x2="PAD_L + plotW" :y1="speedY(t)" :y2="speedY(t)" class="grid" />
          <text :x="PAD_L - 6" :y="speedY(t) + 3" class="ylabel">
            {{ formatValue(t, speedDigits) }}
          </text>
        </g>
        <!-- 游标画在数据线之前 → 位于下层 → 物理上不可能遮挡数据线 -->
        <line
          v-if="hasSpeed"
          :x1="playheadX"
          :x2="playheadX"
          y1="0"
          :y2="CHART_H"
          class="playhead"
          data-testid="chart-playhead"
        />
        <path v-if="hasSpeed" :d="speedPath" class="line speed" />
        <circle
          v-if="hasSpeed && speedDotY !== null"
          :cx="playheadX"
          :cy="speedDotY"
          r="2"
          class="dot"
        />
      </svg>
      <div class="unit speed-unit">速度 m/s</div>
      <div v-if="!hasSpeed" class="empty">这条轨迹没有速度数据</div>
    </div>

    <!-- ============ 海拔图 ============ -->
    <div class="pane" :style="{ height: CHART_H + 'px' }">
      <svg
        class="layer"
        :width="Math.max(width, 1)"
        :height="CHART_H"
        data-testid="chart-elevation"
        @mousemove="onMove"
        @mouseleave="onLeave"
        @click="onClick"
      >
        <g v-for="t in elevTicks" :key="'eg' + t">
          <line :x1="PAD_L" :x2="PAD_L + plotW" :y1="elevY(t)" :y2="elevY(t)" class="grid" />
          <text :x="PAD_L - 6" :y="elevY(t) + 3" class="ylabel">
            {{ formatValue(t, elevDigits) }}
          </text>
        </g>
        <line
          v-if="hasElev"
          :x1="playheadX"
          :x2="playheadX"
          y1="0"
          :y2="CHART_H"
          class="playhead"
        />
        <path v-if="hasElev" :d="elevPath" class="line elev" />
        <circle
          v-if="hasElev && elevDotY !== null"
          :cx="playheadX"
          :cy="elevDotY"
          r="2"
          class="dot"
        />
      </svg>
      <div class="unit elev-unit">海拔 m</div>
      <div v-if="!hasElev" class="empty">这条轨迹没有海拔数据</div>
    </div>

    <!-- ============ 时间轴 ============ -->
    <svg class="layer" :width="Math.max(width, 1)" :height="AXIS_H" data-testid="chart-axis">
      <g v-for="t in timeTickList" :key="'t' + t">
        <line :x1="xOf(t)" :x2="xOf(t)" y1="0" y2="4" class="grid" />
        <text :x="xOf(t)" :y="15" class="xlabel">{{ formatTick(t) }}</text>
      </g>
    </svg>

    <!-- ============ 悬停提示 ============ -->
    <div v-if="hoverX !== null" class="tip" :style="tipStyle" data-testid="chart-tooltip">
      <span class="t">{{ hoverMs === null ? '—' : formatClock(hoverMs) }}</span>
      <span>速度 {{ formatValue(hoverSpeed, 2) }} m/s</span>
      <span>海拔 {{ formatValue(hoverElev, 1) }} m</span>
    </div>
  </div>
</template>

<style scoped>
.chart {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 46px;
  z-index: 15;
  border-top: 1px solid rgba(127, 209, 255, 0.18);
  background: rgba(10, 16, 26, 0.86);
  backdrop-filter: blur(6px);
  user-select: none;
}

.pane {
  position: relative;
}

.layer {
  display: block;
}

.grid {
  stroke: rgba(127, 209, 255, 0.12);
  stroke-width: 1;
}

.ylabel {
  fill: #93a4bb;
  font-size: 10px;
  text-anchor: end;
}

.xlabel {
  fill: #93a4bb;
  font-size: 10px;
  text-anchor: middle;
}

.playhead {
  stroke: #ffffff;
  stroke-width: 1;
  stroke-dasharray: 4 3;
  opacity: 0.7;
}

.line {
  fill: none;
  stroke-width: 2;
}

.speed {
  stroke: #722ED1;
}

.elev {
  stroke: #165DFF;
}

.dot {
  fill: #ffffff;
}

.unit {
  position: absolute;
  top: 2px;
  right: 12px;
  font-size: 10px;
}

.speed-unit {
  color: #7ee0a6;
}

.elev-unit {
  color: #7ee0a6;
}

.empty {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 11px;
  color: #93a4bb;
}

.tip {
  position: absolute;
  top: 4px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 4px 8px;
  border: 1px solid rgba(127, 209, 255, 0.28);
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.92);
  color: #e7eef8;
  font-size: 11px;
  line-height: 1.5;
  pointer-events: none;
}

.tip .t {
  color: #7fd1ff;
}
</style>
