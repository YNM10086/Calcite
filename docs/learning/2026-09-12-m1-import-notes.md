# Calcite 学习笔记（第三天：轨迹导入 —— M1 收官）

> 前两份是《第一阶段学习笔记》（基础知识点）和《第二天学习笔记》（回放 + 速度/海拔曲线）。
> 这一份讲 M1 的最后一块：**让数据进得来**。
>
> 今天你第一次写了真正的 Java 单元测试，第一次处理真实世界的脏数据，
> 也第一次撞上 Spring 框架的几个经典陷阱。

---

## 0. 今天做出来的东西

左边面板上方多了一个**「导入轨迹」**按钮：

1. 点它 → 选一个 `.gpx` 文件 → 等一两秒
2. 轨迹被画到地球上，自动选中，底部出现播放条和曲线
3. 面板上显示一行摘要：

> 导入成功：2026年6月22日户外跑步 · 2342 点 · 3.93 km · 39分08秒 · 标记 8 个疑似漂移点

**另一条路是批量导入**（给以后下载 GeoLife 数据集准备的），走命令行：

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/api/import/geolife `
  -ContentType 'application/json' -TimeoutSec 600 `
  -Body '{"path":"D:\\GeoLife\\Data","maxTracks":50}'
```

---

## 1. 知识点十：为什么"按文件内容"识别格式

你导出的那份文件，全名是：

```
2026年6月22日户外跑步.gpx.bin_tmp
```

**扩展名根本不是 `.gpx`。**

如果程序按扩展名判断（`if (name.endsWith(".gpx"))`），这个文件会被**直接拒掉**——而它明明是完全合法的 GPX。

所以 `FormatDetector` 只看**内容**：

```java
// GPX：XML 文档，可能带 <?xml 声明，也可能直接以 <gpx 开头
if (text.startsWith("<?xml") || text.startsWith("<gpx") || text.contains("<gpx")) {
    return "gpx";
}
// GeoLife .plt：每行 7 个逗号分隔字段，前两个是数字
if (f.length == 7 && isNumber(f[0]) && isNumber(f[1])) {
    return "geolife";
}
```

**这条经验很通用**：文件扩展名是「给人和操作系统看的提示」，不是可靠的事实。浏览器上传、邮件附件、下载工具都可能改掉它。**判断格式要看内容（很多格式还有"魔术数字"）**。

---

## 2. 知识点十一：可插拔解析器 与「统一中间结构」

这是今天**架构上最重要的一个决定**。

### 问题

我们要支持：

- 3 种格式：GPX、GeoLife `.plt`、（以后可能有的）CSV
- 2 个入口：网页上传、目录批量

如果每个组合各写各的：3 × 2 = **6 套代码**，而且**清洗规则要写 6 遍**。

### 解法

```
网页上传 ─┐
          ├→ 按内容选解析器 → 清洗 → 入库
目录批量 ─┘
              ↑
     三个解析器都输出同一种东西：RawPoint
```

```java
// 统一的中间结构 —— 三个解析器吐出来全是这个
public record RawPoint(double lat, double lon, Double elevationM, OffsetDateTime recordedAt) {}

// 解析器接口 —— 每个格式实现一次
public interface Importer {
    String format();
    ParsedTrack parse(InputStream in) throws Exception;
}
```

于是：

- **格式差异**在各自的解析器里消化掉（GPX 读 XML，`.plt` 读逗号）
- **清洗规则只写一份**（`TrackCleaner`），它只认 `RawPoint`，根本不知道数据从哪来
- 以后加 CSV：**只写一个新解析器类**，其他代码一行不动

**这就是"面向接口编程"的实际价值**——不是为了显得高级，而是把「N × M 种组合」压成「N + M 份代码」。

---

## 3. 知识点十二：两种格式，两个坑

### GPX（你手机导出的）

XML 格式。解析用 **JDK 自带的 DOM**，**没有引入任何新依赖**——和项目里"手写 SVG 不装图表库"是同一个取舍。文件才 300 KB，一次性读进内存没问题。

⚠️ **安全提醒**：解析外部文件时一定要关掉"外部实体"：

```java
factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
```

不关的话，别人构造一个恶意 XML 就能**让你的服务器去读本地文件**（这个漏洞叫 XXE）。

### GeoLife `.plt`

每行 7 个逗号分隔字段：

```
39.984702,116.318417,0,492,39744.1201851852,2008-10-23,02:53:04
  纬度      经度   占位 海拔(英尺) 1899年以来的天数   日期      时间(UTC)
