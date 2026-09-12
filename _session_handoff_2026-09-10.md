# Calcite 项目 · 会话交接文档

> **生成时间**：2026-09-10
> **生成原因**：DSH 从 `0.1.2-rc.1` 升级到 `0.1.5-rc.2`，会话历史可能不兼容，需要把上下文落成文件。
> **已核实**：`0.1.5-rc.2` 在 npm 上存在（`next` 标签；`latest` 是 `0.1.5-rc.1`）。

---

## 怎么用这份文件

升级完 DSH 后，开新会话，**第一句话**：

```
先读 E:\JAVA_IDEA_package\JAVA_Project\Calcite\_session_handoff_2026-09-10.md
和 _session_context.md，恢复上下文，然后告诉我当前进度。
```

新会话读完这两份，就等价于恢复了本会话的绝大部分记忆。

**两份文件的分工**：

| 文件 | 内容 | 长度 |
| --- | --- | --- |
| `_session_context.md` | 项目进度速查（每次开工读、收工更新） | 短 |
| **本文档** | 环境、用户偏好、决策理由、坑、命令 —— 一次性交接 | 长 |

---

## 第 0 步：升级前先备份（**先做这个**）

### 0.1 必须备份：DSH 会话历史

```powershell
# 82 MB，88 个文件，这是历次对话的原始记录，升级不兼容就没了
Copy-Item "C:\Users\丧彪\.dsh\sessions" "D:\dsh-sessions-backup-20260910" -Recurse -Force
```

### 0.2 建议备份：配置与技能（✅ **已于 2026-09-10 执行完毕**）

**已完成**，备份在 `D:\dsh-backup-20260910\`：

| 内容 | 来源 | 大小 |
| --- | --- | --- |
| `sessions/` | `C:\Users\丧彪\.dsh\sessions` | 88 文件 / 82.28 MB |
| `storages/` | `C:\Users\丧彪\.dsh\storages` | 92 文件 / 0.61 MB |
| `agents-skills/` | `C:\Users\丧彪\.agents\skills` | **187 文件 / 1.87 MB（20 个技能）** |
| `skills/` | `C:\Users\丧彪\.dsh\skills` | 1 文件（只有 officecli） |
| `settings.yaml` / `AGENTS.md` / `.credentials.yaml` | `C:\Users\丧彪\.dsh\` | 合计约 8.4 KB |
| `.skill-lock.json` | `C:\Users\丧彪\.agents\` | 0.38 KB |

⚠️ **注意技能的真实位置**：技能分两个根——

- `C:\Users\丧彪\.agents\skills\` ← **主力的 20 个技能在这**（session-memory、brainstorming、writing-plans、executing-plans、test-driven-development、systematic-debugging、verification-before-completion、officecli 相关的 morph-ppt 等，以及 `session-memory/global-knowledge.md` 全局踩坑库）
- `C:\Users\丧彪\.dsh\skills\` ← 只有 `officecli` 一个

**只备份 `.dsh\skills` 等于没备份技能**（这是这次差点踩的坑）。要恢复原始命令：

```powershell
$dst = "D:\dsh-backup-20260910"
Copy-Item "C:\Users\丧彪\.dsh\sessions"          "$dst\sessions"      -Recurse -Force
Copy-Item "C:\Users\丧彪\.dsh\storages"          "$dst\storages"      -Recurse -Force
Copy-Item "C:\Users\丧彪\.agents\skills"         "$dst\agents-skills" -Recurse -Force
Copy-Item "C:\Users\丧彪\.dsh\skills"            "$dst\skills"        -Recurse -Force
Copy-Item "C:\Users\丧彪\.dsh\settings.yaml"     "$dst\"
Copy-Item "C:\Users\丧彪\.dsh\AGENTS.md"         "$dst\"
Copy-Item "C:\Users\丧彪\.dsh\.credentials.yaml" "$dst\"
Copy-Item "C:\Users\丧彪\.agents\.skill-lock.json" "$dst\"
```

（`.credentials.yaml` 里有 API 密钥，备份后别传网盘。）

**恢复时**：把 `agents-skills/` 覆盖回 `C:\Users\丧彪\.agents\skills\`，其余按原路径放回。`sessions/` 若新版不兼容，至少原始记录还在，可以手工翻。

### 0.3 项目代码：不用额外备份

所有代码已提交到本地 git（40 个提交，工作区干净）。**但注意：从未推送过**，所以 git 仓库是唯一副本，别删 `.git`。

---

## 一、DSH 环境现状

| 项 | 值 |
| --- | --- |
| 当前版本 | `0.1.2-rc.1` |
| 安装位置 | `C:\Users\丧彪\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\` |
| `DSH_HOME` | `C:\Users\丧彪\.dsh` |
| Web GUI | `http://127.0.0.1:3080`（**IPv4**，`::1` 连不上是正常的） |
| 主模型 | `deepseek-flash` / `deepseek-v4.1-flash` |
| 识图能力 | ✅ **当前模型支持 `read_image`**（升级后若换模型失效，见第十节） |

