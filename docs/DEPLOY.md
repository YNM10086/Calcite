# Calcite 部署指南

> **本文状态**：第 **1~10 节已全部写完**（适用范围 / 前置条件 / 数据库 / 后端配置 / 启动后端 /
> 启动前端 / 演示数据 / 常见报错表 / 停止与清理 / 跑验收）。
>
> **实测进度（2026-09-27，Windows 11 + PostgreSQL 18.3 + PostGIS 3.6 + JDK 25 + Node 24）**：
> 已在**空库 `calcite_demo`** 上真实走通 ——
> **§3 数据库（建库 → 初始化 → 验证）、§3.4 找 psql、§5.1 `GET /api/health`、§6.2 起 Vite、
> §7.1 演示数据导入、§10 的测试与构建数字**。这些位置的实测输出集中在文末
> **「附录 · 实测记录（2026-09-27）」**，正文里对应的「（待实测）」以附录为准。
>
> **仍未实测**（正文里继续标「（待实测）」，这就是本文的诚实边界）：GeoLife 官方下载链接可达性、
> macOS / Linux 分支命令、`npm install` 的输出、§9.2 清理演示数据、§9.3 `DROP DATABASE …
> WITH (FORCE)` 与 `pg_dump`。
>
> **硬规则（不变）**：凡是本文里**没有真正执行过**的命令，输出一律写成「预期输出（待实测）」，
> 不许当成实测结果。已实测的标「✅ 实测」并注明机器与日期。

---

## 1. 适用范围

**这份文档只覆盖：一台机器上的开发环境，从零把数据库和后端配起来。**

| 项目 | 本文覆盖 | 本文不覆盖 |
| --- | --- | --- |
| 部署形态 | 单机、单实例、本机回环（`localhost`） | 生产集群、多节点、容器编排（Docker/K8s）、云主机 |
| 数据库 | 本机 PostgreSQL 18 + PostGIS 3.6，一个库 `calcite` | 主从复制、连接池扩容、定期备份策略、迁移工具 |
| 网络 | `localhost:5432` / `8080` / `5173`，无鉴权 | 公网暴露、HTTPS/TLS、反向代理（Nginx）、防火墙规则 |
| 账号 | 数据库超级用户 `postgres`，应用直接用它连 | 应用专用低权限数据库账号、用户体系、登录鉴权 |
| 前端 | Vite 开发服务器（`npm run dev`） | 生产构建产物托管、CDN、静态站点部署 |
| 操作系统 | 命令以 **Windows PowerShell** 为主，bash 写法并排给出 | Windows 服务化（注册成系统服务）、开机自启 |

**换句话说**：本文的目标是「让一个第一次拿到这个仓库的人，在自己的电脑上把后端跑起来、能连上库」。
里面所有路径、盘符、服务名都来自**作者这台机器的实际安装**，你必须按自己的机器改（第 4 节会逐条指出哪些必须改）。

**操作系统说明**：项目本身是跨平台的（Spring Boot + Vue），但本项目的实测环境是 **Windows**，
所以 macOS / Linux 上的命令只给写法、**未实测**。

---

## 2. 前置条件与版本核对

先把这些装好，再动数据库。版本要求的**出处**是 `backend/pom.xml`、`frontend/package.json` 和 README 的技术栈表——不是拍脑袋定的。

| 组件 | 要求 | 依据 | 核对命令（PowerShell） |
| --- | --- | --- | --- |
| JDK | **25** | `backend/pom.xml` 的 `<java.version>25</java.version>` | `java -version` |
| Maven | **3.9+** | README「前置条件」（实测用的是 3.9.11） | `mvn -v` |
| Node.js | **20+** | README「前置条件」 | `node -v` |
| npm | 随 Node 一起装 | — | `npm -v` |
| PostgreSQL | **18** | README「前置条件」 | `& "E:\PostgreSQL\bin\psql.exe" --version`（路径按你机器改，见 3.4） |
| PostGIS | **3.6** | README「前置条件」 | `SELECT PostGIS_Version();`（**要连库**，放到第 3.3 步再跑） |

### 2.1 JDK 25

```powershell
# PowerShell
java -version
```

```bash
# bash
java -version
```

✅ **实测输出**（2026-09-27，本机）：

```
java version "25.0.2" 2026-01-20 LTS
Java(TM) SE Runtime Environment (build 25.0.2+10-LTS-69)
Java HotSpot(TM) 64-Bit Server VM (build 25.0.2+10-LTS-69, mixed mode, sharing)
```

**判读**：第一行的主版本号必须是 **25**。

- 报 `'java' 不是内部或外部命令` / `CommandNotFoundException` → JDK 没装，或没进 `PATH`。
- 版本是 17 / 21 → 后面 `mvn compile` 会报 `invalid target release: 25`，
  或运行期报 `UnsupportedClassVersionError`。装 JDK 25 并确认 `PATH` 里指向的是它
  （`Get-Command java` 看解析到了哪个路径）。
- 只有 JRE 没有 JDK 也不行——编译要 `javac`。

### 2.2 Maven 3.9+

```powershell
# PowerShell
mvn -v
```

```bash
# bash
mvn -version
```

预期输出（**待实测**）：

```
Apache Maven 3.9.x
Maven home: ...
Java version: 25.0.2, vendor: ...
```

**判读**：第一行是 `Apache Maven 3.9.x`（或更高）即通过。

⚠️ **本机实测的一个情况**：在作者这台机器的普通终端里，`mvn -v` 会报
**`CommandNotFoundException: 无法将"mvn"识别为 cmdlet、函数、脚本文件或可运行程序的名称`**——
也就是 **Maven 没有进 `PATH`**。这不算版本不达标，是没装/没配环境变量。三种处理办法：

1. 装 Maven 3.9+ 并把 `bin` 目录加进 `PATH`（推荐，一劳永逸）；
2. 用 IDE 自带的 Maven（IntelliJ IDEA 自带的在
   `<IDEA 安装目录>\plugins\maven\lib\maven3\bin\mvn.cmd`）；
3. **本仓库没有 Maven Wrapper**（根目录下没有 `mvnw` / `mvnw.cmd`），所以不能靠 `./mvnw` 兜底。

> 项目没有自定义插件仓库，`mvn` 第一次跑会下载依赖，需要联网。

### 2.3 Node.js 20+

```powershell
# PowerShell
node -v
npm -v
```

```bash
# bash
node -v
npm -v
```

✅ **实测输出**（2026-09-27，本机）：

```
v24.14.0
11.9.0
```

**判读**：`node -v` 输出 `v20.x` 或更高（本机 `v24.14.0` ✓），`npm -v` 能正常返回即可。
报 `'node' 不是内部或外部命令` 就是没装或没进 `PATH`。

> 只有第 4 节结束之后才需要用到 Node（启动前端），这里先核对版本，避免后面返工。

### 2.4 PostgreSQL 18 + PostGIS 3.6

分两步：**先看服务在不在、psql 是哪个版本**（不连库），**PostGIS 版本留到 3.3 连上库再查**。

```powershell
# PowerShell：看 PostgreSQL 服务是否安装并运行
Get-Service postgresql*
```

```powershell
# PowerShell：看 psql 版本（路径按你机器改，本机见 3.4）
& "E:\PostgreSQL\bin\psql.exe" --version
```

```bash
# bash（macOS/Linux）
psql --version
systemctl status postgresql    # 或 brew services list
```

✅ **实测输出**（2026-09-27，本机）：

```
psql (PostgreSQL) 18.3
```

**判读**：主版本号必须是 **18**。PostGIS 是**按库启用的扩展**，不在 `psql --version` 里体现，
必须连上库才能确认——放到 3.3 验证步骤里查 `SELECT PostGIS_Version();`。

> ⚠️ 装 PostgreSQL 时**必须勾选 PostGIS 组件**（Windows 安装包有独立的 PostGIS 选项，
> 或单独装 PostGIS 的 bundle）。没装 PostGIS 就算 PostgreSQL 18 也过不了 3.3 验证，
> 后端启动时会报 `type "geometry" does not exist`。

---

## 3. 数据库

顺序：**建库 → 初始化 → 验证**。三步全部在**仓库根目录**执行（脚本路径是相对的）。

本机的实际安装（**换机器务必替换**）：

| 项 | 本机值（✅ 实测） |
| --- | --- |
| 安装目录 | `E:\PostgreSQL` |
| psql 完整路径 | `E:\PostgreSQL\bin\psql.exe` |
| 服务名 | `postgresql-x64-18` |
| 数据目录 | `E:\PostgreSQL\data` |
| 端口 | `5432` |
| 超级用户 | `postgres` |

