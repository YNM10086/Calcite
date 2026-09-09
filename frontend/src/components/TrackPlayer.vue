<script setup>
/**
 * 回放控制条 —— 和 TrackList 一样是纯展示组件。
 *
 * 它不知道 Cesium 的存在，也不持有播放状态：
 * 父组件传 props 进来，用户操作时只往外抛事件。
 */
import { computed } from 'vue'
import { formatClock, progressOf } from '../lib/playback.js'

const props = defineProps({
  playing: { type: Boolean, default: false },
  // 当前时刻 / 起止时刻，都是毫秒时间戳
  currentMs: { type: Number, default: 0 },
  startMs: { type: Number, default: 0 },
  endMs: { type: Number, default: 0 },
  loop: { type: Boolean, default: true },
  // 缺时间信息时置灰
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle', 'seek', 'toggle-loop'])

/** 进度 0~1，由当前时刻算出来，不额外存状态 */
const progress = computed(() => progressOf(props.currentMs, props.startMs, props.endMs))
const currentLabel = computed(() => formatClock(props.currentMs))
const endLabel = computed(() => formatClock(props.endMs))

/** range 滑块给的是 0~1000 的整数，换算回毫秒 */
function onSeek(event) {
  if (props.disabled) return
  const ratio = Number(event.target.value) / 1000
  emit('seek', props.startMs + ratio * (props.endMs - props.startMs))
}
</script>

<template>
  <div class="player" :class="{ disabled }" data-testid="player">
    <button
      type="button"
      class="btn play"
      data-testid="play-toggle"
      :disabled="disabled"
      :title="playing ? '暂停' : '播放'"
      @click="emit('toggle')"
    >
      {{ playing ? '❚❚' : '▶' }}
    </button>

    <input
      class="seek"
      data-testid="seek"
      type="range"
      min="0"
      max="1000"
      step="1"
      :value="Math.round(progress * 1000)"
      :disabled="disabled"
      @input="onSeek"
    />

    <span v-if="disabled" class="hint">这条轨迹缺时间信息，无法回放</span>
    <span v-else class="clock" data-testid="clock">{{ currentLabel }} / {{ endLabel }}</span>

    <button
      type="button"
      class="btn loop"
      data-testid="loop-toggle"
      :class="{ on: loop }"
      :disabled="disabled"
      :title="loop ? '关闭循环' : '开启循环'"
      @click="emit('toggle-loop')"
    >
      ↻ 循环
    </button>
  </div>
</template>

<style scoped>
.player {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 46px;
  padding: 0 16px;
  border-top: 1px solid rgba(127, 209, 255, 0.18);
  background: rgba(10, 16, 26, 0.86);
  backdrop-filter: blur(6px);
  font-size: 12px;
}

.btn {
  flex: none;
  padding: 4px 10px;
  border: 1px solid rgba(127, 209, 255, 0.28);
  border-radius: 6px;
  background: rgba(127, 209, 255, 0.08);
  color: #e7eef8;
  font: inherit;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn:hover:not(:disabled) {
  border-color: rgba(127, 209, 255, 0.6);
  background: rgba(127, 209, 255, 0.18);
}

.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.play {
  min-width: 40px;
  color: #7fd1ff;
}

.loop.on {
  border-color: #7fd1ff;
  background: rgba(127, 209, 255, 0.24);
  color: #7fd1ff;
}

.seek {
  flex: 1;
  height: 4px;
  margin: 0;
  appearance: none;
  border-radius: 2px;
  background: rgba(127, 209, 255, 0.18);
  cursor: pointer;
}

.seek::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #7fd1ff;
  cursor: pointer;
}

.seek:disabled {
  cursor: not-allowed;
}

.clock {
  flex: none;
  color: #93a4bb;
  font-variant-numeric: tabular-nums;
}

.hint {
  flex: 1;
  color: #ff9b9b;
}

.player.disabled {
  opacity: 0.75;
}
</style>
