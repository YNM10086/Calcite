# Calcite 项目结构地图

> **这份笔记不讲算法，只讲「东西在哪、怎么流动、以后往哪加」。**
>
> 前面两份（《第一阶段学习笔记》《第二天学习笔记》）讲的是知识点——PostGIS 怎么用、回放怎么做、曲线怎么画，那些是**地形**。
> 这一份是**地图**。地形看不动的时候，回来看地图，先搞清楚自己在哪一层。

## 0. 这份笔记怎么用

你不需要背它。它有三个使用场景：

| 场景 | 看哪一章 |
| --- | --- |
| 「我完全不知道这个项目是怎么回事」 | 第 1 章 + 图 1，看五分钟就够 |
| 「我要加个功能，但不知道从哪下手」 | 第 9 章（放哪里）+ 第 11 章（改哪几个文件） |
| 「这个文件到底是干嘛的」 | 第 2 章（目录结构）+ 第 3 章（流程） |

**最重要的一句**：你不需要懂每一层的内部算法。你只需要知道**每一层负责什么、边界在哪**，剩下的用到再钻。

---

## 1. 总览：四层结构

![图 1 · Calcite 总体架构](docs/learning/figs/fig1-arch.png)

整个项目就是**四个盒子**，每个盒子只跟相邻的盒子说话：

| 层 | 是什么 | 跑在哪 | 端口 | 它挂了会怎样 |
| --- | --- | --- | --- | --- |
| 浏览器 | 你看到的画面 | 你的 Chrome | — | 白屏 |
| 前端 | Vue 代码 | Vite 开发服务器 | 5173 | 页面打不开 |
| 后端 | Java 代码 | Spring Boot | 8080 | 页面能打开，但数据加载失败 |
| 数据库 | 存数据的地方 | PostgreSQL + PostGIS | 5432 | 后端能启动，但查询全报错 |

**记住这张表的最后一列**。以后出问题，先看「哪一层挂了」，就能立刻判断该去查谁。比如「页面能打开但列表一直转圈」→ 后端或数据库的问题，跟前端代码无关。

### 1.1 为什么是四层，不是两层

理论上你可以写一个程序直接读数据库、直接在屏幕上画图。但那样会变成一坨。分成四层的实际好处：

- **前端改样式不影响数据库**：你想换个曲线颜色，不用碰 Java，更不用碰 SQL
- **后端可以换实现**：以后想把 Spring Boot 换成别的框架，前端的 `fetch('/api/...')` 一行都不用改
- **每层都能单独测**：纯计算逻辑（`lib/`）能用 node 秒测，不用开浏览器

这就是「分层」的全部意义：**让改动局限在一层里**。

---

## 2. 目录结构：每个格子负责什么

![图 2 · 目录结构地图](docs/learning/figs/fig2-tree.png)

补充几个容易搞混的：

| 路径 | 一句话 | 常见误解 |
| --- | --- | --- |
| `backend/` 和 `frontend/` | **两个完全独立的项目**，各有自己的依赖清单 | 不是「一个项目里两个文件夹」，它们甚至用不同的包管理器 |
| `backend/pom.xml` | Java 的依赖清单（Maven） | 只有这里加依赖，Java 才认识新库 |
| `frontend/package.json` | JS 的依赖清单（npm） | 同上，只有这里加依赖，JS 才认识新包 |
| `scripts/db/` | 数据库的**唯一真相** | 表结构在这里手写，不是 Hibernate 自动建的（`ddl-auto: none`） |
| `frontend/src/lib/` | 纯计算，没有界面 | 不要在这里 `import` Vue 或 Cesium，否则就没法用 node 测了 |
| `docs/` | 先写文档再写代码 | 顺序反了的话，改到一半会不知道自己要做什么 |

### 2.1 node_modules 和 .m2 是什么

你会在项目里看到 `frontend/node_modules/` 和 `.m2/repository/` 这两个很大的目录：

