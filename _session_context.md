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
  - 处置：**2026-09-12 已把数据库密码从 `557096138Cc` 换成强密码**
    （改法：`ALTER USER postgres WITH PASSWORD '...'` + 同步 `application-local.yml`）
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
- **GeoLife 已下载**：`D:\Calcite-note\GPX-Data\Geolife Trajectories 1.3\`（182 用户 / **18,670 个 `.plt`** / 1.59 GB）
- **已导入**：用户 `000` 的 21 条（`POST /api/import/geolife` 用 `maxTracks` 控制量，幂等所以可反复跑）
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

### ▶ 下次接着做（2026-09-14 收工时的状态）
- **M2 第一阶段（停留点）已完成**，学习笔记已产出并看过（用户反馈"效果好"）
- **下一步 = M2 第二阶段「热点区域」**：把**所有轨迹**的停留点汇总起来做空间聚类，
  回答"哪些地方经常有人停留"。它建立在第一阶段的 `StayPointService` 之上
- **第三阶段是「轨迹相似度」**（判断两条轨迹是不是走的同一条路）
- 开工前建议先做的一件事：**确认要不要先把停留点入库 `stay_point` 表** ——
  热点要跨轨迹查所有停留点，一条条现算会变慢，这个决策最好在动手前定
- 本地未推送的提交：`ce7a902`(文档同步) → `3abaa97`(学习笔记) → `15334f6`(面板改版)
  + 之后再补的提交；按推送节奏，**攒到 M2 整体完成再推**
- 收工时服务状态：后端 8080 **已关闭**，前端 5173 Vite 仍在运行（重启后端用
  计划里那条 `spring-boot:run` 命令即可）

## 工作流
- 技术栈：SpringBoot3 + Vue3 + Cesium + PostgreSQL/PostGIS
- 数据库连接：`psql -U postgres -h localhost -p 5432 -d calcite`，密码见 `application-local.yml`
- 敏感文件策略：`application-local.yml`、`_session_context.local.md`、`.env`、`*.key/*.pem/*.jks`、`logs/` 等已在 `.gitignore` 排除；
  `_session_context.md` 已脱敏（只留密码指针），因此**可以正常入库、享有版本历史**
- 每次改动后本地提交留回滚点；**仓库已公开（2026-09-12 起）**
- 📌 **推送节奏（用户 2026-09-12 明确要求）：不要频繁推，攒到里程碑完成再推**
  - 下一个推送节点：**M2 完成**
  - 平时照常本地提交（每个任务一个提交，保留回滚点）
- ⚠️ **绝不要把密码/密钥写进任何会入库的文件**（连 SQL 注释里也不行）——
  2026-09-12 就是靠"改数据库密码"才补上了早期 `03-show-results.sql` 注释里的泄漏
- 项目目标与范围以设计文档为准；要改范围，先改文档再改代码
- 用户是小白：每步要解释「做什么/为什么」，命令给可直接复制粘贴的形式
