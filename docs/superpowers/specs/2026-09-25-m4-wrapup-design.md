# M4 收尾（交付与文档）设计

> **一句话**：把项目从「我能跑」变成「**陌生人能看懂、愿意动手的人能跑起来**」——
> 刷新 README、画一张全景架构图、写一份能照做的部署文档、给一份 clone 就能导入的演示数据集、
> 把 M1–M3 的技术取舍整理成自检问答；**不新增任何分析功能、不改前后端代码**。
>
> **日期**：2026-09-25　**阶段**：M4（总设计文档第 142-145 行「M4 收尾（第 12 周）」）
> **范围**：文档 + 图 + 演示数据 + 脚手架整理；**代码零改动**（真改了就必须跑全量回归）
> **前期状态**：M1/M2/M3/数据管理全部完成并已推送（`main = origin/main = 42dad47`）

---

## 1. 目标与范围

### 1.1 要做什么

总设计文档给 M4 的两行原文：

> - README + 架构图 + 部署文档 + 演示数据集
> - 技术要点自检：每个技术点准备"为什么这么做、不用它行不行"

对应成 5 件交付 + 1 项整理：

| # | 交付 | 一句话 |
|---|---|---|
| 1 | **README 刷新** | 陌生人打开仓库 5 分钟知道：这是什么、做到哪了、怎么跑、有哪些取舍 |
| 2 | **全景架构图** | 一张图说清「前端 → 后端 → 数据库」四层 + 已实现的 M1–M3 能力 |
| 3 | **部署文档** | 从空机器到五个面板都能用，含**常见报错表**（把踩过的坑写成步骤） |
| 4 | **演示数据集** | 合成演示集（`clone → psql -f` 即可）+ GeoLife 自下载导入脚本 |
| 5 | **技术要点自检** | 28 个问答，每题都指向真实代码/文档出处 |
| 6 | **脚手架整理** | `.tmp/` 里 42 个强制入库的文件按三桶归位；加 LICENSE；旧交接文档归档 |

### 1.2 为什么要做

这一阶段**没有新功能**，它的价值全在"可传递性"上：

- 项目已经攒下 **3 份设计文档、3 份实施计划、6 份学习笔记/报告、7 张结构图、8 个浏览器验收脚本**，
  但**入口是 M1 时代的 README**（见 2.1），第一次来的人看到的是一年前的进度；
- 代码里有几处**只对作者友好的硬编码**（`allowed-roots`、`recycle-dir`，见 2.5），
  别人照 README 跑会在毫无线索的地方失败；
- "边做边学"的成果大多散在学习笔记里，缺少一份**按技术点组织的"为什么这么做"**清单。

### 1.3 成功标准（可验收）

M4 没有功能回归可言，验收换成四条（详见第 5 节）：

1. **从零跑通**：在**空库**上严格按 `docs/DEPLOY.md` 走一遍，能起服务、能看到界面、能查五个面板；
2. **五个面板都有东西看**：导入演示数据集后，停留点 / 热点 / 密度 / 相似 / 圈选 逐个非空（接口断言）；
3. **链接与图片全可达**：脚本扫描 README/DEPLOY 的相对路径，100% 存在；
4. **既有基线不退化**：后端 162 / node 7 套件 157 / 浏览器 8 脚本 123 / 接口对拍 5 脚本 / `vite build` 1506 modules。

### 1.4 范围之外（明确不做）

| 不做 | 理由 |
|---|---|
| Docker / Docker Compose | 本机**没有安装 docker**（实测 `docker` 命令不存在）→ 写了也无法验证，等于交付未验证的东西 |
| 英文版 README 全量翻译 | 保留现有英文一句话摘要即可；受众是中文读者 |
| 修前后端代码 / 改配置默认值 | M4 是交付阶段；`allowed-roots`、`recycle-dir` 的机器相关默认值**只写进文档**，不改代码（改了会影响作者本机工作流） |
| 修订历史 spec / 计划里的旧路径引用 | 历史文档是当时的记录；用 `scripts/acceptance/README.md` 的对照表解决（见 4.6） |
| 新增分析功能、性能优化 | M3 已收口；M4 之后不再加分析能力 |

---

## 2. 现状盘点（全部为 2026-09-25 本机实测）

### 2.1 README 的陈旧点（逐条）

`README.md` 共 224 行，写于 M1 完成时（2026-09-12 前后）。已确认过时的地方：

