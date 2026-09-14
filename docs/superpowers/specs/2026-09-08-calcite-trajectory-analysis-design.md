# Calcite 设计文档：GPS 轨迹时空分析平台

> **一句话定位**：把 GPS 轨迹数据存进 PostGIS，用空间索引和空间函数做时空分析，再在 Cesium 三维地球上按时间轴回放，并把分析结果叠加到地球上。

---

## 零、三分钟看懂 Calcite（小白导读）

### 一个具体场景

小明骑车上班，手机每秒记一个点：

```
19:00:00  39.9847, 116.3184
19:00:05  39.9849, 116.3188
19:00:10  39.9852, 116.3191
... 一共 5000 个点
```

这 5000 个点直接存进数据库，其实**什么也不是**——就是一堆数字。

**Calcite 要做的事，就是让这堆数字能回答下面这些问题：**

| # | 问题 | 技术名词 |
|---|---|---|
| 1 | 几点出发、几点到？走了多远、平均多快？ | 统计 |
| 2 | 在哪里停了 20 分钟？那是公司还是早餐店？ | 停留点识别 |
| 3 | 早高峰哪些路段骑车的人最多？ | 热点分析 |
| 4 | 周一和周二走的路线是同一条吗？ | 轨迹相似度 |
| 5 | 有没有经过某条河以东的区域？ | 空间范围查询 |

### 三个技术分别干什么

| 技术 | 在这件事里的角色 | 大白话 |
|---|---|---|
| PostgreSQL + PostGIS | 存点、算距离、判范围、建索引 | 一个**会算地理**的数据库 |
| SpringBoot | 把数据库能力做成网页能调用的接口 | **中间人**，前端要数据它去拿 |
| Vue + Cesium | 在三维地球上画轨迹、拖时间轴回放 | **画布**，把数据变好看 |

### 数据从哪来

| 来源 | 说明 | 必须吗 |
|---|---|---|
| GeoLife 公开数据集 | 微软收集的北京真实 GPS 轨迹（182 人 / 5 年 / 约 2400 万点） | ✅ **主数据** |
| 上传 GPX / CSV | 网页上传自己的轨迹文件 | 可选 |
| 自己的跑步记录 | 有就用，**没有完全不影响** | 可选 |

### 你不需要现在就懂

这份文档是**路标**，写给三个月后的你。现在只要记住一句话：

> 我们要做一个网站：**能在地球上回放轨迹，并回答上面那 5 个问题。**

每一步具体怎么做，动手前我会单独讲清楚，讲到你能听懂为止。

---

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0 |
| 日期 | 2026-09-08 |
| 状态 | 已评审通过（第 1-5 节逐节确认） |
| 项目定位 | 个人项目 · 兴趣驱动的技术实践 |
| 方向 | GIS / 时空数据开发 |
| 技术栈 | SpringBoot 3.5.16 · PostgreSQL 18.3 + PostGIS 3.6.2 · Vue 3.5 + Vite 8 · Cesium |
| 交付周期 | 12 周（2026-09 起） |
| 主数据源 | 公开轨迹数据集（GeoLife / T-Drive），辅以 GPX / CSV 导入接口 |

---

## 一、项目定位

### 1.1 Calcite 是什么

Calcite 是一个**轨迹时空分析平台**。它做三件事：

1. **收进来**——把散乱的 GPS 轨迹（GPX / CSV / 公开数据集）解析、清洗、存入 PostGIS
2. **算出来**——用空间索引和 `ST_` 空间函数回答"谁、在哪、什么时候、多久、多密集"这类问题
3. **看出来**——在 Cesium 三维地球上按时间轴回放轨迹，并把分析结果（热区、缓冲区、停留点）叠加展示

### 1.2 它解决什么问题

原始的 GPS 数据只是**一堆"经纬度 + 时间"的点**，本身没有价值。价值在于它能回答的业务问题：

