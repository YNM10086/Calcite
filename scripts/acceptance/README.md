# Calcite 验收脚本目录（`scripts/acceptance/`）

**这些脚本是「可重复运行的验收」**：任何人 clone 下来、按 `docs/DEPLOY.md` 起好服务，就能重跑一遍，
拿到的数字应当与下面的「预期数字」一致。它们原先是 `.tmp/` 里的临时文件
（`.tmp/` 被 `.gitignore` 忽略，这 22 个是历史上用 `git add -f` 强行入库的），
2026-09-25 的 M4 收尾把它们搬到这里 —— `.tmp/` 是运行时产物目录，不该是陌生人找脚本的地方。

## 1. 统一约定：**从仓库根目录运行**

所有脚本都按「**当前工作目录 = 仓库根**」解析相对路径（读写 `.tmp/...`、`docs/...`、`scripts/...`）。
请在仓库根执行，不要 `cd scripts/acceptance` 再跑 —— 从别处跑会因为找不到 `.tmp/` 或 `frontend/` 而报错。

```powershell
# 例：接口对拍（需后端 8080 已启动）
$env:PYTHONIOENCODING='utf-8'; $env:LC_MESSAGES='C'
& "E:\python\python_address\python.exe" scripts\acceptance\verify-within-api.py

# 例：浏览器验收（需后端 8080 + 前端 5173 已启动，且**提权** danger-full-access）
& "E:\python\python_address\python.exe" scripts\acceptance\check-within.py

# 例：组件级桩测试（不需要任何服务在跑）
node scripts/acceptance/check-runtime-task9.mjs
```

脚本里的**运行时产物（截图、DOM 转储、临时编译产物）一律仍写在 `.tmp/`** —— `.tmp/` 已 gitignore，
不进版本库。唯一的例外是 `check-runtime-task9.mjs`：它临时编译出的 JS 必须落在**本目录**，
跑完自动删除（原因见文件内注释）。

⚠️ **所有 Playwright 脚本在 DSH 沙箱内必须提权 `danger-full-access`**：浏览器子进程靠命名管道通信，
沙箱禁用命名管道。跑浏览器验收前请确认 **后端 8080 + 前端 5173 都已启动**。

## 2. 脚本清单（22 个，从 `.tmp/` 搬来）

| 脚本 | 类型 | 依赖 | 预期数字 | 原路径 |
|---|---|---|---|---|
| `check-stay-points.py` | 浏览器验收 | 前端 5173 + 提权 | **7** | `.tmp/check-stay-points.py` |
| `check-chart-pixels.py` | 浏览器验收 | 前端 5173 + 提权 | **10** | `.tmp/check-chart-pixels.py` |
| `check-import-pixels.py` | 浏览器验收 | 前端 5173 + 提权 | **6** | `.tmp/check-import-pixels.py` |
| `check-filter.py` | 浏览器验收 | 后端 8080 + 前端 5173 + 提权 | **7** | `.tmp/check-filter.py` |
| `check-hotspots.py` | 浏览器验收 | 后端 8080 + 前端 5173 + 提权 | **17** | `.tmp/check-hotspots.py` |
| `check-density.py` | 浏览器验收 | 后端 8080 + 前端 5173 + 提权 | **15** | `.tmp/check-density.py` |
| `check-similarity.py` | 浏览器验收 | 后端 8080 + 前端 5173 + 提权 | **17** | `.tmp/check-similarity.py` |
| `check-within.py` | 浏览器验收 | 后端 8080 + 前端 5173 + 提权 | **44** | `.tmp/check-within.py` |
| `check-data-edit.py` | 浏览器验收 | 后端 8080 + 前端 5173 + 提权 | ⚠️ 未列入固定基线（历史实测 19） | `.tmp/check-data-edit.py` |
| `verify-within-api.py` | 接口对拍 | 后端 8080 + `psql` | **105** | `.tmp/verify-within-api.py` |
| `verify-hotspot-api.py` | 接口对拍 | 后端 8080 | **375** | `.tmp/verify-hotspot-api.py` |
| `verify-density-api.py` | 接口对拍 | 后端 8080 + `psql` | **51** | `.tmp/verify-density-api.py` |
| `verify-similarity-api.py` | 接口对拍 | 后端 8080 + `psql` | **45** | `.tmp/verify-similarity-api.py` |
| `verify-data-edit-api.py` | 接口对拍 | 后端 8080 + **提权** ⚠️ **会真删掉一条轨迹** | ⚠️ 未列入固定基线（按现场实测） | `.tmp/verify-data-edit-api.py` |
| `check-runtime-task9.mjs` | 组件级桩 | `frontend/node_modules`（Vue compiler-sfc）；无需任何服务 | **67** | `.tmp/check-runtime-task9.mjs` |
| `cesium-stub.mjs` | 组件级桩（替身） | 被 `check-runtime-task9.mjs` import；不单独运行 | — | `.tmp/cesium-stub.mjs` |
| `vue-stub.mjs` | 组件级桩（替身） | 被 `check-runtime-task9.mjs` import；不单独运行 | — | `.tmp/vue-stub.mjs` |
| `shot-hotspot-ui.py` | 截图工具 | 前端 5173 + 提权 | —（产出 `.tmp/hotspot-ui.png` + `.tmp/hotspot-ui-rects.json`） | `.tmp/shot-hotspot-ui.py` |
| `shot-similarity.py` | 截图工具 | 前端 5173 + 提权 | —（产出 `.tmp/sim-*.png`） | `.tmp/shot-similarity.py` |
| `shot-within-report.py` | 截图工具 | 前端 5173 + 提权 | —（产出 `docs/learning/figs/fig-within-shot-*.png`） | `.tmp/shot-within-report.py` |
| `probe-polygon-triangle.py` | 缺陷探针 | 前端 5173 + 提权 | 判据 = `POST /api/analysis/within` 的请求体：点 4 个顶点应当**一个请求都不发**；闭合后外环 7 个坐标 / 去重 4 个顶点（修复前是第 4 次点击就发请求、外环 4 坐标 = 3 顶点） | `.tmp/probe-polygon-triangle.py` |
| `pw-playback.py` | 浏览器验收（回放） | 前端 5173 + 提权 | —（回放证据脚本：时刻推进 07:30:00→07:33:20→07:36:43、白色移动点位移 50.5 px） | `.tmp/pw-playback.py` |

