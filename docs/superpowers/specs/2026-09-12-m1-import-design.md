# M1 收尾：轨迹导入功能设计

> 文档日期：2026-09-12
> 上游文档：`docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`（项目总设计）
> 本文档是 M1 最后一个功能块（轨迹导入）的详细设计，实施计划另见 `docs/superpowers/plans/`

---

## 一、背景与目标

### 1.1 为什么现在做这个

按项目总设计第四节，**M1 的完整范围是三块**：

| M1 内容 | 状态 |
| --- | --- |
| 轨迹列表 + 详情（距离 / 时长 / 点数） | ✅ 已完成 |
| Cesium 三维回放 + 速度/海拔曲线 | ✅ 已完成 |
| **轨迹导入** | ❌ **本文档要做的** |

所以 M1 目前完成度约 2/3。补完这一块，M1 才算真正闭环。

### 1.2 目标

让"数据进得来"：

1. **网页上传**：上传单个 GPX 文件，解析、清洗、入库、在地图上看见
2. **批量导入**：读取本地 GeoLife 数据集目录，批量灌入 `.plt` 轨迹
3. **数据质量可控**：真实 GPS 数据必然有漂移、缺失、重复，导入环节要能识别并标记

### 1.3 验收标准（做完什么样算成功）

- [ ] 把 `D:\Calcite-note\GPX-Data\2026年6月22日户外跑步.gpx.bin_tmp` 通过网页上传，能在地图上画出轨迹、能回放、速度曲线正常
- [ ] 该轨迹的海拔面板显示「这条轨迹没有海拔数据」（而不是一条贴底直线）
- [ ] 该轨迹的疑似漂移点被标记（`is_outlier = true`），且**没有任何正常点被误标**
- [ ] 同一文件重复上传不会产生第二条轨迹，而是返回已有的那条
- [ ] 用自造的 `.plt` 样本测试 GeoLife 解析器，解析出的点数与时间范围正确
- [ ] `mvn test` 全绿
- [ ] 现有 17 + 37 项前端回归仍然全绿

---

## 二、范围

### 2.1 做

| 项 | 说明 |
| --- | --- |
| `POST /api/tracks/import` | 网页上传单个 GPX 文件 |
| `POST /api/import/geolife` | 批量导入本地目录下的 GeoLife `.plt` |
| 格式识别 | **按文件内容识别**，不看扩展名 |
| 清洗与标记 | 见第五节 |
| `is_outlier` 字段 | `track_point` 新增一列 |
| 导入结果摘要 | 返回点数、距离、时长、标记数 |

### 2.2 不做（YAGNI）

| 不做 | 理由 |
| --- | --- |
| **CSV 上传** | 没有真实数据源使用它，格式还得自己拍；解析器接口已就位，以后加一个类即可。项目总设计第 45 行自己也标了「可选」 |
| 上传进度条 | 单文件几百 KB，瞬间完成 |
| 拖拽上传 / 多文件上传 | 一个按钮够用；多文件用脚本循环 |
| 异步任务 + 进度查询 | 见 4.2，当前规模用不上 |
| 登录 / 权限 | 项目总设计已明确排除 |
| 导入历史记录表 | 没有查询需求 |
| 撤销导入 | 直接 SQL 删除 |
| 坐标系自动转换 | 已实测确认为 WGS84（见第七节），不需要转 |
| KML / GeoJSON | 无数据源 |

---

## 三、架构与数据流

### 3.1 数据流

```
入口一：网页上传单个文件        入口二：本地目录批量
POST /api/tracks/import         POST /api/import/geolife
        │                                │
        └────────────┬───────────────────┘
                     ▼
            ImportService（新增）
                     │ ① 按内容识别格式 → 选解析器
                     ▼
              Importer 接口（三个实现）
              ├─ GpxImporter
              ├─ GeoLifeImporter
              └─（未来）CsvImporter
                     │ ② 统一输出 List<RawPoint>{lat, lon, ele, time}
                     ▼
            TrackCleaner（清洗规则只有这一份）
                     │ ③ 排序 / 重编号 / 海拔归 NULL / 标记异常
                     ▼
        TrackRepository + TrackPointRepository
                     │ ④ 分批写入（每 1000 条 flush）+ 算派生字段
                     ▼
              返回新轨迹 id + 导入摘要
```

