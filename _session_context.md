# Calcite — 会话记忆

> **本文件会入库（git）**：禁止写入密码 / 密钥 / token。需要记这类东西就放 `_session_context.local.md`（已 gitignore）。
> 为可公开，本地路径里的用户名一律写成 `%USERPROFILE%`。

> 📌 **2026-09-10 DSH 升级交接**：本文件只记「项目进度」。环境版本、用户沟通偏好、
> 踩过的坑、命令速查、备份位置等**完整上下文**在 **`_session_handoff_2026-09-10.md`**。
> 若这是升级 `0.1.5-rc.2` 之后的新会话，**请先读那份交接文档**。

## 项目总结
个人项目 Calcite：以 SpringBoot3 + Cesium + PostGIS 为核心的三件套（前端 Vue3）。
用户是学生，对三者均不熟悉，边做边学。

**项目定位（2026-09-08 经完整需求梳理后确定）**：
- 目的：**个人项目 · 兴趣驱动的技术实践**（方向：GIS / 时空数据开发），交付周期 12 周
- 主线：**GPS 轨迹时空分析平台**——轨迹存入 PostGIS → 时空分析 → Cesium 三维时间轴回放
- 主数据：公开轨迹数据集（GeoLife / T-Drive），辅以 GPX/CSV 导入接口（含用户自己的 vivo 健康跑步记录）
- 路线：采用"方案 C：先回放、后分析"——M1 第 3 周即可演示，避免长期无成果
- 设计文档（项目目标/范围/数据模型/接口的唯一权威）：`docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`（提交 `86dcdab`）

**当前进度（2026-09-08）**：
- 环境就绪 + 前后端骨架已实测通过 + 设计文档已定稿（`86dcdab`）
- PostGIS 初体验脚本已跑通（`da8eda9`）：空间索引 106ms → 1.1ms（94×），时空联合索引 0.54ms
- **Cesium 三维地球已接入并验证渲染成功**（`38e91df`）：底图用 Cesium 自带离线 NaturalEarthII，**无需 token / 无需联网**；像素分析确认地球（海洋 11.9% / 陆地 8.8%）与 Vue 浮层均已渲染
- **三张核心表已建好 + 示例轨迹已入库**（`1811c05`）：`track`/`track_point`/`stay_point` + 5 个索引（含 `GIST(geom, recorded_at)` 时空联合）；示例轨迹 121 点 / 9444.2 m / 3000 s / 均速 11.33 km/h
- **中文 Windows 下 psql 两个编码坑已修**（`2910130` / `447867d` / `542c9a0`）：① 文件是 UTF-8 但 psql 按 GBK 读 → 脚本首行 `\encoding UTF8`；② psql 自身提示行 `(1 行记录)` 按 GBK 输出、数据按 UTF-8 → 跑前 `$env:LC_MESSAGES='C'`；中文数据在控制台仍可能乱码，用 `-o 文件` + `code 文件` 兜底
- **M1 后端接口已通并实测**（`ba47315`）：`Track`/`TrackPoint` 实体（JTS `LineString`/`Point` 映射 PostGIS geometry）、两个 Repository、`GET /api/tracks`（列表）+ `GET /api/tracks/{id}`（详情含 121 个点，坐标拆成 lon/lat）；`/api/tracks/999` 正确返回 404
- **M1 前端收尾完成**（`8676744`）：`TrackList.vue`（纯展示 + 抛 select 事件）、`CesiumGlobe.vue`（`points` prop → Polyline `#7fd1ff` + 起/终点标记 + 相机 flyTo 到轨迹包围盒，实体用固定 id 重绘先删旧）、`App.vue`（统一管健康检查/列表/选中详情，支持 `?track=<id>` 深链接）
- **安全清理**（`c726fa3`）：明文数据库密码从 `_session_context.md` 与学习笔记中移除，记忆文件改为可入库

**下一步**：M1 时间轴回放（`CesiumGlobe.vue` 里 `timeline`/`animation` 目前是关的，做回放时打开），之后进 M2（停留点 / 热点 / 轨迹相似度）。

**前端渲染验证方法（2026-09-09 定稿，必读）**：用 **Playwright + 真实时间**，不要用虚拟时钟截图。
- ❌ `chrome --headless --virtual-time-budget=N --screenshot` **对本项目无效**：轨迹线由 `Primitive` 异步几何体
  （worker 创建）渲染，虚拟时钟下 worker 不完成 → 线永远不出现；而点标记是同步的 `PointPrimitive`，
  于是出现"只有两个端点、中间没有线"的假象，极易误判成代码 bug（本次就误判了一轮）。
- ✅ 正确做法：`.tmp/pw-check.py`（Playwright，`launch(channel="chrome")`）→ 打开页面 → 点 `.track-list .item`
  → `page.wait_for_timeout(10000)` 真实等待 → 截图 → `.tmp/analyze2.py` 数颜色。
- 判定标准：精确色 `#7fd1ff` 命中 ≈3812 px，包围盒 `x[766,833] y[93,813]`（纵向 720px）。
- 沙箱内 Playwright 必须提权 `danger-full-access`（浏览器子进程靠管道通信）。
- 另：左上角 UI 面板会贡献 `#7fd1ff` 像素，统计时要排除 `x<400` 的区域。

**⏸️ 用户已要求暂停（2026-09-08）**：用户表示"感觉想一步登天"，要求先消化第一阶段内容再继续。
已产出学习笔记 `docs/learning/2026-09-08-phase1-notes.md`（14 节，含环境地图/PostGIS/表设计/编码坑/
后端分层/HTTP/REST/Vue+Vite+Cesium/完整请求链路/踩坑对照表/术语表/动手练习/命令速查），
并用 `scripts/tools/md2docx.py` 生成 Word 到 `D:\Calcite-note\Calcite-第一阶段学习笔记.docx`。
**恢复开发前先确认用户是否已消化。**

**用户困惑点（已解答）**：以为"有 Cesium 却看不到地图"——地图是网页，要看浏览器 http://localhost:5173，
PowerShell 只负责启动和查错，不显示图形。

**文档工具决策（2026-09-08 定稿，不再换）**：Word 生成统一用 **python-docx**（`scripts/tools/md2docx.py`，
本机已装 1.2.0，纯文件写入、沙箱可用、已验证 329 段落/16 表格）。
- `officecli` skill 已挂回 DSH 全局技能目录（`~/.dsh/skills/officecli` → `~/.claude/skills/officecli`），
  但**本沙箱内只能读、写必然静默失败**（resident 靠命名管道，沙箱禁命名管道；且 `validate` 会对空文档假报
  `Validation passed`，只有 `officecli raw` 能验真）——**不要用它写 docx**。
- `minimax-docx` 已从 DSH 技能目录移除（需 .NET SDK + 离线 OpenXML DLL，本机 `No SDKs were found`，暂不折腾）。
- 教训：DSH 的技能根只有 5 个（项目 `.dsh/skills`、`.agents/skills`、`customSkillDirs`、`~/.dsh/skills`、
  `~/.agents/skills`）；`D:\GitHub-pack\skills-main` 之类克隆目录不会被扫描，需 junction 到上述根才生效。

### 目录结构
- `backend/` —— Spring Boot 3.5.16 + Java 25（Maven），包根 `com.calcite`
  - `CalciteApplication.java` 启动类
  - `web/HealthController.java` → `GET /api/health` 返回 status/database/postgis 版本
  - `application.yml` 入库（通用配置，默认 profile=local）
  - `application-local.yml` **含数据库密码，已 gitignore**；`application-local.yml.example` 为可提交模板
- `frontend/` —— Vue 3.5.42 + Vite 8.2.2
  - `vite.config.js` 把 `/api` 代理到 `http://localhost:8080`（避免跨域）；`define.CESIUM_BASE_URL` 指向 `/cesiumStatic`（由 vite-plugin-static-copy 从 node_modules 拷贝）
  - `src/App.vue` 统一管数据：`/api/health` + 轨迹列表 + 选中详情，支持 `?track=<id>` 深链接
  - `src/components/CesiumGlobe.vue` 三维地球：`points` prop → Polyline + 起终点标记 + 相机 flyTo；Viewer 用 `shallowRef`
  - `src/components/TrackList.vue` 纯展示组件（props 进、`select` 事件出），不发请求