| 行 | 现在写的 | 实际 |
|---|---|---|
| 33-45 | 功能表只有 M1 的 8 项 | M2（停留点/热点/密度/相似）+ M3（圈选）+ 数据管理（增删改查）都没写 |
| 145 | 「后端单元测试（**41 项**）」 | **162 项** |
| 148-149 | 前端「17 + 37 项」、只列 2 个 `check:` | **7 个套件 157 项**（playback/chart/hotspot/density/similarity/region/data-edit） |
| 155-156 | 只列 2 个浏览器脚本 | **8 个**（含圈选 `check-within.py` 44 项） |
| 201-203 | 「**GeoLife 数据集尚未导入**」 | 已导入，库内 **246 条轨迹 / 286,019 个点** |
| 203 | 「没有做轨迹抽稀」 | 仍然属实 —— 保留 |
| 212-213 | 「M2 进行中 / M3 计划中」 | **M2、M3 均已完成**；还漏了「数据管理」这一阶段 |
| 7-11 | 只有一张 M1 截图 | 仓库里已有密度昼夜、相似度、圈选五边形、缓冲区 4 张真实截图可复用 |
| 86 | 架构图指向 `docs/learning/figs/fig1-arch.png`（M1 时代的分层图） | 缺少一张覆盖 M2/M3 的全景图（任务 2 补） |

### 2.2 仓库根目录与文档分布

```
根目录：README.md · _session_context.md · _session_handoff_2026-09-10.md · .gitignore
docs/              57 个文件：map-matching-assessment.md + superpowers/(specs|plans) + learning/(笔记+figs)
backend/           79 个文件
frontend/          33 个文件
scripts/            5 个：db/01-schema.sql · db/02-sample-track.sql · db/03-show-results.sql
                          learning/01-postgis-basics.sql · tools/md2docx.py
.tmp/              42 个**强制入库**的文件（.tmp/ 在 .gitignore 里，这些是 `git add -f` 加进来的）
```

- **没有 LICENSE、没有 CHANGELOG、没有 Dockerfile**；
- `_session_handoff_2026-09-10.md` 是一次性的「DSH 升级交接件」（升级原因已消失），放在根目录已无意义。

### 2.3 `.tmp/` 里 42 个入库文件的真实成分

| 桶 | 数量 | 内容 | 处置 |
|---|---|---|---|
| **A · 可重复运行的验收脚本** | **22** | 9 个浏览器验收 `check-*.py`（chart-pixels / data-edit / density / filter / hotspots / import-pixels / similarity / stay-points / within）、5 个接口对拍 `verify-*-api.py`、3 个桩/组件检查（`check-runtime-task9.mjs` `cesium-stub.mjs` `vue-stub.mjs`）、3 个截图脚本（`shot-hotspot-ui.py` `shot-similarity.py` `shot-within-report.py`）、1 个缺陷复现探针（`probe-polygon-triangle.py`）、1 个回放浏览器检查（`pw-playback.py`） | 搬进 `scripts/acceptance/` |
| **B · 图生成器** | **1** | `render-density-scales.py`（生成 `fig-density-scales.png`） | 搬进 `docs/learning/figs/`（与 `make_*_figs.py` 同类） |
| **C · 一次性工具** | **19** | 15 个 `fix-*.py`（一次性改文档）、`analyze-density.py` `analyze-playback.py` `where-is-my-data.py` `_red-verify-task6.py` | `git rm --cached`（**文件留在本地 `.tmp/`**，只是不再入库） |

22 + 1 + 19 = 42 ✓

### 2.4 运行环境事实

| 项 | 实测 |
|---|---|
| Java | 25.0.2（`pom.xml` 要求 25） |
| Node | v24.14.0（Vite 8 / Vue 3.5） |
| PostgreSQL / PostGIS | 18.3 / 3.6，库名 `calcite`；**装在非默认目录 `E:\PostgreSQL`**，即 `psql` 在 `E:\PostgreSQL\bin\psql.exe`（实测可用）。查找方法：`sc.exe qc postgresql-x64-18` 看 `BINARY_PATH_NAME` 的 bin 目录 |
| Docker | **无**（命令不存在） |
| `psql` | **不在沙箱 PATH 上**（`psql --version` 失败，但 `E:\PostgreSQL\bin\psql.exe --version` 正常）→ 部署文档必须给"怎么找到 psql"的方法 |
| 仓库可见性 | **公开**（2026-09-12 起）→ 演示数据不得包含个人数据或需授权的第三方数据 |

### 2.5 部署路上的「硬编码地雷」（陌生人必踩）

| 配置 | 当前值 | 陌生人的后果 |
|---|---|---|
| `spring.datasource.password` | 只在 `application-local.yml`（未入库） | 不复制模板填密码 → 启动失败，报 `password authentication failed` |
| `calcite.import.allowed-roots` | `D:\Calcite-note\GPX-Data\Geolife Trajectories 1.3\Data` | 批量导入任何其它目录 → 被白名单拒绝（这是**安全设计**，不是 bug） |
| `calcite.data.recycle-dir` | `D:\Calcite-note\backups\deleted` | 该目录不存在/不可写时，**删除轨迹返回 500**（M3 踩过：沙箱里 `WinError 5`） |
| `calcite.import.max-tracks-per-call` | 50 | 单次批量导入最多 50 个文件（**不是 50 条轨迹**，是 50 个文件 —— 数据管理阶段踩过） |

这四条都会写进 `DEPLOY.md` 的「常见报错表」。

### 2.6 可复用的素材（不要重造）