```

**两个坑：**

**坑一：海拔单位是英尺。** 必须 × 0.3048 才是米。忘了乘，海拔会差 3.28 倍。

**坑二：时间是「1899-12-30 以来的天数」。** 这个基准日不是 1900 年也不是 1970 年，是 Excel 用的那个（`1899-12-30`）。而且第 5 个字段和第 6/7 个字段是**自洽的**：

```
0.1201851852 天 × 86400 秒 = 10384 秒 = 02:53:04   ✓ 对得上
```

所以我们用第 6/7 个字段（可读、无浮点误差），但**写了一条测试专门校验两者一致**——这样万一哪天格式变了，测试会立刻报警。

---

## 4. 知识点十三：真实 GPS 数据到底有多脏

这是今天最有意思的部分。把你那份 2342 个点的校园跑做了一次完整体检：

| 指标 | 实测值 | 说明了什么 |
| --- | --- | --- |
| 采样间隔 | 每 1 秒一个点 | 很密 |
| 时间戳重复 / 断档 / 倒流 | 0 / 0 / 0 | 时间维度很干净 |
| 海拔 | **2342 个点全是 `0.0`** | vivo 根本没记海拔 |
| 最高速度 | **12.13 m/s（43.7 km/h）** | ⚠️ **人跑不出来** |
| 超过 8 m/s 的段 | **4 段** | 都是 GPS 漂移 |
| 低于 0.5 m/s 的段 | 53 段 | 起跑前站着、等红灯 |
| 总距离（球面公式） | 3933.5 米 | vivo 自己记的是 4010.0 米 |

### 两个重要认识

**① 两条距离差了 1.9%，这不是 bug。**
vivo 用的算法和你自己算的不一样（椭球 vs 球面、采点密度、有没有算高度）。**"距离怎么算"本身就有多种答案**，面试时这是个能展开讲的话题。

**② 那条 43.7 km/h 是 GPS 漂移，不是你真跑那么快。**
手机 GPS 在城市里受高楼、树荫影响，偶尔会"跳"到几百米外再跳回来。

### 怎么识别漂移：自适应阈值

最朴素的想法是「速度 > 8 m/s 就算异常」。**但这会害死 GeoLife**——那个数据集里有**汽车（20 m/s）甚至火车（80 m/s）**的轨迹，全都会被误标。

所以用**自适应阈值**：

```
异常段 = 速度 > max(8 m/s, 3 × 该轨迹速度的中位数)
```

中位数会**自动适应轨迹类型**：

| 轨迹类型 | 速度中位数 | 3 × 中位数 | 实际阈值 | 效果 |
| --- | --- | --- | --- | --- |
| **你这份校园跑** | 1.627 m/s | 4.88 | **8.0**（取绝对下限） | 12.13 m/s 那段 ✅ 被标出 |
| GeoLife 汽车 | ~12 m/s | 36 | **36** | 正常行驶 20 m/s **不会**被误标 |
| GeoLife 高铁 | ~60 m/s | 180 | **180** | 只拦真正的坐标跳变 |

**这就是「不要写死魔法数字，让它自己适应」的一个具体例子。**

### 标记哪一端？

一个漂移点会造成**两段**异常速度（跳出去 + 跳回来），但我们**无法判断是哪一端漂了**。

**做法：两端都标。** 宁可多标，不可漏标。你这份数据里最多标 8 个点，占 2342 的 **0.34%**——完全可以接受。

### 海拔全 0 怎么处理

**规则：整条轨迹的海拔全相同时，一律当成"没有海拔数据"，全部存 NULL。**

为什么不能存 0？0 米是海平面，而福建校园实际海拔约 300 米——**0 表示"没记录"，不是"海拔为零"**。存 0 会让前端画出一条贴着底边的直线，误导看的人。

好消息是：前端**早就写好了降级显示**，会直接显示「这条轨迹没有海拔数据」。这就是为什么设计时"让每一层能优雅降级"是值得的。

---

## 5. 知识点十四：幂等 —— 重复上传同一个文件

**幂等**的意思是：同一个操作做一次和做十次，结果一样。

如果你把一个文件上传两次，不应该出现两条一模一样的轨迹。

### 怎么判断"是同一个文件"

| 方案 | 问题 |
| --- | --- |
| 按文件名 | 改个名就认不出了 |
| 按文件大小 | 不同文件可能一样大 |
| 按上传时间 | 那不就是每次都是新的 |
| **按内容哈希** ✅ | 改文件名也认得出；内容有一字节不同就不同 |

我们算文件的 **SHA-256**，取前 32 位当身份证：

```java
String externalId = sha256Hex(content);   // 例：4898c13a5f0508d0...
Optional<Track> existing = trackRepository.findByExternalId(externalId);
if (existing.isPresent()) {
    return ...skippedDuplicate(true), "这条轨迹已经导入过了";
}
```

数据库里 `track` 表本来就有 `external_id` 这一列（`TrackRepository` 里的 `findByExternalId` 方法也是早就写好的）——**说明当初设计表结构时就预见到了这件事**。

---

## 6. 知识点十五：Spring 今天坑了我们三次

这三个都是**网上搜不到具体名字、但一踩就卡住**的坑。

### 坑一：`@Transactional` 在"类内部自己调自己"时不起作用

Spring 的 `@Transactional` 是靠**代理**实现的：

```
外部调用 → [代理] 开事务 → 真正的对象.方法() → 提交事务
```

但**类内部自己调自己不走代理**：

```
this.importBytes(...)   ← 根本没经过代理，事务注解等于没写
```

**为什么这会出事**：批量导入方法如果标了 `@Transactional`，整批就是**一个巨型事务**。这时如果某一条数据出错，事务会被标记成 "只能回滚"——**后面所有文件的保存都会失败**，你写的 `catch` 也救不回来。

**解法**：批量方法**不标**事务，改成**每个文件单独开一个事务**：

```java
ImportResult r = txTemplate.execute(status -> importBytes(content, fallback));
```

这样一个文件失败只回滚它自己，循环能正常继续。

### 坑二：`@Value` 绑不了 YAML 列表

```yaml
calcite:
  import:
    allowed-roots:
      - D:\GeoLife
