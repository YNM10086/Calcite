# Calcite · M2 第二阶段设计：停留热点（跨轨迹聚类）

> 状态：待评审
> 前置：M2 第一阶段「停留点识别」已完成（`docs/superpowers/specs/2026-09-14-m2-stay-point-design.md`）
> 日期：2026-09-15

---

## 1. 目标与范围

### 要解决什么问题

第一阶段能回答「**这一条**轨迹的人在哪里停过」。但它回答不了跨轨迹的问题：

> **哪些地方总有人停留？** —— 同一个地点，被几条不同的轨迹访问过？

这就是「热点」。它是把**所有轨迹**的停留点汇总起来，把**挨得足够近的**合并成一个地点，
并统计这个地点被访问的强度。

### 明确的范围边界（避免和设计文档原文混淆）

设计文档 `2026-09-08-calcite-trajectory-analysis-design.md` 第 128 行也写了「热点」，
但**那是另一个功能**：

| | 本阶段（停留热点） | 设计文档 M2 原文（网格密度） |
|---|---|---|
| 输入 | **停留点**（10 个） | **全部 track_point**（13,720 个） |
| 回答 | 哪些地方**总有人停下来** | 早高峰哪些**路段**人多 |
| 方法 | 距离聚类 | `ST_SnapToGrid` 网格统计 |
| 本质 | 目的地分析 | 车流分析 |

**两者都做，本阶段先做停留热点**，网格密度排在它之后（用户 2026-09-15 决定）。
命名上必须分开：本阶段用 `hotspot`（停留热点），网格那套将来用 `density`（密度）。

### 成功标准

1. 调 `GET /api/analysis/hotspots` 能在几百毫秒内返回全部热点
2. 每个热点带**三个热度口径**：停留次数、不同轨迹条数、累计停留时长
3. 前端能在地球上看出热点分布，在面板里看到明细，点一条能飞过去
4. 真实数据上结果与独立 Python 脚本**逐个数字对得上**

---

## 2. 真实数据现状（本设计的依据）

> 下面所有数字都是**实测**的，来自 `.tmp/analyze-hotspot-data.py` 与 `.tmp/hotspot-expected-json.py`。

- 库里有 **25 条轨迹 / 13,720 个点**（21 条 GeoLife + 3 条用户 GPX + 1 条示例）
- 第一阶段算法在默认参数下识别出 **10 个停留点**，来自 **6 条 GeoLife 轨迹**
- ⚠️ **用户自己的 4 条 GPX（资料一~四）一个停留点都没有** —— 那是跑步轨迹，中途没有
  在 50 米内停留超过 5 分钟。**热点功能实际只会展示 GeoLife 的数据**，这是正常的，不是 bug
- 10 个停留点全部落在 **2.3 km × 0.55 km** 范围内（北京），明显分成两堆
  （西边 7 个、东边 3 个；聚类后西边那一堆会拆成热点①和热点③）

### 参数的依据：距离分布里有一个空档

把 10 个停留点的 **45 对**两两距离排序：

| 距离区间 | 对数 |
|---|---|
| < 100 米 | 9 |
| 100 ~ 500 米 | 7 |
| > 500 米 | 29 |

最小值 1.4 米，最大值 2270 米。关键在于**空档的位置**：

```
... 118.3 米  |  ← 这里空了 113 米 →  |  231.5 米 ...
        ↑                                    ↑
   同一个人去了两次的同一地点            两个不同地点之间最近的
```

> **结论：`radiusM` 取 119 ~ 231 米之间任意值，聚类结果完全相同。**
> 默认取 **200 米**（落在空档正中），所以这个参数**不敏感**，不是拍脑袋定的。

---

## 3. 核心设计：聚类算法

### 算法：并查集单链聚类（single-link / 等价于 minPts=2 的 DBSCAN）

**五步**：

1. 收集所有（筛选后的）轨迹的停留点，每个都记住**它属于哪条轨迹**
2. 两两计算球面距离（复用 `GeoUtils.haversineMeters`）
3. 距离 **≤ radiusM** 的，连一条边
4. 用**并查集**求连通分量 —— 每个连通分量就是一个簇
5. 簇内点数 **< minVisits** 的判定为**孤立点**，不进热点列表

**伪代码**：

```
parent = [0..n-1]                     # 并查集
for i in 0..n-1:
    for j in i+1..n-1:
        if distance(stays[i], stays[j]) <= radiusM:
            union(i, j)
cluster = group_by(find(i))           # 每个根 = 一个簇
hotspots = [c for c in cluster if len(c) >= minVisits]
for c in hotspots:
    center = 所有点的重心
    visitCount     = len(c)
    trackCount     = 去重后的 trackId 个数
    totalDurationS = sum(点的时长)
    radiusM        = max(点到重心的距离)     # 这是真实散布，不是画的圈
```

