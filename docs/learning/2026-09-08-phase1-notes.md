# Calcite 第一阶段学习笔记

> PostGIS + Spring Boot + Cesium 入门
>
> 写于 2026-09-08，对应 Git 提交 `ba47315`

这份笔记写给「刚跟着做完第一阶段、但感觉没吃透」的你。

目标不是让你记住所有 API，而是让你**能看懂后面会发生什么**：知道每个名词在项目里干什么、为什么需要它、出了问题去哪儿查。

---

# 0. 先回答一个让你发懵的问题：地图到底在哪？

你问：「为什么有 Cesium 了，但跑 PowerShell 还是没看到前端地图？」

**因为地图不在 PowerShell 里，它在浏览器里。**

| 你在哪看 | 能看到什么 |
| --- | --- |
| PowerShell | 命令行的文字输出。它是「终端」，只能显示字 |
| 浏览器（Edge / Chrome） | 网页。三维地球、地图、按钮，都在这里 |

Cesium 是**浏览器里的 JavaScript 库**。它画的球体是网页内容，PowerShell 根本显示不了图形界面。

所以正确看法是：**打开浏览器，地址栏输入 http://localhost:5173**

那个「5173」就是前端开发服务器（Vite）在跑的地方。它此刻确实在运行——刚才实测返回 HTTP 200。

小结一句话：

> PowerShell 负责「启动和查错」，浏览器负责「看效果」。两者分工不同，不是前者没生效。

---

# 1. 这个项目到底在做什么

## 1.1 一句话

把 GPS 轨迹数据存进 PostGIS，用空间函数做分析，再用 Cesium 在三维地球上画出来、按时间回放。

## 1.2 数据怎么流动

```
原始 GPS 数据（GeoLife / GPX / CSV）
        ↓  导入
   PostgreSQL + PostGIS          ← 存数据、算距离、做空间查询
        ↓  SQL / JPA
   Spring Boot 后端（8080）      ← 把数据变成 HTTP 接口
        ↓  JSON
   Vue 前端（5173）              ← 页面、列表、按钮
        ↓
   Cesium 三维地球               ← 画线、飞行、时间轴回放
        ↑
     你（浏览器里看）
```

每一层只干一件事，层与层之间用**约定好的格式**沟通（SQL、JSON）。这就是所谓的「分层架构」。

## 1.3 为什么是这三件套

| 技术 | 它解决什么问题 | 在你项目里的角色 |
| --- | --- | --- |
| PostGIS | 普通数据库只会存「经度=116.39，纬度=39.90」两个数字，不会算「这两点距离多少米」「哪些点落在某条线附近」 | 时空数据的计算引擎 |
| Spring Boot | 把数据库的数据变成网页能读的接口 | 后端 API |
| Cesium | 在浏览器里显示三维地球，支持海量点线面 | 可视化 |

一句话：**PostGIS 会算，Spring Boot 会传，Cesium 会画。**

---

# 2. 你电脑上现在装着什么

这一节是「环境地图」。以后看到报错提到某个名字，可以回来查它是什么。

| 软件 | 版本 | 干什么的 | 在哪 |
| --- | --- | --- | --- |
| PostgreSQL | 18.3 | 数据库本体 | E:\PostgreSQL |
| PostGIS | 3.6 | 给 PostgreSQL 加空间能力的扩展 | 装在上面的库里 |
| psql | 18.3 | 命令行工具，用来执行 SQL | E:\PostgreSQL\bin\psql.exe |
| Java (JDK) | 25.0.2 | 运行 Spring Boot 的虚拟机 | — |
| Maven | 3.9.11 | Java 的「依赖 + 构建」工具 | IntelliJ 自带 |
| Spring Boot | 3.5.16 | 后端框架 | backend/ |
| Hibernate | 6.6.53 | ORM，Java 对象 ↔ 数据库表的翻译官 | 依赖引入 |
| hibernate-spatial | — | 让 Hibernate 认识 PostGIS 的 geometry 类型 | 依赖引入 |
| Tomcat | 10.1.55 | 内嵌的 Web 服务器，监听 8080 | Spring Boot 自带 |
| Node.js | 24.14.0 | 跑前端工具链的运行时 | — |
| npm | 11.9.0 | Node 的包管理器 | — |
| Vue | 3.5.42 | 前端框架（组件化） | frontend/ |
| Vite | 8.2.2 | 前端开发服务器 + 打包工具，监听 5173 | frontend/ |
| Cesium | 1.145.0 | 三维地球库 | frontend/node_modules/cesium |

**注意一个容易混的点**：