### 1.1 DSH_HOME 里有什么

```
C:\Users\丧彪\.dsh\
├── sessions/          88 个文件, 82.1 MB   ← 会话历史，升级前必须备份
├── skills/            **只有 officecli 一个**（技能主目录在下面 .agents 里）
├── attachments/       会话里的图片附件
├── collab/
├── llm-deepseek/
├── profiles/          node_modules / web（web.bak-20260814 是旧版备份）
├── storages/          会话索引与工作区状态（session_projcache、workspace.json）
├── settings.yaml      设置
├── AGENTS.md          全局指令（很重要的行为规则，见下）
├── .credentials.yaml  API 密钥
└── .anonymous-user-id

C:\Users\丧彪\.agents\      ← **技能的真实主目录（20 个）**
├── skills/            session-memory / brainstorming / writing-plans / officecli 相关…
│   └── session-memory\global-knowledge.md   ← 全局踩坑知识库
└── .skill-lock.json
```

⚠️ **技能有两个根**：主力在 `C:\Users\丧彪\.agents\skills\`（20 个），`.dsh\skills\` 里只有 `officecli`。备份或迁移时**别只备份 `.dsh\skills`**。

**没有** `.agent-presets/`，也**没有** `projects/` —— 本会话没有创建过自定义 agent preset，也没有用过动态 Cordis 插件（`cordis_define`），所以这块没有需要迁移的东西。

### 1.2 `AGENTS.md` 里的关键规则（升级后要确认还在）

`C:\Users\丧彪\.dsh\AGENTS.md` 定义了每次会话必须遵守的规则，逐条列在这里以防丢失：

1. **每次对话开始必须先恢复会话记忆**：glob `_session_context.md` → 读全文 → grep `global-knowledge.md` 的小节标题 → 读相关条目
2. **识图用 `read_image`**（模型原生视觉）；模型不支持时报错要**如实说明，禁止假装看过图片**
3. **解读大文件优先用 `good_assistant`**（opencode + 免费 mimo），文件内容不进主模型上下文
4. **GitHub 是隔离任务**：主模型**绝不直接** `web_search`/`web_fetch` 碰 GitHub 内容，一律派子代理、过滤后回传。原因：2026-09-09 真实事故——直接抓取第三方仓库导致整个会话被内容审核判违规报废，**不可恢复**
   - 白名单例外：仅 `github.com/deepseek-ai/deepseek-harness` 及其 README/releases/CHANGELOG
   - 查版本优先用 npm registry（零风险）

---

## 二、用户画像与协作方式（**最容易被升级弄丢的部分**）

### 2.1 他是谁

- **编程小白，自学中**，正在做个人项目 Calcite（学 Cesium + PostGIS 方向，为找工作/毕设级别）
- 原话：「我纯小白我还需要你指导我」「我才开始学第二天」
- 学习方式是**「边做边学」**：喜欢先看到东西跑起来，再理解原理

### 2.2 沟通偏好（照做，别自行发挥）

| 要求 | 说明 |
| --- | --- |
| **先讲「做什么/为什么」，再讲怎么做** | 不要上来就甩代码 |
| **命令给可直接复制粘贴的绝对路径形式** | 他经常直接粘贴，别给占位符 |
| **一次一件小事** | 大段细节会淹没他。他自己说过「deep detail 会让我不知所措」 |
| **报错要原样贴给他看** | 不要美化，不要只说「报错了」 |
| **不用出题考他** | 原话：「我早上看完了一遍笔记，不要出题」 |
| **执行模式选 Inline Execution** | 我边做边讲，而不是甩一个计划让他自己跑 |

### 2.3 笔记方向（**2026-09-10 的重要反馈，务必遵守**）

他明确表达过挫败感：

> 「看笔记感觉挺绝望，这包含的东西太多，如果连底层算法和命名方式等等原理都要学，那怕是有几万点，我肯定做不到，最起码我得明白这个项目的完整结构和流程图」

**结论：他要的是「地图」，不是「地形」。**

- ✅ 他要：完整结构、流程图、每一层职责、以后加东西放哪里、分类怎么分
- ❌ 他不要：底层算法推导、命名规范大全、知识点堆叠

以后写笔记，**默认写成地图型**（结构 + 流程 + 索引），知识点型只在某个功能做完后针对那一个功能写。

### 2.4 Git 规则（硬性）

- **只本地提交，绝不推送**。原话：「暂时先不推送到GitHub上，只在改动之后先缓存保留回滚退路」
- 每次改动后提交，留回滚点
- 提交信息用中文，说清「改了什么/为什么」

---

## 三、项目 Calcite 全景

### 3.1 一句话

把 GPS 轨迹数据存进 PostGIS，用 Spring Boot 提供接口，用 Vue + Cesium 在三维地球上画出来，并能回放、分析（速度/海拔曲线、停留点、相似度）。

### 3.2 技术栈与版本（已核实）

| 层 | 技术 | 版本 |
| --- | --- | --- |
| 后端 | Spring Boot | 3.5.16 |
| | Java | 25.0.2 LTS (2026-01-20) |
| | Maven | 3.9.11 |
| | Hibernate ORM | 6.6.53.Final（含 `hibernate-spatial`） |
| | Tomcat | 10.1.55（内嵌） |
| 前端 | Vue | ^3.5.42 |
| | Vite | ^8.2.2（⚠️ rolldown 版） |
| | Cesium | ^1.145.0 |
| | `@vitejs/plugin-vue` | ^6.0.8 |
| | `vite-plugin-static-copy` | ^4.1.1 |
| 数据库 | PostgreSQL | 18.3 |
| | PostGIS | 3.6（USE_GEOS/PROJ/STATS=1） |
| | 扩展 | `postgis` + `btree_gist` |
| 运行时 | Node | v24.14.0 / npm 11.9.0 |
| | Python | 3.12.6（`E:\python\python_address`），Pillow 12.2.0 |
| | Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` |