- 它们是**下载下来的依赖包本体**，不是你写的代码
- 它们**不进 git**（在 `.gitignore` 里），因为它们可以由 `package.json` / `pom.xml` 重新下载出来
- 所以「换台电脑怎么跑起来」的答案是：拷代码 + 重新 `npm install`

---

## 3. 核心流程一：启动项目时发生了什么

这个项目**要同时开两个服务器**，很多人一开始会懵：「为什么不是一个？」

因为前端和后端是**两个独立的程序**，各自需要自己的运行环境（一个跑 Java，一个跑 Node）。

### 3.1 启动后端（`mvn spring-boot:run`）

```
① Maven 读 backend/pom.xml，按清单把依赖从 .m2 里找出来
② 编译 src/main/java 下的 .java 文件
③ 启动 Spring Boot，它会扫描 com.calcite 包，找出所有带注解的类
④ 读到 application.yml → 激活 local 配置 → 连上 PostgreSQL（5432）
⑤ 启动内嵌的 Tomcat，监听 8080
   → 这时候访问 http://localhost:8080/api/health 会返回 JSON
```

**第 ③ 步是 Spring 的核心魔法**：你从来没写过「把 TrackController 注册到路由表」这种代码，Spring 靠**扫描包 + 看注解**自动完成。所以类必须放在 `com.calcite` 下面，放外面就扫不到。

### 3.2 启动前端（`npm run dev`）

```
① npm 读 frontend/package.json，确认依赖都在 node_modules 里
② 执行 "dev": "vite" 这条脚本
③ Vite 读 vite.config.js：
     - 设置端口 5173
     - 设置代理：/api → http://localhost:8080
     - 把 Cesium 的 Workers/Assets/Widgets 拷到 cesiumStatic 目录
④ Vite 启动开发服务器，监听 5173，同时开始「盯着」src 下每个文件
   → 你保存任何文件，浏览器自动刷新（热更新）
```

**第 ③ 步的代理很关键**。浏览器有个安全限制叫「跨域」：`localhost:5173` 的页面默认不允许请求 `localhost:8080`。代理的作用是——请求先发给 5173，由 Vite 在**服务器端**转发给 8080，浏览器就以为一切正常。

所以你的前端代码里永远写 `fetch('/api/tracks')`，**不用写完整的 8080 地址**。

### 3.3 常见启动问题对照

| 现象 | 多半是 |
| --- | --- |
| 前端报 `spawn EPERM` | 沙箱限制了 Vite 探测路径，需要提权 |
| 后端启动报连接失败 | PostgreSQL 服务没开，或密码不对 |
| 页面能开但列表空 | 后端没起来（前端的代理转发失败） |
| 两个都开着但端口冲突 | 上一次的进程没退干净 |

---

## 4. 核心流程二：打开页面到地图出现

```
① 浏览器请求 http://localhost:5173
② Vite 返回 index.html —— 里面只有一个空的 <div id="app">
③ 浏览器继续请求 /src/main.js
④ main.js 执行 createApp(App).mount('#app')
     → Vue 把 App.vue 渲染成一堆真实 DOM 塞进那个空 div
⑤ CesiumGlobe.vue 挂载时初始化 Cesium，去 /cesiumStatic 取 Workers 和贴图
⑥ 同一时间，App.vue 的 onMounted 发起两个请求：
     fetch('/api/health')  → 底部状态条显示「后端已连接」
     fetch('/api/tracks')  → 左侧列表显示轨迹
```

**第 ④ 步解释了一个常见困惑**：`index.html` 里为什么几乎是空的？因为**页面是 JS 现场生成的**，不是写死在 HTML 里的。这也是为什么「查看网页源代码」看不到内容——那是 `index.html` 的原文，而你看到的画面是 Vue 后来画上去的。

**第 ⑤ 步解释了一个小坑**：Cesium 的很多文件（Web Worker、地球贴图）**不能被打包器处理**，必须原样拷贝出来。这就是 `vite.config.js` 里 `viteStaticCopy` 存在的原因。少了它，地球会变成一片黑。