**为什么用并查集而不是写完整 DBSCAN**：`minVisits=2` 时 DBSCAN 退化成单链聚类，
两者的连通分量完全一致。DBSCAN 多出来的只是「核心点/边界点/噪声点」的分类，
而我们要的「孤立点」判断用 `簇大小 < minVisits` 一行就够了。**用简单实现拿到等价结果。**

### ⭐ 必须知道的算法特性：传递性（链式效应）

单链聚类是**传递**的：

```
A ──150m── B ──150m── C        A 和 C 相距 300 米
└──────── 合成同一个热点 ────────┘
```

**这意味着一个热点可能横跨几百米，形成一条"链"。**

这是单链聚类的固有行为，**DBSCAN 在 `minPts=2` 时也一样**，换算法解决不了。
要消除它得改用 K-Means 或加"最大簇直径"限制，复杂度上一个台阶。

**决定：不修。** 但必须——
- 写成单元测试**钉住**（见第 8 节）
- 写进本文档和用户文档，避免将来误判成 bug

### 复杂度

O(n²) 两两比较。当前 n=10，45 次比较，可忽略。
**这是本设计最大的已知性能限制**，见第 9 节。

---

## 4. 接口设计

### `GET /api/analysis/hotspots`

| 参数 | 默认 | 说明 |
|---|---|---|
| `radiusM` | 200 | 聚类半径（米），两个停留点在此距离内视为同一地点 |
| `minVisits` | 2 | 至少几个停留点才算热点 |
| `from` | 无 | 可选，ISO 时间；只统计此时间**之后**开始的停留 |
| `to` | 无 | 可选，ISO 时间；只统计此时间**之前**结束的停留 |

### 响应（真实数据实测值，用作验收基准）

```json
{
  "scannedTracks": 25,
  "scannedStays": 10,
  "params": { "radiusM": 200.0, "minVisits": 2, "from": null, "to": null },
  "hotspots": [
    {
      "rank": 1,
      "centerLat": 40.011572,
      "centerLon": 116.296853,
      "visitCount": 4,
      "trackCount": 3,
      "totalDurationS": 1730,
      "radiusM": 9.4,
      "firstVisit": "2008-10-28T00:50:51Z",
      "lastVisit": "2008-11-11T00:47:19Z",
      "trackIds": [9, 13, 15]
    },
    {
      "rank": 2,
      "centerLat": 40.008948,
      "centerLon": 116.321793,
      "visitCount": 3,
      "trackCount": 3,
      "totalDurationS": 1228,
      "radiusM": 58.1,
      "firstVisit": "2008-10-23T09:50:00Z",
      "lastVisit": "2008-11-14T11:28:19Z",
      "trackIds": [5, 6, 20]
    },
    {
      "rank": 3,
      "centerLat": 40.006719,
      "centerLon": 116.296562,
      "visitCount": 2,
      "trackCount": 1,
      "totalDurationS": 650,
      "radiusM": 59.1,
      "firstVisit": "2008-11-04T01:47:48Z",
      "lastVisit": "2008-11-04T02:12:53Z",
      "trackIds": [13]
    }
  ]
}
```

**读这份结果要看出的三件事**：

1. `scannedStays: 10` 但只有 3 个热点 —— 差的 1 个是**孤立点**（只去过一次）
2. **热点①**：同一个人在三周内（10-28 / 11-04 / 11-11）去了同一个地方 **4 次**，
   而且这 4 次**真实散布只有 9.4 米** —— 这是极强意义上的"常去地点"
3. **热点③**：`visitCount=2` 但 `trackCount=1` —— **同一个人去了两次**。
   这正是需要三个口径的原因：按次数它排第 3，按轨迹数它和孤立点一样"冷"

**排序口径**：`rank` 按 `trackCount ↓` → `visitCount ↓` → `totalDurationS ↓` →
`centerLat ↑` → `centerLon ↑` **五级**排序。
选"轨迹数优先"是因为它最接近"这是个公共地点"的含义。
**为什么是五级而不是三级**：只写三级时，前三项全平局的两个热点顺序会随输入顺序漂移，
结果就不是**完全确定**的，也没法写进测试。后两级用坐标兜底正是为了消掉这个不确定性。

**错误处理**：

- 0 个停留点 / 0 个热点 → 返回 `hotspots: []`，**不是错误**（HTTP 200）
- `radiusM <= 0` 或 `minVisits < 1` → HTTP 400（和 `StayPointService` 构造器校验参数一致的风格）

