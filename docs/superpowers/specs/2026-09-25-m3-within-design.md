# Calcite · M3 设计：空间范围查询（画一块区域，找出穿过它的轨迹）

> **日期**：2026-09-25
> **仓库 HEAD**：`980f17d`（= `origin/main`）
> **对应的总设计方针**：`docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`
> —— M3 第一条（第 134 行）、接口表第 357 行 `POST /api/analysis/within`、场景表第 30 行场景 5
> **前置阅读**：`docs/superpowers/M3-START-HERE.md`、`_session_context.md`
> **一句话**：让你在地球上圈一块区域（拉框 / 自由多边形 / 缓冲区），立刻知道哪些轨迹穿过它、
> 这块区域里到底有什么，并把区域和命中轨迹叠在三维地球上。

---

## 1. 目标与范围

### 要做什么

1. **第五档「圈选」**：前端分析面板现在是四档 `[停留点 | 热点 | 密度 | 相似]`，加第五档。
2. **三种圈选形状**：拉框（矩形）、自由多边形、缓冲区（点一个中心 + 半径）。
3. **一个接口**：`POST /api/analysis/within` —— 传一个 GeoJSON 几何，返回
   **穿过的轨迹列表** + **区域统计** + **后端实际使用的区域**（`region` 回显）。
4. **叠加到三维地球**：画出区域轮廓，并把命中的轨迹叠画上去（默认前若干条）。
5. **空间查询优化的实测结论**（M3 第二件事，见第 2、3 节）——本轮所有性能判断都由 `EXPLAIN ANALYZE` 实测支撑。
6. **路网匹配可行性评估**（M3 第三件事，见第 12 节）——只给结论，不实现。

### 为什么要做

总设计文档的场景 5 是「**有没有经过某条河以东的区域？**」，M3 的验收标准原文是
「**能在地图上画多边形，查出穿过的轨迹**」。这是 M3 唯一还没做的一条——
轨迹相似度已在 M2 第四阶段完成（且实测证明 `ST_FrechetDistance` 不可用），网格密度已在 M2 第三阶段完成。

### 成功标准（可验收）

- [ ] 在网页上能**拉框 / 画多边形 / 点一个中心给半径**，三种都能查出穿过的轨迹
- [ ] 结果同时给出**区域统计**（条数 / 区域内点数 / 累计里程 / 停留点数 / 来源分布 / 时间跨度）
- [ ] 区域轮廓与命中轨迹**画在地球上**，列表与地图联动
- [ ] 缓冲区的**圆由后端算**，前端照着 `region` 回显画 → 看到的圈 = 实际查的范围
- [ ] 非法几何 / 非法参数一律 **400 且说明原因**；区域内没有轨迹是 **200 + 空列表**（不是错误）
- [ ] 后端 JUnit、前端 node、浏览器/接口脚本**全绿且不退化**
- [ ] 设计文档里有**缓冲区优化的前后实测对比**（M3「空间查询优化」的交付物）

### 范围之外（本轮不做）

保存/命名区域、区域导出、多区域叠加、路网匹配**实现**、区域内的深度指标（限速/爬升）、时间轴动画。
另：M3-START-HERE 第 3 节列的四笔欠账（空间索引以外的三笔）**经用户决定全部不还**，留给以后。

---

## 2. 真实数据与可行性实测（本设计的全部依据）

> 本节所有数字都是 2026-09-25 在 `calcite` 库上实测的（`EXPLAIN (ANALYZE, BUFFERS)` + psql 计时）。
> **凡与本文件冲突的旧数字，以本文件为准。**

### 2.1 数据现状（实测，⚠️ 更正记忆里一条过时描述）

```
track 246 条 / track_point 286,019 个
地理构成：北京 235（含 1 条示例轨迹）、上海 5、京沪长途 3、福建 3
```

⚠️ `_session_context.md` 里写的「geoLife 242 条 = 北京 171 + 长三角 71」**已过时**——
实测是 **北京 234 + 上海 5 + 京沪长途 3**（另有 3 条福建 GPX 与 1 条示例）。
总数 246 对得上，地理构成对不上；推测与「数据管理」阶段那次 `maxTracks` 事故后的 SQL 清理有关。
**本设计按实测写。**

另有两类必须知道的数据特征（后面第 3 节要用）：

| 特征 | 实测 |
|---|---|
| 相邻两点间距 > 1 km 的段 | **83** 段 |
| > 10 km | **15** 段 |
| > 50 km | **3** 段 |
| 总段数 / 最长段 | 285,773 段 / **1,076,364 m（1076 km）** |
| 含 > 50 km 跳跃的轨迹 | **3 条：id 121 / 161 / 166**（北京↔上海的长途记录，疑似飞行或记录中断） |

**第二长的段只有 14.8 km** —— 也就是说，除了那 3 条，全库轨迹的几何都是"密"的。

### 2.2 轨迹级圈选**本来就命中索引** ✅

```sql
SELECT t.id FROM track t
WHERE ST_Intersects(t.geom, ST_MakeEnvelope(116.28, 39.98, 116.42, 40.02, 4326));
```

```
Bitmap Heap Scan on track  (actual time=3.002..21.548 rows=232.00)
  ->  Bitmap Index Scan on idx_track_geom  (rows=232.00)
        Index Cond: (geom && '...'::geometry)
Execution Time: 24.164 ms
```

**232 条命中 / 24 ms。** 结论：**"线和多边形相交"这个谓词本身就是索引友好的**，
拉框与自由多边形不需要任何特殊优化。

⚠️ 注意这与 M2 第三阶段的记录**不矛盾**：那条讲的是 **`track_point`（286k 行）上的 `geom && ...` 没走索引**，
这里是 **`track`（246 行）上的 `ST_Intersects` 走了索引**。两张表、两种结论，别混。

### 2.3 ⭐⭐ 缓冲区的瓶颈**不是**"没走索引"，而是"逐顶点算球面距离"

这是本设计最重要的一次实测更正。四种写法，同一个查询（圆心 116.32/40.00，半径 1000 m）：

| 写法 | 耗时 | 命中 | 执行计划 |
|---|---|---|---|
| ❌ `ST_DWithin(t.geom::geography, 点::geography, 1000)`（现状直觉写法） | **303–329 ms** | 225 | **Seq Scan**（`::geography` 是表达式，用不上索引） |
| ⚠️ 加外扩矩形粗筛 `geom && ST_Expand(点, 0.0141, 0.0108)` + 上面的 `ST_DWithin` | 271–281 ms | 225 | Bitmap Index Scan ✅ **但只快 10%** |
| ✅ **圆多边形** `ST_Intersects(t.geom, ST_Buffer(点::geography, 1000)::geometry)` | **7.9 ms** | 225 ✓ | Index Scan ✅ |
| ❌ 平面度数 `ST_DWithin(t.geom, 点, 0.008983)` | 4.5 ms | **222 ✗** | —（结果错，见 3.3） |