- PostgreSQL 是「数据库服务器」，它一直在后台跑（Windows 服务 postgresql-x64-18）
- psql 是「客户端」，是你手动敲命令去连它的工具
- 就像「网站」和「浏览器」的关系

---

# 3. 知识点一：PostGIS 与空间数据

## 3.1 PostGIS 是什么

PostgreSQL 本身是个普通的关系型数据库。PostGIS 是一个**扩展**，装上之后：

- 多了一种列类型：`geometry`
- 多了几百个以 `ST_` 开头的函数（Spatial Type）

启用方式（在 calcite 库里执行过一次了）：

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

注意：**PostGIS 是按数据库启用的**，不是全局。同一个 PostgreSQL 里，calcite 库有，别的库可以没有。

## 3.2 geometry 类型

普通列存数字或字符串，`geometry` 列存的是**几何对象**：

```sql
POINT(116.3974 39.9093)              -- 一个点
LINESTRING(116.39 39.90, 116.40 39.91)  -- 一条线
POLYGON(...)                          -- 一个面
```

创建带几何列的表时，要写清楚「是哪种几何」和「用哪套坐标」：

```sql
geom geometry(Point, 4326)      -- 点，SRID 4326
geom geometry(LineString, 4326) -- 线，SRID 4326
```

## 3.3 SRID 4326 是什么

SRID = Spatial Reference System Identifier，空间参考系统编号。

- **4326** 是 WGS84，也就是「经纬度」，GPS 设备、手机定位、谷歌地图用的就是它
- 单位是**度**
- 全球通用，所以我们的表全部用 4326

还有一个常见的是 **3857**（Web 墨卡托），用于网页地图瓦片，单位是米。

**关键规则：不同 SRID 的几何不能直接比较。** 你会亲眼看到这个错误（第 10 节）。

## 3.4 ST_ 函数家族（本项目实际用到的）

| 函数 | 作用 | 本项目用在哪 |
| --- | --- | --- |
| ST_MakePoint(lon, lat) | 造一个点 | 生成示例轨迹 |
| ST_SetSRID(geom, 4326) | 给几何贴上 SRID 标签 | 必须包住 ST_MakePoint |
| ST_MakeLine(点数组) | 把一堆点连成线 | 生成轨迹线 |
| ST_LineInterpolatePoint(线, 比例) | 在线段上按比例取点 | 均匀生成 121 个点 |
| ST_Translate(geom, dx, dy) | 平移几何 | 给点加一点抖动，模拟真实 GPS |
| ST_Length(geom) | 算长度 | 算轨迹总距离 |
| ST_DWithin(a, b, 距离) | 判断两点是否在给定距离内 | 查天安门 1 公里内的点 |
| ST_NPoints(geom) | 数线上有几个顶点 | 验证 121 个点 |
| ST_StartPoint / ST_EndPoint | 取线的起点/终点 | 查看轨迹起终点 |
| ST_X(geom) / ST_Y(geom) | 取点的经度/纬度 | 把坐标拆成两列 |
| ST_AsText(geom) | 几何转成可读文本 | 打印出来看 |
| ST_IsValid / ST_IsSimple | 检查几何是否合法/不自交 | 数据质量检查 |

**记忆技巧**：`ST_` 是 Spatial Type 的缩写，看到就知道是空间函数。

## 3.5 【重点】度 vs 米 —— 本项目最大的一个坑

这是你现在最该记住的一条。

在 4326 坐标系下，`ST_Length(geom)` 返回的单位是**度**，不是米！

实测（示例轨迹那条线）：

```sql
SELECT ST_Length(geom) FROM track WHERE external_id = 'SAMPLE-001';
-- 0.085967  ← 单位是"度"，不是"米"
```

0.085967 度是多少米？你没法心算，因为**一度在不同纬度对应的距离不一样**（赤道约 111 公里，北京约 85 公里）。

正确做法是把几何转成 `geography` 类型：

```sql
SELECT ST_Length(geom::geography) FROM track WHERE external_id = 'SAMPLE-001';
-- 9444.243...  ← 单位是米
```

`::geography` 的意思是：请用「地球是球体」的算法来算，自动按米输出。

**于是有了一个经典矛盾**（你已经在 EXPLAIN 里见过）：

- `ST_DWithin(geom, 点, 0.01)` —— 快，能用空间索引，但 0.01 的单位是度，不直观
- `ST_DWithin(geom::geography, 点, 1000)` —— 慢，因为 `geom::geography` 是个**计算表达式**，索引对它无能为力，只能逐行算

实测证据（EXPLAIN 输出）：