**前端依赖是刻意精简的**：只有 `cesium` + `vue` 两个运行时依赖，**没有装测试框架**。测试用 node 内置 `assert` 和 Playwright+Pillow 外挂做，这是有意为之的设计，不要「好心」加 Jest/Vitest。

### 3.3 四层架构

```
浏览器 (Chrome)  ──HTTP──▶  前端 Vue3 (Vite dev :5173)
                                    │ /api 代理
                                    ▼
                            后端 Spring Boot (:8080)
                                    │ JDBC
                                    ▼
                          PostgreSQL + PostGIS (:5432)
```

**关键点**：前端代码里永远写 `fetch('/api/...')`，**不写 8080 全地址**——`vite.config.js` 里配了代理，用来绕开浏览器跨域限制。

---

## 四、代码结构与分层

### 4.1 目录

```
Calcite/
├── backend/                        Spring Boot（独立进程）
│   ├── pom.xml                     ← Java 依赖清单
│   └── src/main/
│       ├── java/com/calcite/
│       │   ├── CalciteApplication.java     启动类（必须在根包，否则扫不到组件）
│       │   ├── domain/                     实体：Track, TrackPoint
│       │   ├── repository/                 持久层：TrackRepository, TrackPointRepository
│       │   └── web/                        接口层：HealthController, TrackController
│       │       └── dto/                    TrackSummary, TrackDetail, TrackPointDto
│       └── resources/
│           ├── application.yml            主配置（profile=local, ddl-auto=none, port=8080）
│           └── application-local.yml      **含数据库密码，已被 gitignore**
├── frontend/                       Vue3（独立进程）
│   ├── package.json                ← npm 依赖清单
│   ├── vite.config.js              ← 端口 5173 / 代理 /api→8080 / Cesium 资源拷贝
│   ├── index.html                  只有一个空的 <div id="app">
│   ├── src/
│   │   ├── main.js                 createApp(App).mount('#app')
│   │   ├── App.vue                 **状态中心**（311 行）
│   │   ├── style.css
│   │   ├── components/             CesiumGlobe.vue(277) / TrackList.vue(128)
│   │   │                           TrackPlayer.vue(147) / SpeedChart.vue(362)
│   │   └── lib/                    纯计算，不 import Vue/Cesium
│   │       ├── playback.js  (56)   倍速、时间范围、能否播放
│   │       └── chart.js    (187)   刻度、坐标映射、插值
│   └── scripts/                    check-playback.mjs / check-chart.mjs
├── scripts/
│   ├── db/                         01-schema.sql / 02-sample-track.sql / 03-show-results.sql
│   ├── learning/01-postgis-basics.sql
│   └── tools/md2docx.py            Markdown → Word（已修好 + 支持插图）
├── docs/
│   ├── learning/                   学习笔记源文件 + figs/（7 张流程图的生成脚本与 PNG）
│   └── superpowers/specs/ plans/   设计文档与实施计划
├── _session_context.md             会话记忆（每次开工读）
└── _session_handoff_2026-09-10.md  本文档
```