**这套设计的核心是第 ② 步的统一中间结构 `RawPoint`。** 各解析器只管自己的格式差异，输出同一种东西；清洗层只认这一种，所以清洗规则只写一份。这是"可插拔解析器"相对"每条路各写各的"的核心价值。

### 3.2 包结构决策（**与项目总设计不一致，需同步更新总设计**）

项目总设计第 276-289 行规划的是**按功能分包**（`com.calcite.track` / `importer` / `analysis`），但代码实际是**按层分包**（`com.calcite.web` / `repository` / `domain`）。

**决策：保持按层分包**，本次新增 `service/` 和 `importer/` 两个包：

```
com.calcite
├── CalciteApplication.java
├── domain/                    实体（Track / TrackPoint）
├── repository/                持久层
├── service/                   ★ 新增：ImportService、TrackCleaner
│   └── importer/              ★ 新增：Importer 接口 + GpxImporter、GeoLifeImporter
└── web/                       接口层
    └── dto/                   DTO（新增 ImportResult）
```

理由：

1. 用户刚通过《项目结构地图》掌握了按层分包的结构，换分包方式会让已学内容作废
2. 当前共约 10 个类，按层分包更好理解；业界一般在 50+ 个类、按层包过于拥挤时才转按功能分包
3. 项目规则「要改范围，先改文档」→ 本文档即是对总设计的修订，实施时同步更新总设计第 276-289 行

---

## 四、接口设计

### 4.1 网页上传

```
POST /api/tracks/import
Content-Type: multipart/form-data
字段：file

成功 200：
{
  "id": 2,
  "name": "2026年6月22日户外跑步",
  "pointCount": 2342,
  "distanceM": 3933.5,
  "durationS": 2348,
  "outlierCount": 8,
  "skippedDuplicate": false,
  "message": "导入成功"
}

重复导入同一文件 200（幂等，不报错）：
{
  "id": 2,
  ...,
  "skippedDuplicate": true,
  "message": "这条轨迹已经导入过了"
}

无法识别的格式 400：
{ "error": "无法识别的文件格式（只支持 GPX，以及 GeoLife .plt）" }

数据非法 400（0 个点 / 1 个点 / 坐标越界）：
{ "error": "文件里没有有效的轨迹点" }
```

**幂等实现**：`external_id` = 文件内容的 **SHA-256**（十六进制，取前 32 位）。导入前先 `findByExternalId`，存在则直接返回旧轨迹。

### 4.2 批量导入 GeoLife

```
POST /api/import/geolife
Content-Type: application/json

{ "path": "D:\\GeoLife\\Data", "maxTracks": 50 }

成功 200：
{
  "path": "...",
  "scanned": 137,          // 本次扫描到的 .plt 文件数
  "imported": 50,          // 成功导入
  "skipped": 87,           // 跳过（已存在 或 超过 maxTracks）
  "failed": 0,             // 解析/清洗失败
  "totalPoints": 71234,
  "elapsedMs": 18422
}
```

**为什么不做成异步任务**：一次导入 5-10 个用户约 50-150 万点，用 `maxTracks` 限制单次工作量（默认 50 条，约秒级到几十秒），配合**幂等**特性，脚本循环调用即可自动推进——每次调用都会跳过已导入的、继续往后取。这样：

- 每次调用都有明确反馈，不会"卡住没动静"
- 不需要任务状态表、进度接口、线程池
- 等将来真要一次灌 182 个用户，再引入异步任务（那时 `maxTracks` 的循环模式会成为瓶颈）

调用示例：

```powershell
1..10 | ForEach-Object {
  Invoke-RestMethod -Method Post http://localhost:8080/api/import/geolife `
    -ContentType 'application/json' -TimeoutSec 600 `
    -Body '{"path":"D:\\GeoLife\\Data","maxTracks":200}'
}
```

**安全约束**：`path` 必须落在 `application.yml` 配置的白名单根目录下：