```
-- 写法 A：直接用 geom
Index Scan using idx_track_point_st
  Index Cond: ((geom && st_expand(...)) AND (recorded_at >= ... ))

-- 写法 B：转成 geography
Bitmap Index Scan on idx_track_point_st
  Index Cond: (recorded_at >= ...)     ← 只剩时间条件走了索引
  Filter: st_dwithin((geom)::geography, ...)   ← 空间条件退化成逐行过滤
```

**结论**：能接受「度」作单位时，就用 `geom` 保住索引；必须精确到米时，接受性能代价，或者把数据投影到米制坐标系（本项目暂不做）。

## 3.6 空间索引 GiST

普通 B-tree 索引解决的是「一维排序」问题（比如按 id、按时间）。经度和纬度是**两个维度**，B-tree 排不过来。

GiST（Generalized Search Tree，通用搜索树）就是为多维数据设计的索引类型。

```sql
CREATE INDEX idx_track_point_st ON track_point USING GIST (geom, recorded_at);
```

创建时要写 `USING GIST`，不写默认是 B-tree。

**索引为什么快**：没有索引时数据库要逐行检查（Parallel Seq Scan）；有索引时它先用几何的「外接矩形」快速排除掉绝大部分行，只对剩下几行做精确计算。

## 3.7 复合索引 GIST(geom, recorded_at)

我们建的是「时空联合索引」——同时索引空间和时间两个维度。

为什么需要？因为真实查询几乎总是**带时间范围**的：

```sql
-- "昨天下午 2 点到 3 点之间，这条轨迹经过了哪些地方"
SELECT * FROM track_point
WHERE geom && ST_MakeEnvelope(...)      -- 空间条件
  AND recorded_at >= '2026-09-08 14:00+08'  -- 时间条件
  AND recorded_at <  '2026-09-08 15:00+08';
```

如果只有空间索引，时间条件还得逐行过滤；复合索引可以一次搞定。

## 3.8 怎么看 EXPLAIN

`EXPLAIN` 是数据库的「执行计划说明书」。加 `ANALYZE` 会真的执行并给出实际耗时：

```sql
EXPLAIN ANALYZE SELECT ...;
```

看输出时重点看两处：

| 看到什么 | 说明 |
| --- | --- |
| Seq Scan / Parallel Seq Scan | 全表扫描，没用索引（慢） |
| Index Scan / Bitmap Index Scan | 用了索引（快） |
| Index Cond | 在索引里就完成了过滤（好） |
| Filter | 取出行之后才过滤（差，白读了） |

**「条件出现在 Filter 里」是索引没生效的典型信号。**

## 3.9 实测数据（你自己跑出来的）

在 30 万个随机点上做的对比：

| 场景 | 耗时 |
| --- | --- |
| 无索引，全表扫描 | 106.576 ms |
| GiST 空间索引 | 1.138 ms |
| 复合索引 GIST(geom, recorded_at) | 0.537 ms |

约 **94 倍** 的提升。这就是空间索引存在的意义。

---

# 4. 知识点二：数据库表设计

## 4.1 三张表

| 表 | 存什么 | 量级 |
| --- | --- | --- |
| track | 一条轨迹（一次出行）的元数据 | 少（几千条） |
| track_point | 轨迹上的每个 GPS 点 | 多（百万级） |
| stay_point | 停留点（在某个地方待了一会儿） | 中（M2 才用） |

## 4.2 为什么 track 要存「派生数据」

`track` 表里的 `distance_m`、`duration_s`、`point_count`、`geom` 其实**都能从 track_point 算出来**，为什么要存一遍？

因为：

- 列表页要显示「9.4 公里 / 50 分钟」，如果每次都要把 121 个点（真实数据是几千个）查出来算一遍，太慢
- 这是典型的「用空间换时间」——多占一点存储，换来查询快

代价是：**数据可能不一致**。如果新增了一个点却忘了更新 `distance_m`，两边就对不上了。所以这类字段通常由导入程序统一回填（我们的 `02-sample-track.sql` 最后那段 UPDATE 就是在干这事）。

## 4.3 为什么 track_point 存 geom 而不是 lon/lat 两列

也可以存成 `lon double, lat double` 两列。但那样：

- 没法用 `ST_DWithin`、`ST_Length` 这些空间函数
- 没法建空间索引

存成 `geometry(Point,4326)` 一列，空间能力全都免费获得。需要单独取经纬度时，用 `ST_X(geom)`、`ST_Y(geom)` 拆开就行。

**这是「为查询方式设计表结构」的典型例子。**