- `.m2/`、`.npm-cache/` 为沙箱内构建用的本地缓存（已 gitignore，非标准位置）

### 数据库环境（已确认并修改）
- PostgreSQL 18.3（x64），安装在 `E:\PostgreSQL`，数据目录 `E:\PostgreSQL\data`，psql 在 `E:\PostgreSQL\bin\psql.exe`
- 服务名 `postgresql-x64-18`，运行中；端口 5432，listen_addresses='*'，password_encryption=scram-sha-256
- 超级用户 `postgres`；**密码不在本文件里**，见 `backend/src/main/resources/application-local.yml` 的 `spring.datasource.password`（该文件已 gitignore，不入库）
- PostGIS 3.6（USE_GEOS=1 USE_PROJ=1 USE_STATS=1），按库启用而非全局
- 数据库：`postgres`、`test_db`、`postgis_test`，以及**本项目库 `calcite`（已建，已启用 postgis 扩展）**
- 后端连接串：`jdbc:postgresql://localhost:5432/calcite`，JPA **`ddl-auto=none`**（表结构统一由 `scripts/db/*.sql` 管理；曾用 update，但 PostGIS geometry 列交给 Hibernate 自动补容易改坏）

### 构建与运行（沙箱内）
- Maven：IntelliJ 自带 `E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd`
  - 必须带 `-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository`（`~/.m2` 沙箱不可写、含中文的 TEMP 路径会乱码）
- 前端：`npm_config_cache=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.npm-cache`
  - **`vite build` / `vite dev` 在沙箱内必崩（spawn EPERM），需提权 danger-full-access**（详见 global-knowledge）
- 已验证事实：`mvn clean package` BUILD SUCCESS；`java -jar` 启动 2.59s；`GET /api/health` → PostgreSQL 18.3 + PostGIS 3.6；hibernate-spatial 集成 enabled；`vite build` 通过（11 模块）

### Git / GitHub
- 仓库：`git@github.com:YNM10086/Calcite.git`（GitHub 账号 YNM10086），分支 main
- ✅ **2026-09-12：M1 已推送，仓库是 PUBLIC**
  - **旧的"暂时不推送、只本地提交"规矩就此作废**
  - 推送时本地与远端同步在 `10d746b`（59 个提交一次性推上去）
  - 之后的规矩改为：**继续每完成一块就本地提交；稳定节点再推送**
- ⚠️ **历史里仍有旧的数据库密码（但已是死密码）**
  - 位置：`72eeda5` / `2910130` / `040833c`（`c726fa3` 是清理它的那个）
  - 处置：**2026-09-12 已把数据库密码轮换掉**（旧密码已失效，实测连接被拒）
    （改法：`ALTER USER postgres WITH PASSWORD '...'` + 同步 `application-local.yml`；
    **新密码不写在本文件里**，见那份已 gitignore 的配置文件）
  - 已实测：**旧密码连接被拒绝** → GitHub 上那串是死钥匙，不构成风险
  - 教训：**写脚本时不要把密码写进注释里**——`03-show-results.sql` 就是这么泄漏的
- 提交历史（早期）：`1e342e6` 初始化仓库 + .gitignore；`20da417` 前后端骨架；`349fe65` 删除模板 Main.java；`86dcdab` 设计文档 v1.0；`5f044d8` 小白导读；`da8eda9` PostGIS 初体验脚本；`38e91df` Cesium 三维地球接入；`1811c05` 三表 + 示例轨迹；`72eeda5` 示例轨迹查看脚本；`2910130` psql 编码修复；`447867d`/`542c9a0` 控制台乱码兜底；`ba47315` M1 后端接口；`040833c` 第一阶段学习笔记 + md2docx 转换脚本；`c726fa3` 去除明文数据库密码；`8676744` M1 前端收尾（轨迹列表 + 轨迹线）
- 本仓库 local core.sshCommand：`C:/Windows/System32/OpenSSH/ssh.exe -F C:/ProgramData/_ssh_config -i %USERPROFILE%/.ssh/id_ed25519 -o IdentitiesOnly=yes`
  - 必须带 `-F`：`github.com` 映射到 `ssh.github.com:443`（22 端口被拒/被墙）
  - 必须带 `-i` + `IdentitiesOnly=yes`：`D:\opencode_key` 权限过开放，OpenSSH 拒加载（它与 id_ed25519 是同一把 key，指纹 SHA256:34O4458D...）
- 沙箱限制：git 的 SSH 网络操作（push / ls-remote）在沙箱内必崩（`sh.exe: couldn't create signal pipe, Win32 error 5`），需提权 danger-full-access

### M1 回放（2026-09-09 完成）
- 设计文档 `docs/superpowers/specs/2026-09-09-m1-playback-design.md`；实施计划 `docs/superpowers/plans/2026-09-09-m1-playback.md`
- 新增：`frontend/src/lib/playback.js`（纯计算、零依赖）、`frontend/src/components/TrackPlayer.vue`（纯展示播放条）
- 改动：`CesiumGlobe.vue`（`SampledPositionProperty` 移动标记 + Cesium 时钟 + `defineExpose` play/pause/seekTo + `time-change` 100ms 节流）、`App.vue`（持有 playing / currentMs / loop）
- 整条轨迹固定约 60 秒播完：`clock.multiplier = 轨迹总秒数 ÷ 60`（示例轨迹 = 50 倍）；循环用 `ClockRange.LOOP_STOP` / `CLAMPED` 切换
- **回归命令**：`cd frontend && node scripts/check-playback.mjs`（17 项断言，零依赖，秒级出结果）
- **生产构建已验证**：`cd frontend && npm run build` 通过（`✓ built in 1.57s`）；Vite 构建需提权 danger-full-access（它要 spawn 子进程探测路径，沙箱内报 `spawn EPERM`）
- **验收证据（Playwright + Pillow）**：`.tmp/pw-playback.py` + `.tmp/analyze-playback.py`
  - 时刻推进 `07:30:00 → 07:33:20 → 07:36:43`；拖动到 80% 得 `08:10:00`（精确）
  - 白色移动点：播放中位移 50.5 px、暂停后 0.9 px；控制台零报错
  - 取消选中后播放条消失；121 个点全有时间戳
- 明确未做：倍速按钮、速度/海拔曲线、相机跟随、轨迹抽稀、逐段画线
- ✅ 速度数据已补：`speed_mps` 已回填（120/121 个点，`seq=0` 无前点故为 NULL），平均 11.33 km/h，范围 2.996–3.245 m/s；回填逻辑在 `scripts/db/02-sample-track.sql` 第 3 节（用 `ST_Distance(...::geography) / 时间差`）

### M1 速度/海拔曲线（2026-09-09 完成）
- 设计文档 `docs/superpowers/specs/2026-09-09-m1-speed-chart-design.md`；实施计划 `docs/superpowers/plans/2026-09-09-m1-speed-chart.md`
- 新增：`frontend/src/lib/chart.js`（纯计算，12 个导出函数，零依赖）、`frontend/src/components/SpeedChart.vue`（上下双图，纯展示）
- 改动：`App.vue`（引入组件、`@seek="seekTo"` 复用进度条同一个函数、`.status` 从 `bottom:62px` 上移到 `194px`）
- 布局：速度图 56px + 海拔图 56px + 时间轴 20px = 140px，`position:absolute; bottom:46px`
- 游标：1px 半透明虚线（`stroke-dasharray: 4 3`, opacity .7）+ 交点 r=2 白点；**游标画在数据线之前（下层）所以物理上不可能遮挡数据线**（实测只遮 4px，保留 99.9%）
- 交点用 `valueAt` 线性插值（不是最近的真实点），保证正好落在游标线与数据线的交叉处
- **回归命令**：`cd frontend && npm run check:chart`（37 项断言）；回放仍是 `npm run check:playback`（17 项）
- **验收证据（Playwright + Pillow）**：`.tmp/check-chart-pixels.py`（10 项）
  - 速度线 2888 px / 海拔线 2360 px；播放 4 秒游标位移 46→148 px
  - 点 80% 处时钟 `08:09:58`（期望 `08:10:00`，±3 秒内——1px ≈ 2 秒，鼠标无亚像素）
  - 控制台零报错