下面的 PowerShell 示例直接用完整路径 `& "E:\PostgreSQL\bin\psql.exe"`，**因为它在作者机器上不在 PATH 里（✅ 实测）**。
如果你的 `psql` 已在 PATH，把它换成 `psql` 即可；不在 PATH 怎么办见 **3.4**。

### 3.1 建库

```powershell
# PowerShell —— 在仓库根目录执行
$env:PGPASSWORD = '<你的 postgres 密码>'     # 只在当前窗口有效，关掉即失效
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d postgres -c "CREATE DATABASE calcite ENCODING 'UTF8';"
```

```bash
# bash
export PGPASSWORD='<你的 postgres 密码>'
psql -U postgres -h localhost -p 5432 -d postgres -c "CREATE DATABASE calcite ENCODING 'UTF8';"
```

预期输出（**待实测**）：

```
CREATE DATABASE
```

**说明**：

- 连的是系统自带的 `postgres` 库，**在里面建新库** `calcite`；后端连接串
  `jdbc:postgresql://localhost:5432/calcite`（`backend/src/main/resources/application.yml:11`）就是这个库。
- `ENCODING 'UTF8'` 是显式声明，避免继承到别的默认编码。
- **已经建过就跳过这一步**。重复执行会报 `ERROR: database "calcite" already exists`，
  这是正常的，不是故障。
- 也可以用 `createdb -U postgres calcite`，效果一样。

### 3.2 初始化（建表 + 建扩展）

```powershell
# PowerShell —— 必须在仓库根目录执行（脚本是相对路径）
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -f scripts/db/01-schema.sql
```

```bash
# bash
psql -U postgres -h localhost -p 5432 -d calcite -f scripts/db/01-schema.sql
```

预期输出（**待实测**；首行 `\encoding UTF8` 本身不产生输出）：

```
CREATE EXTENSION
CREATE EXTENSION
########## 建表：track（一条轨迹 = 一次出行）##########
CREATE TABLE
########## 建表：track_point（一个 GPS 点 = 原始真相）##########
CREATE TABLE
########## 建表：stay_point（一次停留，M2 由算法生成）##########
CREATE TABLE
########## 建索引（性能关键）##########
CREATE INDEX
... （共 5 个 CREATE INDEX）
########## 验收：三张表 + 全部索引 ##########
 table_name | ... （3 张表的列清单）
 tablename  | indexname       （5 个索引）
########## 补列（对已存在的老库生效）##########
ALTER TABLE
```

**这个脚本做了什么**（`scripts/db/01-schema.sql`，86 行）：

1. **首行 `\encoding UTF8`** —— 中文 Windows 的控制台默认是 GBK，直接读这个 UTF-8 脚本会报编码错。
   这一句让 psql 按 UTF-8 读，是本项目踩过的坑的修复。
2. **建两个扩展**：
   - `CREATE EXTENSION IF NOT EXISTS postgis;` → 提供 `geometry` 类型和全部 `ST_*` 函数；
   - `CREATE EXTENSION IF NOT EXISTS btree_gist;` → 让 GiST 索引能同时装「空间列 + 普通列」，
     也就是那个时空联合索引 `GIST (geom, recorded_at)`。
   **扩展是在目标库里启用的**，所以必须先连上 `calcite` 库再跑本脚本，别连到 `postgres` 库去跑。
3. **建三张表**：`track` / `track_point` / `stay_point`。
4. **建 5 个索引**（含时空联合索引）。
5. **末尾两段 `SELECT` 就是验收**——直接把表结构和索引列出来给你看。
6. **可重复执行**：全部是 `IF NOT EXISTS`，误跑第二次不会删数据。

⚠️ **中文 Windows 控制台可能乱码**（psql 自己的提示行按 GBK 输出、数据按 UTF-8）。
先执行下面两句再跑脚本，可以显著减少乱码（本项目的既有做法，未在本次会话复测）：

```powershell
chcp 65001
$env:LC_MESSAGES = 'C'
```

### 3.3 验证

初始化脚本末尾自带验收（看它打印的表清单和索引清单即可）。想再独立确认一次，进交互式 psql：

```powershell
# PowerShell
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite
```

```bash
# bash
psql -U postgres -h localhost -p 5432 -d calcite
```

然后在 `calcite=#` 提示符里执行：

```sql
-- 1) 列出当前库的表（应看到 track、track_point、stay_point 三张）
\dt

-- 2) 查 PostGIS 版本（应返回 3.6.x）
SELECT PostGIS_Version();

-- 3) 确认两个扩展真的启用了（应返回 2 行：btree_gist / postgis）
SELECT extname, extversion FROM pg_extension
 WHERE extname IN ('postgis', 'btree_gist') ORDER BY extname;

-- 4) 确认表能查（空库是 0，正常）
SELECT count(*) FROM track;

-- 退出
\q
```

也可以不进交互模式，一条条跑：

```powershell
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -c "\dt"
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -c "SELECT PostGIS_Version();"
```

```bash
psql -U postgres -h localhost -p 5432 -d calcite -c '\dt'
psql -U postgres -h localhost -p 5432 -d calcite -c 'SELECT PostGIS_Version();'
```

预期输出（**待实测**）：

```
              List of tables
 Schema |    Name     | Type  | Owner
--------+-------------+-------+-------
 public | stay_point  | table | postgres
 public | track       | table | postgres
 public | track_point | table | postgres
(3 rows)

 postgis_version
-----------------
 3.6 ...          ← 3.6 即通过；具体小版本以你装的为准
(1 row)
```

**判读**：

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| `\dt` 一张表都没有 | 3.2 没跑成功，或跑到了别的库 | 回到 3.2，确认 `-d calcite` 且 `-f` 路径正确 |
| `ERROR: type "geometry" does not exist` | 目标库没启用 PostGIS | 重跑 3.2（脚本含 `CREATE EXTENSION postgis`），或手动 `CREATE EXTENSION postgis;` |
| `PostGIS_Version()` 返回空/报函数不存在 | 扩展没启用 | 同上 |
| psql 提示 `FATAL: password authentication failed` | 密码不对 | 检查 `PGPASSWORD` 或 `pg_hba.conf` |

### 3.4 psql 不在 PATH 时怎么找

**症状**（本机 ✅ 实测就是这样）：

```powershell
PS> Get-Command psql
# 无输出 —— psql 不在 PATH 里

PS> psql --version
# 'psql' 不是内部或外部命令、可运行的程序或批处理文件。
# （PowerShell 报 CommandNotFoundException）
```

**这不代表 PostgreSQL 没装**，只是命令没进 `PATH`。按下面顺序找：

#### 办法 1：用 `sc.exe qc <服务名>` 看服务的可执行文件路径（推荐，最准）

Windows 上 PostgreSQL 一定是注册成服务的，服务的可执行文件就躺在 `bin` 目录里。

```powershell
# PowerShell —— 服务名按你装的版本改，本机是 postgresql-x64-18
sc.exe qc postgresql-x64-18
```

```bash
# bash（Windows 上的 Git Bash / WSL 同样可用）
sc qc postgresql-x64-18
```

✅ **实测输出**（2026-09-27，本机）：

```
[SC] QueryServiceConfig 成功

SERVICE_NAME: postgresql-x64-18
        TYPE               : 1  WIN32_OWN_PROCESS
        START_TYPE         : 2   AUTO_START
        ERROR_CONTROL      : 1   NORMAL
        BINARY_PATH_NAME   : "E:\PostgreSQL\bin\pg_ctl.exe" runservice -N "postgresql-x64-18" -D "E:\PostgreSQL\data" -w
        LOAD_ORDER_GROUP   :
        TAG                : 0
        DISPLAY_NAME       : postgresql-x64-18 - PostgreSQL Server 18
        DEPENDENCIES       : RPCSS
        SERVICE_START_NAME : NT AUTHORITY\NetworkService
```

**怎么读**：看 `BINARY_PATH_NAME` 那一行——
`"E:\PostgreSQL\bin\pg_ctl.exe"` ⇒ 安装目录是 `E:\PostgreSQL` ⇒ **psql 就在
`E:\PostgreSQL\bin\psql.exe`**。

✅ 实测该文件确实存在：`Test-Path "E:\PostgreSQL\bin\psql.exe"` → `True`，
`& "E:\PostgreSQL\bin\psql.exe" --version` → `psql (PostgreSQL) 18.3`。