| 业务问题 | 需要的空间 / 时间能力 |
|---|---|
| 这个人在这片区域停留了多久？ | 距离计算 + 时间窗口 |
| 某区域 24 小时内经过了多少条轨迹？ | 空间范围查询 + 时间过滤 |
| 哪几条轨迹走的路线几乎一样？ | 轨迹相似度 / 空间比对 |
| 这条轨迹哪一段最慢、堵在哪里？ | 时间分段 + 速度统计 |
| 这个地铁站周边 1 公里内轨迹有多密集？ | 缓冲区 + 密度统计 |

这些问题的共同点：**必须同时用上"空间"和"时间"**。这正是 PostGIS 时空索引存在的理由，也是时空数据开发里最常见的场景。

### 1.3 名字的含义

方解石（Calcite）是晶体矿物——**把杂乱无章的东西结晶成规则结构**。对应到项目：把散乱的 GPS 点，组织成有结构、能回答问题的时空数据。

### 1.4 这个项目能练到什么

做完这个项目，应该能说清楚三件事：

1. **会用空间数据库**——不是把 PostGIS 当 MySQL 用，而是真的用了空间索引和 `ST_` 函数
2. **懂时空查询**——能说清"为什么这个查询要建 GiST 索引""时空联合查询怎么优化"
3. **能把数据变成产品**——三维可视化不是贴图，是能交互、能讲业务含义的

---

## 二、功能范围与里程碑

总周期 12 周，分四个里程碑。**每个里程碑都是一个可演示的完整状态。**

### M1 看得见（第 1-3 周）

- 轨迹导入：（✅ 2026-09-12 完成，见 `2026-09-12-m1-import-design.md`）
  - `POST /api/tracks/import` 支持 **GPX** 文件上传
    —— CSV 暂不做：没有真实数据源会用它，格式还得自己拍；解析器接口已就位，以后加一个类即可
  - GeoLife 数据集批量导入（`.plt` 解析器 + 分批插入）—— `POST /api/import/geolife`
- 轨迹列表 + 详情（距离、时长、点数）
- **Cesium 三维回放**：时间轴拖动，模型沿轨迹移动，配速度 / 海拔曲线

> 里程碑意义：第 3 周即可录屏演示。

### M2 算得出（第 4-7 周）

- 停留点识别（空间距离 + 时间阈值）
- 轨迹统计：总距离、均速、最高速、累计爬升
- 热点区域分析：按固定边长网格统计轨迹点密度（`ST_SnapToGrid`），输出网格热力数据

> 里程碑意义：从"播放"升级为"分析"。

### M3 讲得透（第 8-11 周）

- 空间范围查询：画矩形 / 多边形 / 缓冲区，查出穿过的轨迹
- 轨迹相似度比对：`ST_FrechetDistance`（PostGIS 内置），返回距离值 + 归一化相似度
- 分析结果叠加到三维地球：热力图、缓冲区、区域统计

> 里程碑意义：PostGIS 空间函数真正上场，这个阶段技术密度最高。

### M4 收尾（第 12 周）

- README + 架构图 + 部署文档 + 演示数据集
- 技术要点自检：每个技术点准备"为什么这么做、不用它行不行"

---

## 三、数据模型与空间存储

### 3.1 三张核心表

| 表 | 一行代表什么 | 说明 |
|---|---|---|
| `track` | 一条轨迹（一次出行） | 元数据 + 轨迹线 |
| `track_point` | 一个 GPS 点 | 原始真相，数据量最大 |
| `stay_point` | 一次停留 | M2 阶段由分析算法生成 |