- **真实截图**：`docs/images/screenshot-m1.png`、`docs/learning/figs/2026-09-17-density/density-{day,morning}.png`、`docs/learning/figs/2026-09-17-m2-similarity/similarity-shot.png`、`docs/learning/figs/fig-within-shot-{polygon,buffer}.png`；
- **结构图 7 张**：`docs/learning/figs/fig{1..7}-*.png` + 生成脚本 `make_figs.py`（PIL，`Fig` 类带**自动溢出检查**）；
- **学习笔记**：`docs/learning/2026-09-{10,14,17,21,25}-*.md`（结构地图、停留点、热点、密度、相似度、数据管理、M3 圈选）；
- **既有示例数据**：`scripts/db/02-sample-track.sql`（`SAMPLE-001` 一条北京骑行轨迹，**可重复执行**的写法可直接照抄）。

---

## 3. 关键决策记录

| # | 决定 | 备选 | 理由 |
|---|---|---|---|
| 3.1 | 受众：**展示为主、兼顾能跑** | 纯作品集 / 纯可复现 | 用户 2026-09-25 选定；README 与图是主战场，部署与数据做到"愿意动手的人能一次跑通" |
| 3.2 | 演示数据：**合成集 + GeoLife 自下载脚本**，**不打包**第三方/个人数据 | 打包 GeoLife 小样本 / 打包作者自采 GPX | 仓库公开：GeoLife 再分发属灰色地带；自采 GPX 会公开作者跑步路线与居住区域。合成集无许可与隐私问题 |
| 3.3 | 架构图：**PIL 重画一张全景主图** | Mermaid / 两者都要 / 只更新旧图 | 与既有 7 张图同风格、可离线重建、PNG 在 GitHub 直接显示、可做像素级目视检查 |
| 3.4 | LICENSE：**MIT**，署名用 GitHub 账号 `YNM10086` | 不加 / 其它协议 | 公开仓库无协议 = 默认保留全部权利，陌生人不能合法使用；MIT 最简最通用（署名可随时改一行） |
| 3.5 | 旧交接件 → `docs/archive/` | 删除 / 留在根目录 | 保留历史（它是当时的真实记录），但根目录只留入口文件 |
| 3.6 | `.tmp` 三桶迁移（22 搬 / 1 搬 / 19 取消入库） | 全部保留 / 全部搬 | 验收脚本是**资产**（陌生人"想跑/想验"要找得到）；一次性脚本是**过程垃圾**（不该进交付物） |
| 3.7 | 技术要点自检：**`.md` + Word 都出** | 只出 .md | 用户 2026-09-25 选定；Word 是各阶段的既有交付惯例（`python-docx`，**禁用 officecli**） |
| 3.8 | 历史文档里的旧路径**不改写**，用对照表 | 全库替换路径 | 历史 spec/计划是"当时的事实"，改写会破坏可追溯性 |

---

## 4. 任务分解

> 依赖顺序见第 6 节；每个任务的验收都写进第 5 节的总验收里。

### Task 1：README 重写

**Files**：`Modify: README.md`

**逐节结构**（16 节，保持现有语气：直接、有数字、有取舍）：

| 节 | 必须包含的事实 |
|---|---|
| 1 标题 + 英文副标题 | 保留 |
| 2 **hero 全景架构图** | `docs/images/arch-overview.png`（Task 2 产出） |
| 3 这是什么 | 链路图（原始轨迹 → 清洗入库 → PostGIS → REST → Cesium），强调"设计文档/计划/测试都在仓库里" |
| 4 **已实现的功能** | 按阶段分三组：M1（导入/清洗/幂等/回放/曲线/列表）、M2（停留点/热点/密度/相似度）、M3（圈选：拉框/多边形/缓冲区）+ 数据管理（增删改查/回收站） |
| 5 **真实截图** | 至少 3 张（M1 界面、密度昼夜或相似度、圈选五边形），全部引用仓库内已存在的路径 |
| 6 技术栈 | 更新版本表（含测试栈：JUnit5/Mockito、node assert、Playwright+Pillow） |
| 7 架构 | 分层表（web/service/repository/domain 各自"不该做的事"）+ 全景图 + 指向结构地图 7 张图 |
| 8 快速开始 | 5 条命令（建库 → 初始化 → 配密码 → 起后端 → 起前端），**并指向 `docs/DEPLOY.md`** |
| 9 **演示数据** | 两条路：`psql -f scripts/db/04-demo-data.sql`（30 秒）；GeoLife 自下载 + `scripts/demo/import-geolife.py`（大数据量） |
| 10 测试与验收 | 真实基线：后端 162 / node 7 套件 157 / 浏览器 8 脚本 123 / 接口对拍 5 脚本；并给出 `scripts/acceptance/` 的入口 |
| 11 实现上值得一提的点 | 保留 M1 的 6 条，追加 M2/M3 各 2 条（缓存永不失效、对数色阶、缓冲区算成多边形、事件对象单例） |
| 12 文档索引 | 表：总设计文档 / 结构地图 / 各阶段 spec+plan / 学习笔记 / **技术要点自检** / **DEPLOY** / LICENSE |
| 13 已知限制 | 更新为真实清单：平面 vs 球面 13.4 km、热点热态 3.2 s、区域内点数 180~456 ms、无轨迹抽稀、离线底图分辨率、GCJ-02 |
| 14 路线图 | M1/M2/M3/数据管理/M4 **全部 ✅** |
| 15 关于 | 开发方式（设计文档 → 计划 → TDD → 回归 → 同步文档）+ 名字含义 |
| 16 许可 | MIT（指向 LICENSE） |