```yaml
calcite:
  import:
    allowed-roots:
      - D:\GeoLife
    max-tracks-per-call: 50
    max-speed-mps: 8.0      # 异常速度绝对下限
    speed-median-factor: 3  # 相对倍数
```

不满足则返回 400，错误信息明确说明允许的根目录。本地项目不需要鉴权，但路径必须收敛，避免任意目录读取。

---

## 五、数据模型变更

### 5.1 `track_point` 新增一列

```sql
is_outlier BOOLEAN NOT NULL DEFAULT false    -- 疑似 GPS 漂移点
```

### 5.2 怎么改 `scripts/db/01-schema.sql`

该文件的约定是「**重跑一遍就对齐**」，所以要**两处都写**：

```sql
-- ① CREATE TABLE 里加上（新库直接就有）
CREATE TABLE IF NOT EXISTS track_point (
  ...
  is_outlier  BOOLEAN NOT NULL DEFAULT false,
  ...
);

-- ② 文件末尾补一句（老库能补上：
--    CREATE TABLE IF NOT EXISTS 不会给已存在的表加列）
ALTER TABLE track_point ADD COLUMN IF NOT EXISTS is_outlier BOOLEAN NOT NULL DEFAULT false;
```

**不引入 Flyway / Liquibase**：3 张表、单人开发，`IF NOT EXISTS` 够用。等有多套环境需要同步时再引入——现在引入是纯成本。

### 5.3 派生字段（`track` 表）

全部用 **PostGIS 计算**，不在 Java 里算，避免两套公式不一致：

```sql
distance_m  = ST_Length(line_geom::geography)              -- 必须 ::geography，否则单位是"度"
duration_s  = EXTRACT(EPOCH FROM (end_time - start_time))
point_count = COUNT(*)
geom        = ST_MakeLine(geom ORDER BY seq)
```

⚠️ 已知坑：`ST_Length(geometry(4326))` 返回的是**度**（约 0.0859），必须 `::geography` 才是米（9444.2）。

---

## 六、清洗规则

### 6.1 规则清单

| # | 规则 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | **海拔"全同"视为没有** | 整条轨迹的 `ele` 全相等（含全部缺失）→ 该轨迹所有点 `elevation_m = NULL` | 实测样本 `ele` 全为 `0.0`；存 0 会画出贴底直线误导人 |
| 2 | **异常速度标记** | 见 6.2 | 标记 `is_outlier = true` |
| 3 | **按时间排序 + 重编号** | 按 `time` 升序排序，`seq` 从 0 连续编号 | 保证 `seq` 与时间严格对应 |
| 4 | **时间戳重复** | `dt <= 0` 的段：该点 `speed_mps = NULL`，**点不删** | 防除零；点本身是真相 |
| 5 | **轨迹名缺失用文件名** | 无 `<name>` → 文件名去掉扩展名 | 实测样本无 `<name>`，会命名为「2026年6月22日户外跑步」 |
| 6 | **重复导入幂等** | `external_id` = 内容 SHA-256；已存在则返回旧 id | 改名也能识别 |
| 7 | **非法数据拒绝** | 0 点 / 1 点 / 坐标越界 → 400，不入库 | 不让脏数据进库 |

### 6.2 异常速度判定（自适应阈值）

```
异常段 = 段速度 > max(maxSpeedMps, speedMedianFactor × 该轨迹段速度的中位数)

默认 maxSpeedMps = 8.0 m/s，speedMedianFactor = 3
```

**为什么用自适应而不是固定阈值**：GeoLife 数据集包含**汽车、公交、火车**轨迹，高铁可达 80 m/s。固定 8 m/s 会把大量正常数据标成异常。

真实数据验算：

| 轨迹类型 | 速度中位数 | 3 × 中位数 | 实际阈值 | 效果 |
| --- | --- | --- | --- | --- |
| 校园跑（实测样本） | 1.63 m/s | 4.9 | **8.0** | 12.13 m/s 那段被标出 ✅ |
| GeoLife 汽车 | ~12 m/s | 36 | **36** | 正常行驶 20 m/s 不误标 ✅ |
| GeoLife 高铁 | ~60 m/s | 180 | **180** | 只拦真正的坐标跳变 |

### 6.3 标记哪一端