## 4.4 幂等脚本

我们的 SQL 脚本都写成「跑一次和跑十次结果一样」：

```sql
CREATE TABLE IF NOT EXISTS track (...);
CREATE INDEX IF NOT EXISTS idx_xxx ON ...;
DELETE FROM track WHERE external_id = 'SAMPLE-001';
```

这叫**幂等**（idempotent）。好处是：出错了直接重跑，不用担心「表已存在」报错，也不用先手动清理。

---

# 5. 知识点三：psql 与编码

## 5.1 psql 是什么

psql 是 PostgreSQL 的官方命令行客户端。你在 PowerShell 里敲：

```powershell
psql -U postgres -d calcite
```

就是「以 postgres 用户身份，连到 calcite 库」。

## 5.2 交互式 vs 执行文件

| 方式 | 命令 | 特点 |
| --- | --- | --- |
| 交互式 | psql -U postgres -d calcite | 进入 `calcite=#` 提示符，敲一句执行一句 |
| 执行文件 | psql -f 脚本.sql | 一次性跑完整个文件，不进入提示符 |

**你之前看到「屏幕几乎全黑、退不出来」就是进了交互式模式。** 那时候：

- 如果进了**分页器**（输出很长时），按 `q` 退出
- 如果进了 **psql 提示符**，敲 `\q` 退出

后来改用 `-f 文件` + `-P pager=off` 就再也不会卡住了。

## 5.3 【坑】GBK 编码报错

你遇到过的报错：

```
错误: 编码"GBK"的字符 0x0xa6 0xbb在编码"UTF8"没有相对应值
```

**原因**：中文版 Windows 的控制台默认代码页是 936（GBK）。psql 读你的 SQL 文件时，默认按 GBK 去解码，但文件本身是 UTF-8 存的，中文就解码失败了。

**解决**：在 SQL 文件的**第一行**写：

```sql
\encoding UTF8
```

必须是第一行。如果放在中文注释后面，前面的中文已经按 GBK 解错了，来不及救。

**为什么我之前没发现**：我这边的控制台是 UTF-8，同一条命令跑得好好的。「我这儿能跑」不等于「你那儿能跑」——这是环境差异，不是你的操作问题。

## 5.4 【坑】提示行 `(1 行记录)` 乱码

修好数据编码后，你发现数据中文正常了，但最后一行 `(1 行记录)` 变成 `(1 �м�¼)`。

**原因**：这是两套编码混在一起——

| 内容 | 编码来源 |
| --- | --- |
| 中文数据（表里的 name） | 我们设的 UTF8 |
| psql 自己的提示信息 | 跟随系统语言 = GBK |

**解决**：跑之前让 psql 说英文：

```powershell
$env:LC_MESSAGES='C'
```

实测对照：

| 设置 | 输出 |
| --- | --- |
| LC_MESSAGES=zh_CN.UTF-8 | (1 �м�¼) |
| LC_MESSAGES=C | (1 row) |
| -P footer=off | 不显示这行 |

## 5.5 为什么控制台看不到中文

即使前面都设置对了，你的控制台仍可能显示不出中文——因为**控制台的字体和代码页**两件事都要对：

- 代码页：`chcp 65001` 切到 UTF-8
- 字体：必须是含中文字形的字体（如「新宋体」「Consolas + 回退」）

**最省事的办法**：别跟控制台较劲，把结果写进文件，用编辑器看：

```powershell
psql ... -o 输出.txt -f 脚本.sql
code 输出.txt
```

VS Code 认 UTF-8，中文一定正常。而且日志写文件本来就是更专业的做法。

---

# 6. 知识点四：Spring Boot 后端分层

## 6.1 一个请求怎么走

以 `GET /api/tracks/1` 为例：

```
浏览器/curl
   ↓ HTTP GET
TrackController        ← 接收请求，决定调谁
   ↓ 调用
TrackRepository        ← 去数据库查
   ↓ JPA/Hibernate
PostgreSQL + PostGIS   ← 真正执行 SQL
   ↑ 返回实体对象
TrackController        ← 转成 DTO
   ↑ JSON
浏览器
```

每一层只负责一件事，这叫**单一职责**。

## 6.2 Controller（控制层）

```java
@RestController
@RequestMapping("/api/tracks")
public class TrackController {
    @GetMapping("/{id}")
    public TrackDetail detail(@PathVariable Long id) { ... }
}
```

- `@RestController` = 这个类的返回值直接变成 JSON
- `@RequestMapping("/api/tracks")` = 类里所有接口的公共前缀
- `@GetMapping("/{id}")` = 处理 GET 请求，URL 里带一个变量
- `@PathVariable` = 把 URL 里的 `{id}` 绑到方法参数