> **不知道服务名？** 先列出来再挑：
> ```powershell
> Get-Service postgresql*
> # 或：sc.exe query state= type= service | findstr /i postgres
> ```
> ⚠️ 如果 `Get-Service postgresql*` 没结果，说明服务名不带 postgresql 前缀（自定义安装时常见），
> 用 `Get-CimInstance Win32_Service | Where-Object { $_.PathName -like '*postgres*' } | Select-Object Name, PathName` 兜底。

#### 办法 2：去默认安装目录找

Windows 官方安装包的默认位置：

```
C:\Program Files\PostgreSQL\<版本>\bin\psql.exe
# 例如：C:\Program Files\PostgreSQL\18\bin\psql.exe
```

```powershell
# PowerShell：一把梭找全盘的 psql.exe（慢，但一定能找到）
Get-ChildItem -Path C:\, D:\, E:\ -Filter psql.exe -Recurse -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty FullName
```

```bash
# bash（macOS/Linux）
which psql
find /usr /opt /home -name psql -type f 2>/dev/null
# macOS Homebrew 常见位置：/opt/homebrew/psql 或 /opt/homebrew/opt/postgresql@18/bin/psql
```

#### 找到之后怎么用

**方式 A：用完整路径（最省事，不用改环境）**——本文 3.1~3.3 的写法就是这个：

```powershell
& "E:\PostgreSQL\bin\psql.exe" --version
```

**方式 B：临时加入当前窗口的 PATH**（关窗口失效，零风险）：

```powershell
$env:Path += ';E:\PostgreSQL\bin'
psql --version        # 现在可以直接用了
```

```bash
export PATH="$PATH:/usr/pgsql-18/bin"
psql --version
```

**方式 C：永久加入 PATH**（一劳永逸）：

```powershell
# 当前用户永久生效（需要重开终端）
[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';E:\PostgreSQL\bin', 'User')
```

GUI 路径：`Win + R` → `sysdm.cpl` → 高级 → 环境变量 → 系统变量 `Path` → 编辑 → 新建
`E:\PostgreSQL\bin`。

**方式 D：不碰命令行**——用 **pgAdmin 的 Query Tool** 粘贴 SQL 执行，或用 IDEA/DataGrip
的数据库工具连上去跑 `scripts/db/01-schema.sql` 的内容。
（pgAdmin 装 PostgreSQL 时通常会一起装，开始菜单里搜得到。）

---

## 4. 后端配置

后端的配置分两个文件，**分工必须分清**：

| 文件 | 入库？ | 放什么 |
| --- | --- | --- |
| `backend/src/main/resources/application.yml` | ✅ 会提交 | 与个人机器无关的通用配置（端口、连接串主机、算法参数） |
| `backend/src/main/resources/application-local.yml` | ❌ **已在 `.gitignore`** | 与个人机器强相关的**秘密**：数据库密码（可加本机路径覆盖） |
| `...application-local.yml.example` | ✅ 会提交 | 上面那个文件的**模板**，只有占位符，没有真密码 |

`application.yml` 默认激活 `local` profile（`application.yml:5-6` 的 `spring.profiles.active: local`），
所以 **`application-local.yml` 不存在时，后端就没有数据库密码**，启动会直接失败。

### 4.1 复制模板 → 填数据库密码

```powershell
# PowerShell —— 在仓库根目录执行
Copy-Item backend\src\main\resources\application-local.yml.example `
          backend\src\main\resources\application-local.yml
notepad backend\src\main\resources\application-local.yml
```

```bash
# bash
cp backend/src/main/resources/application-local.yml.example \
   backend/src/main/resources/application-local.yml
# 然后用你喜欢的编辑器打开它
```

复制出来的内容（模板全文，5 行）：

```yaml
# 这是模板文件，可以提交到 Git。
# 用法：复制本文件为 application-local.yml，然后把下面的密码改成你自己的。
spring:
  datasource:
    password: 在这里填你的本地 PostgreSQL 密码
```

把最后一行的占位文字换成**你本机 postgres 用户的真实密码**即可
（用户名、主机、端口、库名都在 `application.yml` 里，不用在这个文件里重复写）。

**关于安全**：

- ✅ `.gitignore:44` 明确排除了 `application-local.yml`（以及 `application-*.local.yml`、`*.local.yml` 等变体），
  **这个文件永远不会被提交**，可以放心写真密码。
- ⚠️ **别把密码写进 `application.yml`**——那个文件是要入库的。本项目历史上真的泄漏过一次数据库密码，
  是靠改密码补救的，所以这条是硬规矩。
- ⚠️ 复制完**不要**把 `application-local.yml` 改名成能匹配 `!` 反向规则的名字来"提交它"——没有这种需求。
- 如果 `application-local.yml` 已存在（比如你之前配过），**不要覆盖**，检查一下密码对不对就行。

### 4.2 ⚠️ 必改一：`calcite.import.allowed-roots`（批量导入目录白名单）

**位置**：`backend/src/main/resources/application.yml:47-48`

```yaml
calcite:
  import:
    # 允许批量导入的根目录白名单。接口收到的 path 必须落在其中之一，否则拒绝。
    allowed-roots:
      - D:\Calcite-note\GPX-Data\Geolife Trajectories 1.3\Data   ← 这是作者机器上的路径
```

**为什么必须改**：

1. **它是白名单，不是默认值。** 批量导入接口 `POST /api/import/geolife` 收到的 `path`
   必须落在 `allowed-roots` 中的某一个根目录**之下**，否则直接拒绝
   （报「不在允许的目录内」）。上面那条是**作者电脑上的 GeoLife 数据目录**，
   你的机器上大概率连 `D:` 盘都没有 ⇒ **批量导入永远失败**。
2. **它本来就是一道安全约束。** 这个本地项目没有登录体系，如果接口能读任意路径，
   就等于把服务器的整个文件系统暴露给了调用方。把读取范围收敛到几个明确的根目录，
   是这个设计的**目的**，不是可有可无的装饰——所以正确做法是**填你自己的数据目录**，
   而不是把它删掉或改成 `D:\`、`/` 这种大范围路径。

**怎么改**（两种方式，选一种）：

- **方式 A（推荐，最直观）**：直接编辑 `backend/src/main/resources/application.yml`，
  把它换成你机器上的 GeoLife（或任意轨迹数据）目录：

  ```yaml
  calcite:
    import:
      allowed-roots:
        - E:\data\Geolife Trajectories 1.3\Data      # ← 换成你自己的目录
  ```

  这个文件会入库，但**路径本身不含秘密**；提交前 `git diff` 看一眼即可，
  不想提交就 `git checkout -- backend/src/main/resources/application.yml` 还原。

- **方式 B（不改入库文件）**：写进 `application-local.yml`，利用 Spring Boot 的
  profile 配置**覆盖** `application.yml` 里的同名配置：

  ```yaml
  calcite:
    import:
      allowed-roots:
        - E:\data\Geolife Trajectories 1.3\Data
  ```

  > ⚠️ 本项目**尚未实测** profile 对列表型配置的覆盖行为（待实测）。
  > 用方式 B 的话，改完请真的跑一次批量导入来确认生效；没生效就改用方式 A。

**改完必须重启后端**——配置只在启动时读一次。

### 4.3 ⚠️ 必改二：`calcite.data.recycle-dir`（删除前的回收站目录）

**位置**：`backend/src/main/resources/application.yml:106-108`

```yaml
calcite:
  data:
    # 删除前的自动导出目录。**删之前先导出，导出失败就不删**（fail-safe）
    recycle-dir: D:\Calcite-note\backups\deleted   ← 这是作者机器上的路径
