<script setup>
/**
 * 通用确认弹窗 —— 纯展示组件（"哑组件"），自己不做决定，只把用户的选择往外抛。
 *
 * 为什么单独抽一个组件：删除要用它，将来"清空全部""替换确认"也要用。
 * 更要紧的是 **Task 6 一个组件要服务三种用途**（删除确认 / 同名冲突 / 错误提示），
 * 所以按钮文案、正文、颜色全部走 prop —— 组件里不许写死"确定/取消"这类字眼。
 *
 * ⚠️ **遮罩点击（点弹窗外面）= 抛 `cancel`，所以 `cancel` 永远只能是"关闭"**：
 * 这是本组件最重要的一条不变量，Task 6 的头号风险就出在它上面 ——
 * 原计划想把 `cancelText` 传成「新增为另一条」、把 `@cancel` 接到真会上传的
 * `resolveKeepBoth()` 上；那样用户在看冲突提示时**随手点一下弹窗外面**，
 * 就会静默往库里追加一条重复轨迹，而他以为只是"把弹窗关掉了"。
 * 一个用户为了"关掉弹窗"而做的动作，绝不能产生数据变更。
 *
 * 所以这里**新增第三个按钮**（`altText` / `@alt`）来承载"第二个正向选项"：
 * 冲突场景排成「取消 / 新增为另一条 / 替换它」三个明确按钮，
 * `cancel` 回到它唯一说得通的含义 —— 关闭，什么都不做。
 *
 * 另外两条行为说明（写在 script 里而不是 <template> 里：
 * **模板里的 HTML 注释会被编译成注释节点、真的进 DOM**）：
 *   1. `cancelText` / `altText` 留空则**不渲染那个按钮**：
 *      提示类弹窗（导入完成 / 改名失败）只有一个「知道了」，
 *      不该多出一个语义不明的「取消」。
 *   2. open=false 时整块不渲染，所以全屏遮罩不会挡住底下的地图拖拽。
 */
defineProps({
  /** 是否显示（由父组件控制，组件自己不开不关） */
  open: { type: Boolean, default: false },
  title: { type: String, default: '确认' },
  /** 正文，按行显示（用换行符切分）—— 让长文案的排版可控，不必让调用方拼 HTML */
  body: { type: String, default: '' },
  /** 右侧（主）按钮文案 */
  confirmText: { type: String, default: '确定' },
  /** 左侧按钮文案 —— 语义就是"关闭"，留空则不渲染这个按钮 */
  cancelText: { type: String, default: '取消' },
  /**
   * 可选的【第三个】按钮（夹在 cancel 与 confirm 中间），留空则不渲染。
   *
   * 为什么需要它：同名冲突要用户三选一（替换 / 新增为另一条 / 取消），
   * 而"新增为另一条"是个真会写数据的动作，**不能**寄生在 `cancel` 上
   * （`cancel` 同时被遮罩点击触发，见文件头注释）。
   */
  altText: { type: String, default: '' },
  /** 危险操作：右侧按钮变红（删除这类不可逆动作用） */
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'cancel', 'alt'])
</script>

<template>
  <div
    v-if="open"
    class="mask"
    data-testid="confirm-dialog"
    role="dialog"
    aria-modal="true"
    @click.self="emit('cancel')"
  >
    <div class="box">
      <h3>{{ title }}</h3>
      <p v-for="(line, i) in String(body).split('\n')" :key="i" class="line">{{ line }}</p>
      <div class="row">
        <button
          v-if="cancelText"
          type="button"
          class="ghost"
          data-testid="confirm-cancel"
          @click="emit('cancel')"
        >{{ cancelText }}</button>
        <button
          v-if="altText"
          type="button"
          class="ghost"
          data-testid="confirm-alt"
          @click="emit('alt')"
        >{{ altText }}</button>
        <button
          type="button"
          :class="{ danger }"
          data-testid="confirm-ok"
          @click="emit('confirm')"
        >{{ confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.box {
  width: min(420px, 90vw);
  background: #0b1220;
  border: 1px solid rgba(127, 209, 255, 0.35);
  border-radius: 10px;
  padding: 16px 18px;
  color: #e7eef8;
}

h3 {
  margin: 0 0 10px;
  font-size: 15px;
}

.line {
  margin: 0 0 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #b9c6d6;
  /* pre-wrap 保留每行开头的空格（deleteConfirmText 的第二句退路是缩进对齐的），
     同时保留换行 —— 少了它那两句操作指引会挤成一段，读起来像免责声明。 */
  white-space: pre-wrap;
}

.row {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}

button {
  padding: 5px 14px;
  border-radius: 6px;
  border: 1px solid rgba(127, 209, 255, 0.45);
  background: rgba(127, 209, 255, 0.12);
  color: #e7eef8;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

button.ghost {
  border-color: rgba(255, 255, 255, 0.2);
  background: transparent;
}

button.danger {
  border-color: rgba(255, 90, 90, 0.6);
  background: rgba(255, 90, 90, 0.18);
  color: #ffb3b3;
}

button:hover {
  filter: brightness(1.2);
}
</style>