一个漂移点会造成**两段**异常速度（跳出去 + 跳回来），但无法判断是哪一端漂了。

**决策：两端都标记**——宁可多标，不可漏标。实测样本中最多标 8 个点（4 段 × 2 端），占 2342 点的 0.3%。

### 6.4 实测样本的预期清洗结果

| 项 | 值 |
| --- | --- |
| 文件 | `2026年6月22日户外跑步.gpx.bin_tmp`（**扩展名不是 .gpx**） |
| 点数 | 2342（全部有时间戳） |
| 时间跨度 | 2348 秒（39 分 08 秒），采样间隔 1 秒 |
| 距离 | 皮球面公式 3933.5 米（vivo 自记 4010.0 米，差 1.9%） |
| 海拔 | 全部 `0.0` → 按规则 1 存 `NULL` |
| 时间戳重复 / 断档 / 倒流 | 0 / 0 / 0 |
| 起终点距离 | 59.1 米（闭合环线） |
| 异常段（> 8 m/s） | 4 段，最高 12.13 m/s |
| 预期标记点数 | 最多 8 |

---

## 七、坐标系（已实测确认）

**结论：WGS84 ✅，无需任何转换。**

验证方法（2026-09-12 实测）：

1. 取轨迹中心点 `25.033600, 117.020900`
2. 用 Photon（OpenStreetMap 数据，全球统一 WGS84）反查 → 返回「**东区操场** · 同心路 · 龙岩市 · 福建省」
3. 取 OSM 上「东区操场」自身坐标 `25.033514, 117.020893`，与我们的点算距离 → **10 米**

**为什么 10 米可以判定为 WGS84**：若数据是 GCJ-02（火星座标）而当成 WGS84 使用，福建地区的偏移量约 **400–600 米**，该点会直接飘出操场。实测仅差 10 米（"2342 点平均中心" vs "操场标注中心"的正常差异）。

附带确认：该轨迹确实是操场跑圈（OSM 标注为「东区操场」），轨迹包围盒 203 米 × 85 米，与 400 米标准跑道吻合。

未来若遇到偏移数据，在 `GeoUtils` 中增加 GCJ-02 → WGS84 转换即可（项目总设计第 349-354 行已预留该话题）。

---

## 八、前端入口

### 8.1 结构

- `TrackList.vue` 顶部新增「导入轨迹」按钮 + 隐藏的 `<input type="file" accept=".gpx,.plt">`
- **组件不发请求**，只 `emit('import', file)`——遵守结构地图第 7 章定的边界（子组件只显示 + 上报意图）
- `App.vue` 负责 `FormData` 上传，成功后：刷新列表 → 自动选中新轨迹 → 显示摘要

### 8.2 摘要展示

复用现有 `.status` 状态条区域：

> 导入成功：2026年6月22日户外跑步 · 2342 点 · 3.93 km · 39分08秒 · 标记 8 个疑似漂移点

失败时显示服务端返回的 `error` 字段。

### 8.3 地图上的表现

疑似漂移点**默认照常绘制**（M1 不改渲染逻辑），因为：

- 用户选择的是「存下来 + 标记」，不是「前端隐藏」
- 前端按标记过滤属于可视化选择，可以作为 M2 的可选项
- 保持 M1 改动最小

---

## 九、错误处理

| 情况 | HTTP | 行为 |
| --- | --- | --- |
| 文件为空 | 400 | "上传的文件是空的" |
| 无法识别格式 | 400 | "无法识别的文件格式" |
| 有效点 < 2 | 400 | "文件里没有有效的轨迹点" |
| 坐标越界 | 400 | "存在非法的经纬度坐标" |
| XML 解析失败 | 400 | "文件内容不是合法的 GPX" |
| 单点解析失败（个别点） | — | **跳过该点并计数**，不影响整体导入 |
| 重复导入 | 200 | 返回已有轨迹 + `skippedDuplicate: true` |
| 批量导入路径不在白名单 | 400 | "路径不在允许的导入目录内，允许：..." |
| 批量导入目录不存在 | 400 | 明确说明路径 |
| 单条轨迹导入失败（批量） | — | **记入 `failed` 计数并继续**，不中断整批 |

---

