<script setup>
import { computed } from 'vue'

const props = defineProps({
  mode: { type: String, default: 'idle' },      // idle | rect | polygon | buffer
  bufferM: { type: Number, default: 500 },
  busy: { type: Boolean, default: false },
  hasResult: { type: Boolean, default: false },
})
const emit = defineEmits(['start', 'cancel', 'clear', 'update:bufferM', 'query-buffer'])

const PRESETS = [200, 500, 1000, 2000]

const hint = computed(() => {
  if (props.busy) return '查询中…'
  switch (props.mode) {
    case 'rect': return '按住左键拖一个框，松开即查询'
    case 'polygon': return '逐个单击加点，双击（或点回起点）闭合即查询'
    case 'buffer': return '单击一个中心点，再点「查询」'
    default: return props.hasResult ? '换一种画法，或点「清除」' : '选一种画法开始'
  }
})

function onBufferInput(e) {
  const v = Number(e.target.value)
  emit('update:bufferM', Number.isFinite(v) ? v : 0)
}
</script>

<template>
  <div class="region-drawer" data-testid="region-drawer">
    <div class="shapes">
      <button type="button" :class="{ on: mode === 'rect' }" data-testid="draw-rect"
              @click="emit('start', 'rect')">拉框</button>
      <button type="button" :class="{ on: mode === 'polygon' }" data-testid="draw-polygon"
              @click="emit('start', 'polygon')">多边形</button>
      <button type="button" :class="{ on: mode === 'buffer' }" data-testid="draw-buffer"
              @click="emit('start', 'buffer')">缓冲区</button>
      <button type="button" class="ghost" data-testid="draw-clear"
              :disabled="!hasResult && mode === 'idle'" @click="emit('clear')">清除</button>
    </div>

    <div v-if="mode === 'buffer' || mode === 'idle'" class="radius">
      <label>半径</label>
      <input type="number" min="1" max="50000" step="50" data-testid="buffer-m"
             :value="bufferM" @input="onBufferInput" />
      <span class="unit">米</span>
      <button v-for="p in PRESETS" :key="p" type="button" class="preset"
              :class="{ on: bufferM === p }" :data-testid="`buffer-preset-${p}`"
              @click="emit('update:bufferM', p)">{{ p >= 1000 ? `${p / 1000}km` : `${p}m` }}</button>
      <button type="button" class="go" data-testid="buffer-query"
              :disabled="mode !== 'buffer' || busy" @click="emit('query-buffer')">查询</button>
    </div>

    <p class="hint" data-testid="draw-hint">{{ hint }}</p>
    <button v-if="mode !== 'idle'" type="button" class="cancel" data-testid="draw-cancel"
            @click="emit('cancel')">取消绘制（Esc）</button>
  </div>
</template>

<style scoped>
.region-drawer { display: flex; flex-direction: column; gap: 6px; }
.shapes { display: flex; gap: 4px; flex-wrap: wrap; }
.shapes button {
  flex: 1 1 auto; padding: 4px 8px; font-size: 12px; cursor: pointer;
  border: 1px solid #3a4a5a; background: #16202b; color: #cfe3f5; border-radius: 4px;
}
.shapes button.on { background: #2a6ea8; border-color: #4a9ede; color: #fff; }
.shapes button:disabled { opacity: .45; cursor: default; }
.shapes button.ghost { flex: 0 0 auto; }
.radius { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; font-size: 12px; }
.radius input {
  width: 68px; padding: 3px 5px; background: #16202b; color: #cfe3f5;
  border: 1px solid #3a4a5a; border-radius: 4px;
}
.radius .unit { color: #8aa4bb; }
.radius .preset {
  padding: 2px 6px; font-size: 11px; cursor: pointer; color: #cfe3f5;
  border: 1px solid #3a4a5a; background: #16202b; border-radius: 4px;
}
.radius .preset.on { background: #2a6ea8; border-color: #4a9ede; color: #fff; }
.radius .go {
  margin-left: auto; padding: 3px 10px; font-size: 12px; cursor: pointer;
  border: 1px solid #4a9ede; background: #2a6ea8; color: #fff; border-radius: 4px;
}
.radius .go:disabled { opacity: .45; cursor: default; }
.hint { margin: 0; font-size: 11px; color: #8aa4bb; line-height: 1.5; }
.cancel {
  align-self: flex-start; padding: 2px 8px; font-size: 11px; cursor: pointer;
  border: 1px solid #6b4a3a; background: #2b1f18; color: #f0b48a; border-radius: 4px;
}
</style>