```

写成 `@Value("${calcite.import.allowed-roots}") List<String>` —— **启动直接报错**。

因为 YAML 列表在 Spring 眼里是 `allowed-roots[0]`、`allowed-roots[1]` 这种多个属性，而 `@Value` 只能读**单个标量**。

**解法**：用 `@ConfigurationProperties`：

```java
@Component
@ConfigurationProperties(prefix = "calcite.import")
public class ImportProperties {
    private List<String> allowedRoots = new ArrayList<>();
    // 记得给 setter，Spring 靠 setter 绑定
}
```

**记忆点**：标量用 `@Value`，**列表/嵌套结构用 `@ConfigurationProperties`**。

### 坑三：Mockito 在受限环境里 attach 不了（本项目环境特有）

报错原文：

```
Could not self-attach to current VM using external process
```

Mockito 靠**运行时改字节码**实现 mock，默认做法是**临时 fork 一个 JVM 去 attach 当前进程**。而本项目跑在受限沙箱里，**禁止 spawn 外部进程**，于是失败。

**解法**：预先用 `-javaagent` 把 agent 挂上，就不需要 self-attach 了（这也是 Mockito 官方在报错里给的解法）。写进了 `pom.xml` 的 surefire 配置。

---

## 7. 知识点十六：TDD 到底是怎么跑的

今天你第一次看到完整的 TDD 循环。**每个功能都走了这四步**：

```
① 写测试        →  ② 跑一遍，确认它【失败】
                        ↑ 这一步最容易被跳过，但最重要