---

## 5. 核心流程三：点一条轨迹，数据走完全程

![图 3 · 点一条轨迹，数据经历了什么](docs/learning/figs/fig3-journey.png)

这是**全项目最重要的一张图**。逐段说明，并标注「改这里会影响什么」：

| 步骤 | 发生什么 | 改这里会影响 |
| --- | --- | --- |
| ①→② | 点击 → `TrackList` 发出事件 → `App.vue` 更新 `selectedId` | 列表的显示样式 |
| ③ | `App.vue` 发 `fetch('/api/tracks/1')` | 请求的 URL、参数 |
| ④ | Vite 把 `/api` 转发到 8080 | 后端地址变了要改 `vite.config.js` |
| ⑤ | `TrackController.detail(1)` 收到请求 | 返回什么字段、找不到时怎么办 |
| ⑥⑦ | 两个 Repository 分别查轨迹和它的所有点 | 查数据的条件、排序 |
| ⑧ | PostgreSQL 用索引 `(track_id, seq)` 取行 | 查询快慢 |
| ⑨ | 实体（Entity）转成 DTO | 发给前端的**字段名和格式** |
| ⑩ | `App.vue` 存进 `detail.value` | — |
| ⑪ | 三个子组件同时收到 `points` 开始画 | 画面长什么样 |

### 5.1 这条流程里最重要的三个「分界点」

**分界点一：③ 和 ⑤ 之间是 HTTP。**
跨过这条线，数据就从「JavaScript 对象」变成「JSON 文本」。所以两边必须约定好字段名——这个约定就是 DTO 的形状。

**分界点二：⑦ 和 ⑧ 之间是 SQL。**
跨过这条线，数据从「Java 对象」变成「数据库的行」。这条线由 Repository 负责，**Controller 里不该有 SQL**。

**分界点三：⑩ 和 ⑪ 之间是 props。**
`App.vue` 把 `points` 传给三个子组件，子组件**只负责显示**，不自己存状态。

### 5.2 为什么 121 个点要传两遍

你会注意到 `points` 被三个组件各用了一次：

- `CesiumGlobe` 要经纬度来画线和让点动
- `SpeedChart` 要时间、速度、海拔来画曲线
- `TrackPlayer` 要起止时间来算总时长

它们**用的是同一份数据**，只是各取所需。这也是为什么数据只存在 `App.vue` 一份——避免出现「地球上有 121 个点、曲线上只有 100 个点」这种不一致。

---

## 6. 后端的分层

![图 4 · 后端为什么要分四层](docs/learning/figs/fig4-backend.png)

| 层 | 文件夹 | 职责 | **不该做的事** |
| --- | --- | --- | --- |
| 接口层 | `web/` | 收请求、决定返回什么、抛 404 | 不写 SQL |
| 传输对象 | `web/dto/` | 定义「发给前端的形状」 | 不放业务逻辑 |
| **业务层** | **`service/`** ⭐ | **算法与编排**：清洗规则、导入流程、距离计算 | **不碰 HTTP，也不写 SQL** |
| 持久层 | `repository/` | 查/存数据库 | 不碰 HTTP |
| 实体层 | `domain/` | 数据库表的 Java 影子 | 不认识前端 |

> ⭐ **`service/` 是 2026-09-12 做 M1 轨迹导入时新增的层。**
>
> 在那之前 Controller 直接调 Repository——因为逻辑很简单，中间加一层是多余的。
> 导入功能带来了真正的业务逻辑：**格式识别 → 解析 → 清洗 → 分批入库**。
> 这些既不该塞进 Controller（那是 HTTP 的事），也不该塞进 Repository（那是数据库的事）。
>
> 这就是分层的**自然生长**：不是一开始就要有，而是逻辑复杂到一定程度后水到渠成。
> （结构地图上一版就把这件事写在第 12.1 节当"预告"，现在它发生了。）

### 6.1 Repository 的方法名就是 SQL