**Controller 的职责**：接请求、做参数校验、调用下层、返回结果。**不该写业务逻辑和 SQL。**

## 6.3 Repository（持久层）

```java
public interface TrackRepository extends JpaRepository<Track, Long> {
    Optional<Track> findByExternalId(String externalId);
}
```

就一个接口，**一行实现都不用写**，Spring Data JPA 自动生成实现。

魔法在于**方法名**：`findByExternalId` 会被翻译成

```sql
SELECT * FROM track WHERE external_id = ?
```

我们的另一个例子：

```java
List<TrackPoint> findByTrackIdOrderBySeqAsc(Long trackId);
-- → SELECT * FROM track_point WHERE track_id = ? ORDER BY seq ASC
```

这叫「方法名派生查询」（Query Derivation）。规则很直观：`findBy` + 字段名 + `And/Or` + `OrderBy` + 字段名 + `Asc/Desc`。

## 6.4 Entity / JPA

**Entity（实体）就是「一张表的 Java 化身」**：

```java
@Entity
@Table(name = "track")
public class Track {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "distance_m")
    private Double distanceM;
}
```

- `@Entity` 告诉 JPA：这是个实体
- `@Table(name="track")` 对应哪张表
- `@Id` 主键，`@GeneratedValue(IDENTITY)` 表示「由数据库自增生成」
- `@Column(name="distance_m")` 对应哪一列

**JPA 是什么**：Java Persistence API，一套标准接口。Hibernate 是它的实现。

**ORM 的价值**：不用手写 `rs.getString("name")` 这种繁琐的映射代码，Java 对象和表行自动对应。

**注意**：实体必须有一个无参构造器（JPA 反射要用），所以我们写了 `protected Track() {}`。

## 6.5 DTO（数据传输对象）

```java
public record TrackSummary(Long id, String name, Double distanceM, ...) {
    public static TrackSummary from(Track track) { ... }
}
```

为什么不让 Controller 直接返回实体？三个理由：

1. 实体里的 `geom` 是 JTS 对象，Jackson 直接序列化会输出一堆内部结构，前端没法用
2. 列表页不需要坐标，返回是浪费带宽
3. 实体是「数据库的样子」，DTO 是「接口的样子」。分开后，改数据库不会直接破坏前端

`record` 是 Java 16+ 语法，一行声明不可变数据类，自动生成构造器、getter、equals、hashCode、toString。getter 名字是 `id()` 而不是 `getId()`。

## 6.6 hibernate-spatial 干了什么

没有它，Hibernate 不认识 JTS 的 `Point` / `LineString`，会报「未知类型」。

有了它，可以这样写：

```java
@Column(columnDefinition = "geometry(Point,4326)")
private Point geom;
```

启动日志里的这一行就是证据：

```
hibernate-spatial integration enabled : true
```

## 6.7 ddl-auto 为什么从 update 改成 none

`ddl-auto` 控制 Hibernate 启动时对表结构做什么：

| 值 | 行为 |
| --- | --- |
| update | 按实体类自动建表、加字段（学习期方便，生产危险） |
| validate | 只检查，不修改 |
| none | 完全不管，表结构由 SQL 脚本负责 |

**我们改成了 none**，因为：

- `geometry(Point,4326)` 这种列类型是 PostGIS 特有的，让 Hibernate 去「自动补」容易改坏
- 表结构应该由版本化的 SQL 脚本（`scripts/db/01-schema.sql`）统一管理，可追溯、可重放

---

# 7. 知识点五：HTTP / REST / JSON

## 7.1 REST 是什么

一种「用 URL 表示资源、用 HTTP 动词表示操作」的接口风格。

| 动词 | 含义 | 例子 |
| --- | --- | --- |
| GET | 读取 | GET /api/tracks 查列表 |
| POST | 新建 | POST /api/tracks 新增轨迹 |
| PUT | 全量更新 | PUT /api/tracks/1 |
| DELETE | 删除 | DELETE /api/tracks/1 |

M1 阶段我们只做了 GET（读）。

## 7.2 我们定义的两个接口

| 接口 | 返回 |
| --- | --- |
| GET /api/tracks | 轨迹列表（不含坐标） |
| GET /api/tracks/{id} | 单条轨迹 + 全部点（含 lon/lat） |

实测结果：

```json
// GET /api/tracks
{
  "id": 1,
  "name": "北京城区骑行 · 天安门→奥林匹克公园",
  "source": "sample",
  "distanceM": 9444.243723726955,
  "durationS": 3000,
  "pointCount": 121
}
```