③ 写实现        →  ④ 跑一遍，确认它【通过】
```

### 为什么第 ② 步不能省

今天有个现成的例子：计划里写的测试代码用了

```java
return sb.append("</gpx>").getBytes(StandardCharsets.UTF_8);   // ❌
```

跑第 ② 步时报错：**`StringBuilder` 没有 `getBytes()` 方法**。

**如果不跑这一步会怎样？** 你会在第 ④ 步看到"测试失败"，然后花时间怀疑是**实现**写错了——而实际上错的是**测试自己**。这就是"先看它红"能帮你省下的时间。

### 另一个例子：真实数据测试

我给清洗器写了一条用**你那份真实 GPX** 的测试：

```java
assertEquals(2342, c.points().size());
assertEquals(List.of(1128, 1129, 1135, 1136, 1144, 1145, 1585, 1586), flagged);
assertEquals(3933.5, c.distanceM(), 1.0);
```

**那串 seq 不是我猜的**，是先用 Python 独立算了一遍，再拿 Java 实现去对。两边数字完全一致——这比"应该大于 0"这种松垮的断言强得多。

**测试的价值不在于数量，而在于它到底钉住了什么。**

---

## 8. 今天的坑对照表

| 现象 | 原因 | 解法 |
| --- | --- | --- |
| 合法 GPX 被拒 | 按扩展名判断格式，而文件名是 `.bin_tmp` | 按**内容**判断 |
| `@Value` 绑 YAML 列表启动就崩 | `@Value` 只能读单个标量属性 | 用 `@ConfigurationProperties` |
| 批量导入"一条坏数据害死整批" | `@Transactional` 自调用不走代理，整批一个事务 | 外层不标事务，用 `TransactionTemplate` 每条单独开 |
| Mockito `Could not self-attach` | 沙箱禁止 fork 进程 attach JVM | surefire 预挂 `-javaagent:byte-buddy-agent` |
| 编译报 `StringBuilder` 找不到 `getBytes` | 忘了 `.toString()` | 跑"红"这一步时发现 |
| `psql -c` 里写中文别名报编码错 | 中文 Windows 下按 GBK 发送 | 用英文别名，或写成 `.sql` 文件用 `-f` |
| 海拔全 0 差点画成贴底直线 | 0 被当成"海拔为零" | 整条全同 → 存 NULL，前端显示"没有海拔数据" |
| `.plt` 海拔差 3.28 倍 | 单位是英尺 | × 0.3048 |

---

## 9. 命令速查

```powershell
# 后端所有单元测试（41 项）
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" test

# 只跑某一个测试类
& "...\mvn.cmd" -B "-Dmaven.repo.local=..." -f "...\backend\pom.xml" test "-Dtest=TrackCleanerTest"

# 上传一个 GPX（PowerShell 7 的 -Form 直接构造 multipart）
$f = Get-Item "某文件.gpx"
Invoke-RestMethod -Uri http://localhost:8080/api/tracks/import -Method Post -Form @{ file = $f }

# 批量导入本地 GeoLife 目录
Invoke-RestMethod -Uri http://localhost:8080/api/import/geolife -Method Post `
  -ContentType 'application/json' -Body '{"path":"D:\\GeoLife\\Data","maxTracks":50}'

