# Calcite 设计文档：GPS 轨迹时空分析平台

> **一句话定位**：把 GPS 轨迹数据存进 PostGIS，用空间索引和空间函数做时空分析，再在 Cesium 三维地球上按时间轴回放，并把分析结果叠加到地球上。

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0 |
| 日期 | 2026-09-08 |
| 状态 | 已评审通过（第 1-5 节逐节确认） |
| 项目定位 | 求职作品集 |
| 目标岗位 | GIS / 时空数据开发 |
| 技术栈 | SpringBoot 3.5.16 · PostgreSQL 18.3 + PostGIS 3.6.2 · Vue 3.5 + Vite 8 · Cesium |
| 交付周期 | 12 周（2026-09 起，目标：春招 / 暑期实习） |
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

这些问题的共同点：**必须同时用上"空间"和"时间"**。这正是 PostGIS 时空索引存在的理由，也是"时空数据开发"岗位每天在做的事。

### 1.3 名字的含义

方解石（Calcite）是晶体矿物——**把杂乱无章的东西结晶成规则结构**。对应到项目：把散乱的 GPS 点，组织成有结构、能回答问题的时空数据。

### 1.4 面试价值

面试官看完项目后应得出三个结论：

1. **会用空间数据库**——不是把 PostGIS 当 MySQL 用，而是真的用了空间索引和 `ST_` 函数
2. **懂时空查询**——能说清"为什么这个查询要建 GiST 索引""时空联合查询怎么优化"
3. **能把数据变成产品**——三维可视化不是贴图，是能交互、能讲业务含义的

---

## 二、功能范围与里程碑

总周期 12 周，分四个里程碑。**每个里程碑都是一个可演示的完整状态。**

### M1 看得见（第 1-3 周）

- 轨迹导入：
  - `POST /api/tracks/import` 支持 GPX / CSV 文件上传
  - GeoLife 数据集批量导入（`.plt` 解析器 + 流式批量插入）
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

> 里程碑意义：PostGIS 空间函数真正上场，面试深挖点集中于此。

### M4 收尾（第 12 周）

- README + 架构图 + 部署文档 + 演示数据集
- 面试话术整理：每个技术点准备"为什么这么做、不用它行不行"

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

-- 索引（面试重点）
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

> 这本身就是面试话题："数据量涨到千万级时你怎么处理"。

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
├── common/                        ← 待建
│   ├── ApiResponse.java           统一响应格式
│   ├── GlobalExceptionHandler.java
│   └── GeoUtils.java              坐标 / 距离工具
├── track/                         ← 待建（M1 主线）
│   ├── TrackController.java
│   ├── TrackService.java
│   ├── TrackRepository.java
│   ├── Track.java                 实体
│   └── TrackPoint.java
├── importer/                      ← 待建
│   ├── GpxImporter.java
│   ├── CsvImporter.java
│   └── GeoLifeImporter.java
└── analysis/                      ← 待建（M2 / M3）
    ├── StayPointService.java      停留点识别
    ├── HotspotService.java        热点分析
    └── SimilarityService.java     轨迹相似度
```

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

### 4.4 三个必须提前想清楚的技术点

**① 数据量：接口为什么要有 `simplify` 参数**

一条轨迹可能有上万个点，前端全量渲染会卡死。后端存全量，返回时按需抽稀（`ST_SimplifyPreserveTopology`），放大地图时再请求细节。

**② 大批量导入：不能一次性读进内存**

千万级点必须流式解析 + 批量插入（每 1000 条 flush 一次）。

**③ 坐标系：中国地图的 GCJ-02 偏移**

- GeoLife 是 **WGS84**（与 Cesium 一致）→ 直接可用
- 高德 / 腾讯 POI 是 **GCJ-02**（火星坐标），叠加会偏移数百米
- vivo 健康数据大概率是 WGS84，导入时需校验
- 坐标转换话题能立刻区分"做过真项目"和"只跑过 demo"

---

## 五、边界、风险与验收标准

### 5.1 明确不做的事

| 不做 | 原因 |
|---|---|
| 用户注册 / 登录 / 权限 | 作品集不需要，面试也不会问 |
| 实时轨迹推流 | 另一套技术栈（WebSocket + 消息队列），会拖垮进度 |
| 多租户 / SaaS 化 | 与目标岗位无关 |
| 移动端 App | 网页足够演示 |
| 路网匹配（Map Matching） | 技术难度过高，M3 之后再评估 |
| 全量导入 GeoLife（2400 万点） | 先导入 5-10 个用户，够体现规模 |

> 作品集的失败往往不是做得太少，而是什么都想做、最后什么都做不完。

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

### 5.5 面试话术模板

每个技术点准备"三句话"：

1. 我用了什么
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

| 项 | 说明 | 计划处理时机 |
|---|---|---|
| GeoLife `.plt` 解析器 | 格式：`lat,lon,0,altitude_ft,days_since_1899,date,time` | M1 期间实现 |
| vivo 健康数据导出方式 | 需确认 App 内导出路径与坐标系 | M1 期间调研 |
| 导入用户范围 | 从 GeoLife 182 个用户中选 5-10 个 | M1 导入脚本编写时确定 |
| Cesium 集成方式 | npm 包 `cesium` + Vite 插件，或静态引入 | M1 前端开发时确定 |
| 路网匹配可行性 | 技术难度评估 | M3 结束后再评估 |

## 附录 C：当前仓库状态（截至 2026-09-08）

- **已完成**：SpringBoot 3 骨架、Vue 3 + Vite 骨架、`/api/health` 健康检查、PostgreSQL + PostGIS 环境、`calcite` 数据库
- **已验证可运行**：`mvn clean package` 成功；`java -jar` 启动 2.591 秒，Tomcat 8080，数据库版本 18.3，PostGIS 3.6；`GET /api/health` 返回 200
- **Git**：`main` 分支，3 次提交，本地领先 `origin/main` 2 个提交（按约定暂不推送）