**为什么"加粗筛"只快 10%**：北京这一片 246 条里有 **228 条**落在粗筛框内（候选占 93%），
真正的开销是**对每条候选轨迹的每个顶点算一遍椭球距离**——粗筛根本减不掉它。
上海那组（候选只有 1 条）对比更刺眼：**现状 292 ms → 圆多边形 8.2 ms**，
执行计划是 `Index Scan using idx_track_geom`、`Execution Time: 0.53 ms`。

**结论（写进实现）**：缓冲区**不当作"距离判断"**，而是**由后端算成一个圆多边形**，
之后与"拉框/多边形"**走完全相同的判定**。

### 2.4 ⚠️ 平面几何 vs 球面距离：在这 3 条轨迹上最大差 11.7 km

用 7 组参数对拍两种写法（`ST_DWithin(球面)` vs `ST_Intersects(圆多边形)`）：

| 参数 | `ST_DWithin` 命中 | `ST_Intersects` 命中 | 只在球面 | 只在平面 |
|---|---|---|---|---|
| 北京 300 m / 1 km / 2 km | 115 / 225 / 10 | 115 / 225 / 10 | 0 | 0 |
| 上海 1 km / 2 km | 1 / 3 | 1 / 3 | 0 | 0 |
| 福建 800 m | 3 | 3 | 0 | 0 |
| **点 (118.95, 35.66) 半径 1.5 km** | **0** | **3** | 0 | **3** ⚠️ |

对 `id=121` 逐项诊断：

```
ST_Intersects(线, 圆)      = true
ST_DWithin(线::geography, 圆心::geography, 1500) = false
真实球面距离               = 11,720.1 m
平面距离                   = 0.00336°（约 375 m）
该轨迹在纬度 35.5~35.8 之间的顶点数 = 0   ← 那一段是一次**没有记录点的超长跨越**
```

**根因**：`LineString` 的一条超长边（这里 1076 km），
在**平面**解释下是经纬度图上的一条直线，在**球面**解释下是大圆航线——两者能差十几公里。
这不是 bug，是两种几何模型的固有差别。

**影响面（已量化，所以可以放心）**：全库只有 **3 条**轨迹（121/161/166）含这种超长边；
其余轨迹最长边 14.8 km，两种解释的差异 < 0.1%。

### 2.5 区域统计（区域内点数）的成本

```sql
SELECT p.track_id, count(*) FROM track_point p
WHERE p.geom && :env AND ST_Intersects(:env, p.geom) GROUP BY p.track_id
```

| 区域 | 耗时 | 说明 |
|---|---|---|
| 北京大框（116.28–116.42 / 39.98–40.02） | **171 ms** | 走顺序扫描（286k 行时优化器认为更划算），232 组 |
| 上海 1 km 圆 | **23 ms** | 小区域反而走索引 |

**这是接口里最贵的一步，但可以接受**（总响应 ≈ 200 ms 量级）。
另：`geom && 区域` 粗筛得 181,218 点，加 `ST_Intersects` 精算得 **181,211 点**——差 7 个落在边界角上的点，
所以**精算谓词不能省**。

### 2.6 缓冲区的圆有多少顶点

`ST_NPoints(ST_Buffer(点::geography, r)::geometry)` = **33**（半径 500 m 与 5000 m 都是 33，
PostGIS 默认每象限 8 段 → 4×8+1）。**服务端生成的缓冲区不需要顶点数限制**；
需要限制的是**用户手画的多边形**（见第 7 节 `max-vertices`）。

### 2.7 前端交互所需的 Cesium API 全部存在 ✅

在装的 Cesium 1.145 的 `Source/Cesium.d.ts` 里逐个确认：

| 需要的 API | 位置 | 用途 |
|---|---|---|
| `ScreenSpaceEventType.LEFT_DOWN / LEFT_UP / LEFT_CLICK / LEFT_DOUBLE_CLICK / MOUSE_MOVE` | 16449 | 拉框与多边形的鼠标事件 |
| `ScreenSpaceEventHandler.setInputAction(action, type, modifiers?)` | 16391/16400 | 注册/注销，可逆 |
| `viewer.screenSpaceCameraController` → **`enableRotate: boolean`** | 44780 / 45315 | **画之前必须关掉左键旋转**（见 6.2） |
| `camera.pickEllipsoid(windowPosition, ellipsoid?, result?)` | 29406 | 屏幕坐标 → 经纬度 |
| `scene.pickPosition(windowPosition, result?)` | 45040 | 同上（贴地时更准） |
| `drawSimilarity(baseline, tracks)` 的多线叠加写法（每条一个 Polyline + 按值配色） | `CesiumGlobe.vue` 273 | **可直接复用于"命中轨迹"图层** |

### 2.8 仓储层的既有写法（决定新代码怎么写）

- 空间 SQL 一律 `@Query(value = "...", nativeQuery = true)` 返回 `List<Object[]>`（见 `TrackRepository`）
- ⭐ **`TrackRepository.findSummariesByIds(ids)` 已存在**，返回
  `[id, name, source, point_count, ST_Length(geography), start_time(ISO 字符串)]` ——
  **正是圈选列表要的东西**，但它正被相似度接口使用，**不能改**（只差 `durationS`/`endTime`，另写一个）
- `timestamptz` 一律用 `to_char(... AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')` 转字符串 ——
  **避免 native query 的类型映射歧义**（`TrackRepository` 的既有注释记着这个坑）
- 点级查询可以用 `ST_DWithin(geography)`（点便宜，相似度接口就这么写的），
  **线级不行**（2.3 实测 303 ms）——这条差异要留在代码注释里，免得以后有人"统一写法"把性能改坏

---

## 3. 判定口径（本设计的核心）

### 3.1 统一用**平面几何谓词**

**判定式**：`ST_Intersects(track.geom, 区域几何)`（SRID 4326），一次性对所有形状生效。

理由三条：
1. **命中 GiST 索引**（2.2 实测 24 ms）
2. **与项目里其它功能语义一致** —— 密度、热点、相似度的空间预筛全部用 `geom &&`（平面）
3. **一个谓词覆盖三种形状**，后端只有一条代码路径

### 3.2 缓冲区 = 由后端算成的**多边形**，不是距离判断

```
用户点一个中心 + 给半径 r
  → 后端：ST_Buffer(中心::geography, r)::geometry   ← 球面缓冲区，33 个顶点（2.6）
  → 得到圆多边形 = 既是对外返回的 region，也是查询用的几何
  → 判定与"拉框/多边形"完全相同：ST_Intersects(track.geom, 圆多边形)
```

⭐ 这个设计的两个好处：
- **性能**：7.9 ms（对比直觉写法的 303 ms）
- **正确性上的自洽**：`region` 回显的就是**真正拿去查的那个几何**，不存在"画的和查的不是一回事"