```

**为什么必须改**：

1. **删除轨迹是「先导出、后删除」的 fail-safe 流程。** `DELETE /api/tracks/{id}` 会先把这条轨迹
   导出成 GeoJSON 到 `recycle-dir`，**导出成功才真正删库**；导出失败就直接返回 500、
   轨迹原样保留。
2. **所以这个目录不存在或不可写时，「删除轨迹」会稳定返回 500。** 这是**设计行为，不是 bug**——
   宁可删不掉，也不允许出现"库里的数据没了、回收站里也没有"的不可逆丢失。
3. 默认值 `D:\Calcite-note\backups\deleted` 是作者机器上的路径，你机器上多半不存在
   ⇒ 一删就 500。

**怎么改**：先建一个你机器上确实存在、且当前用户可写的目录，再把绝对路径填进去。

```powershell
# PowerShell：在仓库根目录建一个本地回收站目录
New-Item -ItemType Directory -Force -Path .\backups\deleted
# 然后把 recycle-dir 填成它的绝对路径，例如：
#   recycle-dir: E:\JAVA_IDEA_package\JAVA_Project\Calcite\backups\deleted
(Get-Item .\backups\deleted).FullName      # 打印绝对路径，直接复制粘贴
```

```bash
# bash
mkdir -p ./backups/deleted
# recycle-dir: /绝对路径/backups/deleted
```

> ⚠️ **路径要写绝对路径**，相对路径在服务工作目录变化时会指到别处。
>
> ⚠️ 如果你在**受限环境**（某些沙箱/容器）里跑，`D:\`、`E:\`、`C:\Users\...` 下的用户目录
> 可能一律 `WinError 5 / Access denied` —— 那是环境限制不是代码问题。
> 把 `recycle-dir` 指到**当前工作目录下的子目录**（如上面的 `.\backups\deleted`）即可绕开。
>
> ⚠️ **别图省事复用 `allowed-roots`**：那个是导入时的**读**白名单，这个是删除时的**写**目标，
> 用途完全不同，Spring 配置里也是两个独立的键（`calcite.import.allowed-roots` /
> `calcite.data.recycle-dir`）。

**改完必须重启后端**，然后可以用一次删除操作验证（删一条不重要的测试轨迹，
确认它在 `recycle-dir` 里生成了 `.geojson` 文件、库里那条也真的没了）。

### 4.4 本节检查清单

| # | 动作 | 状态检查方式 |
| --- | --- | --- |
| 1 | 复制 example → `application-local.yml` | 文件存在，且 `spring.datasource.password` 不是占位文字 |
| 2 | 确认没把密码写进 `application.yml` | `git status` 里 `application.yml` 若有改动，`git diff` 逐行看 |
| 3 | 改 `calcite.import.allowed-roots` | 填的是**你机器上真实存在**的轨迹数据目录 |
| 4 | 改 `calcite.data.recycle-dir` | 填的目录**已创建**且当前用户可写 |
| 5 | 重启后端使配置生效 | 配置只在启动时读一次 |

---

## 5. 启动后端

**前置**：第 3、4 节都做完了（库建好、表建好、`application-local.yml` 里有真密码、
`allowed-roots` / `recycle-dir` 已按本机改过）。

```powershell
# PowerShell —— 必须在仓库根目录执行（-f 的参数是相对路径）
mvn -f backend/pom.xml spring-boot:run
```

```bash
# bash
mvn -f backend/pom.xml spring-boot:run
```

⚠️ **本机 `mvn` 不在 PATH**（2.2 实测），所以作者用的是 IDEA 自带 Maven 的完整路径。
你也可以直接照抄下面这条（把 `<IDEA 安装目录>` 换成你机器上的）：

```powershell
& "<IDEA 安装目录>\plugins\maven\lib\maven3\bin\mvn.cmd" -B -f backend/pom.xml spring-boot:run
```

预期输出（**待实测**；只挑关键几行，前面还有一大段 Spring Boot banner 和依赖下载日志）：

```
2026-09-27T..  INFO ... o.s.b.w.embedded.tomcat.TomcatWebServer  : Tomcat started on port 8080 (http)
2026-09-27T..  INFO ... com.calcite.CalciteApplication          : Started CalciteApplication in X.XX seconds
```

**判读**：

- 上面两行都出现 = 后端起来了。`Tomcat started on port 8080` 是端口，`Started ... in X seconds` 是启动完成。
- **第一次运行会联网下载 Maven 依赖**，慢是正常的；之后走本地仓库就快了。
- 启动后控制台会**一直刷 SQL**（`select ... from track ...`）—— 那是 `application.yml:23` 的
  `spring.jpa.show-sql: true` 在按设计工作，**不是报错**。
- **这个窗口会一直被占着**（前台进程），所以验证请在**另一个窗口**里做；停止见第 9 节。

### 5.1 验证 `GET /api/health`

```powershell
# PowerShell：拿到结构化对象（可读性最好）
Invoke-RestMethod http://localhost:8080/api/health | ConvertTo-Json -Depth 5