```json
// GET /api/tracks/1 的前两个点
{
  "seq": 0,
  "recordedAt": "2026-09-07T23:30:00Z",
  "lon": 116.3974099578142,
  "lat": 39.90930476180898,
  "elevationM": 40.0,
  "speedMps": null
}
```

**注意时间**：`2026-09-07T23:30:00Z` 结尾的 `Z` 表示 UTC。北京时间 07:30 就是 UTC 前一天 23:30。前端负责转成本地时间显示。

## 7.3 为什么找不到要返回 404

```java
.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "轨迹不存在"))
```

返回 404 而不是 200 + 空对象，是为了让前端能**明确区分**「没有这条数据」和「查到了但是空的」。

---

# 8. 知识点六：Vue3 + Vite + Cesium

## 8.1 三者分工

| 名字 | 是什么 | 一句话 |
| --- | --- | --- |
| Vue | 前端框架 | 把页面拆成一个个组件 |
| Vite | 构建工具 + 开发服务器 | 把你写的代码变成浏览器能跑的东西，并提供 5173 这个地址 |
| Cesium | 三维地球库 | 在网页里画地球、点、线、面 |

**它们不是三个平行的东西**：Vue 是骨架，Vite 是工具，Cesium 是被 Vue 组件用起来的一个库。

## 8.2 Vue 组件

一个 `.vue` 文件 = 一个组件，三段式：

```vue
<script setup>
// 逻辑：变量、函数、生命周期
</script>

<template>
  <!-- 结构：HTML -->
</template>

<style scoped>
/* 样式，scoped 表示只作用于本组件 */
</style>
```

我们的 `CesiumGlobe.vue` 就是一个组件：它在 `onMounted` 时创建 Cesium 地球，在 `onBeforeUnmount` 时销毁它（防止内存泄漏）。

## 8.3 Vite 是什么，5173 从哪来

Vite 有两个身份：

1. **开发服务器**：`npm run dev` 启动，监听 5173。你改代码它立刻热更新，浏览器自动刷新
2. **打包工具**：`npm run build` 把代码编译压缩到 dist/，用于部署

`vite.config.js` 里我们还配了一件事——**代理**：

```js
server: {
  proxy: { '/api': 'http://localhost:8080' }
}
```

意思是：浏览器请求 `http://localhost:5173/api/tracks` 时，Vite 转发给 `http://localhost:8080/api/tracks`。

**为什么需要**：浏览器有「同源策略」，5173 的页面直接请求 8080 会被拦截（跨域）。用代理转发，浏览器以为请求的还是 5173，就不存在跨域问题了。

## 8.4 Cesium 为什么在浏览器里

Cesium 用 WebGL 在 `<canvas>` 上绘制三维图形。`<canvas>` 是 HTML 元素，**只有浏览器能渲染**。

所以：

- PowerShell 里永远看不到地球，这是正常的
- 要看效果 → 打开浏览器 → http://localhost:5173

创建地球的核心代码（`CesiumGlobe.vue`）：

```js
const viewer = new Viewer(container, {
  baseLayer: ImageryLayer.fromProviderAsync(
    TileMapServiceImageryProvider.fromUrl(
      buildModuleUrl('Assets/Textures/NaturalEarthII')
    )
  ),
  baseLayerPicker: false,
  // ... 各种 UI 控件关掉
})

viewer.camera.setView({
  destination: Cartesian3.fromDegrees(116.4, 39.9, 12000000)
})
```

几个点：

- `Viewer` 是 Cesium 的主入口，创建它就有了地球
- `baseLayerPicker: false` 是必须的，否则 `baseLayer` 参数不生效
- `Cartesian3.fromDegrees(经度, 纬度, 高度)` 把经纬度转成三维坐标
- `12000000` 是相机高度（米），1200 万米约等于从太空看地球

## 8.5 离线底图 NaturalEarthII

地球需要有「皮肤」（影像贴图），否则只是个白球。

我们用的是 Cesium **自带的离线底图** NaturalEarthII（自然地球，低分辨率世界地图）：

```
node_modules/cesium/Build/Cesium/Assets/Textures/NaturalEarthII
```

**为什么不用在线地图**：在线底图（Cesium ion、高德、天地图）要么需要 token，要么需要联网。我们先用离线的，**不需要 token、不需要联网**，保证一定能跑起来。以后想换成高清影像，改这一行就行。

## 8.6 vite-plugin-static-copy 为什么必须