这是 Spring Data 最实用的一个设计：

```java
List<TrackPoint> findByTrackIdOrderBySeqAsc(Long trackId);
```

翻译成 SQL 就是：

```sql
SELECT * FROM track_point WHERE track_id = ? ORDER BY seq ASC
```

`findBy` = `WHERE`，`OrderBy` = `ORDER BY`，字段名用驼峰写法对应数据库的下划线（`trackId` ↔ `track_id`）。**你不用写一行实现代码**，只要按这个命名规则起名，框架自动生成。

### 6.2 实体和 DTO 为什么要分开

新手最容易觉得「多此一举」的就是这一层。三个理由：

1. **实体里有多余的东西**：数据库的时间戳、内部 id，不该发给前端
2. **前端要的格式不一样**：可能要把两个字段合成一个、要改名、要算个派生值
3. **解耦**：以后数据库改字段名，只要 DTO 的 `from()` 方法跟着改，**前端一行都不用动**

---

## 7. 前端的分层

![图 5 · 前端组件树与数据流向](docs/learning/figs/fig5-frontend.png)

| 文件 | 职责 | 它发出什么事件 | 它暴露什么方法 |
| --- | --- | --- | --- |
| `App.vue` | **状态中心**：选中哪条轨迹、播到第几秒、循环开不开 | — | — |
| `TrackList.vue` | 画左侧列表 | `select` | — |
| `CesiumGlobe.vue` | 画地球、轨迹线、移动的白点 | `time-change` | `play` / `pause` / `seekTo` |
| `TrackPlayer.vue` | 画底部播放条 | `toggle` / `seek` / `loop` | — |
| `SpeedChart.vue` | 画速度/海拔曲线 | `seek` | — |

### 7.1 两条数据通道

- **props（往下）**：父组件把数据传给孩子。孩子**不能改** props
- **emit（往上）**：孩子想改什么，发个事件告诉父组件，由父组件来改

还有一条特殊的：`defineExpose` + `ref`。父组件需要**主动调用**子组件的方法（比如「点播放按钮 → 让地球开始转」），就用这个。`CesiumGlobe` 暴露的 `play/pause/seekTo` 就是干这个的。

### 7.2 `lib/` 为什么单独一层

`playback.js` 和 `chart.js` 里全是纯函数，**不 import Vue、也不 import Cesium**。好处是：

- 可以用 node 直接跑断言（秒级），不用开浏览器
- 逻辑正确性和「画得好不好看」彻底分开，改样式不会弄坏计算

**判断标准**：如果一个函数只用它自己的参数就能算出结果，就该放进 `lib/`。

---

## 8. 数据库的结构

![图 6 · 数据库三张表的关系](docs/learning/figs/fig6-db.png)

### 8.1 一句话理解三张表

| 表 | 是什么 | 现在用了吗 |
| --- | --- | --- |
| `track` | 一次出行 | ✅ 在用 |
| `track_point` | 一个 GPS 点（**原始真相**） | ✅ 在用 |
| `stay_point` | 一次停留 | ⏳ 表建好了，M2 才写算法 |

### 8.2 「派生数据」这个概念

`track` 表里的 `distance_m`、`duration_s`、`point_count`、`geom`（轨迹线）**都能由 `track_point` 算出来**。为什么还要存一份？

因为**列表页只需要这些汇总值**。如果每次都去把 121 个点拉出来现算，列表有 100 条轨迹时就要算 12100 次。存一份是**用空间换时间**。

**但要记住真相在哪**：`track_point` 是唯一的原始数据。如果派生值和它不一致，永远是派生值错了，重新算一遍就行。

### 8.3 索引为什么这么建

```sql
CREATE INDEX idx_track_point_st  ON track_point USING GIST (geom, recorded_at);
CREATE INDEX idx_track_point_seq ON track_point (track_id, seq);
```