> 「预期数字」= 该脚本自报的断言项数（`N 通过 / M 失败`，或输出的 `RESULT` 行）。浏览器 8 个
> 合计 **123 项**、接口对拍 5 个合计 **576 项**、组件级桩 **67 项**。
> ⚠️ `check-runtime-task9.mjs` 的 67 项**不计入** `_session_context.md` 里的回归基线总数，
> 但每次改动 `CesiumGlobe.vue` 都要跑。

⚠️ **`check-data-edit.py` / `verify-data-edit-api.py` 是唯一会真正改动数据的两个脚本**：
它们要读写回收站目录（`calcite.data.recycle-dir`），**必须提权**；`verify-data-edit-api.py`
**会真的删掉一条轨迹**（删前导出回收站）。跑之前先确认数据状态、跑完按脚本提示从源 `.plt` 重新导入
（**轨迹 id 会变**）。基线数据状态：**246 条轨迹 / 286,019 个点**。

### 三类脚本的关系

| 家族 | 回答什么问题 | 要不要起浏览器 | 判据从哪来 |
|---|---|---|---|
| `check-*.py` | **界面上看得见的对不对** —— 像素、DOM、交互 | 要（Playwright + 真实时间，**不要用虚拟时钟截图**） | 页面实测（颜色像素数、包围盒、面板零溢出…） |
| `verify-*-api.py` | **接口返回的对不对** —— 与 SQL 独立算一遍对拍 | 不要，纯 HTTP + `psql` | 直接用 `psql` 跑一遍等价 SQL，两边数字必须相等 |
| `*-stub.mjs` | **组件逻辑的对不对** —— 不启动 Vite，用替身真跑 `setup()` | 不要 | Vue `compiler-sfc` 编译 + `vue`/`cesium` 替身 |

三者互补，缺一层就会漏缺陷：M3 那个「多边形只能画成三角形」的缺陷就是**四层验收全绿**却漏掉的
（浏览器判据只问「有没有结果」、桩测试自己造字面量事件对象比运行时更宽容），
后来补了 `probe-polygon-triangle.py` 与 `cesium-stub.mjs` 的 `clickAt/moveTo/...`。

### 本目录另有两个新脚本（不属于本次迁移）

`verify-demo-data.py`（Task 4 演示数据断言）、`check-doc-links.py`（Task 1 文档链接检查）——
它们是 M4 收尾**新写**的，不在上面 22 个「从 `.tmp/` 搬来」之列。