- 明确未做（YAGNI）：缩放/框选/平移、导出图片、多轨迹对比、速度平滑、加速度/坡度、曲线折叠

### 学习笔记与结构地图（2026-09-10 完成）
- 笔记存放目录：`D:\Calcite-note\`（**仓库外**，写入需提权 danger-full-access）
  - `Calcite-第一阶段学习笔记.docx` —— 基础知识点
  - `Calcite-第二天学习笔记.docx` —— 回放 + 速度/海拔曲线
  - `Calcite-项目结构地图.docx` —— **只讲结构/流程/加东西放哪里**，14 章 + 7 张手画流程图
- 笔记源文件（在仓库内，可重新生成）：
  - `docs/learning/2026-09-08-phase1-notes.md`、`docs/learning/2026-09-10-calcite-structure-map.md`
  - `docs/learning/figs/make_figs.py`（Pillow 画 7 张流程图）+ 对应 PNG
  - 生成 Word：`python scripts/tools/md2docx.py <md> <docx>`（**必须在仓库根目录跑**，图路径是相对的）
- ✅ **修好了 `scripts/tools/md2docx.py` 的老 bug**：三处 XML 元素用 `append` 而非按 OOXML 规定顺序插入，生成的 docx 有 285 个 schema 错误（Word 能开、严格校验器报错），现在 0 错误；并新增 `![图注](路径)` 插图语法
- ✅ **officecli 在本机写不进 docx**（`add`/`save` 报成功但文件是空的，`validate` 对空文档还假报通过）——生成 Word 一律走 python-docx
- 练习改动已提交（`8548f50`）：曲线配色 + `PLAY_SECONDS` 20；想恢复原样用
  `git checkout 38f42c2 -- frontend/src/components/SpeedChart.vue frontend/src/lib/playback.js`
- **用户反馈（重要）**：笔记里「底层算法/命名规范」写太多会造成压力甚至挫败感；他真正需要的是**地图型内容**——完整结构、流程图、每层职责、以后往哪加。后续笔记优先这个方向，不要堆知识点

### M1 轨迹导入（2026-09-12 完成）—— **M1 至此全部完成**
- 设计文档 `docs/superpowers/specs/2026-09-12-m1-import-design.md`；实施计划 `docs/superpowers/plans/2026-09-12-m1-import.md`（12 任务 / 69 步）
- 新增：`service/`（`GeoUtils` 球面距离、`TrackCleaner` 清洗器、`ImportService` 编排、`CleanedTrack`）、`service/importer/`（`Importer` 接口 + `RawPoint` 统一中间结构 + `ParsedTrack` + `FormatDetector` + `GpxImporter` + `GeoLifeImporter`）、`config/ImportProperties`、`web/ImportController`、`web/dto/ImportResult`
- 改动：`track_point` 加 `is_outlier` 列（脚本**两处写法**：CREATE TABLE 内 + 末尾 `ALTER ... IF NOT EXISTS`，保持"重跑即对齐"）、`Track`/`TrackPoint` 补**公开构造器**（原来只有 protected，因为数据一直是 SQL 插的）、`TrackPointDto` 暴露 `outlier`、`application.yml` 加批量插入参数与导入配置
- 两个入口：`POST /api/tracks/import`（网页上传 GPX）、`POST /api/import/geolife`（本地目录批量，配合幂等循环调用自动推进）
- **格式识别按文件内容**，不看扩展名（用户那份文件的扩展名是 `.gpx.bin_tmp`）
- 清洗规则集中在 `TrackCleaner`：排序 / 速度 / **自适应阈值 `max(8, 3×中位数)`** 标记异常（**两端都标**）/ **海拔整条全同 → 全部 NULL**
- 幂等键：文件内容 **SHA-256 前 32 位**（改名也认得）
- **后端首次引入 JUnit 单元测试**：`mvn test` 一条命令，41 项
- **坐标系已实测确认 WGS84**：轨迹中心与 OSM「东区操场」相差 **10 米**（若是 GCJ-02 会偏 400–600 米）
- 实测证据（真实 2342 点 GPX）：`pointCount=2342`、`distanceM=3933.46`、`durationS=2348`、`outlierCount=**8**`（seq 精确为 1128/1129/1135/1136/1144/1145/1585/1586）、点与线 SRID 均 = 4326、重复上传返回 `skippedDuplicate=true`、海拔全为 NULL
- **回归总览（全绿）**：后端 `mvn test` 41 项 + `check:playback` 17 项 + `check:chart` 37 项 + `.tmp/check-import-pixels.py` 5 项 = **100 项**
- ⚠️ **两个环境坑（已解决，记录备查）**：
  1. Mockito 在沙箱内 `self-attach` 失败（要 fork 外部进程 attach JVM）→ `pom.xml` 的 surefire 预挂 `-javaagent:byte-buddy-agent`
  2. `@Value` **绑不了 YAML 列表** → 必须用 `@ConfigurationProperties`
- 明确未做：CSV 上传、上传进度条、拖拽、异步任务、坐标系自动转换
- **待办**：GeoLife 数据集下载（挂机，官方 ID 52367 / Kaggle 镜像），到位后用 `POST /api/import/geolife` 灌 5-10 个用户

### 数据现状与支线任务（2026-09-14）
- 📌 **当前数据规模（2026-09-21 更新，数据管理阶段结束时）**：
  **246 条轨迹 / 286,019 个点 / 264 个停留点 / 37 个热点 / 33 个孤立点**（264 = 37 个热点吃掉 231 + 33 个孤立）
  - ⚠️ **track 39 的 id 现在是 249** —— 原来 id 39 那条被验收脚本删过
    （数据管理的"删除后相似度必须变"就是删它），重新导入后拿了新 id，**数据一致**；
    脚本里写死轨迹 id 配对的地方都要一并改
  - ⚠️ **地理构成已实测更正（2026-09-25 实测更正）**：全库 **246 条 / 286,019 个点**，
    构成 **北京 235（含 1 条示例轨迹）/ 上海 5 / 京沪长途 3 / 福建 3**（235+5+3+3 = 246）。
    **旧记录「geoLife 242 条 = user `000` 北京 171 条 + user `001` 长三角 71 条」已过时** ——
    "171 + 71"是**早期只导了两个用户**时的分布；后来按文件批量导入，geoLife 实为 **242 条**
    （= 北京 234 + 上海 5 + 京沪长途 3；京沪长途 = id **121/161/166**，各含一段 >1000 km 的跳跃），
    再加**示例轨迹 1 条**（北京）+ **用户自采 GPX 3 条**（福建）= 246 条。GeoLife 覆盖 **467 km × 1008 km**
  - ⚠️ **活库当前是 247 条 / 286,324 个点** —— 多出来的一条是 **id 650「verify-new-41c272」
    （geolife / 305 点 / external_id `8899c415…`）**，是 `verify-data-edit-api.py` 早前某次**带提权**运行的
    验收遗留物（它删完要清理时回收站导出失败，轨迹留在了库里）。
    **246 / 286,019 是"去掉这条遗留物"后的干净值**，两者差额正好 305 个点（已用 SQL 逐条核对）。
    ⚠️ 清理它需要提权（沙箱内 `DELETE` 撞回收站导出 → 500 且轨迹原样保留），**留给主控处置**
  - ⚠️ 同一次核对确认：**3 条 >1000 km 跳跃记录的轨迹就是 id 121/161/166**（跨北京↔上海，maxlat 40.07 / minlat 31.19）
  - 用户自采 **3 条 GPX 在福建** —— 仍然是 **0 个停留点**（跑步轨迹没有"50 米内停 5 分钟"的时刻）
- **GeoLife 已下载**：`D:\Calcite-note\GPX-Data\Geolife Trajectories 1.3\`（182 用户 / **18,670 个 `.plt`** / 1.59 GB）
- **已导入（2026-09-14 当时只有这些）**：用户 `000` 的 21 条（`POST /api/import/geolife` 用 `maxTracks` 控制量，幂等所以可反复跑）
- **用户自采数据**：`D:\Calcite-note\GPX-Data\资料一~四.gpx`（vivo 导出，456/623/504/432 点，无海拔，位置分散——正适合 M2 的停留点与热点）
- `allowed-roots` 已改为 `D:\Calcite-note\GPX-Data\Geolife Trajectories 1.3\Data`
- **轨迹列表可用性已改进**（2026-09-14）：`GET /api/tracks?source=&limit=` 返回 `{total, items}`，前端加了来源/条数下拉
- 📌 **支线任务（已调研，暂不实施）**：**底图换成可切换的在线图层**（现在缩放到校园尺度是一片绿色）
  - **用户已有天地图 API Key**（做别的项目时申请的）——实施时不用重新申请
  - ⚠️ **关键坑**：高德/腾讯底图是 GCJ-02，与我们实测的 WGS84 数据会偏 400–600 米；**天地图/OSM 才是对齐的**
  - Key **绝不能入库**（仓库是公开的）→ 放 `frontend/.env.local`（gitignore）
  - 完整调研（方案取舍表 / 实施要点 / 验收标准）在设计文档 **附录 B.3**

### M2 第一阶段 · 停留点识别（2026-09-14 完成）
- 设计文档 `docs/superpowers/specs/2026-09-14-m2-stay-point-design.md`；实施计划 `docs/superpowers/plans/2026-09-14-m2-stay-point.md`（6 任务 / 29 步）
- 新增：`service/StayPoint`（record）、`service/StayPointService`（算法）、`web/dto/StayPointDto` + `StayPointResponse`、前端 `components/StayPointList.vue`
- 改动：`TrackController` 加 `GET /api/tracks/{id}/stay-points`；`application.yml` 加 `calcite.stay-point.*`；`CesiumGlobe` 加 `stayPoints` prop + `drawStayPoints`（ellipse 实体）+ `focusOn`；`App.vue` 面板改两段式 flex 布局
- **算法四条规则**：空间半径 D/2、最短时长 T、**采样间隔 G 断开**、跳段不重复
- **参数默认 50 米 / 300 秒 / 300 秒**（都在 `application.yml`，可调）
- ⭐ **G 规则来自真实数据的坑**：有条轨迹断了 **8217 秒**后原地恢复，不加这条会被判成「停留了 2.3 小时」。
  探索脚本最初漏了 G，21 条轨迹报 23 段；补上后是 **10 段**
- **真实数据验收（21 条 GeoLife）全部命中**：合计 **10 段**，每条轨迹的段数与时长都与独立 Python 计算一致；
  `20081115010133` → **0 段**；操场跑圈那条（2342 点）→ **0 段**
- **真实数据指纹测试**：`sample-real.plt` 默认参数下正好 **1 段**（306 秒 / 半径 24.2 米 / 71 点），
  离两个阈值都很近，算法一改就红
- **回归总览（全绿）**：后端 `mvn test` **58 项** + `check:playback` 17 + `check:chart` 37 + `.tmp/check-stay-points.py` **7 项** = **119 项**
- ⚠️ **浏览器验收抓到一个布局 bug**：面板 z-index 是 10、底部曲线是 15，面板变高后伸进曲线区就被盖住、点不到。
  修法：面板 z-index → 20，`max-height` → `calc(100vh - 220px)`
- ⚠️ **算法的两个"非直觉但正确"行为**（已写成测试钉住）：① 停留窗口会"多吃"接近的那几秒；
  ② 起点提前的代价是能容纳的停留点变少（合成用例里 600 秒的停留报成 579 秒）
- 明确未做：结果入库 `stay_point`、前端调参滑块、停留时段在曲线上标色带（用户选了布局 A）、POI 匹配、语义分类

### 前端面板布局改版（2026-09-14）
- 起因：用户反馈「左上角面板太拥挤，停留点列表的滚动条刺出面板框」
- 量出来的真实原因：面板固定宽度 320px + `max-height: calc(100vh - 220px)`，
  而**固定头部内容就占 392px**（其中「后端连通性」那个 4 行列表一项 120px），
  600px 高的视口里面板只有 397px —— 结构上塞不下，会被 `max-height` 裁掉
- 改法（`App.vue` + `TrackList.vue` + `StayPointList.vue`）：
  1. 面板改成 `top/left/bottom` 双向锚点 + `width: min(420px, 34vw)`，**铺满左上角**，
     下边界永远停在曲线正上方（`--chart-h` / `--player-h` / `--gap` 三个 CSS 变量集中定义）
  2. 连通性 4 行列表压成一行（`UP · PostgreSQL 18.3 · PostGIS 3.6`），完整信息放 `title`；
     去掉多余的「点一条轨迹」提示语
  3. 两个列表 `flex: 1 1 0` 平分剩余空间，最小高度由 `--list-min` 控制
  4. **状态条从「左下角绝对定位浮层」收进面板底部当一行** —— 它原来 z-index 10、
     被面板（20）压住，其实早就坏了
  5. `@media (max-height: 660px)` 矮窗口下隐藏副标题 + 调小列表最小高度
- 实测（`.tmp/shot-panel.py`，三个视口**全部零溢出**）：
  - 1600×900：面板 12,12→432,709，两个列表各 235px（原来只有 80px）
  - 1600×600：面板 397px，列表各 96px
  - 1366×660（笔记本，最常见的矮窗口）：面板 457px，列表各 126px，副标题自动隐藏
- ⚠️ **顺手修了两个 bug**
  1. `.tmp/check-chart-pixels.py` 一直在**假红**：判据写的是「绿色速度线/橙色海拔线」，
     但练习提交 `8548f50` 换过配色（现在是 `#722ED1` 紫 / `#165DFF` 蓝），
     那个"绿色 215 像素"其实是地球底色透过来的。已改成**从 DOM 读 stroke 实际颜色**再数像素
  2. `.tmp/check-stay-points.py` 和 `check-import-pixels.py` 里排除面板用的是写死的
     `x >= 400`，面板加宽到 432px 后会把面板的蓝字/橙色条目误算成地图上的线。
     已改成**问 DOM 要 `.panel` 的右边界**（以后改宽度不会再假红/假绿）