- **`(track_id, seq)`**：给「取某条轨迹的所有点，按顺序」用的——**这正是第 5 章第 ⑦ 步那个查询**。有了它，取 121 个点是直接定位，不用扫全表。
- **`GIST (geom, recorded_at)`**：空间 + 时间放在**同一个**索引里。将来做「某区域某时间段的轨迹」这种查询时，一次扫描就能过滤两个条件。

---

## 9. 以后加东西，放哪里

![图 7 · 以后要加东西，放哪里](docs/learning/figs/fig7-where.png)

### 9.1 依赖和插件放哪（你最关心的那类问题）

这是最容易搞混的地方，因为**Java 和 JS 各有一套**：

| 你想加的东西 | 文件 | 具体位置 | 装完还要做什么 |
| --- | --- | --- | --- |
| Java 库（如 Jackson、JTS） | `backend/pom.xml` | `<dependencies>` 里加 `<dependency>` | 重新启动后端 |
| Maven 构建插件 | `backend/pom.xml` | `<build><plugins>` 里 | 重新跑 Maven |
| JS 运行时要用的包 | `frontend/package.json` | `dependencies` | `npm install` |
| JS 只在开发时用的包 | `frontend/package.json` | `devDependencies` | `npm install` |
| Vite 插件 | `frontend/vite.config.js` | `plugins: [ ... ]` 数组 | 重启前端 |
| Vue 组件 | `frontend/src/components/` | 新建 `Xxx.vue` | 在 `App.vue` 里 import 并挂上 |
| 前端全局样式 | `frontend/src/style.css` | 直接写 | 自动热更新 |
| 前端静态图片 | `frontend/public/` | **这个目录还没建，要先新建** | 用 `/图片名` 访问 |

**怎么区分「运行时」和「开发时」依赖？**

- 打包进最终产品、用户那边也要跑的 → `dependencies`
- 只是你开发时帮忙的（测试工具、构建插件）→ `devDependencies`

比如 Cesium 是运行时依赖（用户要看地球），Playwright 是开发时依赖（只有你验证时用）。

**一个提醒**：`npm install xxx` 会自动往 `package.json` 里写，**不需要你手改**。而 Java 那边必须手动往 `pom.xml` 里加，加完要让 IDE 重新加载 Maven 项目。

### 9.2 加东西的三个判断问题

按顺序问自己：

1. **这东西涉及界面吗？** 不涉及 → 可能是 `lib/` 里的纯函数
2. **需要从数据库拿数据吗？** 需要 → 后端要加 Repository 方法 + Controller 端点
3. **是全新的数据种类吗？** 是 → 先加表（`scripts/db/`），再加实体类

---

## 10. 分类与命名规范

### 10.1 后端（Java）

```
com.calcite
├── CalciteApplication.java    ← 启动类，永远在根包（否则扫不到别的类）
├── domain/                    ← 实体：名词单数，首字母大写
│   ├── Track.java
│   └── TrackPoint.java
├── repository/                ← 持久层：名词 + Repository
│   ├── TrackRepository.java
│   └── TrackPointRepository.java
├── service/                   ← 业务层：算法与编排（名词 + Service / 工具类）
│   ├── GeoUtils.java              球面距离（纯静态工具）
│   ├── TrackCleaner.java          清洗规则（动词 + er）
│   ├── CleanedTrack.java          清洗结果（record）
│   ├── ImportService.java         名词 + Service
│   └── importer/                  子包：可插拔解析器
│       ├── Importer.java          接口（名词）
│       ├── RawPoint.java          统一中间结构（record）
│       ├── ParsedTrack.java
│       ├── FormatDetector.java    动词 + er
│       ├── GpxImporter.java       格式名 + Importer
│       └── GeoLifeImporter.java
├── config/                    ← 配置绑定：@ConfigurationProperties 类
│   └── ImportProperties.java      前缀名 + Properties
└── web/                       ← 接口层：名词 + Controller
    ├── HealthController.java
    ├── TrackController.java
    ├── ImportController.java
    └── dto/                   ← 传输对象：名词 + Summary/Detail/Dto
        ├── TrackSummary.java
        ├── TrackDetail.java
        ├── TrackPointDto.java
        └── ImportResult.java
```

