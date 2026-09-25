# M3 起点 · 从这里开始

> **这份文件的用途**：开新会话做 M3 时，**只需要把这个路径喂进去**，新会话就够用了。
> 它把「M3 要做什么 / 现在什么状态 / 有哪些已知欠账 / 项目怎么干活」集中在一处，
> 并指向所有更深层的文档。
>
> 日期：2026-09-21 · 仓库 HEAD：`980f17d`（= `origin/main`）

---

## 0. 怎么开始

在新会话里说：

```
开始 M3
```

新会话会**自动读 `_session_context.md`**（项目记忆），然后按前几个阶段的流程走：

```
brainstorming（问问题、出设计）
    → 写设计文档到 docs/superpowers/specs/
    → 你审阅
    → writing-plans 出实施计划（docs/superpowers/plans/）
    → 你审阅
    → Subagent-Driven 逐任务执行（每任务一个新子代理 + 关键处人工审查）
    → 全量回归 + 文档同步
    → 合并回 main
```

**推送节奏（用户定的）**：**攒到一块做完再推**。M3 全部完成后再 `git push`。

---

## 1. M3 要做什么（设计文档原文）

**唯一权威**：`docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`

| 位置 | 内容 |
|---|---|
| **第 353 行** | `**M3（第 8-11 周）**` —— M3 的总目标 |
| **第 412 行** | 「路网匹配（Map Matching）\| 技术难度过高，**M3 之后再评估**」 |
| **第 453 行** | 「M3 \| **空间查询优化（`EXPLAIN ANALYZE`）**、轨迹相似度算法（DTW / Fréchet）」 |
| **第 493 行** | 「路网匹配可行性 \| ⏳ 仍待评估（M3 之后再评估）」 |
| **第 356 行附近** | 接口表：`POST /api/analysis/within` —— 传多边形 / 缓冲区，返回**穿过的轨迹** |
| **场景表（第 24-31 行）** | **场景 5**：「有没有经过某条河以东的区域？」→ 空间范围查询 |

### 归纳出来的 M3 范围

1. **空间范围查询** `POST /api/analysis/within`
   - 画矩形 / 多边形 / 缓冲区 → 查出穿过它的轨迹
   - 对应场景 5
2. **空间查询优化**（`EXPLAIN ANALYZE`）
   - ⚠️ **这条和 M2 留下的一笔欠账直接相关** —— 见下面第 3 节第 ① 条
3. **路网匹配评估**（不是"实现"，是"**评估**"）
   - 原计划就是"M3 之后再评估"，做 M3 时要**给出结论**：做不做、为什么

> ⚠️ **注意一处历史冲突**：第 453 行把「轨迹相似度算法（DTW / Fréchet）」列在 M3，
> 但**轨迹相似度已经在 M2 第四阶段做完了**，而且实测证明 **Frechet 不可用**
> （见 `docs/superpowers/specs/2026-09-17-m2-similarity-design.md` 第 2.2 节）。
> **M3 不要再做一遍**，brainstorming 时要和用户确认这条已经划掉。

---

## 2. 现在什么状态（开工前的事实）

```
仓库：main = origin/main = 980f17d，工作区干净，待推送 0
数据：246 条轨迹 / 286,019 个点 / 264 个停留点 / 37 个热点
后端：JUnit 133 项全绿（不需要数据库）
前端：node 6 个套件 134 项全绿
浏览器/接口：11 个脚本全绿
服务：全关（8080 / 5173 / 52342）—— 开工前要自己起
```

**M1 已完成**：回放 / 速度海拔曲线 / 轨迹导入
**M2 已完成**（四个阶段）：停留点识别 → 停留热点 → 网格密度 → 轨迹相似度
**数据管理已完成**：添加 / 替换 / 改名 / 删除（并兑现了 M2 的两处缓存欠账）

前端现在有 **四档**：`[停留点 | 热点 | 密度 | 相似]`，外加一个「数据编辑」入口。

---

## 3. 和 M3 直接相关的已知欠账

### ① ⭐ **空间索引当前没有被使用** —— 这条最该在 M3 处理

M2 第三阶段（网格密度）实测发现：`track_point` 上**确实有** `GIST(geom, recorded_at)` 索引，
但**优化器选择了顺序扫描**（`EXPLAIN` 显示 `geom && ...` 落在 `Filter` 而不是 `Index Cond`）。

当时的判断是"286k 行时全表扫描更划算，等数据更大再评估"。
**M3 的「空间查询优化（EXPLAIN ANALYZE）」正是来评估这件事的。**

出处：`docs/superpowers/specs/2026-09-17-m2-density-design.md` 第 4.3 节 + 第 8 节「已知限制」。

### ② 热点接口热态 3.2 秒

它每次请求都要读 **28.6 万个点**，这部分**不受缓存影响**。
M2 就记在账上：要么改成标量投影、要么按触发条件把停留点入库 `stay_point`（表现在是空的）。

出处：`_session_context.md` 的「已知欠账」。

### ③ 相似度的单向百分比是近似值