- 回归：后端 58 + check:playback 17 + check:chart 37 + check-stay-points 7 +
  **check-chart-pixels 10** + **check-import-pixels 5** + **check-filter 6** = **140 项全绿**
  （之前笔记里写的 119 项只算了前四个，后三个是 M1 留下的脚本，一直没纳入统计）

### M2 第二阶段 · 停留热点（2026-09-17 **已完成**）
- 设计文档 `docs/superpowers/specs/2026-09-15-m2-hotspot-design.md`；实施计划 `docs/superpowers/plans/2026-09-15-m2-hotspot.md`（分支 `feat/m2-hotspot`）
- **接口**：`GET /api/analysis/hotspots` —— 把**所有轨迹**的停留点**跨轨迹**聚类成热点（新增 `AnalysisController` + DTO）
- **算法**：并查集单链聚类（等价 `minPts=2` 的 DBSCAN）。五步：两两 haversine 算距离 →
  `d <= radiusM` 连边（**含等号，有测试钉住**）→ 并查集求连通分量 → 分量点数 < minVisits 判为孤立点 →
  汇总重心 / visitCount / trackCount / totalDurationS / 真实散布 / 首末访问时间
- 排序**五级**：`trackCount ↓ → visitCount ↓ → totalDurationS ↓ → centerLat ↑ → centerLon ↑`（后两级让结果与输入顺序无关）
- **真实数据结果**（25 条轨迹 / 13,720 点 → 10 个停留点 → **3 个热点 + 1 个孤立点**）：

  | rank | 中心 | 次数 | 轨迹数 | 累计时长 | 真实散布 |
  |---|---|---|---|---|---|
  | 1 | 40.011572, 116.296853 | 4 | 3 | 1730 s | 9.4 m |
  | 2 | 40.008948, 116.321793 | 3 | 3 | 1228 s | 58.1 m |
  | 3 | 40.006719, 116.296562 | 2 | 1 | 650 s | 59.1 m |

- ⚠️ **两个必须记住的算法特性**：
  1. **传递性（链式效应）**：A─B 150 m、B─C 150 m 则 A、B、C 合成**一个**横跨 300 米的热点。
     这是单链聚类的定义（`minPts=2` 的 DBSCAN 行为相同），**设计决定不修**，已用测试钉住
  2. **O(n²) 两两比较**：停留点上万时会明显变慢。缓解办法是「先按经纬度分桶再比」，**当前不做**
