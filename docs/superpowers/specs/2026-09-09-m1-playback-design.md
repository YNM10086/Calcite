# Calcite M1 回放设计：时间轴播放轨迹

> **隶属关系**：本文件是主设计文档 `2026-09-08-calcite-trajectory-analysis-design.md` 中
> 「M1 看得见 → Cesium 三维回放」这一条的详细设计。**范围、数据模型、接口清单以主文档为准**；
> 本文件只负责「回放这一块具体怎么做」。如与主文档冲突，以主文档为准。
>
> **状态**：待实施（2026-09-09 设计确认）

---

## 一、目标与非目标

### 目标

在 M1 已完成的「轨迹列表 + 地球画线」基础上，让一条轨迹能**按时间轴回放**：

1. 点播放，一个白色标记沿轨迹移动
2. 暂停 / 继续
3. 拖动进度条跳到任意时刻
4. 循环开关：开着时播到终点自动跳回起点
5. 显示当前时刻的真实钟点（如 `07:30:25`）

### 非目标（本次不做，YAGNI）

| 不做的事 | 理由 |
|---|---|
| 倍速按钮（0.5× / 2× / 4×） | 只是改 `clock.multiplier` 一个数，等需要时再加 |
| 速度 / 海拔曲线（`SpeedChart.vue`） | `track_point.speed_mps` 目前整列为 NULL，先补数据 |
| 相机跟随标记 | 本次轨迹仅 9.4 km，全程可见；长轨迹再考虑 |
| 轨迹抽稀（`?simplify=`） | 121 个点不需要；GeoLife 大批量导入时再做 |
| 播放时的轨迹线渐进绘制 | 视觉效果，非功能必需 |

---

## 二、数据流

```
PostGIS：recorded_at + geom（121 个点，每 25 秒一个）
        ↓  GET /api/tracks/{id}        ← 后端不改，DTO 已含 recordedAt
App.vue：detail.points（每点带 ISO 时间戳）
        ↓  :points
CesiumGlobe.vue
  ├─ 建一次 SampledPositionProperty：121 个 (JulianDate → Cartesian3)
  ├─ Cesium Clock 每帧推进 currentTime
  └─ 白色移动点 position = 该属性 → 自动按时间线性插值
        ↑ play / pause / seekTo（:loop prop）   ↓ time-change（节流 100ms）
App.vue：只存 playing + currentMs + loop
        ↓  props
TrackPlayer.vue：▶ 播放/暂停 · 进度条 · 时刻文字 · ↻ 循环
        ↑ toggle / seek / toggle-loop
```

**关键点**：`SampledPositionProperty` **只建一次**。拖动进度条时只改 `clock.currentTime`，
不重建任何实体——这是唯一可能卡顿的地方，设计上直接绕开。

---

## 三、三个关键决定

### 3.1 速度：整条轨迹约 60 秒播完

示例轨迹真实时长 **3000 秒（50 分钟）**。按 1× 真实时间播放需要 50 分钟，无法演示。

- `clock.clockStep = ClockStep.SYSTEM_CLOCK_MULTIPLIER`
- `clock.multiplier = 轨迹总秒数 ÷ 60`（本示例 = 50）

倍速按钮将来只需改 `multiplier`，不动其他逻辑。

### 3.2 循环：用 Cesium 时钟自带的 `ClockRange`

- 循环开：`clock.clockRange = ClockRange.LOOP_STOP`（播到终点跳回起点）
- 循环关：`clock.clockRange = ClockRange.CLAMPED`（停在终点）

不需要自己写计时器或边界判断。

### 3.3 状态归属：App.vue 管状态，两个子组件都是纯展示

沿用 `TrackList.vue` 已确立的写法——**谁在加载/播放数据只有一个地方管**：

| 层 | 职责 |
|---|---|
| `App.vue` | 持有 `playing` / `currentMs` / `loop`，调用地球组件的方法 |
| `CesiumGlobe.vue` | 只管 Cesium：建属性、控时钟、发 `time-change` |
| `TrackPlayer.vue` | 只管 UI：props 进、事件出，**不 import Cesium** |

---

## 四、组件契约

### 4.1 `CesiumGlobe.vue`（改造）

**props**

| 名字 | 类型 | 说明 |
|---|---|---|
| `points` | `Array` | 轨迹点（已有） |
| `loop` | `Boolean` | 循环开关，watch 后设置 `clockRange` |