# PowerShell：只要原始响应体
(Invoke-WebRequest http://localhost:8080/api/health -UseBasicParsing).Content
```

```bash
# bash
curl -s http://localhost:8080/api/health
```

预期输出（**待实测**）：

```json
{
  "status": "UP",
  "application": "calcite-backend",
  "database": "PostgreSQL 18.3 on x86_64-windows, compiled by ... 64-bit",
  "postgis": "3.6 USE_GEOS=1 USE_PROJ=1 USE_STATS=1"
}
```

**为什么这个接口能同时验证「数据库」和「PostGIS」**：它不是假健康检查 ——
`HealthController.java:35-36` 会真的去库里跑两句 SQL，`SELECT version()` 和 `SELECT PostGIS_Version()`，
两句都成功才返回 `status: "UP"`；任一句失败，接口直接 500。
换句话说：**`database` 字段有值 = PostgreSQL 通了；`postgis` 字段有值 = 目标库启用了 PostGIS 扩展**。

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| 返回上面的 JSON，`status` = `UP` | 后端 + 数据库 + PostGIS 全通 | 继续第 6 节 |
| 连接被拒（`Unable to connect to the remote server` / `curl: (7) Failed to connect`） | 后端还没起完，或没在跑 | 看启动窗口最后几行有没有 `Started CalciteApplication` |
| HTTP 500 / 响应里没有 `database` 字段 | 连不上库 | 第 8 节第 3 行（密码）、第 16 行（服务没起） |
| `Port 8080 was already in use`（启动时） | 8080 被占用 | 第 8 节第 6 行 |

> `database` / `postgis` 的**具体小版本以你机器上装的为准**；**字段名**是代码里定死的
> （`HealthController.java:29-40`），不会随机器变。

---

## 6. 启动前端

### 6.1 装依赖

```powershell
# PowerShell
cd frontend
npm install
```

```bash
# bash
cd frontend
npm install
```

国内网络慢 / 卡住时换镜像（只影响这一次安装，不改你的全局配置）：

```powershell
npm install --registry=https://registry.npmmirror.com
```

```bash
npm install --registry=https://registry.npmmirror.com
```

预期输出（**待实测**）—— 最后一行类似：

```
added 123 packages in 1m
```

**说明**：

- 运行时依赖只有 `vue` + `cesium`（`frontend/package.json:18-21`），另外三个是 devDependencies
  （`@vitejs/plugin-vue` / `vite` / `vite-plugin-static-copy`）。
- ⚠️ `cesium` 包很大（含 Workers / Assets / ThirdParty），第一次装会下几十 MB，慢是正常的。
- 装好后会出现 `frontend/node_modules/`；它不进 Git。

### 6.2 起开发服务器

```powershell
# PowerShell（在 frontend 目录里）
npm run dev
```

```bash
# bash
npm run dev
```

预期输出（**待实测**）：

```
  VITE v8.2.2  ready in XXX ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

**判读**：终端打印的 `Local:` 地址就是你要打开的地址；这个窗口和 5 节的后端窗口一样，
**会一直被占着**。

### 6.3 ⚠️ 必须用 `http://localhost:5173`，不要用 `127.0.0.1:5173`

**在浏览器地址栏输入 `http://localhost:5173`。**

如果输 `http://127.0.0.1:5173`，浏览器会报 **`ERR_CONNECTION_REFUSED` /「无法访问此网站」** ——
**这不是前端崩了，是地址不对**。

**原因**：本项目的 Vite 开发服务器**只绑定了 IPv6 回环地址**（`::1`）。Windows 上
`localhost` 会优先解析到 `::1`，所以 `localhost:5173` 能通；而 `127.0.0.1` 是 **IPv4**，
那个地址上**根本没有进程在监听**。这是本项目的实测行为（M3 计划书里也写着
「地址必须用 `http://localhost:5173`（Vite 只绑 IPv6）」）。

> 想让它同时听 IPv4 也可以：`npm run dev -- --host 127.0.0.1` 或 `--host 0.0.0.0`
> （**待实测** —— 本文没有验证过这两种写法在本项目里的行为；
> 另外 `--host 0.0.0.0` 会把开发服务器暴露给同网段的其它机器，本地开发不建议）。

**打开后应该看到**：

- 一个三维地球 + 左上角面板（地球是一片绿/灰也正常 —— 底图是 Cesium 自带的离线 NaturalEarthII，
  **不需要 token、不需要联网**）；
- 面板顶部「后端连通性」一行显示类似 **`UP · PostgreSQL 18.3 · PostGIS 3.6`**（值以你机器为准）——
  **这一行绿了，说明第 5 节的后端和本节的代理都通了**；
- 这一行是红的或报错 → 先回第 5 节确认 `/api/health`。

前端对 `/api` 的请求由 Vite 开发服务器**代理**到 `http://localhost:8080`
（`frontend/vite.config.js:32-37`），所以浏览器看到的是同源请求，**后端不需要配 CORS**。

### 6.4 顺带一跑：零依赖的纯逻辑回归（可选，**不需要任何服务**）

```powershell
# PowerShell（在 frontend 目录里）
npm run check:playback ; npm run check:chart ; npm run check:hotspot ; npm run check:density ; npm run check:similarity ; npm run check:data-edit ; npm run check:region
```

预期输出：7 个套件共 **157 项全绿**（playback 17 / chart 37 / hotspot 25 / density 25 /
similarity 19 / data-edit 11 / region 23），**2026-09-25 实测基线**。
这几条只用 Node 内置 `assert`，**不连数据库、不需要后端**。

---

## 7. 演示数据

两条路，按需要挑：

| 路线 | 命令 | 规模 | 什么时候用 |
| --- | --- | --- | --- |
| **A · 合成演示集** | `psql -f scripts/db/04-demo-data.sql` | 14 条轨迹 / 4,592 个点 / 601 KB | **推荐**：30 秒让五个面板都有东西看 |
| **B · GeoLife** | 官网下载 → `POST /api/import/geolife` | 182 用户 / 18,670 个 `.plt`（1.59 GB） | 想看大数据量、真实的城市轨迹 |

### 7.1 路线 A：合成演示集（推荐，30 秒）

在**仓库根目录**执行：

```powershell
# PowerShell
$env:PGPASSWORD = '<你的 postgres 密码>'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -f scripts/db/04-demo-data.sql
```

```bash
# bash
export PGPASSWORD='<你的 postgres 密码>'
psql -U postgres -h localhost -p 5432 -d calcite -f scripts/db/04-demo-data.sql
```

**这份数据是什么**（`scripts/db/04-demo-data.sql`，4,912 行）：

- **14 条轨迹**，`external_id` = `DEMO-001` … `DEMO-014`，`source` = `demo`，
  **共 4,592 个点**（逐条点数见文件里每段开头的注释：
  240+240+275+149+201+691+701+712+133+214+131+308+592+5）；
- 坐标落在**北京真实地标**附近（五道口 / 中关村 / 天安门 / 望京 / CBD / 什刹海 / 奥林匹克公园），
  但**轨迹本身是合成的**；时间戳固定在 **2026-09-01 ~ 2026-09-07**（过去时间，可重复）；
- **幂等**：文件开头就是 `DELETE FROM track WHERE external_id LIKE 'DEMO-%'`，重复执行结果一致；
  与示例轨迹 `SAMPLE-001`（`02-sample-track.sql`）**互不干扰**；
- **只写 `track` 和 `track_point` 两张表**；`stay_point` 表保持空 —— 停留点/热点是查询时算的，
  本来就不入库（设计如此）；
- 文件由 `scripts/demo/make-demo-data.py` 生成（固定随机种子，两次输出字节一致）。
  ⚠️ **要改内容请改脚本重新生成，不要手改这个 SQL**。

预期输出（**待实测**，只摘末尾两段验收）：

```
########## 2) 验收：演示轨迹概览 ##########
 external_id |            name             | point_count | 距离米  | 时长秒 | 漂移点 | 有海拔点数
-------------+-----------------------------+-------------+---------+--------+--------+------------
 DEMO-001    | 演示·通勤去程 五道口→中关村 |         240 |  2364.2 |   1546 |      0 |        240
 ...（DEMO-002 ~ DEMO-014，共 14 行）...
(14 rows)

########## 3) 验收：五档各自应当非空 ##########
 演示轨迹数 | 演示点数
------------+----------
         14 |     4592
(1 row)
```

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| 开头打印 `DELETE 14` | 清理掉了上一次的演示数据（幂等设计） | 正常 |
| 开头打印 `DELETE 0` | 第一次导入，没有旧数据可清 | 正常 |
| 末尾 `演示轨迹数 = 14`、`演示点数 = 4592` | 导入完整成功 | 打开第 6 节的页面，五个档逐个点一遍 |
| 报 `relation "track" does not exist` | 表没建 | 回 3.2 跑 `01-schema.sql` |
| `psql` 报编码错 / 中文乱码 | 控制台编码问题 | 见第 8 节第 12 行 |

**导入后五个档应当看到什么**（= 设计文档 5.2 的验收口径）：

| 面板 | 期望看到 |
| --- | --- |
| 列表 | 14 条「演示·…」轨迹（`source = demo`） |
| 停留点 | `DEMO-001`（通勤去程）**≥1 段**；`DEMO-003`（环湖跑步）**诚实地是 0 段** |
| 热点 | **≥2 个**热点，最大的一个 `trackCount` **≥3**（广场的三次到访） |
| 密度 | 北京范围、格边长 `0.002°` 非空，最热闹的格子 **≥3 条轨迹**；把时段切到「早高峰 / 晚间」结果会变 |
| 相似 | 选 `DEMO-001`，**第一名应为 `DEMO-002` 且 ≥60%** |
| 圈选 | 拉一个框 `lon 116.4302 ~ 116.4875 / lat 39.9037 ~ 39.9313` → 命中 `DEMO-013`（穿越 CBD 走廊） |

> 这些断言也有**离线版**（不连数据库）：`python scripts/demo/make-demo-data.py --self-check`
> 会打印每条轨迹的点数 / 距离 / 时长 / 停留段数 / 漂移点数 / 是否有海拔，再画一张 ASCII 密度轮廓图，
> 最后打一行 `✅ 自检通过` 或列出不满足的项（**待实测**）。
> ⚠️ 注意这条命令会**重新生成** `scripts/db/04-demo-data.sql`（内容一致、字节一致）。

### 7.2 路线 B：GeoLife（自己下载后批量导入）

**1) 下载。** GeoLife GPS Trajectories 1.3，微软官方发布，
下载页 ID **52367**：`https://www.microsoft.com/en-us/download/details.aspx?id=52367`
（**本文未实测该链接可达**，以官网当前页面为准）。
仓库**不打包**这份数据 —— 它有再分发许可问题，而且 1.59 GB 也不该进 Git。
本项目作者机器上的规模（实测）：**182 个用户、18,670 个 `.plt` 文件、1.59 GB**；
解压后目录形如 `...\Geolife Trajectories 1.3\Data\<用户号>\Trajectory\*.plt`。

**2) 把数据目录加进白名单。** 见 **4.2**：接口收到的 `path` 必须落在
`calcite.import.allowed-roots` 之下，否则一律 400（响应里写「路径不在允许的导入目录内」）。
**改完必须重启后端**（配置只在启动时读一次）。

**3) 导入。** 用仓库里的脚本 `scripts/demo/import-geolife.py`（它会先确认后端在跑、检查目录、
再调批量导入接口，并把"白名单没配"的报错翻译成怎么改）：

```powershell
# PowerShell —— 从仓库根目录执行
& "E:\python\python_address\python.exe" scripts\demo\import-geolife.py `
    --data-dir "E:\data\Geolife Trajectories 1.3\Data" --user 000 --max-tracks 15
# 先小批量（15 个文件）确认没问题，再放大；--dry-run 只检查不导入
```

不想用脚本也可以直接打接口（等价写法）：

```powershell
# PowerShell
$body = @{ path = 'E:\data\Geolife Trajectories 1.3\Data'; maxTracks = 50 } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8080/api/import/geolife -Method Post `
  -ContentType 'application/json; charset=utf-8' -Body $body | ConvertTo-Json -Depth 5
```

```bash
# bash
curl -s -X POST http://localhost:8080/api/import/geolife \
  -H 'Content-Type: application/json' \
  -d '{"path":"/data/Geolife Trajectories 1.3/Data","maxTracks":50}'
```

请求体只有两个字段（`ImportController.GeoLifeRequest`）：
`{"path": "<本地目录>", "maxTracks": <本次最多处理几个文件>}`；
`maxTracks` 不传时用配置里的 `calcite.import.max-tracks-per-call`（默认 **50**）。

响应（字段名来自 `ImportService.GeoLifeImportResult`，值**待实测**）：

```json
{
  "path": "E:\\data\\Geolife Trajectories 1.3\\Data",
  "scanned": 18670,
  "imported": 50,
  "skipped": 18620,
  "failed": 0,
  "totalPoints": 12345,
  "elapsedMs": 2345,
  "errorSamples": []
}
```