### 3.2 表结构

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- 轨迹
CREATE TABLE track (
  id          BIGSERIAL PRIMARY KEY,
  name        VARCHAR(200) NOT NULL,
  source      VARCHAR(20)  NOT NULL,        -- geolife | gpx | csv
  external_id VARCHAR(100),                 -- 原始数据集里的编号
  start_time  TIMESTAMPTZ  NOT NULL,
  end_time    TIMESTAMPTZ  NOT NULL,
  distance_m  DOUBLE PRECISION,
  duration_s  INTEGER,
  point_count INTEGER,
  geom        GEOMETRY(LineString, 4326),   -- 由点生成的轨迹线
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 轨迹点
CREATE TABLE track_point (
  id          BIGSERIAL PRIMARY KEY,
  track_id    BIGINT      NOT NULL REFERENCES track(id) ON DELETE CASCADE,
  seq         INTEGER     NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL,
  elevation_m DOUBLE PRECISION,
  speed_mps   DOUBLE PRECISION,
  geom        GEOMETRY(Point, 4326) NOT NULL
);

-- 停留点（M2 生成）
CREATE TABLE stay_point (
  id          BIGSERIAL PRIMARY KEY,
  track_id    BIGINT      NOT NULL REFERENCES track(id) ON DELETE CASCADE,
  start_time  TIMESTAMPTZ NOT NULL,
  end_time    TIMESTAMPTZ NOT NULL,
  duration_s  INTEGER     NOT NULL,
  radius_m    DOUBLE PRECISION,
  geom        GEOMETRY(Point, 4326) NOT NULL
);

-- 索引（性能关键）
CREATE INDEX idx_track_point_st  ON track_point USING GIST (geom, recorded_at);  -- 时空联合
CREATE INDEX idx_track_point_seq ON track_point (track_id, seq);
CREATE INDEX idx_track_geom      ON track USING GIST (geom);
CREATE INDEX idx_track_time      ON track (start_time, end_time);
CREATE INDEX idx_stay_point_st   ON stay_point USING GIST (geom, start_time);
```

### 3.3 四个设计决策

**① 为什么存 `geometry` 而不是 `geography`？**

存储用 `geometry(Point,4326)`——紧凑、函数齐全；**需要米制结果时显式转换**。实测数据见附录 A：4326 下的 `ST_Distance` 返回的是**度数**（0.00161），直接当米用会差 5 个数量级。

**② 为什么是 `GIST (geom, recorded_at)` 而不是两个单独索引？**

业务查询永远是"某区域 + 某时间段"同时出现。联合索引把空间和时间做成一个多维边界框，一次索引扫描同时过滤两个条件——这就是"时空索引"的实质。已实测可建（附录 A）。

**③ 为什么既存点又存线？**

点 = 原始数据（不可篡改的真相）；线 = 派生数据（为查询和渲染服务）。线由点生成：

```sql
ST_MakeLine(geom ORDER BY recorded_at)
```

**④ 为什么高程 / 速度是普通列，不塞进 Z/M 维度？**

因为要能直接 `WHERE speed_mps > 5`、`ORDER BY elevation_m`。塞进几何维度后这类查询会非常别扭。

### 3.4 数据量预估与策略

- GeoLife 数据集：182 个用户、约 1.7 万条轨迹、约 2400 万个点
- **策略：先导入 5-10 个用户**（约百万点级），既体现数据规模，又能在普通电脑上流畅运行
- 数据量继续增长时的应对：分区表、BRIN 索引、轨迹抽稀、冷热分离

> 这本身就是个值得展开的点："数据量涨到千万级时你怎么处理"。

---

## 四、系统架构与接口设计

### 4.1 整体架构

```
┌──────────────────────────────────────────────┐
│  浏览器   Vue 3 + Vite + Cesium              │
│  ├─ 轨迹列表 / 详情                           │
│  ├─ Cesium 三维地球 + 时间轴回放              │
│  └─ 图表：速度 / 海拔曲线                     │
└────────────────┬─────────────────────────────┘
                 │  REST / JSON（Vite proxy: /api → :8080）
┌────────────────▼─────────────────────────────┐
│  SpringBoot 3.5（端口 8080）                 │
│  ├─ Controller  接口层                        │
│  ├─ Service     业务逻辑 / 分析算法           │
│  └─ Repository  数据访问                      │
│       ├─ Spring Data JPA  → 普通 CRUD         │
│       └─ 原生 SQL         → ST_ 空间函数      │
└────────────────┬─────────────────────────────┘
                 │  JDBC（HikariCP）
┌────────────────▼─────────────────────────────┐
│  PostgreSQL 18 + PostGIS 3.6（端口 5432）    │
└──────────────────────────────────────────────┘
```

### 4.2 代码结构

**后端**（按业务分模块，不按技术分层）

```
com.calcite
├── CalciteApplication.java        ← 已有
├── domain/                        ✅ 已有：实体（数据库表的 Java 影子）
│   ├── Track.java
│   └── TrackPoint.java
├── repository/                    ✅ 已有：持久层（方法名即 SQL）
│   ├── TrackRepository.java
│   └── TrackPointRepository.java
├── service/                       ✅ 已有：业务逻辑层（M1 导入功能引入）
│   ├── GeoUtils.java              球面距离（Haversine）
│   ├── TrackCleaner.java          **所有清洗规则只此一处**
│   ├── CleanedTrack.java
│   ├── ImportService.java         导入编排：识别 → 解析 → 清洗 → 入库
│   └── importer/                  可插拔解析器
│       ├── Importer.java          接口
│       ├── RawPoint.java          三种格式统一输出的中间结构
│       ├── ParsedTrack.java
│       ├── FormatDetector.java    按【内容】识别格式（不看扩展名）
│       ├── GpxImporter.java       JDK DOM，零新依赖
│       └── GeoLifeImporter.java   .plt（海拔英尺 → 米）
├── config/                        ✅ 已有：配置绑定
│   └── ImportProperties.java      @ConfigurationProperties（YAML 列表必须用它）
├── web/                           ✅ 已有：接口层
│   ├── HealthController.java
│   ├── TrackController.java
│   ├── ImportController.java
│   └── dto/                       TrackSummary / TrackDetail / TrackPointDto / ImportResult
└── analysis/                      ← M2 / M3 待建
    ├── StayPointService.java      停留点识别
    ├── HotspotService.java        热点分析
    └── SimilarityService.java     轨迹相似度
```

> **分包方式的修订（2026-09-12）**：本文档原规划**按功能分包**（`track/` / `importer/` / `analysis/`），
> M1 实现时实际采用了**按层分包**（`web/` / `service/` / `repository/` / `domain/` / `config/`）。
>
> 理由：① 类还少时按层分包更好理解；② 已产出的《项目结构地图》画的也是这套，改分包会让已学内容作废；
> ③ 按功能分包一般是等类多到按层包过于拥挤时才转 —— 那是一次**以后可以做的重构，不是现在**。
>
> 详见 `2026-09-12-m1-import-design.md` 第三节。

现有 `HealthController` 迁至 `common/`，保留为健康检查。

**前端**

```
frontend/src
├── main.js
├── App.vue                  ← 已有
├── api/
│   └── track.js             接口封装（fetch / axios）
├── components/
│   ├── CesiumGlobe.vue      三维地球容器（Cesium Viewer 初始化）
│   ├── TrackList.vue        轨迹列表
│   ├── TrackPlayer.vue      时间轴回放控制
│   └── SpeedChart.vue       速度 / 海拔曲线
└── views/
    ├── TrackDetail.vue      轨迹详情页
    └── AnalysisPanel.vue    分析面板（M2 / M3）
```

### 4.3 接口清单

**M1（第 1-3 周）**

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/tracks/import` | 上传 GPX / CSV 文件，返回 track id |
| GET | `/api/tracks` | 轨迹列表（分页） |
| GET | `/api/tracks/{id}` | 轨迹详情 |
| GET | `/api/tracks/{id}/points?simplify=0.0001` | 轨迹点，支持抽稀，供 Cesium 渲染 |

**M2（第 4-7 周）**

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/tracks/{id}/stats` | 距离、均速、爬升、时间跨度 |
| GET | `/api/tracks/{id}/stay-points` | 停留点列表 |
| GET | `/api/analysis/hotspots` | 指定时间窗内的热点网格 |

**M3（第 8-11 周）**

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/analysis/within` | 传多边形 / 缓冲区，返回穿过的轨迹 |
| GET | `/api/analysis/similarity` | 两条轨迹的相似度 |
| GET | `/api/analysis/density` | 区域密度统计 |

### 4.4 四个必须提前想清楚的技术点

**① 数据量：接口为什么要有 `simplify` 参数**

一条轨迹可能有上万个点，前端全量渲染会卡死。后端存全量，返回时按需抽稀（`ST_SimplifyPreserveTopology`），放大地图时再请求细节。

**② 大批量导入：不能一次性读进内存**

千万级点必须流式解析 + 批量插入（每 1000 条 flush 一次）。

**③ 坐标系：中国地图的 GCJ-02 偏移**

- GeoLife 是 **WGS84**（与 Cesium 一致）→ 直接可用
- 高德 / 腾讯 POI 是 **GCJ-02**（火星坐标），叠加会偏移数百米
- ✅ **vivo 健康数据已实测确认为 WGS84**（2026-09-12）
  - 验证方法：取轨迹中心 `25.0336, 117.0209`，用 OpenStreetMap 数据反查 → 命中「**东区操场**」（龙岩市 · 同心路）
  - 再取 OSM 上该操场的自身坐标 `25.033514, 117.020893`，与我们的点相差 **10 米**
  - 判据：若数据是 GCJ-02 而当成 WGS84 用，福建地区会偏 **400–600 米**，该点会直接飘出操场
  - 结论：**无需任何坐标转换**
- 坐标转换话题能立刻区分"做过真项目"和"只跑过 demo"

**④ 真实 GPS 数据的脏值：异常速度怎么处理**

实测样本（用户那份 2342 点的校园跑）里有 **4 段速度超过 8 m/s，最高 12.13 m/s（43.7 km/h）**
—— 人跑不出这个速度，这是 **GPS 漂移**。

处理方式（2026-09-12 定案）：**存下来 + 标记**，而不是丢弃。

- `track_point` 表增加 `is_outlier BOOLEAN NOT NULL DEFAULT false`
- 判定用**自适应阈值**：`速度 > max(8 m/s, 3 × 该轨迹速度中位数)`
  - 为什么不用固定阈值：GeoLife 里有**汽车（20 m/s）甚至火车（80 m/s）**的轨迹，
    固定 8 m/s 会把它们全部误标成异常
  - 中位数会自适应轨迹类型：跑步轨迹中位数 1.6 → 阈值 8；汽车轨迹中位数 12 → 阈值 36
- 异常段**两端都标记**（无法判断是哪一端漂了，宁可多标不可漏标）
- 实测效果：2342 点里**精确标记 8 个**（seq = 1128, 1129, 1135, 1136, 1144, 1145, 1585, 1586），占 0.34%

另：**海拔整条全同 → 全部存 NULL**。实测样本 `ele` 全是 `0.0`（vivo 没记录海拔），
存 0 会让前端画出一条贴底直线误导人；前端已有「这条轨迹没有海拔数据」的降级显示。

---

## 五、边界、风险与验收标准

### 5.1 明确不做的事

| 不做 | 原因 |
|---|---|
| 用户注册 / 登录 / 权限 | 本项目是单机自用，不需要多用户体系 |
| 实时轨迹推流 | 另一套技术栈（WebSocket + 消息队列），会拖垮进度 |
| 多租户 / SaaS 化 | 与项目目标无关 |
| 移动端 App | 网页足够演示 |
| 路网匹配（Map Matching） | 技术难度过高，M3 之后再评估 |
| 全量导入 GeoLife（2400 万点） | 先导入 5-10 个用户，够体现规模 |

> 个人项目的失败往往不是做得太少，而是什么都想做、最后什么都做不完。

### 5.2 风险与应对

| 风险 | 应对 |
|---|---|
| GeoLife 下载或 `.plt` 格式解析卡住 | 先用 CSV 导入跑通全链路，GeoLife 作为并行任务 |
| Cesium 渲染卡顿 | 抽稀 + 按需加载；必要时降级 2D |
| PostGIS 函数不熟 | 每个函数先在小数据集上验证，写成笔记 |
| 3 个月做不完 | M1 完成即可拿去讲，M2 / M3 是加分项 |
| 中途失去动力 | M1 第 3 周即有可视化成果，正向反馈最关键 |

### 5.3 验收标准

**M1**
- [ ] 网页上传一个 GPX 文件
- [ ] 轨迹出现在列表里
- [ ] 点击后 Cesium 地球上能看到轨迹并回放

**M2**
- [ ] 能查一条轨迹的距离 / 均速 / 爬升
- [ ] 自动识别停留点并在地图上标注
- [ ] 能看指定时间段的热点分布

**M3**
- [ ] 能在地图上画多边形，查出穿过的轨迹
- [ ] 能对比两条轨迹的相似度

**M4**
- [ ] 陌生人按 README 能在 30 分钟内跑起来
- [ ] 能对着架构图讲清完整数据流

### 5.4 配套学习计划

| 阶段 | 补什么原理 |
|---|---|
| M1 | 坐标系与投影（WGS84 / GCJ-02 / Web 墨卡托）、Cesium 坐标体系 |
| M2 | 空间索引原理（R 树 / GiST）、空间关系谓词（`ST_Intersects` 等） |
| M3 | 空间查询优化（`EXPLAIN ANALYZE`）、轨迹相似度算法（DTW / Fréchet） |

### 5.5 技术要点自检清单

每个技术点，都要能讲清楚"三句话"：

1. 用了什么
2. 为什么用它（不用行不行）
3. 遇到什么问题、怎么解决

示例：

> "我用 PostGIS 的 GiST 时空联合索引。因为查询总是'区域 + 时间段'同时出现，分开建两个索引只能命中一个。改成联合索引后，那个查询从 1.2 秒降到 15 毫秒。"

---

## 附录 A：已验证的技术事实

在本机（PostgreSQL 18.3 + PostGIS 3.6.2，数据库 `calcite`）实测：

| 验证项 | 命令要点 | 结果 |
|---|---|---|
| `btree_gist` 扩展可用 | `pg_available_extensions` | ✅ 版本 1.8，已安装到 `calcite` |
| `postgis` 扩展 | `pg_available_extensions` | ✅ 版本 3.6.2，已安装 |
| `(geometry, timestamptz)` 建 GiST 联合索引 | `CREATE INDEX ... USING GIST (g, ts)` | ✅ 返回 `SPACETIME_INDEX_OK` |
| 4326 直接 `ST_Distance` | 同一对点 | ⚠️ `0.00161`（单位：度，**不可当米用**） |
| 转 `geography` 计算 | 同一对点 | ✅ `139.198` 米 |
| 转 EPSG:4547 计算 | 同一对点 | ✅ `139.265` 米 |
| 空间函数可用性 | 查询 `pg_proc` | ✅ `ST_FrechetDistance`、`ST_HausdorffDistance`、`ST_SnapToGrid`、`ST_ClusterKMeans`、`ST_SimplifyPreserveTopology`、`ST_DWithin`、`ST_Intersects`、`ST_MakeLine`、`ST_Transform` 全部存在 |

## 附录 B：待办与开放问题

### B.1 M1 期间已确定的事项

| 项 | 结论 |
|---|---|
| GeoLife `.plt` 解析器 | ✅ 已实现。**关键：真实文件开头有 6 行文件头，数据从第 7 行才开始** —— 所以识别器必须往下扫，不能只看第一行（2026-09-14 踩过：171 个文件全部导入失败，耗时 388ms 说明在解析前就被拒了） |
| vivo 健康数据导出方式 | ✅ 已确认：vivo 运动健康导出 GPX。**坐标系实测为 WGS84** —— 轨迹中心与 OpenStreetMap 标注的「东区操场」相差 **10 米**（若为 GCJ-02 会偏 400–600 米） |
| Cesium 集成方式 | ✅ 已确定：npm 包 `cesium` + `vite-plugin-static-copy` 拷贝 Workers/Assets/Widgets |
| 导入用户范围 | ⏳ 未定：目前导入了用户 `000` 的 21 条。GeoLife 全量是 182 用户 / 18,670 条，建议按需扩到 5–10 个用户（约百万点级） |
| 路网匹配可行性 | ⏳ 仍待评估（M3 之后再评估） |

### B.2 开放问题

| 项 | 说明 | 计划处理时机 |
|---|---|---|
| 轨迹列表规模 | `GET /api/tracks` 已支持 `source` 筛选 + `limit`（2026-09-14 补上，对应第 319 行原本就规划的分页）。数据量再上一个量级时需要真正的分页或虚拟滚动 | 数据量到千条级时 |
| 接口返回全部点 | `GET /api/tracks/{id}` 目前返回全部点。上万点的轨迹需要加 `?simplify=` 用 `ST_SimplifyPreserveTopology` 抽稀 | M2 |
| 演示用底图 | 见 B.3 | **支线，暂不排期** |

### B.3 支线任务：底图 —— 加一个可切换的在线图层

> 状态：**已调研、暂不实施**（用户 2026-09-14 决定作为支线任务保存）。
> 用户**已有天地图的 API Key**（做其他项目时申请过），所以实施时不需要重新申请。

**为什么需要**

现在用的是 Cesium 自带的离线底图 **NaturalEarthII**——分辨率约 1:1000 万，设计用途是"从太空看地球"。
好处是**不需要 token、不需要联网**（见学习笔记 §8.5）；代价是**缩放到城市/校园尺度后是一片纯色**，
没有道路、没有建筑、没有街道名。演示时视觉冲击力差很多。

**为什么现在不做**

- 不是功能主线：M1/M2/M3 的功能都不依赖它
- 需要联网，而面试现场的网络是最不可控的因素
- 属于"锦上添花"，等主线功能稳住再动

**方案取舍**

| 方案 | 路网 / 建筑 | 需要 Key | **与我们的数据对齐？** | 国内速度 |
|---|---|---|---|---|
| **天地图**（推荐） | ✅ 中文路网 + 注记 | 免费申请（**已有**） | ✅ 对齐（CGCS2000 ≈ WGS84） | 快 |
| OpenStreetMap | ✅ 路网 | ❌ 不需要 | ✅ 对齐（WGS84） | 可能慢 |
| **高德 / 腾讯** | ✅ 最详细 | 要 Key | ❌ **会偏 400–600 米** | 快 |
| Cesium ion（Bing 卫星） | ✅ 卫星影像 | 要 token | ✅ 对齐 | 一般 |

**⚠️ 关键坑：底图的坐标系必须和轨迹数据一致**

高德、腾讯、百度的底图是 **GCJ-02（火星座标）**，而本项目的轨迹数据**已实测确认是 WGS84**。
两者混用会导致**轨迹整体偏移 400–600 米**——现象是"我在操场上跑，但地图显示我在旁边的村子里"。

**天地图和 OSM 都是 WGS84 系，和本项目数据天然对齐** ✅

**实施要点**

1. `CesiumGlobe.vue` 里用 `viewer.imageryLayers.addImageryProvider()` 叠加第二个图层
2. **保留离线底图**，做成"可切换"而不是"替换" —— 断网演示不能翻车
3. 天地图用 `WebMapTileServiceImageryProvider`（WMTS，按官方给的 URL 模板）
4. ⚠️ **Key 绝对不能提交进仓库**（本项目仓库是**公开**的）。做法：放在 `frontend/.env.local`
   （加进 `.gitignore`），代码里用 `import.meta.env.VITE_TIANDITU_KEY` 读
   - **参考教训**：2026-09-12 发现数据库密码因为被写进 `03-show-results.sql` 的注释里而泄漏到了公开仓库
     （后来靠更换密码补救）。**任何密钥都不要直接写在会被提交的文件里，连注释也不行。**

**验收标准**

- [ ] 放大到街区级别能看到道路和建筑轮廓
- [ ] **轨迹与底图上的道路对齐**（若明显偏移，说明坐标系不匹配，回查 GCJ-02 问题）
- [ ] 能一键切回离线底图，且断网时自动/手动回退不报错
- [ ] `git ls-files` 的结果里搜不到 API Key

## 附录 C：当前仓库状态（截至 2026-09-08）

- **已完成**：SpringBoot 3 骨架、Vue 3 + Vite 骨架、`/api/health` 健康检查、PostgreSQL + PostGIS 环境、`calcite` 数据库
- **已验证可运行**：`mvn clean package` 成功；`java -jar` 启动 2.591 秒，Tomcat 8080，数据库版本 18.3，PostGIS 3.6；`GET /api/health` 返回 200
- **Git**：`main` 分支，3 次提交，本地领先 `origin/main` 2 个提交（按约定暂不推送）