**emits**

| 名字 | 载荷 | 时机 |
|---|---|---|
| `time-change` | `Number`（epoch 毫秒） | `clock.onTick` 中，距上次发送 ≥ 100 ms 时；`seekTo()` 后**立即补发一次**（绕过节流），避免拖动手感延迟 |

**`defineExpose`**

| 方法 | 作用 |
|---|---|
| `play()` | `clock.shouldAnimate = true` |
| `pause()` | `clock.shouldAnimate = false` |
| `seekTo(ms)` | 只设 `clock.currentTime`，不动实体，然后立即补发一次 `time-change` |

**时钟重置**：`drawTrack()` 内部自动把时钟重置为「起点 + 暂停」
（`currentTime = startTime`、`shouldAnimate = false`），因此**切换轨迹不需要 App 额外调用任何方法**。

**实体 id**：新增 `calcite-track-mover`（白色圆点，`pixelSize: 12`，深色描边），
由 `clearTrack()` 一并清理。

### 4.2 `TrackPlayer.vue`（新建）

**props**：`playing` `currentMs` `startMs` `endMs` `loop` `disabled`

**emits**：`toggle` · `seek`（载荷 ms）· `toggle-loop`

**内部**：`progress` 由 `(currentMs - startMs) / (endMs - startMs)` 计算，不额外存状态；
时刻文字用 `toLocaleTimeString('zh-CN')` 格式化为 **`时:分:秒`**（本示例跨度仅 50 分钟，
不显示日期；将来跨天轨迹再加）。

**`disabled` 为 true 时**：播放/暂停按钮与进度条置灰不可点，并显示提示文字
「这条轨迹缺时间信息，无法回放」。

### 4.3 `App.vue`（改造）

- 新增状态：`playing`（默认 `false`）、`currentMs`（`shallowRef`）、`loop`（默认 `true`）
- `timeRange` 由 `detail.points` 计算得到 `startMs` / `endMs`
- `canPlay`：点数 ≥ 2 且所有点都有可解析的 `recordedAt`
- 选中轨迹 → `:points` 变化后地球组件**自己重置**时钟，App 只需把 `playing` 置回 `false`
- 取消选中 → 隐藏播放条（移动点由 `clearTrack()` 移除）

---

## 五、边界情况

| 情况 | 处理 |
|---|---|
| 点数 < 2 或时间戳缺失/无法解析 | 播放条置灰并提示「这条轨迹缺时间信息，无法回放」，地球照常显示轨迹线 |
| `startMs === endMs`（时间跨度为零） | 视为不可回放，同上 |
| 切换到另一条轨迹 | `drawTrack()` 内部自动重置时钟（回到起点并暂停），App 把 `playing` 置回 `false` |
| 取消选中轨迹 | 移动点消失，播放条隐藏 |
| 拖动进度条 | 只改 `clock.currentTime`，不重建实体 |
| 组件卸载 | 已存在 `viewer.destroy()`；时钟随 Viewer 一起释放 |

---

## 六、验证方法

我（AI）看不到屏幕，所以**不靠「我觉得可以」**，靠截图算：

1. Playwright 打开 `http://localhost:5173`，点轨迹列表第一条
2. 点播放，等 5 秒截第一张，再等 5 秒截第二张
3. 用 Pillow 在两张图里找**白色移动点**的坐标（精确色 `(255,255,255)` 或近白）
4. 断言：两张图的坐标**不同**，且都落在蓝色轨迹线附近（可复用现有的 `#7fd1ff` 包围盒）
5. 再点暂停，等 2 秒截第三张，断言坐标与第二张**相同**

这三张截图构成「动起来了 → 还在动 → 停住了」的完整证据链。
脚本放 `.tmp/`（已 gitignore），验证结果写进 `_session_context.md`。

**已知坑**：不要用 `chrome --headless --virtual-time-budget` 截图验证（Cesium 异步几何体在虚拟时钟下不完成），
必须用 Playwright + 真实时间等待。

---

## 七、实施顺序（供 writing-plans 展开）

1. `CesiumGlobe.vue`：加 `SampledPositionProperty` + 移动点 + 时钟配置 + `defineExpose`
2. `TrackPlayer.vue`：新建纯展示播放条
3. `App.vue`：接线（状态 + 事件 + 传参）
4. Playwright 验证脚本 + 四张截图证据链
5. 本地提交（不推送）+ 更新 `_session_context.md`