# 查库核对（注意别名别用中文）
& "E:\PostgreSQL\bin\psql.exe" -U postgres -d calcite -c "SELECT count(*) AS pts, count(*) FILTER (WHERE is_outlier) AS outliers FROM track_point WHERE track_id=2;"
```

---

## 10. 明天的动手练习

**练习 1：改阈值，看标记数变化**

打开 `backend/src/main/resources/application.yml`，把 `max-speed-mps: 8.0` 改成 `5.0`，重启后端，重新导入一份 GPX（**先删掉旧的那条**，否则会走幂等分支）：

```sql
DELETE FROM track WHERE id = 2;
```

看看 `outlierCount` 从 8 变成多少。再改成 `15.0` 试试。**想清楚为什么中位数那条路径没起作用**（提示：3 × 1.627 = 4.88，比 5.0 小）。

**练习 2：故意传一个坏文件**

随便找个文本文件（比如 `pom.xml`）重命名成 `test.gpx` 传上去。应该返回：

```json
{ "error": "无法识别的文件格式（只支持 GPX 和 GeoLife .plt）" }
```

**这个实验证明了"按内容识别"是真的在工作**——如果按扩展名判断，它会被当成 GPX 然后解析失败。

**练习 3：验证幂等**

同一个文件连传两次，看第二次返回的 `skippedDuplicate`：

```powershell
$f = Get-Item "某文件.gpx"
(Invoke-RestMethod -Uri http://localhost:8080/api/tracks/import -Method Post -Form @{ file = $f }).skippedDuplicate
# 第一次 False，第二次 True
```

**练习 4：亲手跑一次 TDD**

挑一个还没写的测试：**"速度阈值应该可以被配置覆盖"**。

1. 先写测试（会红）
2. 跑一遍确认红
3. 看现有代码，想想需要改什么
4. 改到绿

**练习 5：看 EXPLAIN**

导入后库里有了两条轨迹，试试按时间范围 + 空间范围查：

```sql
EXPLAIN ANALYZE
SELECT * FROM track_point
WHERE geom && ST_MakeEnvelope(117.02, 25.03, 117.03, 25.04, 4326)
  AND recorded_at > '2026-06-22T11:00:00Z';
```

观察一下**空间条件有没有真的用上索引**（提示：这和你之前记录过的 `geom::geography` 坑是同一类问题）。

---

## 11. 阶段小结：M1 全貌

M1 三个阶段，各自解决一个问题：

| 阶段 | 完成时间 | 解决什么 |
| --- | --- | --- |
| **收进来** | 今天 | 数据从哪来：网页上传 GPX + 批量导入 GeoLife |
| **看得见** | 第二天 | 把轨迹画到地球上、能回放 |
| **看得出** | 第二天 | 速度和海拔画成曲线，跟着回放联动 |

**回归总览（100 项）**：

| 检查 | 项数 |
| --- | --- |
| 后端 JUnit `mvn test` | 41 |
| 回放纯逻辑 `npm run check:playback` | 17 |
| 曲线纯逻辑 `npm run check:chart` | 37 |
| 浏览器验收 `.tmp/check-import-pixels.py` | 5 |
| **合计** | **100** |

### 今天新增的概念，一句话各记一个

| 概念 | 一句话 |
| --- | --- |
| 按内容识别格式 | 扩展名不可信，看内容 |
| 可插拔解析器 | N 种格式 + M 个入口，写成 N + M 而不是 N × M |
| 统一中间结构 `RawPoint` | 格式差异在解析器里消化，清洗规则只写一份 |
| XXE 防护 | 解析外部 XML 必须关掉外部实体 |
| 自适应阈值 | `max(8, 3×中位数)` —— 让规则自己适应数据 |
| 幂等 | 同一个操作做一次和做十次结果一样（靠内容哈希） |
| 优雅降级 | 没有海拔就显示"没有海拔数据"，而不是画一条错线 |
| TDD 的红 | 先看测试失败，才能确定它在测对的东西 |
| 代理的边界 | 类内部自调用不走代理，`@Transactional` 会失效 |
| 配置绑定 | 标量用 `@Value`，列表/嵌套用 `@ConfigurationProperties` |

**最重要的一条**：今天所有的坑，都不是"Java 语法不会"，而是**框架的隐含规则**和**真实数据的脏**。这两样只能靠踩和记录积累——**你已经在做这件事了**（坑对照表就是你的资产）。