| 字段 | 含义 |
| --- | --- |
| `scanned` | 这次**扫到**多少个 `.plt` 文件（整个目录） |
| `imported` | 本次**真的入库**了几条 |
| `skipped` | 本次**没处理**的：已经导过（幂等跳过）+ 超出 `maxTracks` 的 |
| `failed` | 解析/入库失败的文件数（`errorSamples` 里给前几条原因） |
| `totalPoints` | 本次入库的点数合计 |

**4) ⚠️ 两个必须记住的口径：**

- **`maxTracks` 是「文件数」上限，不是「轨迹数」。** 一个 `.plt` 文件 = 一条轨迹，
  所以 18,670 个文件一次只处理**前 50 个**（按文件名排序），
  **其余全部计入 `skipped`**。看到 `imported: 50 / skipped: 18620` **不是失败**，是「本次没轮到」。
- **导入是幂等的**（按**文件内容 SHA-256** 判重，改文件名也认得出来）：
  **再调一次同样的请求，已导入的会被跳过、自动往后取下一批** ——
  想灌更多就**反复调用**（或者把 `maxTracks` 调大）。
  这也意味着「重复调同一个请求」永远不会产生重复轨迹。

---

## 8. 常见报错表

按「现象」找行。**前 14 条来自设计文档的预填表**（全部是本项目**真实踩过的坑**），
第 15~21 条是本次补的（同样有代码 / 配置出处）。

| # | 现象 | 根因 | 解决 |
| --- | --- | --- | --- |
| 1 | `ERROR: type "geometry" does not exist` | 目标库没装 PostGIS | 跑 `01-schema.sql`（已含 `CREATE EXTENSION postgis`），或在目标库手动 `CREATE EXTENSION postgis;` |
| 2 | `psql: 无法识别的命令` / PowerShell 报 `CommandNotFoundException: psql` | psql 不在 PATH | 用 `<PG安装目录>\bin\psql.exe`（Windows 默认 `C:\Program Files\PostgreSQL\<版本>\bin`）；找法见 **3.4**；不碰命令行就用 pgAdmin 的 Query Tool |
| 3 | 后端启动报密码认证失败（`FATAL: password authentication failed for user "postgres"`） | 没复制 `application-local.yml`，或里面是占位文字 / 旧密码 | 见 **4.1**：复制 example 并填真实密码（该文件已在 `.gitignore`，不会误提交） |
| 4 | 批量导入报「**路径不在允许的导入目录内**」 | `calcite.import.allowed-roots` 是**白名单**，不是默认值 | 见 **4.2**：改成自己的 GeoLife 数据目录并**重启后端** |
| 5 | 删除轨迹返回 **500**（轨迹却还在） | `recycle-dir` 不存在 / 不可写 —— 「**先导出、后删除**」的 fail-safe 生效了 | 见 **4.3**：建目录或改成可写路径。**这是设计行为，不是 bug** |
| 6 | `Port 8080 was already in use` / `Web server failed to start` | 旧后端进程还占着 8080 | 停掉旧进程（**9.1** 按端口找 PID），或改 `application.yml` 的 `server.port` |
| 7 | 浏览器打不开 5173（`ERR_CONNECTION_REFUSED`） | Vite 只绑 **IPv6**，`127.0.0.1` 是 IPv4 | 用 `http://localhost:5173`，**不要用 `127.0.0.1:5173`**（见 6.3） |
| 8 | `invalid target release: 25` / 运行期 `UnsupportedClassVersionError` | JDK 版本不是 25 | 装 JDK 25 并确认 `java -version`（见 2.1）；`Get-Command java` 看解析到哪个路径 |
| 9 | `npm install` 卡住 / 超时（`ETIMEDOUT`） | 直连 npm 官方源太慢 | `npm install --registry=https://registry.npmmirror.com` |
| 10 | 页面控件（时间轴 / 按钮 / 版权条）**样式散架** | Cesium 的 `widgets.css` 没加载 | 确认依赖装全（`frontend/node_modules/cesium` 存在；`CesiumGlobe.vue:36` 会 `import` 它）；重新 `npm install` 后再验一次 |
| 11 | 五个档里**某一档"没东西"**（打开就是空的） | 演示数据没导入 / 时间窗或视野不对 | 先跑 7.1 的 `04-demo-data.sql`；**密度**看的是当前视野（放太大就只剩几格）、**相似**要先在列表里选一条轨迹、**圈选**要先画一个区域 |
| 12 | psql 读中文 SQL 报编码错 / 输出乱码 | 中文 Windows 控制台默认 GBK | 脚本首行已有 `\encoding UTF8`；再补 `chcp 65001` + `$env:LC_MESSAGES='C'`（见 3.2 末尾）；仍乱码就 `-o 文件` 输出到文件再看（`03-show-results.sql` 头部是范例） |
| 13 | 上传 GPX 报「**无法识别格式**」 | 解析器按**文件内容**识别格式，**不看扩展名** | 确认文件确实是 GPX / PLT 之一；看响应体里的中文原因（`server.error.include-message: always` 已打开，`application.yml:39-40`）；扩展名是 `.gpx.bin_tmp` 之类**不影响**识别 |
| 14 | 单次批量导入**只处理了 50 个文件**就不动了 | `max-tracks-per-call` 是**文件数**上限（**不是 50 条轨迹**） | 再调一次同样的请求（幂等 → 自动跳过已导入的、继续往后取），或调大 `calcite.import.max-tracks-per-call` 后重启后端（见 7.2） |
| 15 | 前端 `npm run dev` 打印的是 **5174**（不是 5173） | 5173 被上一次没退干净的 Vite 占着，Vite 自动换了端口 | 关掉旧窗口 / 按 **9.1** 停掉 5173 的进程；懒得找就直接用终端打印的新端口 |
| 16 | 后端启动报 `Connection to localhost:5432 refused` / `FATAL: 数据库系统正在启动中` | PostgreSQL 服务没起（或正在重启） | `Get-Service postgresql*` 看状态；`Start-Service postgresql-x64-18`（管理员）起回来 |
| 17 | `psql: FATAL: database "calcite" does not exist` | 库还没建（或连错了库名） | 回 **3.1** 建库；所有脚本都要带 `-d calcite` |
| 18 | `mvn` 报 `CommandNotFoundException: 无法将"mvn"识别为…` | Maven 没装或没进 PATH（**本机实测就是这样**） | 见 **2.2** 的三种办法（装 Maven 进 PATH / 用 IDEA 自带 `mvn.cmd`）—— 本仓库**没有** `mvnw`，不能靠 wrapper 兜底 |
| 19 | `mvn test` 报 `Could not self-attach to current VM using external process` | Mockito 需要 fork 外部进程 attach JVM，受限环境禁止 spawn | `pom.xml:88-95` 已预挂 `-javaagent:byte-buddy-agent`；普通机器无此问题。若在别处复现，确认该 agent 的 jar 已下到本地仓库（首次需联网） |
| 20 | 受限环境里 `npm run dev` / `vite build` 报 `spawn EPERM` | 该环境禁止创建子进程（Vite 要 spawn 才能探测路径） | 换到普通终端跑；**不是代码问题**（本项目在沙箱里是靠提权绕过的） |
| 21 | 上传成功但列表里没多出新轨迹，响应里 `skippedDuplicate: true` | 文件**内容**（SHA-256）和库里已有的完全相同 → 幂等跳过 | **不是失败**：改文件名也认得出。真想再入库就换一份内容不同的文件 |

---

## 9. 停止与清理

### 9.1 停服务

- **前端**（跑着 `npm run dev` 的那个窗口）：`Ctrl + C`。
- **后端**（跑着 `mvn spring-boot:run` 的那个窗口）：`Ctrl + C`；看到构建结束 / 回到提示符即已停。

窗口已经关了、或进程还在后台 → **按端口找 PID 再杀**：

```powershell
# PowerShell：找 8080 的 PID（这台机器上 Get-NetTCPConnection 不可靠，用 netstat）
netstat -ano | Select-String ":8080\s" | Select-String "LISTENING"
# 输出的最后一列就是 PID，假设是 12345：
Stop-Process -Id 12345 -Force

# 5173 同理
netstat -ano | Select-String ":5173\s" | Select-String "LISTENING"
Stop-Process -Id <PID> -Force
```

```bash
# bash
lsof -i :8080          # 或 ss -lptn 'sport = :8080'
kill <PID>
```