**⚠️ 时间窗不是性能优化**：`from`/`to` 过滤的是**算出来的停留点**，不是轨迹点。
因为停留点必须先由完整轨迹算出来才知道它的起止时间，所以**无论有没有时间窗，
所有轨迹的点都要读一遍**。时间窗只影响"哪些停留点参与聚类"，不影响 IO 开销。
（如果将来真需要靠时间窗省 IO，那要先入库 `stay_point`。见 10.2。）

---

## 5. 后端组件

### 新增

| 文件 | 职责 |
|---|---|
| `service/TrackedStay.java` | `record TrackedStay(long trackId, StayPoint stay)` —— 把停留点和它的归属绑在一起（`StayPoint` 本身不知道自己在哪条轨迹里） |
| `service/Hotspot.java` | `record`：一个热点的全部输出字段 |
| `service/HotspotService.java` | ★ 核心：聚类。**核心方法 `cluster()` 是纯函数**，不碰数据库 |
| `web/AnalysisController.java` | `GET /api/analysis/hotspots` |
| `web/dto/HotspotDto.java` + `HotspotResponse.java` | JSON 契约 |
| `test/.../HotspotServiceTest.java` | 单元测试（见第 8 节） |

### 需要改动的既有文件

| 文件 | 改动 | 为什么 |
|---|---|---|
| `repository/TrackPointRepository.java` | **新增** `findAllByTrackIds(Collection<Long>)` | 现在**只有** `findByTrackIdOrderBySeqAsc(Long)`，即一次只能查一条轨迹。25 条轨迹就是 25 次查询。批量查询是热点接口的性能前提 |

```java
// TrackPoint 用的是普通 Long trackId 字段（不是 @ManyToOne），所以查询直接写 trackId
@Query("SELECT p FROM TrackPoint p WHERE p.trackId IN :trackIds ORDER BY p.trackId ASC, p.seq ASC")
List<TrackPoint> findAllByTrackIds(@Param("trackIds") Collection<Long> trackIds);
```

> ⚠️ **为什么 `ORDER BY p.trackId, p.seq` 是必须的**：`StayPointService.detect()` 的前置条件是
> "点已按时间升序、且下标等于 seq"。批量查出来的结果必须按 `trackId` 分组后**各自保持 seq 升序**，
> 否则算出来的停留点是错的。这里排好序，Java 侧按 `trackId` 分组即可，不用再排。

> ⚠️ **`IN` 子句的规模**：轨迹超过几千条时，`IN` 里的参数会很多，SQL 会变慢甚至超限。
> 这是 10.2 里"轨迹超过 500 条就入库"那条触发条件的另一个理由。

### 复用（不改动）

- `service/StayPointService` —— 逐条轨迹找停留点
- `service/GeoUtils.haversineMeters` —— 球面距离

### 为什么不塞进 `TrackController`

`TrackController` 管的是**单条轨迹**（列表/详情/停留点），而热点是**跨轨迹**的分析。
职责不同，分开更清楚；将来 `similarity`、`density` 这些分析接口也往 `AnalysisController` 加。

### 数据流与装配方式

```
AnalysisController
  → 一次批量查询取出所有（筛选后的）轨迹的点     ← 不是逐条查
  → 对每条轨迹调 StayPointService.detect()      ← 复用第一阶段
  → 组装成 List<TrackedStay>
  → HotspotService.cluster(stays, radiusM, minVisits)
  → 转成 HotspotResponse
```

`HotspotService` 的签名与装配方式：

```java
@Component
public class HotspotService {
    /** 纯函数：给定停留点和参数，算出热点。无状态、无依赖、可单测 */
    public List<Hotspot> cluster(List<TrackedStay> stays, double radiusM, int minVisits) { ... }
}
```

**为什么参数走方法参数而不是构造器 `@Value`**：第一阶段 `StayPointService` 的三个参数是
**全局固定**的（走 `application.yml`），所以放构造器合理。但热点的 `radiusM` / `minVisits`
**允许每次请求不同**（接口上有这两个查询参数），所以它们必须是**方法参数**。

默认值仍然放 `application.yml`（`calcite.hotspot.*`），由 **`AnalysisController`** 用 `@Value` 读进来，
请求没传参数时用默认值。这样：

- `HotspotService` 本身**无状态**，测试里直接 `new HotspotService().cluster(...)` 就能跑，不用启 Spring
- 参数校验（`radiusM > 0`、`minVisits >= 1`）放在 `cluster()` 入口，非法就抛
  `IllegalArgumentException`，**和 `StayPointService` 构造器的校验风格保持一致**

