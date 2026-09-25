# 路网匹配（Map Matching）在 Calcite 中的可行性评估

## 1. 路网匹配是什么、解决什么问题

- 一句话：GPS 点因定位误差常常落在"路边"甚至"楼里"，路网匹配就是把一串 GPS 点**吸附到它实际行驶的那条道路上**。
- 它输出的不是点，而是**连续的路段序列 + 每条路上走过的距离/时间**，从而修正轨迹、还原真实行车路径。
- 解决的问题：定位漂移、"点在路外"、轨迹穿墙穿楼、以及在密集路网里"两条平行路选错哪条"。
- 外行类比：把一段歪歪扭扭的手绘路线，重新描在城市地图的真实街道上。

## 2. 主流实现路线

- **自研 HMM**（隐马尔可夫）：自己建路网图 + 发射/转移概率 + Viterbi。真正工作量在**路网数据管道**，不是算法本身。
- **开源引擎自带匹配**：OSRM `/match`、Valhalla Meili、GraphHopper map-matching——都要求**先自建路网图**（各自 osrm-extract / valhalla_build_tiles / graphhopper import）。
- **算法库 API 层**：mappymatch（NREL，Python，OSM + LCSS/OSRM/Valhalla 三种 matcher）；leuvenmapmatching、barefoot（Java，OSM 图 + HMM）。库越省事，越依赖你已有的路网数据。
- **输入要求（三家一致）**：OSM PBF/XML 路网 + 轨迹点**经纬度 + 时间戳**，坐标系 **WGS84/EPSG:4326**——与 Calcite 现有数据完全一致，无需转换。
- **工作量量级**：纯 Python 库调通 ≈ 1~2 天（前提是已有路网）；自建 OSRM/Valhalla 服务 ≈ 1~2 周；自研 HMM 到"效果能看"≈ 3~4 周且不稳定。

## 3. 路网数据从哪来、体积多大