### 3.3 为什么不用平面度数 `ST_DWithin`

`ST_DWithin(t.geom, 点, 0.008983)` 只要 4.5 ms，**但结果是错的**：
返回 222 条而正确是 225 条。因为"度"不是等长单位 ——
同样的度数，经度方向的实际长度要乘 `cos(纬度)`（北京纬度 40°，差约 23%）。
**快 1.8 倍但答错，没有讨论余地。**

### 3.4 ⚠️ 已知限制（会写进代码注释与用户可见的说明）

**平面解释与球面解释在"含超长边的轨迹"上会分歧，最大 11.7 km。**
具体：如果一块区域正好落在那 3 条（121/161/166）某次超长跨越的**平面直线**附近，
而那次跨越在球面上离得更远，那么平面判定会说"穿过"，球面判定会说"没穿过"。

**为什么不修**：修它就要放弃索引（2.3 实测 303 ms），或者在查询时把线加密（更贵）；
而这 3 条轨迹本身记录是断的（一次 1076 km 没有记录点），"有没有穿过山东某条河"对它们本来就无意义。
**做法**：把这 3 条作为**已知边界用例钉进验收脚本**（第 9 节），并在返回里不作特殊标记。

---

## 4. 接口设计

### `POST /api/analysis/within`

**为什么是 POST 而不是 GET**：自由多边形的坐标串放在 URL 里既长又要转义；
POST 的 body 天然适合放 GeoJSON。（对比：密度接口只需要 `bbox` 四个数，所以用 GET + query 参数。）

**请求体**

```json
{
  "geometry": { "type": "Polygon", "coordinates": [[[116.30,39.95],[116.40,39.95],[116.40,40.05],[116.30,40.05],[116.30,39.95]]] },
  "bufferM": 500,
  "from": "2008-10-01T00:00:00+08:00",
  "to":   "2008-12-31T23:59:59+08:00",
  "limit": 50
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `geometry` | ✅ | GeoJSON 几何。`Polygon` / `MultiPolygon`（拉框与自由多边形）或 `Point`（缓冲区中心） |
| `bufferM` | 仅当 `geometry` 是 `Point` | 球面缓冲半径（米）。给了它 → 半径 r 的圆；`Point` 不给 → 400 |
| `from` / `to` | ❌ | 时间过滤，**语义见 5.7** |
| `limit` | ❌ | 返回条数上限，默认 50，最大 500。**不影响统计** |

**响应**（200）

```json
{
  "region": { "type": "Polygon", "coordinates": [[...]] },
  "stats": {
    "trackCount": 232,
    "pointCount": 181211,
    "distanceM": 1234567.8,
    "stayCount": 12,
    "sourceCounts": { "geolife": 230, "gpx": 1, "sample": 1 },
    "earliest": "2008-10-23T02:53:04Z",
    "latest":   "2009-07-05T02:53:07Z"
  },
  "items": [
    { "trackId": 15, "name": "20081111001704", "source": "geolife",
      "distanceM": 4321.0, "durationS": 900, "pointCount": 121, "insidePointCount": 88,
      "startTime": "2008-11-11T00:17:04Z", "endTime": "2008-11-11T00:32:04Z" }
  ],
  "total": 232,
  "truncated": true,
  "params": { "bufferM": null, "from": null, "to": null, "limit": 50 }
}
```

- ⭐ **`region` 是后端实际使用的几何**（缓冲区已算成圆多边形，见 3.2）。**前端照着它画。**
- `total` = **命中总数**；`items` 可能被 `limit` 截断，此时 `truncated = true`。
- `stats` **永远是全量的**，不受 `limit` 影响。
- 统计口径见第 5.6–5.7 节（**口径写死，否则数字会被误读**）。

**错误处理**

| 情况 | 状态码 |
|---|---|
| body 不是合法 JSON / 缺 `geometry` | 400 |
| `geometry.type` 不在 `{Polygon, MultiPolygon, Point}` 内 | 400 |
| Polygon 环未闭合，或某环点数 < 4 | 400 |
| 坐标越界（`|lat| > 90` 或 `|lon| > 180`） | 400 |
| 顶点数 > `calcite.within.max-vertices` | 400（"区域太复杂，请简化"） |
| `geometry` 是 `Point` 但没给 `bufferM` | 400 |
| `bufferM <= 0`、非有限数，或 > `max-buffer-m` | 400 |
| `from > to` | 400 |
| `limit < 1` 或 > `max-limit` | 400 |
| **区域内没有轨迹** | **200 + 空 items + 全 0 统计**（"没有"是正常结果，不是错误） |

判据写法沿用 `AnalysisController.hotspots` 的经验：**用 `!(x > 0)` 而不是 `x <= 0`**，
否则 `NaN` 会绕过 400、落到 service 抛异常被映射成 500。

### 4.1 统计口径（写死，否则数字会被误读）

| 字段 | 口径（**必须按这句话理解**） |
|---|---|
| `stats.trackCount` / `total` | 轨迹**线**与区域相交的轨迹条数 |
| `stats.pointCount` | **所有**轨迹落在区域内的点之和（按轨迹分组后相加；线相交但无点落在里面的轨迹贡献 0） |
| `stats.distanceM` | 命中轨迹的**整条**里程之和 —— ⚠️ **不是区域内那一段**（算"区域内那一段"要 `ST_Intersection`，慢且口径更绕） |
| `stats.stayCount` | **命中轨迹**在区域内的停留点个数（见 5.9 的口径说明） |
| `stats.sourceCounts` | 命中轨迹按 `source` 分组计数 |
| `stats.earliest` / `latest` | 命中轨迹 `start_time` 的最早 / `end_time` 的最晚 |
| `items[].insidePointCount` | 该轨迹落在区域内的点数（与 `stats.pointCount` 的分组来源是**同一个查询**，必然自洽） |
| `items[].distanceM` / `durationS` / `pointCount` | 整条轨迹的里程 / 时长 / 点数（**不是区域内的**） |

⭐ 一句话：**除了 `insidePointCount`，items 里所有数字都是"整条轨迹"的**。
`distanceM` 尤其容易被误读成"在区域里跑了多远"，所以接口字段名与文档都不含糊。

---

## 5. 后端实现

### 5.1 组件划分

| 类 | 职责 | 层级理由 |
|---|---|---|
| `web/dto/WithinRequest`（record） | 请求体形状：`JsonNode geometry` + `Integer bufferM` + `OffsetDateTime from/to` + `Integer limit` | DTO 只描述形状 |
| `web/dto/WithinResponse`（record） | 响应：`region` / `stats` / `items` / `total` / `truncated` / `params`；内嵌 `Stats` / `Item` / `Params` | 沿用 `HotspotResponse.Params` 的嵌套 record 风格 |
| `service/RegionGeometry`（纯计算，零依赖） | GeoJSON → 校验 → 顶点数 / 越界检查 → WKT 字符串；环闭合判断 | **纯函数，可以直接用 JUnit 测**（对齐 `SimilarityMath` / `DensityGrid` 的做法） |
| `service/WithinService` | 编排：算 region → 查 id → 查 items → 算统计 → 截断 | 碰数据库的都在这层 |
| `service/WithinProperties`（`@ConfigurationProperties`） | `calcite.within.*` 配置 | ⚠️ **YAML 列表/嵌套必须用 `@ConfigurationProperties`**，`@Value` 绑不了（既有教训） |
| `web/AnalysisController.within()` | 收 HTTP、参数校验、400/200 的取舍 | 不写 SQL |

**为什么不新建 `WithinController`**：`AnalysisController` 的类注释已经写明"跨轨迹的分析接口都放这里"，
`density` / `similarity` 都在它下面。**再加一个 `within` 是遵循它，不是破坏它。**

**两个类型选择要说明**：
- `geometry` 用 `JsonNode` 而不是强类型 —— **类型是否合法由 `RegionGeometry` 判定**，
  因为要给出"人能看懂的 400 原因"，而不是让 Jackson 抛一句反序列化异常
- `from` / `to` 用 `OffsetDateTime`：JSON body 里走 ISO-8601（`spring-boot-starter-web` 自带 JSR-310 支持）。
  ⚠️ 这与现有 **query 参数**用 `@DateTimeFormat` 是**两条不同的路**，写代码时别照搬错的那条

### 5.2 GeoJSON 解析与校验

`RegionGeometry` 的公开接口（纯函数）：

```java
public record Region(String wkt, int vertexCount, boolean hasBuffer) {}
public static Region parse(JsonNode geometry, Integer bufferM, int maxVertices)
```

职责：
1. 只接受 `Polygon` / `MultiPolygon` / `Point`；其余类型抛 `IllegalArgumentException`（→ 400）
2. 环闭合与最少点数检查（Polygon 外环至少 4 个点且首尾相同）
3. 顶点总数累计（`MultiPolygon` 要把所有环加起来）
4. 纬度/经度越界检查
5. 顶点数超限抛异常
6. 输出**WKT 字符串**（`ST_GeomFromText(:wkt, 4326)` 用）

**为什么中间用 WKT 而不是直接把 GeoJSON 塞进 SQL**：
- 校验必须发生在 Java 侧（要给出**人能看懂的 400 原因**，而不是让 PostGIS 抛裸异常）
- 校验完之后 WKT 是最省事的载体，且和 `ST_GeomFromText` 一一对应

### 5.3 缓冲区怎么算成区域

缓冲区要**两件事**：给查询用、给 `region` 回显用 —— 而它们**是同一个东西**，所以只算一次：

```sql
SELECT ST_AsGeoJSON(ST_Buffer(ST_GeomFromText(:pointWkt, 4326)::geography, :r)::geometry)
```

拿到 GeoJSON 后：`region` 直接返回它；查询用的 WKT 用 `ST_AsText` 一起取回（或由同一个 SQL 返回 WKT 再转）。

⚠️ **`::geography` 在这里是必须的**：不加就是"按度缓冲 500 度"。加了才是"球面 500 米"。
且**只在生成圆的那一次用到 geography**，之后的相交判定全是几何（2.3 的性能来源）。

### 5.4 命中的轨迹 id

```sql
SELECT t.id
FROM track t
WHERE ST_Intersects(t.geom, ST_GeomFromText(:wkt, 4326))
  AND t.start_time <= :to
  AND t.end_time   >= :from
