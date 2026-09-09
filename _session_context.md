# Calcite — 会话记忆

> **本文件会入库（git）**：禁止写入密码 / 密钥 / token。需要记这类东西就放 `_session_context.local.md`（已 gitignore）。
> 为可公开，本地路径里的用户名一律写成 `%USERPROFILE%`。

## 项目总结
个人项目 Calcite：以 SpringBoot3 + Cesium + PostGIS 为核心的三件套（前端 Vue3）。
用户是学生，对三者均不熟悉，边做边学。

**项目定位（2026-09-08 经完整需求梳理后确定）**：
- 目的：**求职作品集**，目标岗位 **GIS / 时空数据开发**，交付周期 12 周（目标 2026 春招/实习）
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
- **用户明确要求：暂时不推送到 GitHub，只本地提交保留回滚退路**（当前 `ahead 16`，origin/main = `1e342e6`）
- 提交历史：`1e342e6` 初始化仓库 + .gitignore；`20da417` 前后端骨架；`349fe65` 删除模板 Main.java；`86dcdab` 设计文档 v1.0；`5f044d8` 小白导读；`da8eda9` PostGIS 初体验脚本；`38e91df` Cesium 三维地球接入；`1811c05` 三表 + 示例轨迹；`72eeda5` 示例轨迹查看脚本；`2910130` psql 编码修复；`447867d`/`542c9a0` 控制台乱码兜底；`ba47315` M1 后端接口；`040833c` 第一阶段学习笔记 + md2docx 转换脚本；`c726fa3` 去除明文数据库密码；`8676744` M1 前端收尾（轨迹列表 + 轨迹线）
- ⚠️ **历史泄漏**：数据库密码仍存在于本地历史 `72eeda5`/`2910130`/`040833c` 中（从未推送）。若要公开仓库，需重写历史或先改数据库密码。
- 本仓库 local core.sshCommand：`C:/Windows/System32/OpenSSH/ssh.exe -F C:/ProgramData/_ssh_config -i %USERPROFILE%/.ssh/id_ed25519 -o IdentitiesOnly=yes`
  - 必须带 `-F`：`github.com` 映射到 `ssh.github.com:443`（22 端口被拒/被墙）
  - 必须带 `-i` + `IdentitiesOnly=yes`：`D:\opencode_key` 权限过开放，OpenSSH 拒加载（它与 id_ed25519 是同一把 key，指纹 SHA256:34O4458D...）
- 沙箱限制：git 的 SSH 网络操作（push / ls-remote）在沙箱内必崩（`sh.exe: couldn't create signal pipe, Win32 error 5`），需提权 danger-full-access

## 工作流
- 技术栈：SpringBoot3 + Vue3 + Cesium + PostgreSQL/PostGIS
- 数据库连接：`psql -U postgres -h localhost -p 5432 -d calcite`，密码见 `application-local.yml`
- 敏感文件策略：`application-local.yml`、`_session_context.local.md`、`.env`、`*.key/*.pem/*.jks`、`logs/` 等已在 `.gitignore` 排除；
  `_session_context.md` 已脱敏（只留密码指针），因此**可以正常入库、享有版本历史**
- 每次改动后本地提交留回滚点（不推送）
- 项目目标与范围以设计文档为准；要改范围，先改文档再改代码
- 用户是小白：每步要解释「做什么/为什么」，命令给可直接复制粘贴的形式