- **参数依据 `radiusM = 200`**：实测 10 个停留点的 45 对距离里，**118.3 米之后直接跳到 231.5 米**
  （中间空了 113 米），所以 **119~231 米之间任意取值结果完全相同**
- **停留点仍不入库**：触发入库的条件 = 轨迹数超过 **500 条**，或热点接口耗时超过 **2 秒**
  → 那时把停留点入库 `stay_point`、改 SQL 聚合（见设计文档 10.2）
- **前端交互**：面板加「停留点 / 热点」切换开关；热点圈**大小 = 次数**、**颜色 = 轨迹数**；列表带排序下拉
- 测试：`HotspotServiceTest` **14 项**（含**真实数据指纹**；审查后补了 `minVisits=3` 用例）；
  ⚠️ 夹具坐标必须**全精度**（截断到 5 位小数 ≈ 1 米误差，1e-6 容差直接红）
- 主要提交：`19e2626` 类型+批量查询 → `7d760c4` HotspotService → `6099e5c` 校验/测试修复 →
  `562592b` Controller+DTO → `cc7cc60` 对拍脚本 → `4f90fd7`+`4b20405` 前端 lib →
  `ef586ec` HotspotList → `d45fda1`+`9176c27` CesiumGlobe → `548223b` App 集成 →
  `aea346c` 集成修复（fitBounds 避面板 / 矮窗口溢出）→ `97d38b6` 浏览器验收
- ⚠️ **实测踩到的坑（留给下次）**：**Cesium 的 `flyTo(Rectangle)` 会铺满整个画布，而左侧被面板盖着
  → 西边的热点被面板遮住**。修法：`fitBounds` 现在接一个 `insetLeft` 参数
  （**面板右边界 ÷ 画布宽**）来避开
- **回归：228 项全绿**（后端 `mvn test` **72 项** = 原 58 + 新 14；node 回放 17 + 曲线 37 + 热点纯函数 24；
  浏览器 停留点 7 + 曲线像素 10 + 导入像素 5 + 列表筛选 6 + 热点验收 16；热点对拍 34）
  —— 之前基线 140 项，本次净增 **88 项**

### 学习笔记（M2 第二阶段）
- **`docs/learning/2026-09-17-m2-hotspot-notes.md`** —— 9 节，只讲三件事：热点是什么、
  前端怎么用、**为什么用户看不到自己的数据**；**2026-09-17 追补第 10 节「数据扩充之后」**
- 图：`docs/learning/figs/fig-hot-1-why.png`（你的福建数据 vs 北京 GeoLife，相距 1665 km）、
  `fig-hot-2-howto.png`（前端操作示意，标注位置是从 DOM + 像素**实测**的，不是估的）
- 画图脚本 `docs/learning/figs/make_hotspot_figs.py`；Word 版在 `D:\Calcite-note\Calcite-M2停留热点笔记.docx`
- ⭐ **用户当时的疑问**：以为"自己的数据没形成热点所以没显示"。
  实际是**两件事**：① 他的 3 条 GPX（资料一/二/sample）停留点确实都是 **0**（跑步轨迹没有
  50 米内停 5 分钟的时刻）—— 这半对；② 但**热点显示了 3 个**（当时的数据；扩充后是 37 个），只是全部来自 GeoLife，
  而他的数据在**福建（25.03N, 117.02E）**、GeoLife 在**北京（40.00N, 116.32E）**，
  **相距 1665 公里** —— 切到热点档相机飞到北京，他的轨迹线被甩出屏幕，所以"看着什么都没有"。
  这不是 bug，反而说明算法没把"跑步经过"误判成"停留"。

### M2 第三阶段 · 网格密度（2026-09-17 完成）
- 设计文档 `docs/superpowers/specs/2026-09-17-m2-density-design.md`；实施计划 `docs/superpowers/plans/2026-09-17-m2-density.md`（分支 `feat/m2-density`）
- **接口**：`GET /api/analysis/density?bbox=&cellSize=&metric=&hourFrom=&hourTo=&from=&to=` ——
  把地球切成方格、统计每格有多少轨迹（回答"早高峰哪些路段人最多"）；`metric` = `tracks`（轨迹条数，默认）/ `points`（点数）
- **前端第三档**：面板开关从两档变**三档**「停留点 / 热点 / 密度」；新增 `components/DensityLegend.vue`
  （图例色条 + 时段下拉 + 口径切换 + 统计行）；刷新由 Cesium `camera.moveEnd` 驱动（400ms debounce + 乱序请求防护）
- **四个关键设计决定**：
  1. **按视野裁剪** —— 全量一次性返回不可行：最细档 `0.0001°` 是 **75,970 格 / 3.3 MB**。改由前端把当前视野 `bbox` 传上去，只算视野内
  2. **对数色阶** —— 实测每格轨迹条数**中位数 2 / 最大 152（76 倍）**，线性色阶下绝大多数格子都是最浅色、等于一张白纸；对数才看得出结构
  3. **格边长用固定档位阶梯**（不是连续值）—— 只在**跨档那一瞬间**变一次，其余时候拖动地图**格子纹丝不动**；档位离散 → 可复现、能写测试
  4. **时段筛选两层** —— 一天内时段（整天 / 早高峰 7-9 / 白天 10-16 / 晚间 17-22，**北京时间**，含两端）+ 日期范围 `from`/`to`（复用第二阶段的写法）
- **实现要点**：
  - ⭐ `round(ST_X(geom) / cell)` 等价替代 `ST_SnapToGrid`，**快约 2 倍**。**不是"完全相同"**：
    差异 100% 落在**恰好压格子边界的点**（`116.4095/0.001` 在 double 下是 `116409.49999999999`，
    而 `x*1000` 精确等于 `116409.5` → 取偶规则把同一个点分到相邻格）。
    改用**四条可证明的断言**钉住（边界点才不同 / round 是 snap 的子集 / 差集 ≤ 2 / 默认档格子集合严格相同），
    边界行为写进已知限制 —— **不修代码**：任何网格划分都必须为边界点定规则，换写法只是换规则
  - ⚠️ **阶梯最粗档必须是 5°** —— 挑档规则是「阶梯里 ≥ 视野宽度 ÷ 80 的最小档」，所以阶梯能覆盖的最大视野 = 最粗档 × 80。
    用户**一打开地图就是全球视野（360°）**，最粗档若是 `0.05°`（只覆盖 4°），挑档会退回最粗档 →
    估出 **2592 万个格子** → 后端**直接 400**，等于第一次点「密度」就报错。
    加宽到 15 档、最粗 **5°** 后 `5 × 80 = 400° > 360°`，全球视野下 72 × 36 = **2592 个格子**，安全
  - 上限保护：单次请求格子数 > `max-cells`（**20,000**）直接 400 + "请放大视野或换更粗的格子"
  - 跨 180° 经线时 `west > east` 会被后端判非法 → `getViewBbox` 专门处理过
- **附带任务（热点接口提速）**：`StayPointCache`（**按 trackId 缓存停留点**；关键前提是**轨迹导入后就不再变** ——
  系统没有编辑/删除轨迹的功能，所以缓存永不失效）+ `TrackRepository.findAllIds()`（只取 id，不再水合 246 条 LineString / 28.6 万顶点）。
  热点接口 **4.9s → 2.4s → 1.9s**
- **回归基线（全绿）**：后端 JUnit **96**；前端 node **104**（playback 17 / chart 37 / hotspot 25 / density 25）；
  浏览器与接口脚本 **8 个全绿**（stay 7 / chart-pixels 10 / import-pixels 5 / filter 7 / hotspots 17 / density 15 /
  verify-hotspot-api / verify-density-api 51）
- **学习笔记**：`docs/learning/2026-09-17-m2-hotspot-notes.md` 补了**第 10 节「数据扩充之后」**
  （数据 25→246 条、热点 3→37 个、热点接口 4.9 秒的两个修法、验收脚本写死数字全废的教训）

### M2 第四阶段 · 轨迹相似度（2026-09-17 完成）
- 设计文档 `docs/superpowers/specs/2026-09-17-m2-similarity-design.md`；实施计划 `docs/superpowers/plans/2026-09-17-m2-similarity.md`（分支 `feat/m2-similarity`）
- **接口**：`GET /api/analysis/similarity?trackId=&toleranceM=&limit=` —— 给一条轨迹，找出"走得最像"的其它轨迹；
  前端面板开关从三档变**四档**「停留点 / 热点 / 密度 / **相似**」