> ⚠️ **不要图省事 `Stop-Process -Name java -Force`** —— 那会把 IDEA 和其它 Java 程序一起杀掉。
> 先按端口定位到具体 PID，再杀那一个。

PostgreSQL 服务一般**不用**停；真要停（需要管理员权限）：

```powershell
Stop-Service postgresql-x64-18      # 本机服务名，见 3.4
Start-Service postgresql-x64-18     # 起回来
```

### 9.2 清演示数据（`DEMO-%`）

先数一下会删多少（可选），再删：

```powershell
# PowerShell —— 在仓库根目录执行
$env:PGPASSWORD = '<你的 postgres 密码>'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -c "SELECT count(*) FROM track WHERE external_id LIKE 'DEMO-%';"
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -c "DELETE FROM track WHERE external_id LIKE 'DEMO-%';"
```

```bash
# bash
psql -U postgres -h localhost -p 5432 -d calcite -c "DELETE FROM track WHERE external_id LIKE 'DEMO-%';"
```

预期输出（**待实测**）：

```
DELETE 14
```

**说明**：

- `track_point.track_id` 上有 `ON DELETE CASCADE`（`01-schema.sql:32`），**点会跟着一起删**，
  不需要手动清 `track_point`；
- `LIKE 'DEMO-%'` **不会误伤** `SAMPLE-001` 示例轨迹，也不会误伤你自己导入的 GPX / GeoLife 数据；
- 只想清某一条，也可以用页面上的「数据编辑 → 删除」（走接口，会先导出到回收站）；
- ⚠️ **直接改库不会清后端的内存缓存**：停留点 / 相似度是按轨迹缓存的、**永不失效**，
  缓存只在「导入 / 改名 / 删除**接口**」里被清理。所以清完库之后，
  **热点 / 相似度可能还显示旧结果** —— 这是设计行为（宁可全清也不漏清），
  **重启后端即可**（9.1 + 第 5 节）；
- 想连表一起重来（顺便验证脚本可重复执行）：删完再跑一次 7.1 的导入，结果与第一次完全一致。

### 9.3 删库（确认再也不需要的时候）

```powershell
# 1) 先停后端（连接还开着时 DROP 会被拒绝）
# 2) 连到系统库 postgres，删目标库 calcite
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d postgres -c "DROP DATABASE calcite;"
```

```bash
# bash
psql -U postgres -h localhost -p 5432 -d postgres -c "DROP DATABASE calcite;"
```

预期输出（**待实测**）：

```
DROP DATABASE
```

- 报 `database "calcite" is being accessed by other users` → 还有连接没断
  （后端没停，或 IDEA / DataGrip 的数据库窗口开着）。停掉之后再删；
  PostgreSQL 13+ 也可以强制：`DROP DATABASE calcite WITH (FORCE);`（**待实测**）；
- **演练库同理**：按设计文档 5.1 的纪律，从零演练**只用新库名 `calcite_demo`，绝不动 `calcite`**；
  演练完 `DROP DATABASE calcite_demo;`；
- 删库前想留一份备份（`pg_dump.exe` 与 psql 同目录）：
  `& "E:\PostgreSQL\bin\pg_dump.exe" -U postgres -h localhost -p 5432 -d calcite -Fc -f calcite.dump`
  （**本文未实测**；备份 / 恢复策略不在本文范围内，见第 1 节的「不覆盖」表）。

---

## 10. 跑验收

**入口**：`scripts/acceptance/README.md`（每个脚本一行：做什么 / 依赖什么服务 / 预期数字 / 原路径
—— 那 22 个脚本是 2026-09-27 从 `.tmp/` 迁过来的，**历史设计文档里写的仍是旧路径 `.tmp/xxx`**，
对照表就在这个 README 里）。

> 统一约定：**从仓库根目录运行**（脚本里读写的相对路径都以仓库根为基准）。

### 10.1 三类脚本（+ 一类纯前端回归）

| 类别 | 长什么样 | 需要什么服务 | 实测基线（2026-09-25） |
| --- | --- | --- | --- |
| **A · 浏览器验收** | 9 个 `check-*.py`（Playwright 打开页面 + Pillow 数像素 / 查 DOM） | **后端 8080 + 前端 5173 都要在跑**（第 5、6 节）；需要 Python + Playwright + Chrome | 8 个脚本 **123 项**：stay 7 / chart-pixels 10 / import-pixels 6 / filter 7 / hotspots 17 / density 15 / similarity 17 / within 44 |
| **B · 接口对拍** | 5 个 `verify-*-api.py`（只打 HTTP，和独立算出来的期望值对比） | **只要后端 8080**（+ 库里得有数据）；**不需要浏览器** | within 105 / hotspot 375 / density 51 / similarity 45 / data-edit（需提权，会真删一条轨迹） |
| **C · 组件级桩 / 纯逻辑** | `frontend` 的 7 个 `npm run check:*`（Node 内置 assert，零依赖）+ `check-runtime-task9.mjs` 等 `.mjs` 桩测试 | **不需要任何服务**（有 Node 就行） | node 7 套件 **157 项**；桩测试 `check-runtime-task9.mjs` **67 项** |

另有两条与验收等价的命令：

```powershell
# 后端单测（不需要数据库）
mvn -f backend/pom.xml test              # 预期（待实测）：162 项全绿

# 生产构建（可选，验证能打包）
cd frontend ; npm run build              # 预期（待实测）：1506 modules / ✓ built
```

### 10.2 怎么跑单个脚本

**在仓库根目录跑**（脚本里的相对路径是按仓库根目录写的）：

```powershell
# PowerShell
python scripts/acceptance/check-stay-points.py
python scripts/acceptance/verify-density-api.py
```

```bash
# bash
python scripts/acceptance/check-stay-points.py
python scripts/acceptance/verify-density-api.py
```

**三条纪律**：

1. **A 类必须先起好 8080 + 5173**（第 5、6 节），否则会得到一堆超时 / 白屏的**假红**；
2. 上面那组数字是**当时那套数据的基线**（246 条轨迹 / 286,019 个点：
   GeoLife 242 + 示例 1 + 用户自采 3）。**只导演示集时数字一定会不同** ——
   这些脚本的用途是「和已知基线对齐」，**不是通用断言**；
3. `verify-data-edit-api.py` / `check-data-edit.py` **会真的删掉一条轨迹**
   （删前导出到 `recycle-dir`）。跑完要按脚本提示从源 `.plt` 重新导入，
   **新 id 会和原来不一样**。跑之前先确认数据状态，跑完立刻恢复。

---

> **本文标了「待实测」的地方（等真实演练替换）** —— 这是本文的诚实边界：
>
> - 第 5 节：后端启动日志、`/api/health` 的响应值（**字段名有代码出处，值没有**）；
> - 第 6 节：`npm install` / `npm run dev` 的输出、`--host 127.0.0.1` 变体；
> - 第 7 节：`04-demo-data.sql` 的导入输出（14 行 + 4,592 点，由文件内注释累加得出）、
>   `make-demo-data.py --self-check` 的报告、GeoLife 导入响应、GeoLife 官方下载链接可达性；
> - 第 9 节：`DELETE 14` / `DROP DATABASE`、`DROP ... WITH (FORCE)`、`pg_dump` 那条；
> - 第 10 节：`mvn test` 162 项、`vite build` 1506 modules（数字来自 2026-09-25 的实测基线，
>   但**本文没有重跑**）。
>
> **第 1~4 节的正文一个字没改**（只更新了文首的状态块 —— 它原来写着「第 5 节之后尚未编写」；
> 那部分里原有的「待实测」标记也保持不变）。

---

## 11. 可选：在线底图（高德，演示用）

地球**右上角**有一个**默认关闭**的底图开关。打开后叠加**高德**在线底图，并可切换两套样式：

| 样式 | 内容 | 实测 |
|---|---|---|
| **高德·街道图**（默认） | 矢量：建筑轮廓 + 中文路名 + 绿地水系 | z16 就能看到建筑轮廓与路名 |
| 高德·高清影像 | 卫星影像 | z18 能看清单栋建筑、树木、道路 |

**不需要 key，也不需要任何配置**（`application-local.yml` 里现在只有数据库密码）。
关掉即撤销图层、连贴图一起销毁 —— **关闭状态下一条瓦片请求都不会发**（浏览器验收里数请求数证实）。

### 11.1 ⚠️ 已知限制：GCJ-02 偏移（**暂存，不再投入**）