**验收**：① 链接/图片扫描 0 失效；② 全文数字与 `_session_context.md` 的基线一致（脚本比对关键数字）；③ 无"M2 进行中"类过时表述（grep 关键字）；④ hero 图在 GitHub 渲染正常（本地打开 PNG 目视）。

**风险**：README 容易写成功能清单流水账 → 对策：每节都保留"为什么这么做"的一句话。

### Task 2：全景架构图

**Files**：`Create: docs/learning/figs/make_readme_figs.py`、`docs/images/arch-overview.png`

**图的内容**（一张 1400×~1000 的竖版主图）：

1. **顶层**：一句话定位 + 技术栈徽标条（Java 25 / Spring Boot 3.5 / PostgreSQL 18 + PostGIS 3.6 / Vue 3 + Cesium 1.145）；
2. **四层泳道**：浏览器（Vue 3 · Cesium · 手写 SVG）→ HTTP/JSON → 后端（`web` → `service` → `repository` → `domain`）→ 数据库（`track` / `track_point` / `stay_point` + GiST 索引）；
3. **数据流箭头**：上传 GPX → 解析/清洗 → 入库；查询 → 接口 → 地球图层；
4. **能力清单**：M1–M3 每阶段一行小字（导入清洗 / 停留点·热点·密度·相似 / 圈选）+ 数据管理；
5. **一条"取舍注脚"**：把 3 条最硬的技术取舍写在图角（缓冲区=圆多边形 7.9 ms、对数色阶、事件对象存副本）。

**做法**：复用 `docs/learning/figs/make_figs.py` 的 `Fig` 类（`box/arrow/text/title` + **自动溢出检查**），**不引入新依赖**。

**验收**：脚本自带溢出检查通过；用 `read_image` 目视检查（文字不重叠、箭头不穿框、中文不豆腐块）；连跑两次输出一致。

### Task 3：部署文档

**Files**：`Create: docs/DEPLOY.md`

**章节结构**：

1. 适用范围：**单机开发环境**（Windows/macOS/Linux 通用，命令给两种写法）
2. 前置条件与版本核对（JDK 25 / Maven 3.9+ / Node 20+ / PostgreSQL 18 + PostGIS 3.6）
3. 数据库：建库 → 初始化（`scripts/db/01-schema.sql` 内含 `CREATE EXTENSION postgis` + `btree_gist`）→ 验证（`\dt`、`SELECT PostGIS_Version()`）→ `psql` 不在 PATH 时怎么找（`<PG>\bin\psql.exe`，或 pgAdmin 的 Query Tool）
4. 后端配置：复制 `application-local.yml.example` → 填密码；**必须按自己机器改** `calcite.import.allowed-roots`、`calcite.data.recycle-dir`（逐条说明为什么）
5. 启动后端：`mvn -f backend/pom.xml spring-boot:run` → 验证 `GET /api/health`（返回数据库与 PostGIS 版本）
6. 启动前端：`npm install`（国内镜像可选）→ `npm run dev` → **用 `http://localhost:5173`，不要用 `127.0.0.1`**（Vite 只绑 IPv6，项目实测）→ 验证
7. 演示数据：合成集（`psql -f scripts/db/04-demo-data.sql`）与 GeoLife（自下载 + `scripts/demo/import-geolife.py`）两条路
8. **常见报错表**（预填，见下）
9. 停止与清理：怎么停（Ctrl+C / 端口进程）、怎么删演示数据（按 `external_id LIKE 'DEMO-%'` 清理）、怎么删库
10. 跑验收：`scripts/acceptance/README.md` 指路

**常见报错表**（预填 14 条，全部来自本项目真实踩坑）：