### 4.2 后端分层的边界（不要越界）

| 层 | 职责 | **不该做** |
| --- | --- | --- |
| `web/Controller` | 收 HTTP、决定返回什么、找不到抛 404 | 不写 SQL |
| `web/dto/` | 定义发给前端的形状（`XxxSummary` 列表用 / `XxxDetail` 详情用 / `XxxDto` 通用） | 不放业务逻辑 |
| `repository/` | 查/存数据库，**方法名即 SQL**（`findByTrackIdOrderBySeqAsc` ↔ `WHERE track_id=? ORDER BY seq ASC`） | 不碰 HTTP |
| `domain/` | 数据库表的 Java 影子 | 不认识前端 |

### 4.3 前端的数据流（单向）

- **props 往下**：App.vue → 子组件
- **emit 往上**：子组件发事件，App.vue 改状态
- **defineExpose + ref**：父组件主动调子组件方法（`CesiumGlobe` 暴露 `play/pause/seekTo`）
- **状态只存在 App.vue 一份**，避免「播放条在播、地球停着」这种不一致

`lib/` 里的文件是纯函数（**判断标准**：只用参数就能算出结果），所以能用 node 直接跑断言。

---

## 五、数据库

### 5.1 三张表

| 表 | 是什么 | 状态 |
| --- | --- | --- |
| `track` | 一次出行（含派生字段 `distance_m`/`duration_s`/`point_count`/`geom` LineString） | ✅ 在用 |
| `track_point` | 一个 GPS 点（`seq`/`recorded_at`/`elevation_m`/`speed_mps`/`geom` Point）——**原始真相** | ✅ 在用 |
| `stay_point` | 一次停留（`start_time`/`end_time`/`duration_s`/`radius_m`/`geom`） | ⏳ 表建好了，**M2 才写算法** |