## 3. 历史文档里的旧路径 `scripts/acceptance/` ←→ `.tmp/xxx`

`docs/superpowers/` 里的 spec / 计划 / 进度记录写的是**当时的**路径 `.tmp/xxx`。
**历史文档一律不改写**（它们是那时的真实记录）—— 靠上面第 2 节的表格对应：

| 历史文档里写的 | 现在的实际位置 |
|---|---|
| `.tmp/check-*.py` | `scripts/acceptance/check-*.py` |
| `.tmp/verify-*-api.py` | `scripts/acceptance/verify-*-api.py` |
| `.tmp/check-runtime-task9.mjs`、`.tmp/cesium-stub.mjs`、`.tmp/vue-stub.mjs` | `scripts/acceptance/` 同名文件 |
| `.tmp/shot-*.py`、`.tmp/probe-polygon-triangle.py`、`.tmp/pw-playback.py` | `scripts/acceptance/` 同名文件 |
| `.tmp/render-density-scales.py` | `docs/learning/figs/render-density-scales.py`（与 `make_*_figs.py` 同处） |

**另外 19 个一次性脚本已取消入库**（`git rm --cached`，**本地文件仍在** `.tmp/`）：
15 个 `fix-*.py`、`analyze-density.py`、`analyze-playback.py`、`where-is-my-data.py`、`_red-verify-task6.py`。
历史文档提到它们时仍指向 `.tmp/`，那是准确的 —— 它们本来就不该出现在版本库里。

**现行引用**（`_session_context.md`、`docs/superpowers/M3-START-HERE.md`、根 `README.md`）
已经改成 `scripts/acceptance/...`；`git log --follow scripts/acceptance/<脚本>` 可以追到搬家前的历史。

## 4. 跑之前必须知道的三件事（2026-09-27 实测补充）

**① `PGPASSWORD` —— 三个脚本用它直接取真值，缺了会立刻退出（不会卡住）**

`verify-within-api.py`、`verify-density-api.py`、`verify-similarity-api.py` 会用 `psql` 跑等价 SQL 当判据：

```powershell
$y = Get-Content backend\src\main\resources\application-local.yml -Raw
if ($y -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
```

⚠️ 这三个脚本的 `psql` 调用**一律带 `-w`**（绝不提示密码）。这条是踩出来的：没有 `-w` 时，
`verify-similarity-api.py` 会**静默停在密码提示上等输入**，看起来就是"脚本卡死"
（2026-09-27 实测卡了 30 分钟，`Get-Process python` 显示 CPU 只有 0.2s 才定位到）。

**② 破坏性脚本：会真的删掉一条轨迹**

`verify-data-edit-api.py` 与 `check-data-edit.py` 按设计**真删真加**（删前先导出到回收站），
跑完要按脚本末尾的提示从 `.plt` 重新导入（**id 会变**）。两者都需要提权，且**不要**在交付/快照前顺手跑。

**③ 浏览器脚本需要两个服务同时在跑**

8 个 `check-*.py` 需要**后端 8080 + 前端 5173**，且必须用**真实时间等待**
（Cesium 几何体在 Web Worker 里异步生成，虚拟时钟截图会截到空白，见结构地图的「已知的坑」）。

## 5. 验收演示数据集时别污染主库（推荐做法）

`calcite` 主库里有 246 条真实轨迹，直接灌演示数据会让相似度/热点断言被真实数据干扰。
建议建一个**只装演示数据**的库，再起第二个后端实例指向它：

```powershell
$psql = 'E:\PostgreSQL\bin\psql.exe'
& $psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS calcite_demo;" -c "CREATE DATABASE calcite_demo;"
& $psql -U postgres -d calcite_demo -f scripts/db/01-schema.sql
& $psql -U postgres -d calcite_demo -f scripts/db/04-demo-data.sql

# 起第二个后端（环境变量最省事：绕开 maven 参数的引号问题）
$env:SERVER_PORT = '8081'
$env:SPRING_DATASOURCE_URL = 'jdbc:postgresql://localhost:5432/calcite_demo'
mvn -f backend/pom.xml spring-boot:run

& "E:\python\python_address\python.exe" scripts\acceptance\verify-demo-data.py http://127.0.0.1:8081
```

实测（2026-09-27）：**13 项通过 / 0 失败**（停留点 ≥1、环湖跑步诚实为 0、热点 4 个且最热 3 条轨迹、
密度最密格 5 条、相似度第一名是"通勤回程"、圈选命中且区域内点数 > 0）。