Cesium 运行时需要加载一堆**静态资源**：贴图、Web Worker 脚本、第三方库。它们不在 JavaScript 打包范围内，Vite 默认不会处理。

`vite-plugin-static-copy` 就是干这个的：把 Cesium 的 `Assets/`、`Widgets/`、`Workers/`、`ThirdParty/` 四个目录复制到构建产物里。

配置里有个 `rename: { stripBase: 4 }`，作用是**去掉多余的前缀**，让文件落在 `dist/cesiumStatic/Assets/...` 而不是 `dist/cesiumStatic/node_modules/cesium/Build/Cesium/Assets/...`。

同时 `vite.config.js` 里设了：

```js
define: { CESIUM_BASE_URL: JSON.stringify('/cesiumStatic') }
```

告诉 Cesium：「你的静态资源在 /cesiumStatic 这个路径下」。这个常量在 Cesium 里是个裸的全局变量，所以只能用 Vite 的 `define` 注入。

---

# 9. 一次完整请求的旅程（把所有知识点串起来）

用户在浏览器点「查看轨迹 1」：

1. **Vue 组件** 发出 `fetch('/api/tracks/1')`
2. **Vite 开发服务器（5173）** 收到，因为配了代理，转发到 `http://localhost:8080/api/tracks/1`
3. **Tomcat（8080）** 收到 HTTP GET 请求
4. **TrackController.detail(1)** 被调用
5. 它调 **TrackRepository.findById(1)**
6. **Hibernate** 把方法翻译成 SQL：
   ```sql
   SELECT ... FROM track WHERE id = 1
   ```
7. **PostgreSQL + PostGIS** 执行 SQL，返回一行数据
8. Hibernate 把行**映射成 Track 对象**（其中 geom 列通过 hibernate-spatial 变成 JTS LineString）
9. Controller 把 Track 转成 **TrackDetail DTO**，坐标拆成 lon/lat
10. **Jackson** 把 DTO 序列化成 **JSON**
11. JSON 沿原路返回浏览器
12. **Cesium** 用 `Cartesian3.fromDegrees(lon, lat, 高度)` 把每个点变成三维坐标，`Polyline` 把它们连成线，画在地球上

这条链路上任何一环断了，你都会看到不同的报错。学会**定位是哪一环**，比记住代码更重要。

---