后端用"点对点"而不是"点到折线"（为了走索引，快 19 倍）。
**相似度本身可靠**（取小），但单向百分比对稀疏轨迹会低估。
如果 M3 要做空间查询优化，这条可以顺带重新评估。

### ④ 删除失败的 500 不带原因

Spring 的 `server.error.include-message` 默认 `never`，异常 message 被吞掉。
小债，顺手可修。

---

## 4. 项目怎么干活（约定与踩坑）

### 工作流（前几个阶段一直是这么走的）

| 阶段 | 产出 |
|---|---|
| brainstorming | `docs/superpowers/specs/YYYY-MM-DD-<主题>-design.md` |
| 计划 | `docs/superpowers/plans/YYYY-MM-DD-<主题>.md` |
| 执行 | **Subagent-Driven**（每任务派新子代理，关键处主控亲自盯） |
| 学习笔记 | `docs/learning/`（**map 型**：结构 / 流程 / "以后往哪加"，不是知识罗列） |
| Word 报告 | `python scripts/tools/md2docx.py <md> <docx>`，输出到 `D:\Calcite-note\` |

### ⚠️ 沙箱限制（会反复踩）

| 操作 | 问题 | 怎么办 |
|---|---|---|
| Vite dev / build | `spawn EPERM` | **提权 `danger-full-access`**；子代理提不了权，由主控代跑 |
| Playwright（浏览器验收） | 命名管道被禁，Chrome 起不来 | 同上 |
| 写 `D:\Calcite-note\` | `WinError 5 拒绝访问` | 同上 |
| `git push` | SSH 崩 | 同上 |
| Maven | `-Dmaven.repo.local=...` 参数形式**是有效的**（实测） | 但个别子代理的调用方式会让它失效，那就用 `$env:MAVEN_OPTS` |

### 常用命令

```powershell
# 后端编译 + 全部单测（不需要数据库）
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" test

# 起后端（后台）
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "...\backend\pom.xml" spring-boot:run

# 起前端（要提权）
cd frontend; npm run dev

# 查数据库（密码从 gitignore 的配置取，不要打印）
$yaml = Get-Content "backend/src/main/resources/application-local.yml" -Raw
if ($yaml -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
$env:LC_MESSAGES='C'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -c "SELECT count(*) FROM track;"

# 找 8080 的 PID（Get-NetTCPConnection 在这个环境里不可靠）
netstat -ano | Select-String ":8080\s" | Select-String "LISTENING"
```

### 六条踩坑记录（都在 `_session_context.md` 的「踩坑记录」里）

1. `maxTracks` 是"**最多处理几个文件**"，不是"最多补几条"（曾经把 399 个无关文件导进来）
2. **跑验收前必须确认后端是当前源码**（判别：JVM 启动时间 vs class 编译时间）
3. 沙箱写不进 `D:\Calcite-note\`（WinError 5，环境限制不是代码问题）
4. `@Value` **绑不了 YAML 列表** —— 必须 `@ConfigurationProperties`
5. **`.tmp/` 被 gitignore**，加文件必须 `git add -f`
6. **验收判据不要写死数据量** —— 从接口取期望值（否则导一次数据就废一片）

### 退路（做"会让数据变少"的操作之前确认）

| 层 | 位置 |
|---|---|
| 代码 | GitHub（已推送，本地 = 远端） |
| 原始数据文件 | `D:\Calcite-note\GPX-Data`（18,745 个文件 / 1.6 GB，**功能不碰它**） |
| 数据库快照 | `D:\Calcite-note\backups\calcite-20260921-2007.dump`（21.1 MB，已验证可读） |
| 删除的回收站 | `D:\Calcite-note\backups\deleted\`（删除前自动导出 GeoJSON） |

---

## 5. 要读的文件（按优先级）

**必读（3 份）**

1. `_session_context.md` —— **项目记忆**，新会话会自动读；里面有全部结论、欠账、踩坑
2. `docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md` —— **总设计方针**（M3 的范围在这里）
3. 本文件

**M3 brainstorming 时值得参考（挑着看）**

| 主题 | 文件 |
|---|---|
| 空间索引为什么没被用上 | `docs/superpowers/specs/2026-09-17-m2-density-design.md` 第 4.3 / 第 8 节 |
| 相似度为什么不用 Frechet | `docs/superpowers/specs/2026-09-17-m2-similarity-design.md` 第 2.2 节 |
| 数据库表结构与 PostGIS 用法 | `scripts/db/01-schema.sql` |
| 学习笔记的文风（map 型） | `docs/learning/2026-09-17-M2-全景笔记.md` |
| 最新一份改动报告 | `docs/learning/2026-09-21-数据管理改动报告.md` |

---

## 6. 一句话

> **M3 = 空间范围查询（`POST /api/analysis/within`）+ 空间查询优化（`EXPLAIN ANALYZE`）+ 路网匹配评估。**
>
> 起点干净、退路齐全、记忆完整。**从 brainstorming 开始，别直接写代码。**