| 现象 | 根因 | 解决 |
|---|---|---|
| `type "geometry" does not exist` | 目标库没装 PostGIS | 跑 `01-schema.sql`（已含 `CREATE EXTENSION`），或在目标库手动 `CREATE EXTENSION postgis` |
| `psql: 无法识别的命令` / 找不到 psql | psql 不在 PATH | 用 `<PG安装目录>\bin\psql.exe`（Windows 默认在 `C:\Program Files\PostgreSQL\<版本>\bin`），或用 pgAdmin 的 Query Tool |
| 后端启动报密码认证失败 | 没复制 `application-local.yml` | 复制 example 并填真实密码（文件已在 `.gitignore`，不会误提交） |
| 批量导入报「不在允许的目录内」 | `calcite.import.allowed-roots` 是白名单 | 改成自己的 GeoLife 数据目录并重启后端 |
| 删除轨迹返回 500 | `recycle-dir` 不存在/不可写（**先导出后删除**的 fail-safe 生效了） | 建目录或改成可写路径；这是设计行为，不是 bug |
| `Port 8080 was already in use` | 旧进程占端口 | 停旧进程，或改 `server.port` |
| 浏览器打不开 5173 | Vite 只绑 IPv6 | 用 `http://localhost:5173`，不要 `127.0.0.1` |
| `invalid target release: 25` / `UnsupportedClassVersionError` | JDK 版本不是 25 | 装 JDK 25 并确认 `java -version` |
| `npm install` 卡住/超时 | 直连 npm 慢 | `npm install --registry=https://registry.npmmirror.com` |
| 页面控件（时间轴/按钮）散架 | Cesium 的 `widgets.css` 没加载 | 确认依赖装全；生产构建后再验一次 |
| 五档里某一档"没东西" | 演示数据没导入 / 时间窗或视野不对 | 先 `psql -f 04-demo-data.sql`；密度/圈选注意当前视野 |
| psql 读中文 SQL 报编码错 | 控制台编码不是 UTF-8 | 脚本首行已有 `\encoding UTF8`；Windows 先 `chcp 65001` |
| 上传 GPX 报"无法识别格式" | 解析器按**内容**识别，不认扩展名 | 确认是 GPX/PLT 之一；看响应体里的中文原因（`server.error.include-message: always`） |
| 单次批量导入超过 50 个文件被截断 | `max-tracks-per-call` 是**文件数**上限 | 分批导入，或调大该值 |

**验收**：**在空库上按文档从零走一遍**，把真实命令与输出（含 `psql` 全路径写法）记进文档；
演练库用新名字 **`calcite_demo`**，**绝不碰 `calcite` 库**，演练完 `DROP DATABASE calcite_demo`。

### Task 4：演示数据集

**Files**：`Create: scripts/demo/make-demo-data.py`、`scripts/db/04-demo-data.sql`、`scripts/demo/import-geolife.py`

**设计原则**：演示集的唯一 KPI 是「**导入后五个面板都有东西看**」，所以它按**功能需求反推**设计，
而不是随机撒点。所有轨迹落在**北京真实地标附近**（坐标真实、轨迹是合成的），时间戳固定在
**2026-09-01 ~ 2026-09-07**（过去时间，可重复），`external_id` 用 `DEMO-001`… 便于一键清理。

| # | 演示轨迹 | 形状/内容 | 服务于哪个面板 | 关键参数（阈值见 4.4 注） |
|---|---|---|---|---|
| 1 | 通勤 A→B | 起点停留 8 分钟 → 骑行 → 终点停留 10 分钟 | **停留点**（≥1）、密度 | 停留半径 <50 m、时长 >300 s |
| 2 | 通勤 B→A（回程） | 与 #1 路线高度重合、略有偏移 | **相似度**（互为第一名，期望 ≥60%） | 采样间距 ~15 m，偏移 ~20 m < 容差 50 m |
| 3 | 环湖跑步 | 闭合环，无停留点、**无海拔** | 停留点（诚实显示 0 个）、曲线（海拔缺失提示） | 海拔列全部 NULL |
| 4 | 含 GPS 漂移的骑行 | 中间插入 3 个速度尖刺（>12 m/s） | **数据清洗**（漂移标记） | 阈值 = max(8 m/s, 3×中位数) |
| 5 | 跨城长途（≈120 km） | 稀疏采样（~500 m 间隔） | **密度**（大尺度）、圈选（大范围） | 用于展示粗档格网 |
| 6-8 | 同一商圈早/午/晚三条 | 同一区域不同时段（08:xx / 12:xx / 18:xx） | **密度昼夜对比**、热点 | 三条都径过同一路口 |
| 9-11 | 三次到访同一广场 | 每条在该广场停留 5-12 分钟 | **热点**（3 次到访 → size 明显） | 热点半径 200 m、min-visits 2 |
| 12 | 两次到访同一咖啡店 | 两条各停留一次 | **热点**（2 次到访，与 #9-11 形成大小对比） | — |
| 13 | 穿越 CBD 的一条 | 径直穿过一个便于圈选的矩形区域 | **圈选**（拉框即可命中） | 矩形可写进文档示例 |
| 14 | 极短轨迹（5 个点） | 边界情况 | 列表/详情健壮性 | 距离 <100 m |

> 共 **14 条**（约 1.5 万个点，SQL 文件预计 <2 MB）。

**做法要点**：

- 生成脚本**只用标准库**（`math`/`random`/`json`/`datetime`），**固定随机种子** ⇒ 连跑两次输出**字节一致**（可复现、可评审）；
- 输出为 **SQL**（`\encoding UTF8` + `DELETE FROM track WHERE external_id LIKE 'DEMO-%'` 开头 ⇒ 可重复执行），
  与既有 `02-sample-track.sql`（`SAMPLE-001`）**共存**，互不干扰；