# 10. 你踩过的坑：对照表

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 编码"GBK"的字符 0x0xa6 0xbb在编码"UTF8"没有相对应值 | psql 按 GBK 读 UTF-8 文件 | SQL 文件第一行加 `\encoding UTF8` |
| 中文数据正常，但 `(1 行记录)` 乱码 | psql 提示信息跟随系统语言（GBK），数据是 UTF-8 | 跑前 `$env:LC_MESSAGES='C'` |
| 中文数据在控制台全是乱码 | 控制台代码页/字体不支持 UTF-8 | 用 `-o 文件` 输出到文件，`code 文件` 打开 |
| 屏幕几乎全黑、退不出来 | 进了 psql 交互模式或分页器 | 按 `q` 退分页器，敲 `\q` 退 psql |
| LWGEOM_dwithin: Operation on mixed SRID geometries (Point, 4326) != (Point, 0) | ST_MakePoint 造出的点 SRID 是 0，和表里的 4326 不匹配 | 用 `ST_SetSRID(ST_MakePoint(...), 4326)` 包一层 |
| 空间查询很慢 | 条件写成了 `geom::geography`，表达式让索引失效 | 能接受「度」为单位时直接用 `geom` |
| 端口 8080 已被占用 | 后端已经启动了一个实例 | 先停掉旧的，或改 `server.port` |
| spawn EPERM（跑 vite 时） | 沙箱限制，不是代码问题 | 提权运行 |
| 打开 localhost:5173 没反应 | 前端开发服务器没启动 | 在 frontend 目录执行 `npm run dev` |
| 打开 localhost:8080 显示 404 | 后端只有 /api/* 接口，根路径没内容 | 访问 `/api/health` 或 `/api/tracks` |

---

# 11. 术语表

| 英文 | 中文 | 一句话解释 |
| --- | --- | --- |
| SRID | 空间参考系统编号 | 4326 = 经纬度（WGS84），单位度 |
| geometry | 几何 | PostGIS 的列类型，存点/线/面 |
| geography | 地理 | 同样存几何，但按球体算，单位米 |
| GiST | 通用搜索树 | 多维数据的索引类型 |
| ST_ | 空间类型函数前缀 | 如 ST_Length、ST_DWithin |
| ORM | 对象关系映射 | Java 对象 ↔ 数据库表的翻译 |
| JPA | Java 持久化 API | ORM 的标准接口 |
| Entity | 实体 | 一张表的 Java 类 |
| Repository | 仓储 | 负责数据库读写的接口 |
| DTO | 数据传输对象 | 专门用于接口传输的数据结构 |
| REST | 表述性状态转移 | 用 URL + HTTP 动词表示操作的风格 |
| JSON | JavaScript 对象表示法 | 前后端交换数据的文本格式 |
| CORS | 跨域资源共享 | 浏览器的同源策略限制 |
| proxy | 代理 | Vite 把 /api 请求转发给后端 |
| idempotent | 幂等 | 执行一次和多次结果相同 |
| EXPLAIN | 执行计划 | 数据库告诉你会怎么执行这条 SQL |

---

# 12. 动手练习

按顺序做，每一步都有明确结果。**不要跳过第 1 步**，它是理解后面一切的基础。

## 练习 1：确认前端地图真的在跑

1. 打开浏览器（Edge 或 Chrome）
2. 地址栏输入 `http://localhost:5173` 回车
3. 应该看到一个**三维地球**，能鼠标拖动旋转

如果打不开，在 PowerShell 里跑：

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
npm run dev
```

**这一步的目的**：亲眼确认「地图在浏览器里，不在 PowerShell 里」。

## 练习 2：用浏览器直接看接口

地址栏输入：

```
http://localhost:8080/api/tracks
```

应该看到一段 JSON。

再输入：

```
http://localhost:8080/api/tracks/1
```

应该看到轨迹详情，里面有 121 个点。

**这一步的目的**：理解「接口就是一段可以被浏览器打开的 URL」。

## 练习 3：故意制造一个 404

```
http://localhost:8080/api/tracks/999
```

看到 404 页面。**这一步的目的**：理解 HTTP 状态码的含义。

## 练习 4：在 psql 里验证「度 vs 米」

把下面存成 `E:\JAVA_IDEA_package\JAVA_Project\Calcite\.tmp\test-degree.sql`：

```sql
\encoding UTF8
SELECT
  ST_Length(geom)              AS length_in_degrees,
  ST_Length(geom::geography)   AS length_in_meters
FROM track
WHERE external_id = 'SAMPLE-001';
```

然后跑：

```powershell
$env:PGPASSWORD='557096138Cc'
$env:LC_MESSAGES='C'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -d calcite -P pager=off -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\.tmp\test-degree.sql"
```

看到 0.085967 和 9444.24 两个数。**这一步的目的**：亲手体验单位差异。

## 练习 5：看 EXPLAIN 长什么样

```sql
\encoding UTF8
EXPLAIN
SELECT * FROM track_point
WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(116.3974, 39.9093), 4326), 0.01);
```

留意输出里有没有 `Index Scan` 和 `Index Cond`。

## 练习 6：改一行前端代码，看热更新

打开 `frontend\src\App.vue`，随便改一句文字，保存。浏览器**不用刷新**就会变——这就是 Vite 热更新。

---

# 13. 命令速查

## 启动服务

```powershell
# 后端（在 IntelliJ 里点绿色 ▶ 最方便；命令行方式：）
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" spring-boot:run

# 前端
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
npm run dev
```

## 查数据库

```powershell
$env:PGPASSWORD='557096138Cc'
$env:LC_MESSAGES='C'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -d calcite -P pager=off -f "路径\脚本.sql"
```

## 看接口

```
http://localhost:8080/api/health    健康检查
http://localhost:8080/api/tracks    轨迹列表
http://localhost:8080/api/tracks/1  轨迹详情
http://localhost:5173               三维地球页面
```

## 退出 psql

- 卡在分页器：按 `q`
- 卡在 `calcite=#`：敲 `\q`

---

# 14. 阶段小结

第一阶段（M1「看得见」）完成了：

- 环境跑通：PostgreSQL 18.3 + PostGIS 3.6 + Spring Boot 3.5.16 + Vue 3.5.42 + Cesium 1.145
- 数据库：三张表 + 5 个索引，示例轨迹 121 点 / 9444.2 米 / 50 分钟
- 后端：两个 GET 接口，能从 PostGIS 读出数据变成 JSON
- 前端：三维地球能显示（离线底图，无需 token）
- 空间索引实测：106 ms → 1.1 ms

**还差最后一步**：把轨迹画到地球上（前端拉接口 + Cesium Polyline）。

不急，先把上面这些消化掉。等你觉得「第 9 节那条链路我能自己讲一遍」了，再继续。