### 5.2 关键设计决策（改之前先理解为什么）

1. **`ddl-auto: none`**——表结构完全由 `scripts/db/*.sql` 手写管理，Hibernate 不碰数据库。原因：PostGIS 的 `geometry` 列是手写 DDL 声明的，让 Hibernate 去「补」容易把列改坏。（原来是 `update`，特意改掉的）
2. **存 `geom` 而不是 `lon`/`lat` 两列**——这样才能建空间索引、用 `ST_` 函数
3. **`track` 存派生数据**——用空间换时间，列表页不用现算。**但真相在 `track_point`**，不一致时永远是派生值错
4. **`open-in-view: false`**——避免 Web 请求期间一直占着数据库连接
5. **索引**：`idx_track_point_seq ON track_point(track_id, seq)` 给「取某条轨迹所有点」用；`idx_track_point_st USING GIST(geom, recorded_at)` 是时空联合索引

### 5.3 示例轨迹数据（真实值）

| 项 | 值 |
| --- | --- |
| 轨迹 id / 名称 | `1` / 北京城区骑行 · 天安门→奥林匹克公园 |
| 点数 | 121（`seq` 0..120） |
| 采样间隔 | 25 秒 |
| 总时长 | 3000 秒（50 分钟），07:30 → 08:20 |
| 总距离 | 约 9.4 km |
| 海拔 | 32–48 m（121/121 都有） |
| 速度 | 120/121 有值（`seq=0` 无前点故为 NULL），min 2.996 / avg 3.148 / max 3.245 m/s |

**速度是怎么来的**（`02-sample-track.sql` 第 3 节回填）：

```sql
LAG(geom) OVER (ORDER BY seq)                                   -- 取上一行的坐标
ST_Distance(geom::geography, prev_geom::geography)              -- 球面距离，单位【米】
  / NULLIF(EXTRACT(EPOCH FROM (recorded_at - prev_at)), 0)      -- 除以秒数差，防除零
```

⚠️ **`::geography` 绝对不能漏**：不加的话 `ST_Distance` 返回的是「度」（约 0.0007），不是米（约 78.7），差 11 万倍。

---

## 六、已完成的功能（M1）

### 6.1 M1 · 轨迹回放（2026-09-09 完成）

- 底部播放条：播放/暂停、可拖动进度条、当前时刻、循环开关
- 白色移动点跟着时钟沿轨迹走
- **核心公式**：`clock.multiplier = 轨迹真实总秒数 ÷ 60`（示例轨迹 = 50 倍速，即 50 分钟用 60 秒播完）
- `ClockStep.SYSTEM_CLOCK_MULTIPLIER`；`ClockRange` 循环开=`LOOP_STOP`、关=`CLAMPED`
- `SampledPositionProperty` 让点的位置由时钟决定；`JulianDate.fromIso8601` 转时间
- `CesiumGlobe` 的 `time-change` 事件做了 **100ms 节流**
- 回归：`npm run check:playback` = **17 项**

### 6.2 M1 · 速度/海拔曲线（2026-09-09 完成）

- 屏幕底部上下两张图（速度 56px 绿 / 海拔 56px 橙）+ 共享一条时间轴（20px）= 140px，`bottom: 46px`；`.status` 上移到 `194px`
- **手写 SVG，零依赖**；游标（1px 白色虚线，`4 3`，opacity .7）与回放**双向联动**；悬停读数；点击跳转
- **游标画在数据线之前**（SVG 里后写的盖住先写的）→ 结构上不可能遮挡数据线
  - 实测：藏起游标/交点前 4957 个数据线像素 → 显示后 4953 个，**保留 99.9%**
- 交点用 `valueAt` **线性插值**（不是最近的真实点），保证精确落在交叉处
- `ResizeObserver` 量真实像素宽度 + `window.resize` 兜底
- 回归：`npm run check:chart` = **37 项**；浏览器验收 `.tmp/check-chart-pixels.py` = **10 项**