- **三个关键设计决定**：
  1. ⭐ **双向重合度取小** `min(fwd%, rev%)` —— 用一条轨迹的点算"有多少落进对方的容差范围"，**两个方向都算、取小值**。
     **这是整套度量的关键**：只算单向的话，一条短轨迹**完全被包含**在长轨迹里就是 100%
     （实测 track 6 的 1.3 km 完全落在 track 18 的 20.7 km 上），这个"被包含"必须被压下去 —— 取小后是 **34.4%**
  2. **`ST_FrechetDistance` 实测不可用，改用双向重合度** —— Fréchet 看着最合适（PostGIS 内置），实测被否掉：
     ① 4326 下**单位是度不是米**；② 数据跨两个城市（北京 + 长三角），**没有任何单一投影带能罩住**；
     ③ **转 `geography` 后没有这个函数**；④ 它取"最坏的那个点对"，**对 GPS 跳点极度敏感**（一个野点就毁掉整条相似度）
  3. **让主线的点驱动查询**（走空间索引）—— 同样语义换个写法 **0.79 秒 → 8.5 秒（11 倍）**，
     用"点到折线"则 **12.8 秒（19 倍）**；只有点驱动才命得中 `track_point` 上的 GiST 索引
- ⚠️ **一次重要的前提更正（采样间距）**：原先断言"GeoLife 采样间距 3~15 米，所以'用采样点代表折线'的近似成立"，
  **实测是 5~42 米（差 8 倍）** → **单向百分比被严重低估**（真值 100% 只算成 43%）。
  但 **相似度（取小）几乎不受影响**：被低估的那一路恰好是本来更大的那一路，
  **六组实测与真值差 ≤ 0.6 个百分点**。⭐ **这个性质是意外收获、不是设计出来的，已写成测试钉住**
- **实现要点**：
  - 缓存键**必须带 `toleranceM`**（同一 `trackId` 换个容差是另一组结果，漏了会返回错数据）
  - SQL **不写 `LIMIT`** —— 响应里的 `compared`（本次比了多少条）要的是全量候选数
  - `eps`（容差换算成度）**按主线自身纬度算**，不当常量
- **实测结果**：track 20 与 **197 条**轨迹比过，第一名 track 39 = **91.1%**
- **性能**：首次约 **2 秒**（要算 197 条候选），之后按 `(trackId, toleranceM)` 缓存**瞬间返回**
- **回归基线（全绿）**：后端 JUnit **121**；前端 node **123**（playback 17 / chart 37 / hotspot 25 / density 25 / **similarity 19**）；
  浏览器与接口脚本 **10 个全绿**（stay 7 / chart-pixels 10 / import-pixels 5 / filter 7 / hotspots 17 / density 15 / **similarity 17** /
  verify-hotspot-api / verify-density-api 51 / **verify-similarity-api 35**）

### 数据管理（2026-09-21 完成）
- 设计文档 `docs/superpowers/specs/2026-09-21-data-management-design.md`；实施计划 `docs/superpowers/plans/2026-09-21-data-management.md`（分支 `feat/data-management`）
- **交付物（后端）**：`PATCH /api/tracks/{id}`（改名，非空 / 去首尾空格 / ≤ 200 字）、
  `DELETE /api/tracks/{id}`（删除）、`POST /api/tracks/import?mode=&replaceTrackId=&allowSameName=`（添加 / 替换 / 同名 409）。
  新增 `config/DataProperties`、`service/TrackExporter`（GeoJSON 导出）、`service/TrackEditService`（编排）、
  `web/dto/TrackConflictResponse`；改 `web/TrackController`、`service/ImportService`、`application.yml`
- **交付物（前端）**：`TrackList` 的「导入轨迹」按钮改成「**数据编辑**」→ **整个面板切换成管理视图**
  （不从按钮下方展开）；新增 `components/DataManager.vue`（表格 + 行内改名 + 删除确认 + 同名三选一）、
  `components/ConfirmDialog.vue`、`lib/dataEdit.js`（纯计算）；`App.vue` 加 `panelView: 'analysis' | 'manage'`
- ⭐ **账已兑现**：`StayPointCache` / `SimilarityCache` 的 javadoc 里一直写着
  「将来加了"删除轨迹 / 重新导入覆盖同名轨迹"，**必须调用 invalidate 清理**」—— 这个功能把它们接上了。
  **四条关键测试（实测通过）**：
  1. 删掉相似度第一名（track 39）→ 主线 20 的 `compared` **197 → 196**（缓存真被清了）
  2. 改名 → 别的主线的匹配列表显示**新名字**（`SimilarityMatch` 带 `name`，不清就是旧名字）
  3. 删除前回收站文件**真的落盘**（点数与删除前一致、每个点都带时间）
  4. **新增导入 → `compared` 196 → 197**（新增也清了；这条是实施时补的第四条，设计里只写了三条）
- **六个关键设计决定**（都有实测依据）：
  1. **删除前先导出到回收站，导出失败就不删（fail-safe）** —— 实测回收站目录写不进去时
     `DELETE` 返回 **500 且轨迹原样保留**（这正是设计要的行为）
  2. **同名上传返回 409**，让用户决定「替换 / 新增 / 取消」（同名是意图问题，系统猜不准；自动替换不可逆）
  3. **替换保持 `trackId` 不变**（原地更新，不删不插）
  4. **改名也必须清相似度缓存** —— 因为 `SimilarityMatch` 里带了 `name`（摸代码时才发现，光看"改名"两个字想不到）
  5. **宁可全清缓存不要漏清** —— 漏一个就是"界面显示一条已经不存在的轨迹"；全清的代价只是下次点相似度等 2 秒
  6. **整个面板切换成管理视图**（不从按钮下方展开）—— 表格形态最不容易点错（246 条里要删的是哪一条一眼能确认）
- **回收站目录**：`D:\Calcite-note\backups\deleted`（配置项 `calcite.data.recycle-dir`；
  **不复用** `calcite.import.allowed-roots` —— 那个是导入时的读白名单，用途不同）
- **回归基线（实测全绿）**：后端 JUnit **133**（上一阶段 121）；前端 node **134**
  （playback 17 / chart 37 / hotspot 25 / density 25 / similarity 19 / **data-edit 11**）；
  浏览器与接口脚本 **11 个全绿**：stay 7 / chart-pixels 10 / **import-pixels 6** / filter 7 / hotspots 17 /
  density 15 / similarity 17 / **data-edit 19** / verify-hotspot-api 375 / verify-density-api 51 / **verify-similarity-api**
- **数据现状（2026-09-21 实测）**：**246 条轨迹 / 286,019 个点 / 37 个热点 / 264 个停留点**
- ⚠️ **收尾时修掉的**：`verify-similarity-api.py` 里写死的轨迹配对 —— track 39 被验收脚本删掉后脚本**除以零**红掉；
  改成从接口取期望值（同第三阶段的教训：验收判据不要写死数据量 / 数据 id）

### M3 · 空间范围查询（2026-09-25 完成）
- 设计文档 `docs/superpowers/specs/2026-09-25-m3-within-design.md`；实施计划
  `docs/superpowers/plans/2026-09-25-m3-within.md`（12 任务）；起点导读 `docs/superpowers/M3-START-HERE.md`
- **接口**：`POST /api/analysis/within`，body `{geometry(GeoJSON), bufferM?, from?, to?, limit?}`；
  返回 `{region, stats{trackCount, pointCount, distanceM, sourceCounts, earliest, latest}, items[], total, truncated, params}`
- **三种画法**：拉框 / 自由多边形 / 缓冲区 —— 前端分析面板从四档变**第五档「圈选」**
  （`[停留点 | 热点 | 密度 | 相似 | 圈选]`）
- ⭐ **`region` 回显后端真正用过的几何** —— "校验的几何 / 查询用的几何 / 回显的几何"由**同一条小查询**产出，
  于是"**看到的圈 = 查的范围**"是**结构上的保证**，而不是靠纪律（设计文档 11.4）