- 轨迹几何用 `ST_MakeLine`/`ST_GeomFromText` 写入，`track.distance_m` 等派生列**由生成脚本按与导入器一致的公式算好**（不依赖数据库函数），避免"演示数据与真实导入数据字段口径不一致"；
- 生成脚本自带 `--self-check` 模式：导入后调 5 个接口断言非空（见 5.2），不满足就报错并提示调参。

**GeoLife 脚本**：`scripts/demo/import-geolife.py`
- 参数：`--data-dir <GeoLIFE Data 目录>`、`--user 000`、`--limit 15`；
- 先调 `GET /api/health` 确认后端在跑 → 判断 `--data-dir` 是否落在后端 `allowed-roots` 内（不在就**打印需要改的配置项与改法**，不硬闯）；
- 调用既有接口 `POST /api/import/geolife`，body `{"path": "...", "maxTracks": N}`（**注意：N 是文件数不是轨迹数**）；
- 数据来源只给**官方获取指引**（GeoLIFE 官网），仓库不打包数据。

**验收**：见 5.2（五个面板逐条断言）+ 生成脚本两次输出一致 + `04-demo-data.sql` 连续执行两次结果一致（幂等）。

### Task 5：技术要点自检

**Files**：`Create: docs/learning/技术要点自检.md`、`docs/learning/技术要点自检.docx`

**形式**：每个技术点 3 段 —— **为什么这么做** / **不用它行不行（替代方案的代价）** / **出处**（文件:行 或 设计文档小节）。
**硬规则：出处必须能在仓库里核到；核不到就删掉这道题**（不许写成"我记得"）。

**题目清单（28 题）**：

*M1 · 导入与清洗（6）*
1. 为什么按文件**内容**识别格式，不看扩展名？
2. 清洗阈值为什么是 `max(8 m/s, 3×中位数)`，不用固定 8 m/s？
3. 海拔缺失为什么存 NULL 而不是 0？
4. 为什么用文件内容 SHA-256 做幂等键？
5. 批量导入为什么每个文件单独开事务（`TransactionTemplate`），不整批一个 `@Transactional`？
6. 解析上传 XML 为什么要关掉外部实体（XXE）？

*M2 · 四项分析（13）*
7. 停留点为什么必须"半径 + 时长 + 断档"三个条件？
8. `max-gap-s`（断档）解决的是什么现实问题？
9. 热点聚类半径为什么取 200 m？
10. 为什么"只去过一次的地方"不算热点？
11. 热点接口为什么按 `trackId` 缓存停留点，且缓存永不失效？
12. 热点接口为什么不再加载 track 几何？
13. 密度为什么必须按视野裁剪？
14. 密度为什么用对数色阶？
15. `round(ST_X/cell)` 为什么能替 `ST_SnapToGrid`，差异出在哪？
16. 格边长为什么要固定阶梯，最粗档为什么必须 5°？
17. 相似度为什么取 `min(正向, 反向)` 而不是平均？
18. 容差为什么必须设上限（1000 m）？
19. 为什么验收判据要从接口取期望值，不写死数据量？

*M3 · 圈选与空间查询（9）*
20. 「线与多边形相交」为什么能走 GiST 索引（两阶段过滤）？
21. 缓冲区为什么不用 `ST_DWithin(::geography)`？
22. `region` 为什么必须回显**后端用过**的几何？
23. 平面几何与球面差 13.4 km，为什么不修？
24. 自交多边形为什么不报错却返回 237 条？为什么挡成 400 而不用 `ST_MakeValid`？
25. 绑定参数为什么会让同一个 SQL 慢 2.5 倍？
26. Cesium 的鼠标事件对象为什么必须存副本？（三角形缺陷）
27. 「左键旋转」为什么要收敛到一个 `rotateEnabled()` 出口？
28. 为什么验收判据不能只问"有没有结果"？