### 6.3 明确没做（YAGNI，别自作主张加）

缩放/框选/平移、导出图片、多轨迹对比、速度平滑、加速度/坡度指标、曲线折叠。

---

## 七、Git 状态与回滚点

```
工作区     : 干净（无未提交改动）
本地 HEAD  : 0f4f9ca
远端       : origin/main = 1e342e6  ← 落后，**从未推送过**
累计提交   : 40
```

### 关键回滚点

| 提交 | 含义 |
| --- | --- |
| `0f4f9ca` | 当前（会话记忆更新） |
| `8548f50` | 练习改动（曲线配色 + `PLAY_SECONDS=20`） |
| `9b3c2c6` | 修图（中文方块 / 框重叠） |
| `8a66ab2` | **结构地图 + 修好 md2docx** |
| `38f42c2` | 曲线完成 |
| `1fcb9dd` | App 接线曲线 |
| `600c0bc` | SpeedChart 组件 |
| `96d95ba` | **M1 回放开始前**（回放计划的提交） |
| `21f24cd` | M1 回放设计文档 |

只还原某两个文件：

```powershell
git checkout 38f42c2 -- frontend/src/components/SpeedChart.vue frontend/src/lib/playback.js
```

---

## 八、环境与命令速查

### 8.1 路径

| 用途 | 路径 |
| --- | --- |
| 项目根 | `E:\JAVA_IDEA_package\JAVA_Project\Calcite` |
| Maven | `E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd` |
| Maven 本地仓库 | `E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository`（**必须显式指定**，默认 `~/.m2` 含中文路径会出问题） |
| npm 缓存 | `E:\JAVA_IDEA_package\JAVA_Project\Calcite\.npm-cache`（同上，必须显式指定） |
| Python | `E:\python\python_address\python.exe` |
| psql | `E:\PostgreSQL\bin\psql.exe` |
| 笔记目录 | `D:\Calcite-note\`（**仓库外**） |

### 8.2 启停服务

```powershell
# 后端（:8080）—— 后台任务
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" spring-boot:run

# 前端（:5173）—— 需要提权 danger-full-access
$env:npm_config_cache = "E:\JAVA_IDEA_package\JAVA_Project\Calcite\.npm-cache"
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend; npm run dev
```

⚠️ **Vite 只绑 IPv6**：地址必须是 `http://localhost:5173`，写 `127.0.0.1:5173` 连不上。

### 8.3 回归检查

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite\frontend
npm run check:playback       # 17 项，纯逻辑
npm run check:chart          # 37 项，纯逻辑

# 浏览器像素验收（10 项，需要两个服务都在跑，需提权）
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
$env:PYTHONIOENCODING='utf-8'
& "E:\python\python_address\python.exe" .tmp\check-chart-pixels.py
```

### 8.4 数据库

```powershell
$env:PGPASSWORD='<见 backend/src/main/resources/application-local.yml>'; $env:LC_MESSAGES='C'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -d calcite -P pager=off -f <sql文件>
```

⚠️ `-c "..."` 里的 SQL **不要写中文别名**（`AS 时刻`），PowerShell 按 GBK 编码发出去会报 `无效的 "UTF8" 编码字节顺序`。要中文就写成 `.sql` 文件用 `-f`。

### 8.5 重新生成笔记

```powershell
cd E:\JAVA_IDEA_package\JAVA_Project\Calcite
python docs\learning\figs\make_figs.py                                   # 生成 7 张流程图
python scripts\tools\md2docx.py docs\learning\<源>.md <输出>.docx          # 必须在仓库根目录跑
```

---

## 九、沙箱与提权清单

沙箱模式 `workspace-write`，工作区 = `E:\JAVA_IDEA_package\JAVA_Project\Calcite`。**批准策略 `ask`**。

以下操作**已知会被拒绝，直接一次性提权 `danger-full-access` + 一句理由**：

| 操作 | 报错 |
| --- | --- |
| `vite dev` / `vite build` | `spawn EPERM`（Vite 要 spawn 子进程探测 Windows 网络盘） |
| Playwright（python） | `PermissionError [WinError 5]`（要建命名管道） |
| 写 `D:\Calcite-note\` | `Access to the path ... is denied` |
| 写 `C:\Users\丧彪\.agents\` | `file access denied under workspace-write` |
| 写 `C:\Users\丧彪\.dsh\skills` | 同上 |
| `git ls-remote` / `git push` | `sh.exe: couldn't create signal pipe, Win32 error 5` |