- ⭐ **性能的关键发现：缓冲区不要用 `ST_DWithin`** ——
  `ST_DWithin(t.geom::geography, 圆::geography, r)` 实测 **303 ms 且顺序扫描**
  （`::geography` 是表达式、用不上索引；真正的瓶颈是"对每条候选轨迹的**每个顶点**算椭球距离"）。
  改成**让 PostGIS 把圆算成多边形**：`ST_Intersects(t.geom, ST_Buffer(点::geography, r)::geometry)`
  → **7.9 ms（约 38 倍）**；后端因此**只剩一条判定路径**（圆多边形与手画多边形走同一段代码）
- ⚠️ **平面 vs 球面的分歧**：全库有 **3 条**轨迹（id **121/161/166**）各含一段 >1000 km 的跳跃记录，
  平面解释与球面解释在这 3 条上**最大差 11.7 km**。实测 `(118.95, 35.66)` + 1.5 km 缓冲区：
  **平面（圆多边形）3 条 / 球面（`ST_DWithin`）0 条**。**有意不修** ——
  修它就得放弃索引（回到 303 ms）；已用**测试 + 验收**钉住（设计文档 3.4）
- ⚠️ **非法几何会"静默出错"**：自交（蝴蝶结）多边形 `ST_IsValid = false`，
  但 `ST_Intersects` **不报错**，而是返回 **237 条** —— 比它的外接矩形（232 条）**还多**，用户无从察觉。
  所以加了 `ST_IsValid` 守卫：一律 **400 + 中文原因**（"区域有交叉，请重画"），**不自动修复**
  （这是**拓扑**问题，`RegionGeometry` 的结构校验管不到；环未闭合之类的**结构**问题在那一层就被挡成 400）
- ⚠️ **绑定变量会换执行计划**：区域内点数统计用**字面量**实测约 **180 ms**（顺序扫描 + 聚合）；
  改用**绑定参数**走通用计划时，优化器改选空间索引、但要多付一次**外部排序落盘**（2.1 MB）→ **456 ms**。
  本轮**接受 180~456 ms 区间**（接口总耗时实测 **203~628 ms**，远低于 1000 ms 红线），**未优化**
- ⚠️ **`pointCount` 必须也受时间窗约束**（计划评审时抓到的**真缺陷**，设计文档 11.12）——
  否则会出现"**0 条轨迹穿过、却有 18 万个点**"这种统计卡。时间窗口径与 `trackCount` 一致
- **新增回归基线**：后端 `mvn test` **162**（基线 133 → 162）；前端 node **7 个套件 153 项**
  （playback 17 / chart 37 / hotspot 25 / density 25 / similarity 19 / data-edit 11 / **region 19**）；
  浏览器 `.tmp/check-within.py` **31 项通过 / 0 失败 / 0 跳过**
  ⚠️ 注意：任务书里写的"期望 163"是**陈旧值** —— 163→162 是 Task 4 修复轮**有意合并**了一条
  （断言更强，非丢测试；`progress.md:175`、计划 `:1320/:1379/:2820` 都写 162）
- ⚠️ **已知限制（不修）**：极快甩动绘制后地球会**轻微跳一下** ——
  合成拖拽实测 **20% 视野跨度**，人类速度拖拽实测 **0**（Cesium 输入聚合器在合成事件下被激发）
- 📌 **明确未做**：保存 / 命名区域、区域导出、多区域叠加、区域内的深度指标（限速 / 爬升）

### ▶ 下次接着做（2026-09-25 M3 收工时的状态）
- ✅ **M2 全部完成**（四个阶段：停留点识别 → 停留热点 → 网格密度 → 轨迹相似度）；
  前端**四档**「停留点 / 热点 / 密度 / 相似」可用
- ✅ **已推送到 GitHub（2026-09-17）** —— `e62b1c8..7e6fe23  main -> main`，
  90 个提交已上传；本地与 origin/main 同步（0 待推送 / 0 落后）。**M2 至此正式交付。**
- ✅ **「数据管理」已完成、已合并、已推送**（2026-09-21）——
  添加 / 替换 / 改名 / **删除** 全通，并兑现了 M2 留下的两处缓存欠账（详见上一节）。
  分支 `feat/data-management` 已快进合并回 main 并删除；
  `3a3cbe2`（功能）+ `44369c0`（Word 报告）两次推送，**本地 = origin/main**。
- ✅ **M3 全部完成（2026-09-25）** —— 两个交付项都已落地：
  - ✅ **空间范围查询** `POST /api/analysis/within`（拉框 / 自由多边形 / 缓冲区；前端第五档「圈选」）
  - ✅ **路网匹配评估** —— **结论：不做（不实现）**。理由是前置空缺太大（零路网数据 / 无 pgRouting，
    光把全国 OSM 导进 PostGIS 就要一周以上）、数据形态与算法假设不匹配（5~42 米采样对主流引擎属低频；
    3 段 >1000 km 跳变会被强制断链）、且对现有能力**零增益**。
    完整结论在设计文档**第 12 节**，调研底稿另存 `docs/map-matching-assessment.md`；
    将来若要轻量替代（点到最近道路距离 / 路网可视化 / 一次性离线演示）见 12.3，各约 1 天
- **下一步 = M4 收尾**：**README + 架构图 + 部署文档 + 演示数据集**（M3 之后不再加新的分析功能）
- ⚠️ **合并与推送未做**：分支 `feat/m3-within` 只做了**本地提交**，
  **合并回 main 与 `git push` 由主控在最终审查之后处理**（本阶段所有任务都遵守这条）

- ✅ **用户点名的 Word 交付物已交**（2026-09-21）——
  `D:\Calcite-note\2026-09-21-数据管理改动报告.docx`（40 KB / 61 段落 / 5 表格），
  仓库里也有：`docs/learning/2026-09-21-数据管理改动报告.{md,docx}`；
  更早那份四阶段全景 `2026-09-17-M2-全景笔记.docx` 也在同一目录。

- 📌 **（以下为历史记录，已完成）** 当初点名的交付物：
  **生成一份 Word 文档讲述 M2 第三阶段（网格密度）**，其中要**重点讲「数据扩充对 Calcite 的影响」**。
  素材已齐，可直接取：
  - `docs/superpowers/specs/2026-09-17-m2-density-design.md`（设计）
  - `docs/learning/2026-09-17-m2-hotspot-notes.md` **第 10 节「数据扩充之后」（专讲这件事）**
  - 本文件的「M2 第三阶段」小节
  要覆盖的影响面：
  ① 数据 **25 → 246 条**（geoLife 两个用户两个城市：北京 171 + 长三角 71）、**热点 3 → 37 个**、最热的从 3 条轨迹变成 22 条；
  ② 数据长大**逼出来的三个设计决定** —— 格子数爆炸（全量最细档 3.3 MB）→ 必须按视野裁剪；
     数值极端偏斜（轨迹条数中位数 2 / 最大 152）→ 必须上**对数色阶**（线性下下半数格子平均深浅只有 0.008，等于白纸）；
     `ST_SnapToGrid` 要排序并落盘 6.5 MB → 换等价的 `round(ST_X/cell)`（快约 2 倍）；
  ③ **热点接口 4.9 → 1.9 秒**（按 trackId 缓存 + 不再加载 track 几何）；
  ④ **验收基线里 9 处写死的数字同时失效**（教训：验收判据要从接口取期望值，不要写死数据量）；
  ⑤ **用户自采 GPX 仍为 0 停留点**这个结论没被推翻（跑步轨迹不停）。
  生成工具：**`python-docx`** —— 先写 .md，再在**仓库根目录**跑
  `python scripts/tools/md2docx.py <md> <docx>`（图路径是相对的，必须在根目录跑）。
  ⚠️ **不要用 officecli 写 docx** —— 它在本机写不进（add/save 报成功但文件是空的，
  validate 对空文档还假报通过）。这条决策 2026-09-08 就定稿了（见本文件前面的「文档工具决策」）。
- 开工前值得先定的一件事：**要不要趁这时把停留点入库 `stay_point`** ——
  触发条件是轨迹数 > **500 条** 或 热点接口 > **2 秒**；当前 246 条、热态 **1.9 秒**
  （在红线内但**余量很薄**），所以还没入库