```

- `ST_Intersects` 自带包围盒预筛，实测命中 `idx_track_geom`（2.2）
- `from` / `to` 为空时由 Java 传"无限宽"的边界值（**不要在 native query 里写 `IS NULL` 判断** ——
  可空参数的类型推断很容易出问题，这是 `aggregateDensity` 注释里记着的经验）
- 时间条件用 `idx_track_time (start_time, end_time)`

### 5.5 items 的摘要

`TrackRepository.findSummariesByIds(ids)`（2.8）返回的字段形状**几乎就是 items 要的**
（`id / name / source / pointCount / lengthM / startTime`，且**不水合 `geom`** —— 这点很重要，
水合 246 条 LineString 就是 28.6 万个顶点，热点接口为此付出过 2.4 秒的代价）。

**但它不被复用**：items 还差 `durationS` 与 `endTime`，而 `findSummariesByIds` **不能改**
（它正被相似度接口使用，改它就是拿 M2 的回归去冒险）。

**做法**：新写一个专用查询 `findWithinSummariesByIds(ids)`，**字段形状照抄它**再补两个字段。
好处是以后两个接口的字段口径不会互相牵制。

```sql
SELECT t.id, t.name, t.source, t.point_count, t.duration_s,
       ST_Length(t.geom::geography),
       to_char(t.start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
       to_char(t.end_time   AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
FROM track t WHERE t.id IN (:ids)
```

⚠️ **`IN (:ids)` 的规模**：命中 232 条时参数很多但只有 232 个，没问题；
设计文档 10.2 里"轨迹超过 500 条"那条触发条件这里同样适用（到那时要把 items 也改成 join 而不是传 id 列表）。

### 5.6 区域统计：区域内点数（一次查询拿到总数与每条）

```sql
SELECT p.track_id, count(*) AS inside
FROM track_point p
WHERE p.geom && ST_GeomFromText(:wkt, 4326)
  AND ST_Intersects(ST_GeomFromText(:wkt, 4326), p.geom)
GROUP BY p.track_id
```

- 结果**同时**提供：`stats.pointCount`（各行相加）与每个 item 的 `insidePointCount`
- 实测成本见 2.5（北京大框 171 ms）
- **谓词用 `ST_Intersects` 而不是 `ST_Contains`**：点恰好落在边界上时 `ST_Contains` 为 false，
  而"线穿过"用的 `ST_Intersects` 对边界是 true —— 两者保持一致，避免"点不进去但线穿过了"这种自相矛盾

### 5.7 时间过滤的语义（要写死）

**一个轨迹算"在时间窗内"，当且仅当 `[start_time, end_time]` 与 `[from, to]` 有重叠（含端点）。**

- 对应场景「某区域 **24 小时内**经过了多少条轨迹」——"经过"意味着那段时间它**在路上**
- **不按 `track_point.recorded_at` 过滤**：那会把判定谓词从"线"降级成"点"，
  而点比线稀（采样间距 5–42 米），会出现"线穿过了区域但没有任何点落在里面"的漏判；
  更糟的是**有没有时间过滤会导致两套不同的判定谓词**，结果无法互相解释
- `pointCount` / `stayCount` 的口径**不随时间窗变化**（它们回答"这个区域里有什么"，不是"这段时间里有什么"）

### 5.8 排序与截断

- `items` 排序：**`insidePointCount` 降序 → `trackId` 升序**（后者保证结果与输入顺序无关，可复现）
- `limit` 截断在 **Java 侧**（SQL 里截断就拿不到 `total` 了 —— 这条教训来自相似度接口的 `compared`）
- `stats` 与 `total` **一律全量**

### 5.9 停留点统计（复用缓存）

命中轨迹的停留点：`StayPointCache.get(trackId, () -> stayPointService.detect(points))`，
然后筛出**落在区域内**的（点与多边形判定，用已有的几何判断）。

- ✅ **只对命中轨迹算**，不是全库 —— 所以成本与命中条数成正比，不进"热点接口读 28.6 万点"那条慢路径
- ⚠️ 口径要说明：这是"**命中轨迹在区域内的停留点**"，
  不是"区域内所有轨迹的停留点"（后者要读全库，且会引入热点接口那 2 秒的开销）

---

## 6. 前端设计

### 6.1 第五档「圈选」

`App.vue` 的 `viewMode` 从四档变五档：`[停留点 | 热点 | 密度 | 相似 | 圈选]`。
沿用现有互斥逻辑（五者都往地球上画东西，同时画会糊在一起）。

⭐ 接线点已核实：开关就是一行 `<button>`，每个带 `data-testid="mode-<名字>"`（第 653-686 行），
加第五个按钮是照抄；`frontend/package.json` 的脚本约定是 `"check:<名字>": "node scripts/check-<名字>.mjs"`，
所以 `check:region` 与 `scripts/check-region.mjs` 完全对齐命名惯例。

⚠️ **新增一条要盯的风险**：面板宽度是 `min(420px, 34vw)`，
**第五个按钮 + 圈选档内部的子按钮 / 半径输入 / 统计卡**都会让左上角面板变高变挤；
这个面板**历史上就因为固定高度溢出、点不到内容**（M2 第一阶段修过一次，`z-index` 与 `max-height` 都改过）。
实施时必须在 **1366×660** 与 **1600×600** 两个视口实测零溢出（`.tmp/shot-panel.py` 已有现成脚本）。

进入「圈选」档后，面板出现三个子按钮 + 一个清除：

```
[ 拉框 ] [ 多边形 ] [ 缓冲区 ]        [ 清除 ]
半径 [ 500 ] 米   （200m / 500m / 1km / 2km 四个预设）
```

### 6.2 ⚠️ 绘制模式必须**临时关掉地球的左键旋转**

Cesium 默认 **左键拖动 = 旋转地球**。不关掉的话，用户拉一个框，地球会跟着转，框画得歪七扭八。
`viewer.screenSpaceCameraController.enableRotate`（2.7 已确认该属性存在）在进入绘制模式时置 `false`，
绘制结束 / 取消 / 切档 / 组件卸载时**必须恢复 `true`**。

**这是一条硬要求**：恢复动作要挂在 `onUnmounted` 与"退出绘制"的唯一出口上，
和项目里"实体用固定 id 重绘先删旧"是同一类纪律（**不能有状态泄漏**）。

### 6.3 三种画法

| 画法 | 操作 | 结束条件 | 结束动作 |
|---|---|---|---|
| **拉框** | 按下 → 拖动（实时显示矩形预览）→ 松开 | 松开鼠标 | **松手即查** |
| **多边形** | 单击逐个加点（实时显示已画折线，并回到起点时高亮） | 双击 / 点回起点 | **闭合即查** |
| **缓冲区** | 单击一个中心点（显示一个待定圆点） | 点"查询"按钮 | 用当前半径查询 |

- 画完**自动退出绘制模式并恢复左键旋转**
- `ESC` 取消（清掉半成品，恢复旋转，不查询）
- 三种画法共用同一条"屏幕坐标 → 经纬度"的转换（`camera.pickEllipsoid` / `scene.pickPosition`）；
  **点在球外（返回 undefined）时忽略该次点击**，不要产生 `NaN` 坐标
- 事件注册用 `ScreenSpaceEventHandler`（2.7），**在退出时逐个 `removeInputAction`**，可逆

### 6.4 地图上画什么

1. **区域轮廓**：按后端返回的 `region` 画（黄色描边 + 半透明填充）——**不是**按用户本地画的形状画。
   这是"看到的圈 = 查的范围"这条保证的落点（缓冲区尤其重要）。
2. **命中轨迹**：默认只叠画**列表最前面的 `DRAW_LIMIT = 20` 条**（橙色半透明，宽 2），
   列表里点某一条 → 把它**补画**上去并高亮（复用 `drawSimilarity` 的多线叠加写法）。
   ⚠️ **不能全画**：北京一个中等框就命中 232 条、全库 28.6 万个顶点，一次性画上去会卡。
3. **相机不动**：用户刚画完的区域就在视野里，自动 `flyTo` 只会让人晕。
   （对比：热点档会 `fitBounds`，那是因为热点可能不在当前视野。）

### 6.5 面板内容

- **区域统计卡**（`insidePointCount` 之外的 6 个数字）：命中条数 / 区域内点数 / 累计里程 / 停留点数 / 时间跨度 / 来源分布
- **命中轨迹列表**：名字、来源、点在区域内多少个、里程、时长；
  点一条 → 地图补画 + 高亮；超过 `DRAW_LIMIT` 时提示"地图上只画了前 20 条"
- **截断提示**：`truncated = true` 时显示"共 N 条，列表只显示前 M 条"
- **空结果**：明确显示"**这块区域里没有轨迹穿过**"（不是空白，也不是报错）

### 6.6 组件划分

| 文件 | 职责 |
|---|---|
| `frontend/src/lib/region.js`（**纯计算，零依赖**） | GeoJSON 组装（矩形 4 角 / 点序列 / 闭合）、顶点数与越界自检、统计数字格式化、结果排序与截断的本地镜像 |
| `frontend/src/components/RegionDrawer.vue` | 第五档的子控件：三个画法按钮 + 半径输入与预设 + 清除；只抛事件，不碰 Cesium |
| `frontend/src/components/WithinStats.vue` | 统计卡 + 列表（纯展示，props 进、事件出 —— 对齐 `TrackList` / `StayPointList` 的既有风格） |
| `frontend/src/components/CesiumGlobe.vue`（改） | 新增 `region` / `withinTracks` props 与绘制函数；新增"绘制模式"的开启/关闭与事件处理；新增 `drawing` 状态对外通知 |
| `frontend/src/App.vue`（改） | 第五档接线：绘制状态、请求编排、结果状态、与其它四档的互斥 |

**纪律**（沿用既有约定）：`lib/` 里只放"只用参数就能算出结果"的纯函数，所以能用 node 直接断言；
组件里不发明状态，状态只在 `App.vue` 一份。

### 6.7 清除与取消

- `清除`：清掉区域、命中轨迹、统计、列表，并**清掉选中高亮**（但不动选中轨迹本身）
- 切到别的档：区域与命中痕迹**全部清掉**（与现有四档互斥的纪律一致）
- 数据被改过（管理视图回来）→ 清掉圈选结果（沿用 `App.vue` 现有"数据改动后清空各档结果"的编排）

---

## 7. 参数与默认值

```yaml
calcite:
  within:
    max-vertices: 2000        # 用户手画几何的顶点上限（MultiPolygon 所有环合计）
    default-buffer-m: 500     # 缓冲区默认半径
    max-buffer-m: 50000       # 缓冲区半径上限（50 km）
    default-limit: 50         # items 默认返回条数
    max-limit: 500            # items 条数上限
```

- **为什么 `max-vertices = 2000`**：手画多边形顶点是用户点出来的，正常几十个；
  2000 是防"程序生成的巨型几何"把 SQL 参数撑爆。**服务端生成的缓冲区不受此限**（它固定 33 个顶点，2.6）
- **为什么 `max-buffer-m = 50 km`**：再大就不该用"缓冲区"这个交互了（直接拉框更直观），
  而且 50 km 的圆已经能覆盖北京主城区
- **前端另有一个常量** `DRAW_LIMIT = 20`（地图上默认叠画多少条），它**不是后端参数**：
  它是渲染取舍，不是接口语义

---

## 8. 类的划分：纯逻辑与碰数据库的分开

| 类型 | 类 | 能不能用 JUnit 直接测（不需要数据库） |
|---|---|---|
| 纯计算 | `service/RegionGeometry` | ✅ 能 —— **所有 GeoJSON 校验分支都在这里** |
| 碰数据库 | `service/WithinService` | ❌ 不能（但有 mock 的 repository 就能测编排） |
| HTTP | `web/AnalysisController.within()` | ❌（`AnalysisController` 目前没有任何 `@WebMvcTest`，这是 M2 留下、本轮不还的债） |
| 配置 | `service/WithinProperties` | ✅ 能 |

**对齐既有做法**：`SimilarityMath` / `DensityGrid` 是纯的，`SimilarityService` / `DensityService` 是编排的。
本设计把**所有容易出错的输入校验**放进纯类，正是为了让 `mvn test` 能覆盖到它们。

---

## 9. 测试与验收

### 9.1 四层（与 M2 各阶段一致）

| 层 | 命令 | 需要什么在跑 |
|---|---|---|
| 后端 JUnit | `mvn test` | 什么都不需要（不需要数据库） |
| 前端 node | `npm run check:region` | 什么都不需要 |
| 接口对拍 | `.tmp/verify-within-api.py` | 后端 8080 + 数据库 |
| 浏览器像素/交互 | `.tmp/check-within.py`（Playwright + Pillow） | 后端 8080 + 前端 5173 |

### 9.2 后端 JUnit（新增 `RegionGeometryTest`，预计 ~20 项）

- 合法矩形 / 多边形 / MultiPolygon / Point+bufferM 各自解析成功，WKT 正确
- 环未闭合 → 异常；环点数 < 4 → 异常；`geometry` 缺 `type` → 异常
- 类型不在白名单（`LineString` / `Feature` / 乱写）→ 异常
- 纬度 91 / 经度 181 → 异常
- 顶点数 = `max-vertices` 通过、+1 拒绝（**边界值两侧都要测**）
- `Point` 没给 `bufferM` → 异常；`bufferM = 0` / 负数 / `NaN` → 异常
- MultiPolygon 的顶点数是**所有环之和**（防漏算）

`WithinServiceTest`（mock 仓库，预计 ~8 项）：排序（`insidePointCount` 降序 → `trackId` 升序）、
`limit` 截断后 `truncated` 正确、空结果返回全 0 统计、`from/to` 的传参（空值变成无限宽边界）。

### 9.3 前端 node `check:region`（预计 ~15 项）

矩形四角顺序与闭合、点序列转 GeoJSON、MultiPolygon/单环的包装、
统计数字格式化（`null` 不能显示成 `0` —— **`Number(null) === 0` 这个坑项目里踩过**）、
列表排序与 `DRAW_LIMIT` 截断的本地镜像、空结果文案。

### 9.4 接口对拍 `.tmp/verify-within-api.py`（预计 ~30 项）

⭐ **判据一律从 SQL 取真值，不写死数字**（M2 各阶段反复踩的教训：导一次数据就废一片脚本）。

- 用 psql 算出同一块区域的**期望**：命中 id 集合、区域内点数、按来源分组
- 与接口返回**逐项对拍**：集合相等、统计相等、`total == len(items) + 被截断数`
- 三组区域各测一遍：**北京大框**（命中多、走顺序扫描）、**上海小圆**（命中 1 条、走索引）、
  **空区域**（200 + 0）
- `region` 回显：缓冲区的 `region` 是**多边形**且顶点数 = **33**；面积与 `πr²` 的相对误差 < 1%
- 400 分支逐条打：非法类型、环未闭合、顶点数超限、`Point` 无 `bufferM`、`bufferM = 0`、
  `from > to`、`limit = 0` 与 `limit = 501`
- ⚠️ **已知边界用例**：那 3 条含超长边的轨迹（121/161/166）——用 `(118.95, 35.66)` + 1.5 km 缓冲区
  断言"**返回 3 条**"，并在注释里写明"这 3 条是平面解释的产物，见设计文档 3.4"。**这是有意钉住的，不是 bug。**

### 9.5 浏览器验收 `.tmp/check-within.py`（预计 ~15 项）

用真实时间等待（**不要用 `--virtual-time-budget`** —— Cesium 的异步几何体在虚拟时钟下不完成）：

- 进入第五档 → 三个子按钮存在
- 拉框：按住拖动松开 → 统计卡出现且**与接口返回一致**
- 多边形：点 4 个点 + 双击 → 同上
- 缓冲区：点一个中心 + 改半径 → 图形变化（区域多边形像素数随半径增大）
- **绘制模式期间左键拖动不旋转地球**（对比绘制前后同一拖动的相机坐标变化）
- 退出绘制 / `ESC` / 切档后**左键旋转恢复**（读 `enableRotate`）
- 区域轮廓与命中轨迹像素存在（从 DOM + 像素统计，坐标不写死）
- 空区域时显示"没有轨迹穿过"且**控制台零报错**

### 9.6 回归（不能退化的基线）

| 套件 | 当前基线 |
|---|---|
| 后端 `mvn test` | **133** |
| 前端 node（playback 17 / chart 37 / hotspot 25 / density 25 / similarity 19 / data-edit 11） | **134** |
| 浏览器与接口脚本 | 11 个全绿 |

本阶段净增：后端 ≈ +28、前端 node ≈ +15、新增两个 Python 脚本（≈ +45 项断言）。
**跑浏览器验收必须后端 8080 + 前端 5173 同时运行**；Vite 与 Playwright 在沙箱内需提权 `danger-full-access`。

---

## 10. 已知限制与明确不做的事

| 项 | 说明 |
|---|---|
| **平面 vs 球面的分歧** | 只影响 3 条含超长边的轨迹（121/161/166），最大 11.7 km。见 3.4，**有意不修**，用测试钉住 |
| **区域内点数统计走顺序扫描** | 286k 行时 171 ms。**不优化**：优化器认为全表更划算，M2 密度阶段已有同样结论 |
| **停留点是"命中轨迹的"** | 不是"区域内所有轨迹的"（后者要读全库 28.6 万点，等于把热点接口 2 秒的开销搬进来）。见 5.9 |
| **不保存区域** | 无区域档案、无命名、无历史记录（YAGNI） |
| **无区域导出** | 不提供 GeoJSON 下载（设计文档没要求） |
| **无多区域叠加** | 一次只有一块区域 |
| **地图默认只画前 20 条** | 命中 232 条全画会卡；统计仍是全量 |
| **不做区域内的深度指标** | 限速、爬升、区域内的极值 —— 都不是本阶段要回答的问题 |

---

## 11. 关键决策记录

### 11.1 为什么一个接口吃三种形状（GeoJSON），而不是三种参数
三种形状的后端判定**本来就是同一个谓词**（线和多边形相交），分三套参数只会带来三套分支。
GeoJSON 是 Web GIS 的通用语言，以后要加"导入一块区域文件"不用改接口。
代价是解析与校验要自己写 —— 这部分被隔离在纯类 `RegionGeometry` 里，可以直接单测。

### 11.2 ⭐ 为什么缓冲区要算成多边形，而不是用 `ST_DWithin`
**这是本轮最重要的一次实测更正**（2.3）。直觉上"缓冲区 = 距离判断"，
但实测：`ST_DWithin(geom::geography, ...)` **303 ms** 且顺序扫描，
而"球面缓冲成多边形 + 几何相交" **7.9 ms**、命中索引。
瓶颈不是扫表，是**对每条候选轨迹的每个顶点算椭球距离**（北京有 228 条候选，粗筛减不掉）。
副产品：后端真的只剩一条代码路径，且 `region` 回显天然正确。

### 11.3 为什么不用平面度数 `ST_DWithin`
4.5 ms 但答案是错的（222 vs 225）。"度"在经度方向要乘 `cos(纬度)`，北京差 23%。**快而错没有讨论余地。**

### 11.4 为什么 `region` 要回显
否则"用户画的圈"与"后端查的区域"是两份独立计算 —— 缓冲区尤其容易算出不一致的圆。
回显之后，**前端画的永远是后端真正用过的那个几何**，"看到的 = 查到的"成为结构上的保证，而不是纪律。

### 11.5 为什么时间过滤按"轨迹时段重叠"，而不是按点的时间
见 5.7：按点过滤会把判定谓词从"线"降级成"点"（漏判），
并且会变成"有没有时间过滤 = 两套判定谓词"，结果无法互相解释。
"重叠"也更贴合场景语义（"24 小时内经过"= 那段时间在路上）。

### 11.6 为什么不改 `findSummariesByIds` 而是新写一个
它正被**相似度接口**使用（M2 已交付、有 19 项 node + 35 项对拍断言钉着）。
为了两个字段去改它，等于拿 M2 的回归换一点代码复用。**新写一个专用查询更便宜。**

### 11.7 为什么地图只画前 20 条而统计是全量
两者回答不同的问题："这块区域里有什么"（统计，必须准）与"让我看一眼长什么样"（渲染，可以采样）。
232 条全画 = 28.6 万个顶点一次性上屏。**把渲染取舍和接口语义分开**，接口不做截断以外的丢弃。

### 11.8 为什么相机不自动飞
用户刚画完的区域就在视野中央。自动 `flyTo` 会把画面挪走，属于"帮倒忙"。
（热点档需要 `fitBounds` 是因为热点可能在视野外，情况不同。）

### 11.9 为什么不还 M3-START-HERE 里列的那几笔欠账
经用户明确决定：**M3 只做主线**。欠账（热点提速、HTTP 层测试、删除失败不带原因、补数据）
各有各的回归风险，混进来会让"这一阶段改了什么"说不清。**它们记在文件里，不会丢。**

---

## 12. 路网匹配可行性评估（M3 第三件事）

> 总设计文档第 412 / 493 行把这件事标为「技术难度过高，**M3 之后再评估**」。
> 本节就是那次评估的**结论**。**结论：不实现。**
>
> 本节是**自洽的完整结论**；更详细的调研底稿（含各引擎的默认参数与逐条依据）另存一份：
> `docs/map-matching-assessment.md`。

### 12.1 结论：**不建议做**

1. **前置空缺太大** —— 本项目**零路网数据、零路由依赖、无 pgRouting**
   （实测：库内只有 `track` / `track_point` / `stay_point` 三张业务表，
   扩展只有 `postgis` / `btree_gist` / `plpgsql`，`pom.xml` 里没有任何路由图依赖）。
   即便只做北京 bbox，也要走"下全国 OSM 包（**1.6 GB**）→ 抽取路段 → 导入 PostGIS（再膨胀 2~3 倍）→ 建索引"，
   **一周以上**才到"还没开始匹配"的起跑线。
2. **数据形态与算法假设不匹配**（用本项目实测数字对照，见 2.1）：
   - 采样间隔 **5~42 米**对主流引擎属于低频 —— Valhalla 默认 `search_radius` 50 m
     （上限 100 m）、OSRM `/match` 默认只有 **5 m**，都是按"1 秒级密集采样"设计的
   - **3 段 >1000 km 的记录跳跃**会被强制断链（Valhalla `breakage_distance` 默认 2000 m；
     OSRM 遇时间戳大跳变会自动 split）→ **一条轨迹被切成几段 sub-trace**，
     与本项目"整条轨迹"的语义（回放、曲线、停留点都以整条为单位）直接冲突
   - **已标记的 GPS 漂移点**漂移量常超过 50~100 m 搜索半径 → 被判"找不到候选路段"而丢弃；
     强行放大半径会匹配到错误道路，**制造假数据**
3. **对现有能力零增益** —— 回放 / 速度海拔曲线 / 停留点 / 热点 / 网格密度 / 相似度 / 圈选，
   **没有一个消费匹配结果**；它只能做成一个孤立的新页面，而不是给既有功能加分。
   12 周项目的收尾阶段，投入产出不成立。

### 12.2 唯一"没坑"的一环

坐标系 **WGS84 直通**（本项目已实测确认无需 GCJ-02 转换），与 OSRM / Valhalla / mappymatch 的输入要求一致。
但逐点匹配必须做成**后端离线跑批 + 结果落库**，不是页面点一下能出结果。

### 12.3 如果将来要做：轻量替代（1~3 天）

| 做法 | 内容 | 成本 |
|---|---|---|
| 点到最近道路距离 | bbox 内主干道入 PostGIS 建 GIST，`ST_Distance` 出"偏离道路距离分布"指标 | ~1 天 |
| 路网可视化 + 吸附示意 | Cesium `GeoJsonDataSource` 叠主干道，把点投影到最近线段（示意级，不严谨但演示够） | ~1 天 |
| 一次性离线演示 | 本地起 OSRM，对一条北京轨迹跑一次 `/match?tidy=true&gaps=split`，结果存表直接回放 | ~1 天 |

三者共同点：**只碰"距离 / 可视化 / 一次性结果"，不碰"可靠性、前后一致性、批量重算"。**

### 12.4 如果将来要做完整版：最小可行版本（≈ 4~5 天）与前置条件

1. **先补数据**：只导**轨迹 bbox 内的 motorway~tertiary** 路段，入 PostGIS 建 GIST 索引
   （目标：路段数万级、几百 MB 以内），坐标系直接 4326
2. **先补数据质量**：在库里把 **3 段超长跳跃显式切成子轨迹**、把已标记的漂移点排除出匹配集合
   —— **这一步不做，匹配结果一定不可解释**
3. **不自研 HMM**：起 OSRM `match`，`radiuses` 放宽到 50~100 m、`gaps=split`、`tidy=true`，
   **离线批处理** 246 条（预计数小时），结果落一张 matched 结果表
4. **前端只做一件事**：Cesium 三层叠加（路网 + 原始轨迹 + 吸附后折线）+ 每条的匹配置信度与丢弃点数

⚠️ 真正的风险不在代码，而在"**跑完发现一半轨迹的匹配质量很差**"。

### 12.5 主流路线的工作量量级（供将来参考）

| 路线 | 代表 | 量级 |
|---|---|---|
| 自研 HMM | 隐马尔可夫 + Viterbi | ≈ 3~4 周，且真正的工作量在**路网数据管道**而不是算法 |
| 开源引擎自带匹配 | OSRM `/match`、Valhalla Meili、GraphHopper | ≈ 1~2 周（都要先自建路网图） |
| 算法库 | mappymatch（NREL）、leuvenmapmatching、barefoot | ≈ 1~2 天（**前提是已有路网**） |

### 12.6 参考来源

[OSRM Match API](https://project-osrm.org/docs/v5.24.0/api/) ·
[Valhalla Meili 配置](https://valhalla.github.io/valhalla/contributing/architecture/meili/configuration/) ·
[mappymatch（NREL）](https://mappymatch.readthedocs.io/en/stable/) ·
[Geofabrik 中国抽取](https://download.geofabrik.de/asia/china.html) ·
[BBBike 中国抽取（含体积实测）](https://data.bbbike.org/osm/region/asia/china/)

> 调研过程遵守本项目的 GitHub 隔离规则：**全程未访问任何 GitHub 页面**，未读取 issue / PR / 评论等用户生成内容。
> ⚠️ 诚实标注：「中国/北京路段总数」**没有查到权威数字**，12.1 里只给了公开资料的数量级（百万级 ways），没有编造精确值。

---

## 附录 A · 对总设计文档的影响

| 总设计文档原文 | 本设计的处理 |
|---|---|
| 第 134 行「空间范围查询：画矩形 / 多边形 / 缓冲区，查出穿过的轨迹」 | ✅ 本设计实现（三种形状都做，见 6.3） |
| 第 357 行 `POST /api/analysis/within` | ✅ 沿用该路径与 POST 方法（4 节） |
| 第 30 行场景 5「有没有经过某条河以东的区域？」 | ✅ 这是本功能要回答的问题 |
| 第 439-441 行 M3 验收「能在地图上画多边形，查出穿过的轨迹」 | ✅ 成功标准第一条 |
| 第 453 行 M3 学习配套「空间查询优化（`EXPLAIN ANALYZE`）」 | ✅ 第 2 节就是实测作业，结论在 3.2 |
| 第 138 行「分析结果叠加到三维地球：热力图、缓冲区、区域统计」 | ✅ 热力图=M2 密度、缓冲区=本设计、区域统计=本设计 |
| 第 412 / 493 行「路网匹配：M3 之后再评估」 | ✅ 第 12 节给出结论 |
| 第 358 行 `GET /api/analysis/similarity` 列在 M3 接口表 | ⚠️ **已在 M2 第四阶段提前完成，本轮不重做**（总设计文档已在第 135-137 行注明） |
| 第 359 行 `GET /api/analysis/density` 列在 M3 接口表 | ⚠️ **已在 M2 第三阶段提前完成，本轮不重做** |

---

## 附录 B · 本阶段的文件清单（预期）

**后端（新增）**

```
backend/src/main/java/com/calcite/
├── web/dto/WithinRequest.java            请求体（record）
├── web/dto/WithinResponse.java           响应（record，内嵌 Stats / Item / Params）
├── service/RegionGeometry.java           ⭐ 纯计算：GeoJSON 校验 → WKT、顶点数、越界
├── service/WithinService.java            编排：region → id → items → 统计 → 截断
└── service/WithinProperties.java         calcite.within.* 配置
```

**后端（改动）**

```
backend/src/main/java/com/calcite/
├── web/AnalysisController.java           加 within() 端点 + 400 分支
├── repository/TrackRepository.java       加 findWithinSummariesByIds（不改 findSummariesByIds）
└── repository/TrackPointRepository.java  加 countPointsInsideGrouped（对齐 aggregateDensity 的写法）
backend/src/main/resources/application.yml 加 calcite.within.*
```

**后端（测试）**

```
backend/src/test/java/com/calcite/service/
├── RegionGeometryTest.java               ~20 项（所有校验分支 + 边界值）
└── WithinServiceTest.java                ~8 项（排序 / 截断 / 空结果 / 时间参数）
```

**前端（新增）**

```
frontend/src/
├── lib/region.js                         ⭐ 纯计算：GeoJSON 组装、格式化、排序截断镜像
├── components/RegionDrawer.vue           三个画法按钮 + 半径输入 + 清除
└── components/WithinStats.vue            统计卡 + 命中轨迹列表
frontend/scripts/check-region.mjs         ~15 项 node 断言
```

**前端（改动）**

```
frontend/src/components/CesiumGlobe.vue   region / withinTracks 图层 + 绘制模式（enableRotate 开关）
frontend/src/App.vue                      第五档接线 + 请求编排 + 与四档互斥
frontend/package.json                     加 check:region 脚本
```

**验收脚本（`.tmp/`，已 gitignore，需 `git add -f`）**

```
.tmp/verify-within-api.py                 ~30 项接口对拍（真值从 SQL 取）
.tmp/check-within.py                      ~15 项浏览器验收（Playwright 真实等待）
```

**文档**

```
docs/superpowers/specs/2026-09-25-m3-within-design.md   本文件
docs/superpowers/plans/2026-09-25-m3-within.md          实施计划（下一步）
_session_context.md                                     收工时同步
```