**Word 交付**：`python scripts/tools/md2docx.py docs/learning/技术要点自检.md docs/learning/技术要点自检.docx`
（**仓库根目录**执行，图路径是相对的；**禁用 officecli**），生成后复制到 `D:\Calcite-note\` 并验证
（文件大小、能读回、标题层级/表格正常、内嵌图片数）。

**验收**：28 题的出处逐条核到行；Word 通过读回验证；`.md` 在 GitHub 上表格渲染正常。

### Task 6：`scripts/acceptance/` 迁移

**Files**：`Create: scripts/acceptance/`（22 个脚本 + `README.md`）、`docs/learning/figs/render-density-scales.py`；`git rm --cached` 19 个

**做法**：

1. `git mv` 桶 A 的 22 个脚本到 `scripts/acceptance/`（保留原文件名，历史可追）；
2. 统一"**从仓库根目录运行**"的约定；脚本里的**输出路径**一律留在 `.tmp/`（运行时产物不该进 `scripts/`）；
3. `scripts/acceptance/README.md` 内容：每个脚本一行（做什么 / 依赖什么服务 / 预期数字 / **原路径 `.tmp/xxx`**），
   并说明三者关系（`check-*.py` 浏览器验收、`verify-*-api.py` 接口对拍、`*-stub.mjs` 组件级桩测试）；
4. 桶 B 的 `render-density-scales.py` 移到 `docs/learning/figs/`（与其它 `make_*` 脚本同处），
   并核对它输出的 `fig-density-scales.png` 路径仍然正确；
5. 桶 C 用 `git rm --cached`（**不删本地文件**）；
6. 更新**现行**引用：`_session_context.md`、`docs/superpowers/M3-START-HERE.md`、`README.md`（Task 1 会写新路径）；
   **历史 spec/计划不改写**，由 `scripts/acceptance/README.md` 的对照表兜住。

**验收（等价性证明）**：搬迁后**逐个重跑**全部可运行脚本，数字必须与搬迁前一致：

| 套件 | 搬迁前基线 |
|---|---|
| 浏览器 8 个 | stay 7 / chart-pixels 10 / import-pixels 6 / filter 7 / hotspots 17 / density 15 / similarity 17 / within 44 |
| 接口对拍 5 个 | within 105 / hotspot 375 / density 51 / similarity 45 / data-edit（需提权，会真删一条轨迹） |
| 组件级桩 | `check-runtime-task9.mjs` 67 项 |

⚠️ 跑浏览器与 `data-edit` 需要**重启后端 8080 + 前端 5173**（并提权）；`verify-data-edit-api.py` / `check-data-edit.py`
**会真的删掉一条轨迹**（删前导出回收站，跑完按提示从 `.plt` 重新导入，**id 会变**）——
按 M3 的纪律：**跑之前先确认数据状态，跑完立刻恢复**（246 条 / 286,019 点）。

**跑不通的脚本**：就地修好；**修不好的一律归入桶 C（取消入库）** ——不留"跑不通但躺在仓库里"的脚本。

### Task 7：归属类收尾

**Files**：`Create: LICENSE`；`Move: _session_handoff_2026-09-10.md → docs/archive/`；`Modify: _session_context.md`

1. `LICENSE`：MIT，`Copyright (c) 2026 YNM10086`；
2. 旧交接件移到 `docs/archive/`（并在 `docs/archive/README.md` 写一句"这是 2026-09-10 的 DSH 升级交接件，仅供追溯"）；
3. `_session_context.md` 同步：M4 完成状态、新增文件、`scripts/acceptance/` 新路径、基线数字、遗留债清单更新；
4. 全量回归（第 5.4 节）+ 合并回 `main`（**推送等用户发话**）。

---

## 5. 验收

### 5.1 从零跑通（人工演练，一次）

用**新库** `calcite_demo`（绝不动 `calcite`）严格按 `docs/DEPLOY.md` 走：建库 → 初始化 → 配置 → 起后端 → 起前端 →
导入演示数据 → 打开界面。**把真实命令与输出贴进文档**；演练完 `DROP DATABASE calcite_demo`。

### 5.2 五个面板都有东西看（脚本断言）

| 面板 | 断言 |
|---|---|
| 列表 | `GET /api/tracks?limit=50` ≥ 14 条（含 `DEMO-*`） |
| 停留点 | `GET /api/tracks/{id}/stay-points` 对 #1 ≥ 1 个；对 #3（环湖跑步）= 0 个（**诚实为 0 也是验收项**） |
| 热点 | `GET /api/analysis/hotspots` ≥ 2 个热点，最大 `trackCount` ≥ 3 |
| 密度 | `GET /api/analysis/density?bbox=北京范围&cellSize=0.002` 非空且 `maxCount` ≥ 3；带 `hourFrom/hourTo` 时结果变化 |
| 相似度 | `GET /api/analysis/similarity?trackId=<#1>` 第一名是 #2 且 ≥60% |
| 圈选 | `POST /api/analysis/within`（覆盖 CBD 的矩形）≥1 条，`stats.pointCount` > 0 |

断言脚本落在 `scripts/acceptance/verify-demo-data.py`（新增，属桶 A）。

### 5.3 链接与图片全可达（脚本）

`scripts/acceptance/check-doc-links.py`（新增）：扫描 `README.md`、`docs/DEPLOY.md`、`docs/learning/技术要点自检.md`
里的**相对链接与图片路径**，逐个 `os.path.exists`；报告 0 失效。同时 grep 过时表述（`M2 进行中`、`尚未导入`、`41 项`）。

### 5.4 既有基线不退化

代码按计划零改动；**若因任何原因改了代码**，必须全绿：

| 层级 | 基线 |
|---|---|
| 后端 `mvn test` | **162** |
| 前端 node（7 套件） | **157** |
| 浏览器（8 脚本） | **123** |
| 接口对拍（5 脚本） | 见 4.6 表 |
| `vite build` | **1506 modules / ✓** |

### 5.5 文档一致性 +「陌生人视角」复核