**包名全小写，类名大驼峰，方法/变量小驼峰**——这是 Java 的铁律，不是风格偏好。

**DTO 的命名有个惯例**（看名字就知道用途）：

- `XxxSummary` —— 列表页用的精简版
- `XxxDetail` —— 详情页用的完整版
- `XxxDto` —— 通用的传输对象

### 10.2 前端（JavaScript / Vue）

| 类型 | 规范 | 例子 |
| --- | --- | --- |
| Vue 组件文件 | **大驼峰** | `SpeedChart.vue` |
| 纯逻辑文件 | **小驼峰** | `playback.js`、`chart.js` |
| 组件里的函数 | 动词开头，小驼峰 | `selectTrack`、`togglePlay`、`seekTo` |
| 常量 | 全大写 + 下划线 | `PLAY_SECONDS`、`CHART_H` |
| 事件名 | 小写 + 连字符 | `time-change`、`seek` |
| 计算属性 | 名词或 `is/has/can` 开头 | `trackPoints`、`canPlayback` |

**一个实用判断**：文件名大驼峰 = 它是个组件（有界面）；小驼峰 = 它是个工具（没界面）。看文件名就知道。

### 10.3 数据库脚本

```
scripts/db/
├── 01-schema.sql         ← 建表（编号 = 执行顺序）
├── 02-sample-track.sql   ← 灌示例数据
└── 03-show-results.sql   ← 查看结果
```

**为什么编号**：以后要加新脚本，就顺着编号加 `04-xxx.sql`。别人一看就知道该按什么顺序跑。

**一条重要纪律**：脚本要**可重复执行**（全部用 `IF NOT EXISTS`），这样重跑不会报错、也不会误删数据。

### 10.4 文档命名

```
docs/
├── learning/2026-09-08-phase1-notes.md            ← 学习笔记
├── superpowers/specs/2026-09-08-xxx-design.md     ← 设计文档
└── superpowers/plans/2026-09-09-xxx.md            ← 实施计划
```

**日期开头**，这样文件夹里天然按时间排序。`specs` 回答「做成什么样」，`plans` 回答「分几步做」。

---

## 11. 速查：我想做 X，改哪几个文件

| 我想…… | 按顺序改这些 |
| --- | --- |
| 改曲线颜色 / 布局 | `SpeedChart.vue`（只有这一个） |
| 改轨迹线的颜色 | `CesiumGlobe.vue` |
| 改播放速度 | `lib/playback.js` |
| 给轨迹列表加一列 | ① `web/dto/TrackSummary.java` 加字段 ② `TrackList.vue` 显示 |
| 加一个新接口 | ① `web/XxxController.java` ② 逻辑放 `service/` ③ 查库改 `repository/` ④ 想好 DTO |
| **加一段业务逻辑（算法/清洗/编排）** | **`service/` 下新建类**；纯计算的就别碰 Spring，写成静态方法更好测 |
| **加一种新的导入格式** | `service/importer/` 下实现 `Importer` 接口 + 在 `ImportService.pickImporter()` 里加一个 case + 在 `FormatDetector` 里加识别规则 |
| **加一个可配置项** | 标量用 `@Value`；**列表/嵌套结构用 `@ConfigurationProperties`**（放在 `config/`） |
| 加一张新表 | ① `scripts/db/04-xxx.sql` ② `domain/Xxx.java` ③ 跑脚本 |
| 改接口返回的字段名 | `web/dto/` 里对应的 `from()` 方法 + 前端用的地方 |
| 加一个 npm 包 | `frontend/package.json`（用 `npm install` 自动写） |
| 加一个 Java 库 | `backend/pom.xml` |
| 改后端端口 | `application.yml` 的 `server.port` + `vite.config.js` 的代理目标 |
| 换底图 | `CesiumGlobe.vue` 里的 imageryProvider |