**网络**：pwsh/curl/dotnet 出网被拦；**python 出网放行**；npm 走 `https://registry.npmmirror.com` 可用（但需把 `npm_config_cache` 指到工作区，否则 `EPERM`）。

**本地 localhost 请求**（`Invoke-RestMethod http://localhost:8080/...`）是通的，可以用来验服务。

---

## 十、已知的坑（这个会话踩过的，别再踩）

| 坑 | 现象 | 解法 |
| --- | --- | --- |
| **Cesium 无头截图空白** | 用无头 Chrome 的 `--virtual-time-budget` 截图，轨迹线是空的 | Cesium 几何体在 web worker 里**异步**生成，虚拟时间会提前截图。**必须用 Playwright 真实等待** |
| **Vite 构建假绿** | 新建的组件「构建通过」但根本没编译 | 组件没被 `import` 时 Vite 不会解析它。要看**包体积/哈希是否变化**才算真验证 |
| **officecli 写不进 docx** | `add` 报成功、`save` 报已保存，但文件是空的；`validate` 对空文档还假报通过 | 该工具靠命名管道和 resident 通信，沙箱禁管道。**生成 Word 一律用 python-docx**（`scripts/tools/md2docx.py`） |
| **python-docx 生成非法 XML** | Word 能开，但校验器报几十上百个 `unexpected child element` | `pPr`/`rPr`/`tcPr` 子元素**顺序是强制的**，不能用 `append`，要用 `insert_element_before(el, *后续标签)` |
| **Pillow 中文变豆腐块** | 图里英文正常、中文全是 □ | Consolas 等宽字体**没有中文字形**，含中文的行必须用 `msyh.ttc` |
| **psql 中文别名报编码错** | `无效的 "UTF8" 编码字节顺序: 0xbf` | `-c` 里别写中文，或写成 `.sql` 文件用 `-f` |
| **`Number(null) === 0`** | 没速度的点被画成「速度 0」，曲线掉到底 | 转数字前先判 `null/undefined/''` |
| **Maven 仓库路径** | 默认 `~/.m2` 含中文用户名会出问题 | 显式 `-Dmaven.repo.local=<项目>\.m2\repository` |
| **`read_image` 失效** | 报 `model does not declare image input` | 是模型/配置没声明视觉能力，**不是 DSH 版本旧**。此时**禁止假装看过图片**，要如实说明 |
| **`("单行文字")` 少逗号** | Pillow 里 for 循环逐字符处理，文字竖排 | 单元素元组要写 `("文字",)` |

---

## 十一、笔记与文档索引

### 11.1 学习笔记（Word，给用户看的）

```
D:\Calcite-note\
├── Calcite-第一阶段学习笔记.docx    (56 KB)  基础知识点：PostGIS/表设计/后端分层/HTTP/Vue+Cesium
├── Calcite-第二天学习笔记.docx      (55 KB)  回放 + 速度回填 + 曲线（含 4 处代码勘误已修）
└── Calcite-项目结构地图.docx       (897 KB) 14 章 + 7 张手画流程图 ★最新
```

### 11.2 仓库内的源文件