- 来源：Geofabrik / BBBike 的 OSM 抽取（[Geofabrik 中国页](https://download.geofabrik.de/asia/china.html)、[BBBike 中国页](https://data.bbbike.org/osm/region/asia/china/)），或 Overpass API 按 bbox 现拉。
- **中国全境 PBF ≈ 1.6 GB**（BBBike 实测值，2026-09 更新）；GeoParquet 版本 ≈ 4 GB，导入 PostGIS 后通常再膨胀 2~3 倍。
- 路段条数：未查到权威的"中国/北京路段总数"；公开资料中 OSM 路网量级为**百万级 ways，其中机动车可用道路 160 万条以上**。
- 关键点：**不能用全国数据**。正确做法是只取轨迹覆盖的 bbox（北京 + 上海 + 福建），且只保留 `motorway/trunk/primary/secondary/tertiary`，体积可压到几十 MB、路段数万到十几万条。
- 现成代价：Calcite 数据库里**一条路网都没有，也没有 pgRouting**，这一步是纯新增，不是改造。

## 4. 对采样间隔与定位精度的要求（对照 Calcite 数据）

- 主流引擎的默认参数是"**按 1 秒级密集采样设计**"的：Valhalla 默认 `search_radius` 50 m（上限 100 m）、`interpolation_distance` 10 m；OSRM `/match` 默认 radius 仅 **5 m**。
- **5~42 米间隔**本身不算灾难（属于中频轨迹），但引擎的时间/距离一致性模型会明显变差；需要把 radius 放宽、并接受一部分点被判为 outlier 而被丢弃。
- **超过 1000 公里的 3 段跳跃**：Valhalla 的 `breakage_distance` 默认 2000 m，超了直接断链；OSRM 对时间戳大跳变也会**自动把轨迹切成多段 sub-trace**。结果不是"匹配失败"，而是"一条轨迹被切成几段"，与 Calcite 的"整条轨迹"语义冲突。
- **GPS 漂移点**：漂移量往往 > 50~100 m 搜索半径，引擎会判定"找不到候选路段"→ 该点被丢弃或整段匹配失败；强行放大 radius 会匹配到错误道路，反而制造假数据。
- **WGS84 直通不用转 GCJ-02**，这是本任务唯一"没坑"的一环；但 246 条 × 数百点的逐点匹配必须做成**后端离线跑批 + 结果落库**，不是页面点一下能出结果。

## 5. "不需要路网就能演示"的轻量替代

- **点到最近道路距离**：只需把 bbox 内主干道导入 PostGIS 并建 GIST 索引，`ST_Distance` 算出每点到路的距离，输出"偏离道路距离分布/最大值"作为一个新指标卡。
- **路网可视化 + 轨迹吸附示意**：Cesium 用 `GeoJsonDataSource` 叠主干道，再把每点投影到最近线段连线（P2D point-to-curve，不严谨但演示足够），零算法成本、视觉收益最大。
- **借现成 `/match` 服务做一次性离线演示**：本地起一个 OSRM 容器，对同一条北京轨迹跑一次 `/match?tidy=true&gaps=split`，把返回的 matched 折线存成一张结果表直接播放，不接实时链路。
- 三条轻量路线的共同点：**只碰"距离/可视化/一次性结果"，不碰"可靠性、前后一致性、批量重算"**——工作量 1~3 天，而不是 2~4 周。

## 6. 结论

**建议不做。** 三条理由：

1. **前置空缺太大**：项目零路网数据、零路由依赖、无 pgRouting。即便只做北京 bbox，也要走"下 1.6 GB 全国包 → 抽取路段 → 导入 PostGIS → 建索引"整条新增数据管道，一周以上只换来一个还没开始匹配的起跑线。
2. **数据形态与算法假设不匹配**：5~42 m 间隔对引擎是"低频"、3 段 1000 km 跳跃会被强制断成多段（Valhalla `breakage_distance` 2000 m / OSRM 大跳变自动 split）、漂移点会超出 50~100 m 搜索半径被丢弃——最后得到的是一条被切碎、丢点、且无法与"整条轨迹"语义对齐的结果。
3. **对现有能力零增益**：Calcite 的卖点（回放、速度/海拔曲线、停留点、热点聚类、网格密度、相似度、圈选）都不消费路网匹配结果；匹配只能作为一个孤立的新页面，而不是给既有功能加分。12 周 + M3 最后阶段，投入产出不成立。

**如果坚持要做，最小可行版本（MVP）与前置条件：**

- 先补数据：只导出**轨迹 bbox 内的 motorway~tertiary**，导入 PostGIS 建 GIST 索引（目标：路段数万级、几百 MB 以内），坐标系直接 4326。
- 先补数据质量：把 3 段超长跳跃在**数据库里显式切成子轨迹**（加 segment 字段），把已标记的漂移点排除出匹配集合——这一步不做，匹配结果一定不可解释。
- MVP 范围：不做自研 HMM。起一个 OSRM `match` 服务，`radiuses` 放宽到 50~100 m、`gaps=split`、`tidy=true`，**离线批处理**跑 246 条（预计数小时），结果落一张 matched 结果表。
- 前端只做一件事：Cesium 上叠加"路网 + 原始轨迹 + 吸附后折线"三层，并给出每条的匹配置信度与丢弃点数——演示价值已足够。
- 工作量估算：路网抽取 1 天、PostGIS 导入与索引 0.5 天、OSRM 容器与跑批 1.5 天、前端叠加与结果展示 1.5 天 ≈ **4~5 天**；其中真正的风险不在代码，而在"跑完后发现一半轨迹匹配质量很差"。

---
参考来源：[OSRM Match API](https://project-osrm.org/docs/v5.24.0/api/)、[Valhalla Meili 配置](https://valhalla.github.io/valhalla/contributing/architecture/meili/configuration/)、[mappymatch（NREL）](https://mappymatch.readthedocs.io/en/stable/)、[Geofabrik 中国抽取](https://download.geofabrik.de/asia/china.html)、[BBBike 中国抽取（含体积）](https://data.bbbike.org/osm/region/asia/china/)。