---

## 12. 后面的模块会加在哪里

设计文档里规划的功能，提前知道它们会落在哪一层，就不会慌：

### 12.1 M2 · 停留点分析

| 要加的东西 | 放哪里 | 备注 |
| --- | --- | --- |
| 停留点算法 | `backend/.../service/StayPointService.java` | `service/` 包**已经存在**（M1 导入功能建的），直接往里加类即可 |
| 查询接口 | `backend/.../web/StayPointController.java` | 新文件 |
| 数据表 | `stay_point` | ✅ **已经建好了**，`scripts/db/01-schema.sql` 里 |
| 地图上的停留圆圈 | `CesiumGlobe.vue` 里加图层 | 或新建 `StayPointLayer.vue` |
| 停留点列表 | 新建 `StayPointList.vue` | 在 `App.vue` 挂上 |

> 📌 **上一版这里写着"要新建 `service/` 包"——现在它已经存在了。**
> M1 的导入功能就是那个"算法复杂到需要中间层"的时刻（见第 6 章）。

### 12.2 轨迹导入 —— ✅ **2026-09-12 已完成**

实际落地的位置（和下面这版规划略有出入，以实际为准）：

| 做的东西 | 实际放在哪 |
| --- | --- |
| 上传接口 | `web/ImportController.java`（新建的，没有塞进 TrackController） |
| 编排流程 | `service/ImportService.java` |
| 格式识别 | `service/importer/FormatDetector.java`（**按内容，不看扩展名**） |
| GPX 解析 | `service/importer/GpxImporter.java` |
| GeoLife `.plt` 解析 | `service/importer/GeoLifeImporter.java` |
| 清洗规则 | `service/TrackCleaner.java`（**所有规则只此一处**） |
| 前端上传按钮 | `TrackList.vue` 里加了按钮（没有单独开组件——就一个按钮，不值得） |

### 12.3 M3 · 轨迹相似度

| 要加的东西 | 放哪里 |
| --- | --- |
| 相似度算法 | `service/SimilarityService.java` |
| 结果缓存表 | `scripts/db/05-xxx.sql` |
| 对比界面 | 新建 `CompareView.vue` |

### 12.4 一个规律

看出来了吗？**每次加功能，都是同一套动作**：

```
需要新数据？   → 加表（scripts/db/）+ 实体（domain/）
需要新查询？   → 加 Repository 方法
需要新逻辑？   → 加 service/ 类（复杂时）
需要新接口？   → 加 Controller 端点 + DTO
需要新界面？   → 加 .vue 组件 + 在 App.vue 挂上
需要纯计算？   → 加 lib/ 里的 .js + 检查脚本
```

**这套动作你做三五次就成肌肉记忆了。** 到那时候，你就不再需要这份地图了——但在此之前，迷路就回来看第 11 章那张表。

---

## 13. 怎么自己更新这张地图

地图会过期。每次加完东西，花两分钟做这三件事：

1. **目录结构变了？** → 改 `docs/learning/figs/make_figs.py` 里的 `fig2()`，重跑一遍
2. **加了新的流程？** → 在第 5 章那张「数据旅程」表里加一行
3. **踩了新坑？** → 加到第 3.3 节的问题对照表

重新生成 Word 的命令：

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
python docs\learning\figs\make_figs.py
python scripts\tools\md2docx.py docs\learning\2026-09-10-calcite-structure-map.md 输出.docx
```

---

## 14. 最后：关于「要学的东西太多」

这份地图存在的意义，就是为了让你**不必**同时记住所有细节。

- 「底层算法怎么实现的」——用到那一个的时候再看那一个，看完就忘也没关系
- 「命名规范」——不用背，照着现有文件抄，抄多了自然记住
- 「这个项目有多少东西」——四层、三张表、五个组件。**就这么点。**

真正需要长期记住的只有一件事：

> **改任何东西之前，先问「它在哪一层」。**

答案出来了，剩下的都是细节。