| 文件 | 说明 |
| --- | --- |
| `docs/learning/2026-09-08-phase1-notes.md` | 第一份笔记源 |
| `docs/learning/2026-09-10-calcite-structure-map.md` | 结构地图源 |
| `docs/learning/figs/make_figs.py` | 7 张流程图的生成脚本（Pillow） |
| `docs/learning/figs/fig1..7-*.png` | 流程图成品 |
| `scripts/tools/md2docx.py` | Markdown→Word（**已修好 XML 顺序 bug，并新增 `![图注](路径)` 插图语法**） |
| `docs/superpowers/specs/*-design.md` | 设计文档 |
| `docs/superpowers/plans/*.md` | 实施计划（含完整代码，TDD 分任务） |

### 11.3 结构地图的 7 张图是什么

1. 总体架构（四层 + 端口 + 箭头）
2. 目录结构地图（19 个格子各负责什么）
3. **点一条轨迹，数据走完全程**（⑪ 步，最重要的一张）
4. 后端为什么要分四层
5. 前端组件树与数据流向
6. 数据库三张表的关系
7. 以后要加东西放哪里（8 个场景）

---

## 十二、下一步待办

### 12.1 用户侧

- **他要花时间消化结构地图**（原话：「我需要一段时间去理解今天这份笔记」）。**不要催他推进度。**
- 练习 1/2/5 做完了；练习 3（SQL）已经用「四层拆解」的方式给他讲清楚了，他跑通了
- 有个待定：曲线配色。当前 `.speed` 紫 `#722ED1`、`.elev` 蓝 `#165DFF`、两个单位标签(326/330)都是绿 `#7ee0a6`。**他还没决定要不要统一**，别自作主张改

### 12.2 功能侧（按设计文档的顺序）

| 阶段 | 内容 | 会新建什么 |
| --- | --- | --- |
| **M2** | 停留点 / 热点分析 | `service/StayPointService.java`（**全新的 `service/` 包**）、`web/StayPointController.java`、`StayPointList.vue`、地图停留图层。表 `stay_point` **已经建好了** |
| 导入 | GeoLife `.plt` 解析 + `POST /api/tracks/import` | `service/GeoLifeParser.java`、`ImportController`、前端上传按钮 |
| M3 | 轨迹相似度 | `service/SimilarityService.java`、结果缓存表 `05-xxx.sql`、`CompareView.vue` |
| 性能 | `GET /api/tracks/{id}/points?simplify=` | 轨迹抽稀 |

### 12.3 悬而未决的小事

- 是否清理本地 git 历史里的数据库密码（`application-local.yml` 已被 gitignore，但**早期提交里可能有残留**）。当前决定：**不推送就先不管**。将来要推送前必须处理（旋转密码 / `git filter-repo`）
- 离线底图 NaturalEarthII 在城市级缩放下是一片绿色糊状，观感一般（非阻塞）
- `.tmp/` 下有约 4.8 MB 临时文件（截图、试验脚本），未入库，可随时删。其中 `check-chart-pixels.py` 和 `pw-playback.py` 是**已被 git 跟踪**的验收脚本，删了不影响 git

---

## 十三、行为红线（升级后请确认仍然生效）

1. **GitHub**：主模型**永远不直接**抓取/搜索 GitHub 内容。要访问就派子代理，且子代理只回传结论、不回传页面原文。唯一白名单是 `deepseek-ai/deepseek-harness` 的 README/releases/CHANGELOG。查版本用 npm registry
   - **这不是洁癖，是有真实代价的**：2026-09-09 直接抓第三方仓库导致整个会话被内容审核判违规，**不可恢复、无法事后清理**
2. **不假装看过图片**：`read_image` 报不支持就要如实说
3. **不推送 git**（用户明确要求）
4. **不给出题**（用户明确要求）
5. **笔记写地图，不写知识点堆叠**（用户明确反馈）
6. **大段代码不要甩给用户**：解释「做什么/为什么」，代码放在文件里让他自己看

---

## 附：一句话总结当前状态

> M1 全部完成（回放 + 速度/海拔曲线，64 项回归全绿），项目结构图和学习笔记已产出；当前处于「用户消化理解」阶段，**没有进行中的功能开发**；git 40 个提交全部在本地、工作区干净；两个服务已关停。