---

## 6. 前端设计

### 交互模式：顶部切换开关（用户 2026-09-15 选定方案 A）

面板顶部加一个「**停留点 / 热点**」两档开关。**地球只画当前这一档的东西**。

**为什么不两个都画**：10 个停留点正好落在 3 个热点圈里，两种圈颜色叠在一起完全看不清
（浏览器伴侣里已画出来给用户确认过）。而且"热点"本来就不属于某条轨迹，和轨迹详情混在一起逻辑不顺。

### 地球上的画法：两个视觉通道各管一个维度

| 视觉 | 绑定 | 一眼看出 |
|---|---|---|
| **圆的大小** | `visitCount` | 越大 = 越常来 |
| **圆的颜色** | `trackCount` | 越红 = 越多不同轨迹来过；偏黄 = 同一个人常来 |

用两个通道是必须的：只用一个的话，**热点①（4 次/3 条轨迹）** 和
**热点③（2 次/1 条轨迹）** 会表达成同一件事，而这正是用户选"三口径都要"要解决的问题。

⚠️ 圆是**高亮**，**不代表精度**。热点①真实散布只有 9.4 米，按真实尺寸画就看不见了。
这一点要在界面上用文字说明，避免误解。

### 相机

进入热点模式时，自动飞到**能装下所有热点的包围盒**（复用第一阶段 `flyTo` 的思路）。

### 组件

| 文件 | 改动 |
|---|---|
| `components/HotspotList.vue` | 新增。纯展示，props 进 / `focus` 事件出，**自己不发请求**（和 `StayPointList` 同规矩） |
| `components/CesiumGlobe.vue` | 加 `hotspots` prop + `drawHotspots()`；`focusOn` 复用 |
| `App.vue` | 加 `hotspots` 状态、`loadHotspots()`、`viewMode`（stay/hotspot）、模式切换 UI、排序状态 |

三种状态都要有：**加载中 / 一个热点都没有 / 请求失败**。

---

## 7. 参数与默认值

```yaml
calcite:
  hotspot:
    radius-m: 200        # 聚类半径。依据见第 2 节：119~231 米之间结果完全相同
    min-visits: 2        # 至少几个停留点才算热点
```

改完重启后端即可，Java 代码不用动。

---

## 8. 测试与验收

### 8.1 后端单元测试 `HotspotServiceTest`

纯函数，直接 `new HotspotService()`，不启 Spring、不连数据库。

| 类别 | 用例 |
|---|---|
| 空输入 | 空列表 → 空结果 |
| 不够门槛 | 只有 1 个停留点 → 空（`minVisits=2`） |
| 合并 | 两点相距 150 米 → 1 个热点，`visitCount=2` |
| 不合并 | 两点相距 250 米 → 空 |
| **边界** | 两点**正好 200 米** → 应该合并（含等号） |
| **⭐ 传递性** | A—B 150m、B—C 150m、A—C 300m → **合成 1 个**（钉住链式效应） |
| 去重 | 同一条轨迹的 3 个点聚在一起 → `visitCount=3` 但 `trackCount=1` |
| 汇总 | `totalDurationS` 累加正确；重心坐标正确 |
| 排序 | `rank` 严格按 `trackCount → visitCount → totalDurationS → centerLat → centerLon` 五级降序 |
| 参数校验 | `radiusM <= 0`、`minVisits < 1` → 抛 `IllegalArgumentException` |
| **真实数据指纹** | 25 条轨迹 → 正好 **3 个热点**，且 `visitCount` / `trackCount` / `centerLat` / `centerLon` / `radiusM` 与第 4 节那组**精确值**一致（坐标容差 1e-6，半径容差 0.2 米） |

> 真实数据指纹这条是**最强的防线**：它同时钉住了算法、参数、排序和数据本身。
> 它挑的是"三周内 4 次停留、散布 9.4 米"这种临界样本，算法被改错一点点就会红。

### 8.2 浏览器验收 `.tmp/check-hotspots.py`

| 检查 | 判据 |
|---|---|
| 热点列表渲染 | 正好 3 条 `[data-testid="hotspot-item"]` |
| 显示三个口径 | 每行能读到"次/条轨迹/分钟" |
| 地球上有热点圈 | 橙色系像素数 > 阈值（排除面板区域，**用 DOM 取面板右边界，不写死**） |
| 点击不报错 | 点第一条 → 相机飞行 → 无异常 |
| 切模式地球不花 | 切到"停留点"后，热点圈像素归零 |
| 排序切换生效 | 切"按时长"，第一条的排名变化符合预期 |
| 控制台零报错 | 与现有验收一致的判据 |