高德是 **GCJ-02（火星坐标）**，我们的轨迹是 WGS84（GPS 原始），直接用会让轨迹整体偏 300~600 米。
本项目在影像的 `rectangle` 上做**反向补偿**（`frontend/src/lib/basemap.js` 的 `gcj02Offset()` /
`compensatedWorldRectangle()`，参考点取当前相机中心），把影像推回 WGS84 位置 ——
**但补偿后仍有百米级残差**（偏移量随地点缓变，单一常数推不平）。

- **2026-09-27 决定：暂存这个问题**（边际收益已经很低）。要看当前对齐效果，跑验收脚本留的两张图：
  `.tmp/basemap-align-tiananmen.png`（相机对准天安门 WGS84 坐标）与
  `.tmp/basemap-align-track.png`（真实 GeoLife 轨迹压在街道图上——真轨迹跟着路网走，一眼可判）。
- **补偿为什么只能"部分生效"**（两条路都实测过，2026-09-27）：
  1. 把世界矩形反向挪 delta 交给 `provider.rectangle`（当前做法）：Cesium 构造时做
     `Rectangle.intersection(options.rectangle, tilingScheme.rectangle)` ⇒ 超出世界边界的部分**被裁掉**
     （实测 `west` 恒等于 -180、`east` 保留偏移），"平移"退化成"以世界西/南边缘为锚点的缩放"：
     北京只恢复约七成、**残余 ~150 米**。
  ⇒ **但这条最终没采用**（见下面第 3 点）：**已解决（2026-09-27）**：最终没走「挪影像」，改成**显示期坐标转换** —— 底图是火星坐标时把画在地球上的几何整体 **+delta**、用户画出来的坐标 **−delta** 转回真实 WGS84 再查库（`lib/basemap.js` 的 `wgs84ToGcj02` 等，`App.vue` 一处接上）。**按点取 delta ⇒ 精确**、与城市无关。实测（验收脚本读**地球实际画出来的坐标**）：底图开着位移 **+523 米东 / +146 米北**，关掉后 **0.0 米**。
  2. 改去挪**剖分方案**的墨卡托米制边界（更"正统"）：**经度方向走不通** —— 世界西边界本来就是 -180，
     任何向西平移都会越过 ±180，Cesium 归一化后矩形退化（实测构造出的 `provider.rectangle.west` 变成 +179.99），
     图层入地球时 `Rectangle.intersection` 返回 `undefined` ⇒ 抛 `DeveloperError`、渲染直接停住。
     （`UrlTemplateImageryProvider` 不传 `rectangle` 时它就是 `undefined`，同样会炸——必须显式传。）
- **要彻底消除偏移，只能做"显示期坐标转换"**（把 WGS84 几何转成 GCJ-02 再画，或反过来）；
  代价是轨迹/停留点/热点/密度格/圈选区域都要转，圈选交互还得反向转回来查库 —— 另一件较大的事，**暂存**。
  另一条路是换回**无偏移坐标系**的底图（天地图 CGCS2000≈WGS84 / OSM）。
  天地图**曾经接过**，但用户那把 key 没开通「矢量底图」服务（任何层级都返回 200 + 空白/占位瓦片），
  公开影像又只到 12 级，**2026-09-27 已整体移除**（含后端配置接口）；相关教训保留在
  `_session_context.md`（`_w` 矩阵集 0 级是 1×1、HTTP 200 ≠ 有内容）。

### 11.2 自查（两条命令）

```powershell
# ① 纯逻辑：URL 模板 / GCJ-02 补偿 / 样式（不需要服务）
cd frontend; npm run check:basemap

# ② 浏览器验收：默认关 + 关闭时零请求 + 图层 1→2→1 + **瓦片真有内容**（需要 8080 + 5173 在跑）
& "E:\python\python_address\python.exe" scripts\acceptance\check-basemap.py
```

⚠️ 验收判据用的是「**最常见颜色占比**」而不是状态码、也不是颜色种数：
底图服务没数据时会返回 `200` + 全白/占位图（实测空白 100% 单色、占位 98.2%），
而高德**矢量**图本身只有 250 来种颜色 —— 这两条都踩过，别再退回旧判据。

---

## 附录 · 实测记录（2026-09-27）

> 环境：Windows 11 · PostgreSQL 18.3（装在**非默认目录** `E:\PostgreSQL`）· PostGIS 3.6 · JDK 25.0.2 ·
> Node v24.14.0 · Maven 3.9+。演练用一个**全新的空库 `calcite_demo`**（不碰主库 `calcite`）。

**① §3.2 初始化（`psql -f scripts/db/01-schema.sql`）** —— 退出码 0，输出含：

```
CREATE EXTENSION          （postgis）
CREATE EXTENSION          （btree_gist）
CREATE TABLE × 4          （track / track_point / stay_point / …）
CREATE INDEX × 8
########## 补列（对已存在的老库生效）##########
注意:  关系 "track_point" 的列 "is_outlier" 已经存在，跳过
ALTER TABLE
```

⚠️ 最后那段「补列」在**新建库**上也会打印 —— 它是幂等脚本的正常输出，不是错误。

**② §3.3 验证**

```
$ psql -d calcite_demo -c "\dt"
 Schema |     Name        | Type  |  Owner          ← 4 行
 public | spatial_ref_sys | table | postgres        （PostGIS 自带）
 public | stay_point      | table | postgres
 public | track           | table | postgres
 public | track_point     | table | postgres

$ psql -d calcite_demo -c "SELECT PostGIS_Version();"
 3.6 USE_GEOS=1 USE_PROJ=1 USE_STATS=1
```

**③ §3.4 找 psql（本机实测）**

```
$ sc.exe qc postgresql-x64-18
BINARY_PATH_NAME : "E:\PostgreSQL\bin\pg_ctl.exe" runservice -N "postgresql-x64-18" -D "E:\PostgreSQL\data" -w
$ & "E:\PostgreSQL\bin\psql.exe" --version
psql (PostgreSQL) 18.3
```

**④ §5.1 `GET /api/health`（真实响应体）**

```json
{"status":"UP","application":"calcite-backend",
 "database":"PostgreSQL 18.3 on x86_64-windows, compiled by msvc-19.44.35225, 64-bit",
 "postgis":"3.6 USE_GEOS=1 USE_PROJ=1 USE_STATS=1"}
```

**⑤ §6.2 前端启动（真实输出片段）**

```
> calcite-frontend@0.0.1 dev
> vite

  VITE v8.2.2  ready in 907 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
[vite-plugin-static-copy] Collected 389 items.
```

（`npm install` 的输出本轮未实测 —— 本机 `node_modules` 已存在。）

**⑥ §7.1 演示数据导入（真实结果）** —— `psql -f scripts/db/04-demo-data.sql`，退出码 0：

```
tracks = 14    points = 4592    km = 155.2
is_outlier 的点 = 9            elevation_m IS NULL 的点 = 1525
```

- 概览表打印 14 行（`DEMO-001` … `DEMO-014`，含每条的点数/距离/时长/漂移点数/有海拔点数）；
- **连续执行两次结果一致**（文件幂等：开头 `DELETE FROM track WHERE external_id LIKE 'DEMO-%'`）；
- 生成器 `scripts/demo/make-demo-data.py` 连跑两次**字节一致**（643,185 字节，SHA-256 相同）；
- 五面板验收 `scripts/acceptance/verify-demo-data.py`（在只装演示数据的库上跑，后端实例
  `SERVER_PORT=8081` + `SPRING_DATASOURCE_URL=…calcite_demo`）：**13 项通过 / 0 失败**。

**⑦ §10 测试与构建（本轮真跑的数字）**

| 命令 | 实测 |
|---|---|
| `mvn -f backend/pom.xml test` | **162 项，0 失败**（不需要数据库） |
| `cd frontend && npm run build` | **1506 modules / built** |
| 前端纯逻辑 `npm run check:*`（7 个套件） | **157 项**（playback 17 / chart 37 / hotspot 25 / density 25 / similarity 19 / region 23 / data-edit 11） |
| 浏览器验收 `scripts/acceptance/check-*.py`（8 个） | **123 项**（stay 7 / chart-pixels 10 / import-pixels 6 / filter 7 / hotspots 17 / density 15 / similarity 17 / within 44） |
| 接口对拍 `scripts/acceptance/verify-*-api.py` | within **105** / density **51** / similarity 全绿 / hotspot 全绿 |

⚠️ 两个**破坏性**脚本（`verify-data-edit-api.py`、`check-data-edit.py`）本轮**没跑** ——
它们按设计会真删一条轨迹（跑完 id 会变），见 `scripts/acceptance/README.md`。
