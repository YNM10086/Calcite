// Task 9 自检用：vue 运行时替身（只留组件里用到的 5 个 API）。
// ref/shallowRef 返回真实形状 { value }，watch 不接调度（本检查直接调方法，不依赖响应式）。
export const hooks = { mounted: [], beforeUnmount: [] }

export function onMounted(fn) { hooks.mounted.push(fn) }
export function onBeforeUnmount(fn) { hooks.beforeUnmount.push(fn) }
export function ref(v) { return { value: v } }
export function shallowRef(v) { return { value: v } }
export function watch() { return () => {} }