- 全文数字与 `_session_context.md` 一致（脚本比对关键数字）；
- **陌生人视角复核**：我扮演第一次来的人，**只读 README + DEPLOY**（不看记忆文件、不看历史 spec）走一遍，
  把每一步"卡住/看不懂/要去别处翻"的地方记下来并改文档；改完再走一遍直到不卡。

---

## 6. 实施顺序与依赖

```
Task 2 全景图 ─┐
Task 4 演示数据 ┼─→ Task 3 部署文档 ─→ Task 1 README ─→ Task 5 技术要点自检 ─→ Task 6 迁移 ─→ Task 7 收尾
              │        （部署文档要引用演示数据的命令；README 要引用图与数据）
              └──（4 的 self-check 需要能起服务，所以先确认 8080/5173 起得来）
```

理由：
- **图和数据先做**（README 与 DEPLOY 都要引用它们，反序会返工）；
- **迁移放后面**（它要重跑全部验收脚本，前面任务若仍在改文档，路径引用会反复变）；
- 每个任务一个提交，M4 结束时合并回 `main`（推送等用户发话）。

**工作量估计**：约 7 个任务；预计 **2 个工作段**（① 图 + 数据 + 部署文档；② README + 自检 + 迁移 + 收尾）。

---

## 7. 风险与对策

| # | 风险 | 对策 |
|---|---|---|
| 1 | 迁移后脚本因相对路径/互相 import 失效 | 搬完**逐个重跑**并与基线数字对齐；跑不通就修，修不好归桶 C（**不留坏脚本**） |
| 2 | 历史文档里的旧 `.tmp/xxx` 路径让人困惑 | `scripts/acceptance/README.md` 放对照表；现行引用（记忆/START-HERE/README）改新路径；不改写历史 |
| 3 | 部署演练误伤现有 `calcite` 库 | 只用新库名 `calcite_demo`；所有 SQL 幂等；演练完 drop；**禁止**在演练里跑 `verify-data-edit-api.py` |
| 4 | 演示数据触发不了停留点/热点（阈值 50 m/300 s、200 m/2 次） | 生成脚本内置 `--self-check`：导入后调 4 个接口断言非空，不满足就调参重生成 |
| 5 | 生成脚本不可复现（随机漂移） | 固定随机种子；连跑两次**字节一致**作为验收项 |
| 6 | 技术要点自检写出"看起来对但没出处"的答案 | 每题必须有出处列并逐条核到行；核不到就删题 |
| 7 | Word 生成踩老坑（officecli 写不进、中文乱码） | 只用 `python-docx`（`scripts/tools/md2docx.py`，仓库根目录执行）+ 生成后读回验证 |
| 8 | 文档量大、容易把上下文烧光 | 分任务提交；长文档用脚本自检（链接/过时词/数字）而不是通读；生成类工作（图/数据/文档骨架）能外包给 `good_assistant` 的就外包 |
| 9 | 演练时服务起不来（M4 开始时服务已全关） | Task 4 之前先起后端 8080 + 前端 5173（沙箱内提权），并把起停命令写进 DEPLOY |

---

## 8. 附录

### 附录 A · 文件清单（预期）

**新增**：
```
LICENSE
docs/DEPLOY.md
docs/archive/README.md
docs/archive/_session_handoff_2026-09-10.md      （从根目录移入）
docs/images/arch-overview.png
docs/learning/figs/make_readme_figs.py
docs/learning/figs/render-density-scales.py      （从 .tmp 移入）
docs/learning/技术要点自检.md / .docx
scripts/demo/make-demo-data.py
scripts/demo/import-geolife.py
scripts/db/04-demo-data.sql
scripts/acceptance/README.md
scripts/acceptance/<22 个脚本>                    （从 .tmp 移入）
scripts/acceptance/verify-demo-data.py            （新写）
scripts/acceptance/check-doc-links.py             （新写）
```

**修改**：`README.md`（重写）、`_session_context.md`、`docs/superpowers/M3-START-HERE.md`（路径引用）、`.gitignore`（若需）

**取消入库**（`git rm --cached`，文件保留在本地 `.tmp/`）：15 个 `fix-*.py` + `analyze-density.py` + `analyze-playback.py` + `where-is-my-data.py` + `_red-verify-task6.py`

**代码**：**零改动**（`backend/`、`frontend/` 一行不动）

### 附录 B · 与总设计文档的对应

| 总设计文档第 142-145 行 | 本设计 |
|---|---|
| README | Task 1 |
| 架构图 | Task 2 |
| 部署文档 | Task 3 |
| 演示数据集 | Task 4 |
| 技术要点自检：每个技术点准备"为什么这么做、不用它行不行" | Task 5（28 题，每题强制出处） |

### 附录 C · 本设计刻意留下的"不做"清单

1. 不加 Docker / CI / 生产部署脚本（无法在本机验证）；
2. 不改 `allowed-roots`、`recycle-dir` 的默认值（只写文档）；
3. 不改写历史 spec/计划里的旧路径；
4. 不打包 GeoLife 或作者自采 GPX；
5. 不做英文 README 全量翻译；
6. 不加新分析功能、不做性能优化。