- ⚠️ **三个已知的后续优化（都不是缺陷，是欠账）**：
  1. **热点接口热态 ~1.9 秒** —— 已在 2 秒红线内，但余量薄。要么改成**标量投影**
     （只取需要的列，别水合实体），要么按设计文档 10.2 的触发条件**把停留点入库**
  2. **密度接口的颜色只在同一视野内可比** —— 后端只返回本视野的格子、颜色深浅按**本次响应的最大值**归一化，
     换个视野同一个格子颜色会变；图例写了**绝对刻度**作为补偿，但"跨视野比色"本身不可靠
  3. **相似度的"单向百分比"是近似值** —— 用**点对点**（主线点 ↔ 对方点）代替**点到折线**，
     对方轨迹稀疏时会**低估**（实测 GeoLife 采样间距 5~42 米，真值 100% 能算成 43%）；
     但 ⭐ **相似度本身是可靠的**（取小那一路恰好是本来更大的那一路，六组实测差 ≤ 0.6pp）。
     要更准就得上点到折线，**代价 19 倍**（0.79 秒 → 12.8 秒），当前不做
- 跑浏览器验收（`.tmp/check-*.py` 系列）必须**后端 8080 + 前端 5173 同时运行**；
  重启后端的命令见实施计划里的 `spring-boot:run`（Vite 在沙箱内要提权 `danger-full-access`）

**⚠️ 第二阶段结尾审查提出、但决定推迟的两件事**（不是缺陷，是下一阶段顺手补的债）：
1. **HTTP 层零自动化测试** —— `AnalysisController` / `HotspotDto` / `HotspotResponse` /
   `findAllByTrackIds` 没有任何 `@WebMvcTest`。后果很具体：**把 `HotspotDto.centerLat` 改个名，
   后端 72 项 + 前端 25 项全都还是绿的**；`?radiusM` / `?minVisits` / `from` / `to` 四条参数路径
   和 400 分支一次都没被自动化测过；`params` 回显字段全仓库无人断言。
   现在只靠**手工**的 `.tmp/verify-hotspot-api.py` 兜着（它需要活的后端 + 数据库 + 那 25 条特定轨迹）。
   → 建议在第三阶段开工时顺手加一个 MockMvc 用例（service 用 mock，不需要数据库）。
2. **排序下拉在现有数据上"看不出效果"** —— 三个热点在三个口径下**本来就同序**
   （1730/4/3 → 1228/3/3 → 650/2/1），所以切排序时列表顺序不变。
   因此浏览器验收里"按时长排序后第一条仍是 29 分钟"这条**即使接线断了也照样绿**。
   真正有效的保护只有 `check-hotspot.mjs` 里对 `SORT_OPTIONS` 与键名一致性的断言。
   → 建议等数据里有"多口径不同序"的热点时再补一条真的能分辨的断言。


## 踩坑记录

### 数据管理阶段（2026-09-21，四条）

1. **`maxTracks` 不是"最多补几条"，是"最多处理几个文件"** ——
   主控为了补回被删的一条轨迹，传了 `maxTracks: 400`，结果把**其它用户从未导入过的 399 个文件**也导进来了
   （**245 → 645 条**）。修复方式是**直接走 SQL 删掉多余的**（走 API 删会 399 次都撞上"回收站写不进去" → 500）。
   **教训：批量导入的 `maxTracks` 要按"文件数"理解，补数据之前先算清会扫到哪些文件。**
2. **跑验收前必须确认后端跑的是当前源码** —— 对拍脚本第一次跑红，看着像"新增没清缓存"的重大发现，
   实际是 **JVM 启动时间早于编译时间**（跑的是旧代码）。判别方法：比对
   **`JVM 启动时间` vs `ImportService.class 的编译时间`**。
3. **沙箱里后端写不进 `D:\Calcite-note\backups\deleted`** —— 实测 PowerShell / cmd / Python 三种运行时
   写 `D:\`、`E:\`、`C:\Users\` 下的用户目录**全部 `WinError 5`**。
   **这是沙箱限制，不是代码问题**：同样的源码只改 `calcite.data.recycle-dir` 一个参数、指向工作区目录就一切正常。
   **在沙箱外跑（IntelliJ / 普通终端）不受此限。**
4. **删除失败时 HTTP 响应体不带原因** —— Spring 的 `server.error.include-message` 默认 `never`，
   所以 `RecycleExportFailedException` 的 message 被吞掉，排查只能靠对照实验。
   ✅ **M3 已顺手还上**：`application.yml` 的 server 段加了 `error.include-message: always`（提交 `163d2fd`），
   现在 400/500 的**中文原因**都能进响应体（`verify-data-edit-api.py` 里那次 500 已能看到
   `导出到回收站失败，未执行`）。

### M3 · 空间范围查询（2026-09-25，三条）

1. **Cesium 的 `screenSpaceCameraController` 挂在 `viewer.scene` 上，不在 `viewer` 上** ——
   **现象**：只在浏览器里炸 —— `Cannot set properties of undefined (setting 'enableRotate')`，
   绘制模式**压根进不去**（Critical）。
   **根因**：设计时照着 `.d.ts` 的模块路径推断成 `viewer.screenSpaceCameraController`；
   而**桩测试发现不了** —— 替身把属性放在了 `viewer` 上，于是桩跑全绿、只有真浏览器炸。
   **解法**：改走 `viewer.scene.screenSpaceCameraController`（提交 `2f3ac0e`）。
   ⭐ **教训：设计核验不能只查 `.d.ts`，必须对运行时摸一次。**
2. **判据不能是"恒真"的** ——
   **现象**：浏览器验收里"统计卡存在"这类断言，在**圈选档**里恒成立，**哪怕地球被转了也通过**
   （脚本已经算出 `state_d` 却没消费它，等于用一条永远为真的证据去支撑"D 段降级"）。
   **根因**：`startDraw` 不清统计，且 `WithinStats` 根 div **无 `v-if`、无条件渲染** →
   B 段的 `stat-tracks` 一直留在 DOM 里，"在不在 DOM"与"这次交互有没有生效"无关。
   **解法**：改用**网络请求计数** —— 取 `POST /api/analysis/within` 的前后增量
   （实测 `1→2→3→4`），它直接反映"这次交互真的发了查询"。
   ⭐ **教训：断言要能区分"做对了"和"什么都没发生"；恒真断言比没有断言更危险（它会伪装成证据）。**
3. **代理量推断内部状态有风险** ——
   **现象**：用"视野包围盒位移"判断"旋转有没有被关掉"，在 Playwright **合成快速拖拽**下会被
   **Cesium 输入聚合器**污染 —— 合成拖拽实测位移约 **20% 视野跨度**，而**人类速度拖拽实测为 0**。
   **根因**：代理量（视野位移）**不是**"旋转开关"本身，它同时受输入聚合、惯性余摆等旁路因素影响。
   **解法**：有**直接证据**时就用直接证据 —— `getRotateEnabled()` 判旋转、
   `wait_view_stable` 先等相机停稳；代理量**只作信息输出**（D 段已降级为 `note`，不判红绿）。
   ⭐ **教训：代理量适合"发现问题"，不适合"判决问题"；一旦拿得到真值，就别再让代理量决定红绿。**

## 工作流
- 技术栈：SpringBoot3 + Vue3 + Cesium + PostgreSQL/PostGIS
- 数据库连接：`psql -U postgres -h localhost -p 5432 -d calcite`，密码见 `application-local.yml`
- 敏感文件策略：`application-local.yml`、`_session_context.local.md`、`.env`、`*.key/*.pem/*.jks`、`logs/` 等已在 `.gitignore` 排除；
  `_session_context.md` 已脱敏（只留密码指针），因此**可以正常入库、享有版本历史**
- 每次改动后本地提交留回滚点；**仓库已公开（2026-09-12 起）**
- 📌 **推送节奏（用户 2026-09-12 明确要求）：不要频繁推，攒到里程碑完成再推**
  - 下一个推送节点：**「数据管理」（`feat/data-management`）合并后**（M2 已于 2026-09-17 推送）
  - 平时照常本地提交（每个任务一个提交，保留回滚点）
- ⚠️ **绝不要把密码/密钥写进任何会入库的文件**（连 SQL 注释里也不行）——
  2026-09-12 就是靠"改数据库密码"才补上了早期 `03-show-results.sql` 注释里的泄漏
- 项目目标与范围以设计文档为准；要改范围，先改文档再改代码
- 用户是小白：每步要解释「做什么/为什么」，命令给可直接复制粘贴的形式