### 8.3 回归

现有 **140 项**必须保持全绿（后端 58 + check:playback 17 + check:chart 37 +
check-stay-points 7 + check-chart-pixels 10 + check-import-pixels 5 + check-filter 6）。

---

## 9. 已知限制与明确不做的事

| 限制 | 说明 | 为什么现在不做 |
|---|---|---|
| **O(n²) 两两比较** | 停留点涨到 1 万时是 5000 万次比较，会明显卡 | 现在只有 10 个点。缓解办法是**先按经纬度分桶、只比相邻桶**，等真慢了再上 |
| **热点可能横跨几百米** | 单链聚类的传递性（第 3 节） | 换算法（K-Means / 最大直径限制）复杂度上一个台阶。**已钉成测试** |
| 时间窗没有前端控件 | 后端支持 `from`/`to` | YAGNI，需要时再加控件 |
| 孤立点不返回 | 只去过 1 次的地方不在结果里 | `scannedStays - Σ visitCount` 就能推出有几个 |
| 热点不命名 / 不匹配 POI | 只给坐标，不告诉你"这是北京西站" | 属于另一个功能（POI 匹配） |
| 聚类参数没有前端调节 | 走 URL 参数或配置文件 | 和第一阶段保持一致 |
| 用户自己的 GPX 不产生热点 | 跑步轨迹没有长时间停留 | 数据本身如此，不是 bug |

---

## 10. 关键决策记录

### 10.1 为什么不用网格法（用户先选后改）

用户最初选了网格法，看过**真实数据对比图**后改选聚类法。网格法被否掉的具体原因：

- 网格会把**同一个地点切开**：用户数据里轨迹 13 两次访问相距 **118 米**，
  恰好被 200 米的格子边界切开，报成了两处（聚类法正确合成了一处）
- **结果随网格原点漂移**：换一个原点，同一个热点可能落进不同格子
- 聚类法的中心是**真实重心**，且能顺手分出孤立点

> 注：设计文档 M2 原文的网格法（对 **track_point** 做密度统计）**不受这些批评影响** ——
> 那是对几万个点做统计，网格是自然选择。**批评只针对"用网格聚合 10 个停留点"这个用法。**

### 10.2 为什么停留点不入库（先现算）

**证据**（`.tmp/measure-hotspot-cost.py` 实测）：

| | 现在 | 假设全部导入后 |
|---|---|---|
| 轨迹 / 点数 | 25 条 / 13,720 点 | 18,670 条 / 约 1000 万点 |
| 热点接口耗时 | 逐条走 HTTP 约 **500~600 ms**；真实实现是**进程内一次批量查询**，会明显更快 | 线性外推 **分钟级，不可用** |

**不入库的理由**：

1. 当前规模现算完全够用
2. 入库会引入三件麻烦事：停留点**什么时候算**、**参数改了怎么办**、**导入新轨迹要不要重算**
   —— 这正是第一阶段特意避开的（见附录 B.2）
3. 代码结构已支持随时切换：`StayPointService` 是纯函数，入库只是多一个"写库"步骤，**不是重写**

**触发入库的条件（写下来，让决策可追溯、不是拍脑袋）**：

> 当**轨迹数超过 500 条**，或**热点接口耗时超过 2 秒**时，
> 把停留点入库 `stay_point`，改成 SQL 聚合 + `ST_ClusterDBSCAN`。

### 10.3 为什么用并查集而不是完整 DBSCAN

`minVisits=2` 时两者连通分量等价（见第 3 节）。用简单实现拿到等价结果，代码更好懂、更好测。

### 10.4 保留 `StayPointService` 不变

热点完全建立在第一阶段之上，**不改动它的任何代码**。这样第一阶段的 12 个测试和真实数据指纹
继续有效，是本设计最强的回归保障。

---

## 附录 A · 本阶段对设计文档原文的影响

| 原设计文档的位置 | 变化 |
|---|---|
| 第 128 行「热点区域分析：按固定边长网格统计轨迹点密度」 | **不变**，但推迟到停留热点之后做，且接口命名用 `density` 与 `hotspot` 区分 |
| 第 300 行 `HotspotService.java  热点分析` | 需要拆成两个：`HotspotService`（停留热点）与将来的 `DensityService`（网格密度） |
| 第 349 行 `GET /api/analysis/hotspots`「指定时间窗内的热点网格」 | 路径沿用，但语义改为**停留热点**；网格密度将来用 `/api/analysis/density` |
| 附录 B.2 未决问题「stay_point 表是否入库」 | **本阶段决定仍不入库**，并写明触发条件（见 10.2） |