## 十、测试与验收

这是项目**第一次引入 Java 单元测试**。JUnit 5 / surefire / Mockito 已确认存在于本地 `.m2`（离线可跑），`pom.xml` 中 `spring-boot-starter-test` 已声明。

### 10.1 单元测试（JUnit）

| 测试类 | 覆盖 |
| --- | --- |
| `GpxImporterTest` | 用**真实样本 GPX** 断言：2342 点、首点时间 `11:00:08`、末点 `11:39:16`、`ele` 全 0 |
| `GeoLifeImporterTest` | 用自造 `.plt` 样本断言：点数、时间解析（`days_since_1899` 换算）、海拔单位换算（英尺→米） |
| `TrackCleanerTest` | 海拔全同→NULL；自适应阈值（校园跑标 4 段、模拟汽车轨迹不误标）；时间重复→速度 NULL；排序重编号 |
| `FormatDetectorTest` | 按内容识别 GPX / `.plt`；对 `.bin_tmp` 这种错误扩展名仍能识别 |
| `ImportIdempotencyTest` | 同一内容两次导入返回同一 id |

测试夹具：真实 GPX 复制到 `backend/src/test/resources/`（**用真实脏数据当夹具，比手造的更值钱**）。

### 10.2 接口验收（脚本）

```powershell
# 上传真实 GPX，检查返回摘要
# 再用 psql 核对库里的点数、distance_m、is_outlier 数量
```

### 10.3 浏览器验收（Playwright）

沿用现有手段：打开页面 → 点「导入轨迹」→ 上传文件 → 等待 → 截图 → 断言轨迹线出现。

**注意**：Cesium 几何体异步生成，必须真实等待，不能用虚拟时钟截图（global-knowledge 已记录）。

### 10.4 回归

- `mvn test`（后端新增）
- `npm run check:playback`（17 项，必须仍全绿）
- `npm run check:chart`（37 项，必须仍全绿）

---

## 十一、风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| GeoLife 下载慢或失败 | 批量导入没有真实数据可测 | 用自造 `.plt` 样本开发和测试；下载作为并行任务，不阻塞（用户已选择此策略） |
| `.plt` 海拔单位是英尺 | 海拔数据差 3.28 倍 | 单元测试显式断言英尺→米换算 |
| `days_since_1899` 时间换算出错 | 时间整体偏移 | 单元测试断言已知日期 |
| 批量导入 JPA 逐条插入过慢 | 百万点导入耗时过长 | 配置 Hibernate 批量插入（`hibernate.jdbc.batch_size=500` + `order_inserts=true` + `reWriteBatchedInserts=true`） |
| 自适应阈值在极端数据上失效 | 误标或漏标 | 单元测试覆盖三种典型分布；阈值可配置 |
| 首次引入 JUnit 需要下载依赖 | 沙箱无网导致构建失败 | **已预先验证**：JUnit / surefire / Mockito 均已在本地 `.m2` |

---

## 十二、与项目总设计的差异（需同步更新总设计）

| # | 差异 | 处理 |
| --- | --- | --- |
| 1 | 总设计规划**按功能分包**（`track/` / `importer/` / `analysis/`），实际采用**按层分包** | 更新总设计第 276-289 行，改为按层分包 + `service/` + `importer/` |
| 2 | 总设计第 116 行写上传支持 **GPX / CSV**，第 45 行又标 CSV「可选」 | 本次明确**不做 CSV**，更新第 116 行 |
| 3 | 总设计第 353 行「vivo 数据大概率是 WGS84，导入时需校验」 | **已校验完成**，在总设计补记验证结论（差 10 米，确认为 WGS84） |
| 4 | 总设计未定义"异常速度"的处理方式 | 在总设计补充：存下来 + `is_outlier` 标记 + 自适应阈值 |

---

## 十三、自查记录

- [x] 无 TBD / TODO / 待定占位
- [x] 各节之间无矛盾（范围 vs 接口 vs 测试一致）
- [x] 范围聚焦单一功能块，适合出单个实施计划
- [x] 模糊项已明确：阈值公式、标记端、幂等键、错误码、包结构
- [x] 实测数据均来自真实文件或真实查询，未编造
