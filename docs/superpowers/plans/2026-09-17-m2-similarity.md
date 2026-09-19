# 轨迹相似度（周一和周二走的是同一条路吗）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 选中一条轨迹，找出库里还有哪几条和它走的是同一条路，按相似度排序并在地球上叠画出来。

**Architecture:** 用**双向重合度**（`min(fwd%, rev%)`）代替设计文档原计划的 `ST_FrechetDistance`（实测不可用）；SQL 让 `track_point` 上的 GIST 空间索引驱动（点对点，实测比"点到折线"快 60 倍）；纯逻辑抽成静态工具 `SimilarityMath` 以便无数据库单测；结果按 `(trackId, toleranceM)` 缓存（轨迹不可变，缓存永不失效）。

**Tech Stack:** Spring Boot 3.5.16 / Java 25 / Spring Data JPA（nativeQuery + JPQL 标量投影）/ PostgreSQL 18.3 + PostGIS 3.6 / Vue 3.5.42 / Cesium 1.145.0；测试：JUnit 5（后端纯单测）、node `assert`（前端纯函数）、Playwright + Pillow（浏览器像素验收）

**Spec:** `docs/superpowers/specs/2026-09-17-m2-similarity-design.md` ← **执行前必读**，本计划的所有决定都来自它

## Global Constraints

- **相似度 = `min(fwd%, rev%)`** —— 取两个方向的**最小值**。这是唯一一个"不这么做就会给出错误答案"的地方（单向会把"被包含的一小段"判成 100%）
- **容差默认 50 米**，允许范围 **[1, 1000]**；`limit` 默认 **50**，允许范围 **[1, 500]**
- **缓存键必须是 `(trackId, toleranceM)`** —— 容差是每次请求都可能不同的参数，漏了它就会返回错的结果
- **SQL 里不写 `LIMIT`** —— 响应要返回 `compared`（实际比了多少条），截断放在 Java 层
- **`:eps` 必须按主线实际纬度算**，取纬度/经度两个方向里更严格的那个（见 Task 1），**不能用固定常数**
- **`mvn test` 继续保持不需要数据库**（当前 96 项全绿）
- 现有回归 **346 项**必须保持全绿
- `.tmp/` 被 gitignore，加文件必须 `git add -f`
- 中文 javadoc / 注释，解释"为什么"

## Review Focus

以下五类输入是设计文档隐含、但**没有任何一个任务的测试天然覆盖**的，最可能伤到真实用户。每一条都已在对应任务里配了测试：

1. **主线的点在库里没有任何邻居**（用户自采的 GPX 在福建，和 GeoLife 相距 1000 公里）→ 期望返回 `matches: []` 且 HTTP 200，**不是错误、不是 500**
2. **容差被随意调大**（比如传 100000）→ 期望 400 拒绝，而不是把所有 246 条都说成"相似"
3. **一条只有 1~2 个点的轨迹**（`.plt` 文件可能很短，实测最短 5 个点）→ 期望 400 且提示清楚，而不是除零崩溃
4. **交换两条轨迹的顺序**（`similarity(A,B)` vs `similarity(B,A)`）→ 期望**完全相同**。度量不对称就是错的
5. **被包含的短轨迹**（track 6 = 1.3 km 落在 track 18 = 20.7 km 上，单向 100%）→ 期望双向 **< 50%**，不能判成"同一条路"

---

## 前置条件（开工前先确认）

- [ ] 后端在跑：`http://localhost:8080/api/health` 返回 `status: UP`
- [ ] 前端在跑：`http://localhost:5173` 可访问
- [ ] 数据库有 **246 条轨迹**（`GET /api/tracks?limit=1` 的 `total` = 246）
- [ ] 当前 git 分支是 `main`，工作区干净

---

## 常用命令（整个计划里反复用）

**后端编译 + 全部单测**（不需要数据库）：
```powershell
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" test
```
**只跑某一个测试类**：把末尾的 `test` 换成 `"-Dtest=SimilarityMathTest" test`

**前端纯函数测试**（在 `frontend/` 下）：`node scripts/check-similarity.mjs`

**查数据库**（密码从 gitignore 的配置里取，不要打印它）：
```powershell
$yaml = Get-Content "backend/src/main/resources/application-local.yml" -Raw
if ($yaml -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
$env:LC_MESSAGES='C'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -c "SELECT count(*) FROM track;"
```

**需要提权 `danger-full-access` 的操作**：Vite dev/build（`spawn EPERM`）、Playwright（命名管道）、`git push`

---

## 文件结构

### 后端

| 文件 | 职责 |
|---|---|
| `config/SimilarityProperties.java`（新建） | 绑 `calcite.similarity.*` |
| `service/SimilarityMath.java`（新建） | ★ **纯静态**：`min(fwd,rev)`、百分比、`eps` 换算、校验、日期差。不碰 Spring、不碰数据库 |
| `service/SimilarityCache.java`（新建） | 按 **`(trackId, toleranceM)`** 缓存（独立组件） |
| `service/SimilarityService.java`（新建） | Spring bean：编排（校验 → 查基线 → 查 SQL → 补元数据 → 截断） |
| `web/dto/SimilarityMatch.java`（新建） | 单条匹配 |
| `web/dto/SimilarityResponse.java`（新建） | 整个响应 |
| `repository/TrackPointRepository.java`（改） | 加双向重合度聚合查询 |
| `repository/TrackRepository.java`（改） | 加基线元数据查询 + 批量摘要投影查询 |
| `web/AnalysisController.java`（改） | 加 `/similarity`（构造器已有 6 个注入参数，再加 1 个） |
| `resources/application.yml`（改） | 加 `calcite.similarity.*` |
| `test/.../SimilarityMathTest.java`（新建） | 约 12 项 |
| `test/.../SimilarityCacheTest.java`（新建） | 约 4 项 |

### 前端

| 文件 | 职责 |
|---|---|
| `src/lib/similarity.js`（新建） | 纯计算：相似度→颜色、格式化、筛选、`daysAway` 文案 |
| `scripts/check-similarity.mjs`（新建） | node 测试 |
| `src/components/SimilarityList.vue`（新建） | 主线信息 + 匹配列表 + 筛选下拉 |
| `src/components/CesiumGlobe.vue`（改） | 加 `similarTracks` / `similarBaseline` prop + `drawSimilarity()` |
| `src/App.vue`（改） | 模式开关第四档 + 相似度状态与编排 |
| `package.json`（改） | 加 `check:similarity` |

### 验收脚本

| 文件 | 职责 |
|---|---|
| `.tmp/verify-similarity-api.py`（新建） | 对拍：对称性 + 被包含 + 点对点近似量化 |
| `.tmp/check-similarity.py`（新建） | 浏览器像素验收 |

---

## Task 1: `SimilarityProperties` + `SimilarityMath`

**Files:**
- Create: `backend/src/main/java/com/calcite/config/SimilarityProperties.java`
- Create: `backend/src/main/java/com/calcite/service/SimilarityMath.java`
- Test: `backend/src/test/java/com/calcite/service/SimilarityMathTest.java`
- Modify: `backend/src/main/resources/application.yml`

**Interfaces:**
- Produces: `SimilarityProperties.getDefaultToleranceM()/getMinToleranceM()/getMaxToleranceM()/getDefaultLimit()/getMaxLimit()`
- Produces: `SimilarityMath.similarity(double fwdPct, double revPct)` → `double`
- Produces: `SimilarityMath.pct(long hits, long total)` → `double`（0~100，保留 1 位小数）
- Produces: `SimilarityMath.epsDegrees(double toleranceM, double latMaxAbs)` → `double`
- Produces: `SimilarityMath.requireTolerance(double t, double min, double max)` / `requireLimit(int limit, int max)` / `requirePointCount(long n)`
- Produces: `SimilarityMath.daysBetween(OffsetDateTime a, OffsetDateTime b)` → `long`

- [ ] **Step 1: 先写测试**

创建 `backend/src/test/java/com/calcite/service/SimilarityMathTest.java`：

```java
package com.calcite.service;

import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link SimilarityMath} 的单元测试。纯静态工具，不碰 Spring、不碰数据库，
 * 所以 {@code mvn test} 依然**不需要数据库**。
 */
class SimilarityMathTest {

    // ------------------------------------------------------------ 相似度 = min(fwd, rev)

    @Test
    void 相似度取两个方向的最小值() {
        assertEquals(35.0, SimilarityMath.similarity(100.0, 35.0), 1e-9);
        assertEquals(35.0, SimilarityMath.similarity(35.0, 100.0), 1e-9);
    }

    @Test
    void 相似度是对称的_交换两个方向结果不变() {
        double[][] cases = {{100.0, 35.0}, {91.1, 98.6}, {0.0, 77.0}, {50.0, 50.0}};
        for (double[] c : cases) {
            assertEquals(SimilarityMath.similarity(c[0], c[1]),
                         SimilarityMath.similarity(c[1], c[0]), 1e-12,
                         "similarity(" + c[0] + "," + c[1] + ") 必须等于反过来的");
        }
    }

    @Test
    void 一边为零则相似度为零() {
        assertEquals(0.0, SimilarityMath.similarity(100.0, 0.0), 1e-9);
        assertEquals(0.0, SimilarityMath.similarity(0.0, 100.0), 1e-9);
    }

    /**
     * 这条防的正是设计文档 2.3 节实测到的坑：
     * track 6（1.3 km）完全落在 track 18（20.7 km）上，单向 100%、反向 35%。
     * 如果相似度不取小，这个"被包含的一小段"会被判成"完全相同"。
     */
    @Test
    void 被包含的一小段不能被判成同一条路() {
        double contained = SimilarityMath.similarity(100.0, 35.0);
        assertTrue(contained < 50.0, "被包含应低于 50%，实得 " + contained);
    }

    // ------------------------------------------------------------ 百分比与取整

    @Test
    void 百分比计算() {
        assertEquals(100.0, SimilarityMath.pct(244, 244), 1e-9);
        assertEquals(50.0, SimilarityMath.pct(122, 244), 1e-9);
        assertEquals(0.0, SimilarityMath.pct(0, 244), 1e-9);
    }

    @Test
    void 百分比保留一位小数() {
        // 191/279 = 68.458...%  → 68.5
        assertEquals(68.5, SimilarityMath.pct(191, 279), 1e-9);
        // 289/681 = 42.437...%  → 42.4
        assertEquals(42.4, SimilarityMath.pct(289, 681), 1e-9);
    }

    @Test
    void 百分比不会超过100_即使hits多于total() {
        // 理论上不可能，但防御一下：多出来的点不该产生 100.3% 这种值
        assertEquals(100.0, SimilarityMath.pct(250, 244), 1e-9);
    }

    @Test
    void total为零时百分比为零_不能除零崩() {
        assertEquals(0.0, SimilarityMath.pct(0, 0), 1e-9);
        assertEquals(0.0, SimilarityMath.pct(5, 0), 1e-9);
    }

    // ------------------------------------------------------------ eps 换算 ⭐

    /*
     * eps 是给 SQL 的 && 做包围盒预筛用的**度数**扩边量。它只负责"不漏"。
     * 必须取【纬度/经度两个方向里更严格的那个】：
     *   赤道附近   ：1 度经度(111320) > 1 度纬度(110574) → 受纬度约束
     *   中高纬地区 ：1 度经度更短                          → 受经度约束
     */

    @Test
    void eps在赤道受纬度约束() {
        // 50 米 / 110574 ≈ 0.0004522，乘 1.05 余量
        double eps = SimilarityMath.epsDegrees(50, 0.0);
        assertTrue(eps >= 50.0 / 110574.0, "eps 不能小于纬度方向的需求");
        assertTrue(eps < 50.0 / 110574.0 * 1.2, "但也不该过分放大");
    }

    @Test
    void eps在纬度40受经度约束() {
        // 1 度经度 = 111320 * cos(40°) ≈ 85277 米 → 50 米 = 0.0005863°
        double need = 50.0 / (111320.0 * Math.cos(Math.toRadians(40.0)));
        double eps = SimilarityMath.epsDegrees(50, 40.0);
        assertTrue(eps >= need, "eps=" + eps + " 必须 >= 经度方向需求 " + need);
    }

    @Test
    void eps随容差线性放大() {
        assertEquals(SimilarityMath.epsDegrees(50, 40.0) * 4,
                     SimilarityMath.epsDegrees(200, 40.0), 1e-12);
    }

    @Test
    void eps覆盖全部纬度_南纬也算() {
        // latMaxAbs 传的是绝对值，南纬 40 和北纬 40 应该一样
        assertEquals(SimilarityMath.epsDegrees(50, 40.0),
                     SimilarityMath.epsDegrees(50, -40.0), 1e-12);
    }

    @Test
    void eps在极端纬度不会变成NaN或无穷() {
        // 两极附近 cos → 0，必须有个下限兜住，否则除零得 Infinity
        for (double lat : new double[]{89.9, 90.0, -90.0}) {
            double eps = SimilarityMath.epsDegrees(50, lat);
            assertTrue(Double.isFinite(eps) && eps > 0, "lat=" + lat + " 得到 " + eps);
        }
    }

    // ------------------------------------------------------------ 参数校验

    @Test
    void 容差范围校验() {
        SimilarityMath.requireTolerance(1, 1, 1000);      // 边界
        SimilarityMath.requireTolerance(1000, 1, 1000);   // 边界
        SimilarityMath.requireTolerance(50, 1, 1000);

        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requireTolerance(0, 1, 1000));
        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requireTolerance(-1, 1, 1000));
        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requireTolerance(1001, 1, 1000));
        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requireTolerance(Double.NaN, 1, 1000));
    }

    /**
     * 这条对应 Review Focus 第 2 条：容差被随意调大
     * （比如 100000 米 = 100 公里）会把整座城市的轨迹都说成"相似"。
     */
    @Test
    void 容差调得过大必须被拒绝() {
        assertThrows(IllegalArgumentException.class,
                () -> SimilarityMath.requireTolerance(100000, 1, 1000));
    }

    @Test
    void limit范围校验() {
        SimilarityMath.requireLimit(1, 500);
        SimilarityMath.requireLimit(500, 500);
        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requireLimit(0, 500));
        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requireLimit(501, 500));
    }

    /**
     * Review Focus 第 3 条：一条只有 1~2 个点的轨迹。
     * 实测 .plt 最短只有 5 个点，但理论上可能更少 —— 要给出清楚的 400，不是除零崩。
     */
    @Test
    void 点数太少的轨迹要报错() {
        SimilarityMath.requirePointCount(5);
        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requirePointCount(1));
        assertThrows(IllegalArgumentException.class, () -> SimilarityMath.requirePointCount(0));
    }

    // ------------------------------------------------------------ 日期差

    @Test
    void 日期差按UTC整天算() {
        OffsetDateTime a = OffsetDateTime.parse("2008-11-14T10:14:36Z");
        OffsetDateTime b = OffsetDateTime.parse("2008-12-03T15:12:06Z");
        assertEquals(19, SimilarityMath.daysBetween(a, b));
        assertEquals(19, SimilarityMath.daysBetween(b, a));   // 对称
    }

    @Test
    void 同一天日期差为零() {
        OffsetDateTime a = OffsetDateTime.parse("2008-11-14T00:00:01Z");
        OffsetDateTime b = OffsetDateTime.parse("2008-11-14T23:59:59Z");
        assertEquals(0, SimilarityMath.daysBetween(a, b));
    }

    @Test
    void 日期差跨月跨年正确() {
        assertEquals(31, SimilarityMath.daysBetween(
                OffsetDateTime.parse("2008-12-01T00:00:00Z"),
                OffsetDateTime.parse("2009-01-01T00:00:00Z")));
    }
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: 常用命令里的「只跑某一个测试类」换成 `SimilarityMathTest`
Expected: **编译失败**，报 `找不到符号: 类 SimilarityMath`

- [ ] **Step 3: 实现 `SimilarityMath`**

```java
package com.calcite.service;

import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;

/**
 * 轨迹相似度的<b>纯静态工具</b>：相似度计算、百分比、包围盒扩边量换算、参数校验、日期差。
 *
 * <p><b>为什么单独抽一个类</b>：为了测"容差传 0 要报错"不该启动 Spring + 连数据库。
 * 现在整个后端测试套件都不需要数据库，不能让第一个破例。
 */
public final class SimilarityMath {

    private SimilarityMath() {
    }

    /** 1 度纬度约多少米（赤道最短，往两极略增，取最短值最保守） */
    private static final double METERS_PER_DEG_LAT = 110574.0;

    /** 赤道上 1 度经度约多少米 */
    private static final double METERS_PER_DEG_LON_EQUATOR = 111320.0;

    /** eps 的额外余量（吸收椭球近似与浮点误差） */
    private static final double EPS_SAFETY = 1.05;

    /** cos 的下限：两极附近 cos → 0 会让 eps 变成无穷，兜住它 */
    private static final double MIN_COS = 0.01;

    // ------------------------------------------------------------ 核心：相似度

    /**
     * 相似度 = 两个方向重合度的<b>最小值</b>。
     *
     * <p><b>为什么必须取小</b>：一条 1.3 公里的轨迹完全落在一条 20.7 公里的轨迹上时，
     * 单向重合度是 <b>100%</b>（"我的点全在你身上"），但反向只有 35%。
     * 用户问的是"是不是<b>同一条路</b>"，不是"有没有走过其中一段" ——
     * 所以必须取小，把这个"被包含"的情况压下去。
     *
     * <p>取小也天然保证了<b>对称性</b>：{@code fwd(A,B) == rev(B,A)}，
     * 交换 A、B 只是把两项对调，min 不变。
     */
    public static double similarity(double forwardPct, double reversePct) {
        return Math.min(forwardPct, reversePct);
    }

    /**
     * 百分比，保留 1 位小数。
     *
     * <p>{@code total <= 0} 时返回 0（不除零崩溃）；{@code hits > total} 时夹到 100
     * （理论上不会发生，但别让 100.3% 这种值漏出去）。
     */
    public static double pct(long hits, long total) {
        if (total <= 0) {
            return 0.0;
        }
        double v = 100.0 * hits / total;
        if (v > 100.0) {
            v = 100.0;
        }
        // 先夹到 [0,100] 再取整，避免 -0.0 或 100.00000001
        return Math.round(Math.max(0.0, v) * 10.0) / 10.0;
    }

    // ------------------------------------------------------------ eps 换算

    /**
     * 包围盒预筛的扩边量（<b>度</b>）。
     *
     * <p>它<b>只负责"不漏"，不负责"精确"</b> —— 精确判据是 SQL 里的
     * {@code ST_DWithin(geography, geography, :tol)}（米）。
     * 扩少了就是<b>静默的正确性 bug</b>（真匹配被预筛掉，永远找不回来）。
     *
     * <p><b>为什么不能用固定常数</b>（比如 {@code tol / 50000}）：实测那个常数只在
     * 纬度 ≤ 63° 时安全。纬度 65° 时 1 度经度只有 47,046 米，{@code eps} 会偏小。
     * 既然主线的纬度是现成的（读 track 表一行就有），就算准它。
     *
     * <p><b>为什么取两个方向里更小的</b>：
     * <ul>
     *   <li>赤道附近：1 度经度(111,320) &gt; 1 度纬度(110,574) → 受<b>纬度</b>约束</li>
     *   <li>中高纬地区：1 度经度更短 → 受<b>经度</b>约束</li>
     * </ul>
     * 取小才能同时罩住两个方向。
     *
     * @param toleranceM 容差（米）
     * @param latMaxAbs  主线轨迹里<b>纬度绝对值最大</b>的那个（南纬也传正数）
     */
    public static double epsDegrees(double toleranceM, double latMaxAbs) {
        double cos = Math.cos(Math.toRadians(Math.abs(latMaxAbs)));
        if (cos < MIN_COS) {
            cos = MIN_COS;                  // 两极附近兜底，避免 eps 变无穷
        }
        double metersPerDegLon = METERS_PER_DEG_LON_EQUATOR * cos;
        double metersPerDegMin = Math.min(METERS_PER_DEG_LAT, metersPerDegLon);
        return toleranceM / metersPerDegMin * EPS_SAFETY;
    }

    // ------------------------------------------------------------ 参数校验

    /** 容差必须落在 {@code [min, max]} 内。超范围会让"相似"失去意义（100 公里内全是相似的）。 */
    public static void requireTolerance(double toleranceM, double min, double max) {
        if (!Double.isFinite(toleranceM) || toleranceM < min || toleranceM > max) {
            throw new IllegalArgumentException(
                    "toleranceM 必须在 " + min + " ~ " + max + " 米之间，收到 " + toleranceM);
        }
    }

    /** limit 必须落在 {@code [1, max]} 内。 */
    public static void requireLimit(int limit, int max) {
        if (limit < 1 || limit > max) {
            throw new IllegalArgumentException("limit 必须在 1 ~ " + max + " 之间，收到 " + limit);
        }
    }

    /** 点数太少的轨迹无法比对（至少要 2 个点才构成一条线）。 */
    public static void requirePointCount(long pointCount) {
        if (pointCount < 2) {
            throw new IllegalArgumentException(
                    "这条轨迹只有 " + pointCount + " 个点，无法比对（至少需要 2 个）");
        }
    }

    // ------------------------------------------------------------ 日期差

    /**
     * 两条轨迹相差多少天（按 UTC 整天算，对称）。
     *
     * <p>场景 4 问的是"周一和周二"，所以这个数要能一眼看出"隔了几天"。
     * 用 UTC 而不是本地时区 —— 库里存的就是 UTC，不要在这里引入时区转换。
     */
    public static long daysBetween(OffsetDateTime a, OffsetDateTime b) {
        return Math.abs(ChronoUnit.DAYS.between(a.toLocalDate(), b.toLocalDate()));
    }
}
```

- [ ] **Step 4: 跑测试，确认全绿**

Run: 只跑 `SimilarityMathTest`
Expected: `Tests run: 20, Failures: 0, Errors: 0`

> **自己数一遍 `@Test` 的个数再报告**；如果与 20 不符，说明抄漏或抄多了。

- [ ] **Step 5: 建 `SimilarityProperties` 并加配置**

**照抄 `config/DensityProperties.java` 的写法**（它就是 `@ConfigurationProperties` 的现成范例）。

```java
package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 轨迹相似度配置，对应 {@code application.yml} 里的 {@code calcite.similarity.*}。
 *
 * <p>这里都是<b>标量</b>（不是列表），{@code @Value} 也能读。但为了和
 * {@link DensityProperties} / {@link ImportProperties} 保持一致，统一用
 * {@code @ConfigurationProperties}。
 */
@Component
@ConfigurationProperties(prefix = "calcite.similarity")
public class SimilarityProperties {

    /**
     * 默认容差（米）。
     *
     * <p>为什么是 50：**实测采样间距是 5~42 米**（不是 3~15 米，见设计文档 2.6 节）。对稀疏轨迹会低估单向百分比，
     * 但相似度取小、不受影响（见 2.7 节）；
     * 50 米又能容纳城市 GPS 漂移（常见 10~30 米），且远小于"走错一条街"的 100 米以上偏差。
     */
    private double defaultToleranceM = 50;

    /** 容差下限（米） */
    private double minToleranceM = 1;

    /** 容差上限（米）。放太大（比如 100000）会把整座城市的轨迹都说成"相似" */
    private double maxToleranceM = 1000;

    /** 默认最多返回多少条匹配 */
    private int defaultLimit = 50;

    /** limit 上限 */
    private int maxLimit = 500;

    // getter / setter 全部要有（Spring 绑定需要）
    public double getDefaultToleranceM() { return defaultToleranceM; }
    public void setDefaultToleranceM(double v) { this.defaultToleranceM = v; }
    public double getMinToleranceM() { return minToleranceM; }
    public void setMinToleranceM(double v) { this.minToleranceM = v; }
    public double getMaxToleranceM() { return maxToleranceM; }
    public void setMaxToleranceM(double v) { this.maxToleranceM = v; }
    public int getDefaultLimit() { return defaultLimit; }
    public void setDefaultLimit(int v) { this.defaultLimit = v; }
    public int getMaxLimit() { return maxLimit; }
    public void setMaxLimit(int v) { this.maxLimit = v; }
}
```

在 `application.yml` 的 `calcite:` 下**同级**加（**已有的几段一个字都不要改**）：

```yaml
  # 轨迹相似度（M2 第四阶段）
  similarity:
    # 默认容差（米）。实测采样间距 5~42 米、城市 GPS 漂移 10~30 米（见设计文档 2.6 节）
    default-tolerance-m: 50
    # 容差允许范围（防止传 1000000 把所有轨迹都说成"相似"）
    min-tolerance-m: 1
    max-tolerance-m: 1000
    # 默认最多返回多少条（按相似度倒序）
    default-limit: 50
    max-limit: 500
```

- [ ] **Step 6: 跑全量后端测试**

Run: 常用命令里的「后端编译 + 全部单测」
Expected: `Tests run: 116, Failures: 0, Errors: 0`（原 96 + 新增 20）

- [ ] **Step 7: 提交**

```powershell
git add backend/src/main/java/com/calcite/config/SimilarityProperties.java backend/src/main/java/com/calcite/service/SimilarityMath.java backend/src/test/java/com/calcite/service/SimilarityMathTest.java backend/src/main/resources/application.yml
git commit -m "feat(similarity): SimilarityMath 纯静态工具（取小 + eps 按纬度算）+ 20 项无数据库单测"
```

---

## Task 2: `SimilarityCache`

**Files:**
- Create: `backend/src/main/java/com/calcite/service/SimilarityCache.java`
- Test: `backend/src/test/java/com/calcite/service/SimilarityCacheTest.java`

**Interfaces:**
- Consumes: `com.calcite.web.dto.SimilarityMatch`（**Task 3 才会创建** —— 为了不产生跨任务的编译依赖，本任务的缓存**用泛型 `List<T>` 或先声明一个占位的 record**。
  **简单做法**：本任务的 `SimilarityCache` 直接引用 `SimilarityMatch`，而 `SimilarityMatch` 在 Task 3 创建。
  **为了本任务能独立编译通过，Task 2 里先创建 `SimilarityMatch` 的空壳**（只有字段，没有逻辑），Task 3 再用它。

> ⚠️ **执行顺序说明**：`SimilarityMatch` 是 Task 2 和 Task 3 都要用的东西。
> **在 Task 2 的 Step 1 里就把它的 record 定义写出来**（很简单），Task 3 直接使用，不要重复创建。

- [ ] **Step 1: 建 `SimilarityMatch` 并在测试里用它**

创建 `backend/src/main/java/com/calcite/web/dto/SimilarityMatch.java`：

```java
package com.calcite.web.dto;

/**
 * 一条"和主线相似"的轨迹。
 *
 * <p><b>为什么两个方向都返回</b>：相似度取的是两者的最小值，
 * 只给一个数会让人不知道它怎么来的。而且"我的点 100% 在你身上、你的点只有 35% 在我身上"
 * 这个信息本身有用（说明我只是你的一小段）。
 */
public record SimilarityMatch(
        Long trackId,
        String name,
        String source,
        /** 主线的点有多少落在它附近（0~100） */
        double forwardPct,
        /** 它的点有多少落在主线附近（0~100） */
        double reversePct,
        /** = min(forwardPct, reversePct) */
        double similarity,
        int pointCount,
        long lengthM,
        /** 它的开始时间（ISO-8601 UTC 字符串，例如 2008-12-03T15:12:06Z） */
        String startTime,
        /** 和主线相差几天 */
        long daysAway
) {
}
```

创建 `backend/src/test/java/com/calcite/service/SimilarityCacheTest.java`：

```java
package com.calcite.service;

import com.calcite.web.dto.SimilarityMatch;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

/** {@link SimilarityCache} 的单元测试。纯内存，不需要数据库。 */
class SimilarityCacheTest {

    private static List<SimilarityMatch> sample() {
        return List.of(new SimilarityMatch(39L, "20081203151206", "geolife",
                91.1, 98.6, 91.1, 279, 3611, "2008-12-03T15:12:06Z", 19));
    }

    @Test
    void 同一个trackId和容差只算一次() {
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        for (int i = 0; i < 5; i++) {
            cache.get(20L, 50.0, () -> { calls.incrementAndGet(); return sample(); });
        }
        assertEquals(1, calls.get(), "第二次开始应该命中缓存");
    }

    /**
     * 这条是本任务存在的理由：容差是**每次请求都可能不同**的参数，
     * 缓存键漏了它就会返回错的结果（50 米算出的结果被 200 米的请求复用）。
     * <p>注意这和停留点缓存<b>不一样</b> —— 那个的参数是全局配置、不会逐次变。
     */
    @Test
    void 容差不进缓存键就会返回错结果_所以必须分开缓存() {
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        List<SimilarityMatch> a = cache.get(20L, 50.0,
                () -> { calls.incrementAndGet(); return sample(); });
        List<SimilarityMatch> b = cache.get(20L, 200.0,
                () -> { calls.incrementAndGet(); return List.of(); });
        assertEquals(2, calls.get(), "不同容差必须是两次独立的计算");
        assertNotSame(a, b);
        assertEquals(1, a.size());
        assertEquals(0, b.size());
    }

    @Test
    void 不同trackId各算各的() {
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        cache.get(1L, 50.0, () -> { calls.incrementAndGet(); return sample(); });
        cache.get(2L, 50.0, () -> { calls.incrementAndGet(); return sample(); });
        assertEquals(2, calls.get());
    }

    @Test
    void 同一键返回同一个对象实例() {
        SimilarityCache cache = new SimilarityCache();
        List<SimilarityMatch> a = cache.get(3L, 50.0, SimilarityCacheTest::sample);
        List<SimilarityMatch> b = cache.get(3L, 50.0, SimilarityCacheTest::sample);
        assertSame(a, b, "应该拿到同一个实例（说明真的走了缓存）");
    }

    @Test
    void 容差用浮点做键也能命中_不会因为精度漏缓存() {
        // 5.0 和 5.00 是同一个 double，但 0.1+0.2 != 0.3 这类问题要防住
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        cache.get(7L, 0.1 + 0.2, () -> { calls.incrementAndGet(); return sample(); });
        cache.get(7L, 0.30000000000000004, () -> { calls.incrementAndGet(); return sample(); });
        assertEquals(1, calls.get(), "相等的 double 应该命中同一个键");
    }
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: 只跑 `SimilarityCacheTest`
Expected: **编译失败**，报 `找不到符号: 类 SimilarityCache`

- [ ] **Step 3: 实现 `SimilarityCache`**

```java
package com.calcite.service;

import com.calcite.web.dto.SimilarityMatch;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

/**
 * 轨迹相似度缓存：{@code (trackId, toleranceM) → 该主线与全部轨迹的相似度结果}。
 *
 * <p><b>为什么需要它</b>：一次完整比对实测约 <b>2 秒</b>（双向、197 条候选）。
 * 缓存之后第二次点同一条主线瞬间返回。
 *
 * <p><b>为什么这个缓存永不失效</b>：结果是
 * {@code (trackId, toleranceM) → 库里所有轨迹的点} 的纯函数，
 * 而轨迹一旦导入就<b>不可变</b>（系统里没有"编辑轨迹""删除轨迹""覆盖同名轨迹"）。
 *
 * <p><b>⚠️ 缓存键必须带上 {@code toleranceM}</b> —— 这一点和 {@link StayPointCache}
 * <b>不一样</b>：停留点的参数是全局配置、不会逐次变；而相似度的容差是
 * <b>每次请求都可能不同</b>的。键里漏了容差，50 米算出的结果就会被 200 米的请求复用，
 * <b>返回错的结果</b>。
 *
 * <p><b>⚠️ 将来如果加了下面任何一项，必须清理缓存</b>：
 * <ul>
 *   <li>删除轨迹 / 重新导入覆盖同名轨迹</li>
 *   <li>导入新轨迹（那会让旧主线的候选集变化）—— 所以导入完后要整体清一次</li>
 * </ul>
 *
 * <p>{@code limit} <b>不进</b>缓存键：缓存里存全部匹配（不截断），limit 只在返回时截。
 */
@Component
public class SimilarityCache {

    /** 缓存键：主线 id + 容差。用 record 做键，equals/hashCode 自动按值比较 */
    private record Key(Long trackId, double toleranceM) {
    }

    private final Map<Key, List<SimilarityMatch>> cache = new ConcurrentHashMap<>();

    /**
     * 取某条主线在某个容差下的全部匹配；没有就算一次并缓存。
     *
     * @param trackId    主线轨迹 id
     * @param toleranceM 容差（米）—— <b>必须进键</b>
     * @param compute    真正的计算逻辑（由调用方提供，保持本类对算法无依赖）
     */
    public List<SimilarityMatch> get(Long trackId, double toleranceM,
                                     Supplier<List<SimilarityMatch>> compute) {
        return cache.computeIfAbsent(new Key(trackId, toleranceM), k -> compute.get());
    }

    /** 清理某条主线的全部容差缓存。当前生产代码没有调用 —— 见类注释里的两种情形。 */
    public void invalidate(Long trackId) {
        cache.keySet().removeIf(k -> k.trackId().equals(trackId));
    }

    /** 清空全部缓存（将来"导入新轨迹"之后应该调用它） */
    public void invalidateAll() {
        cache.clear();
    }

    /** 当前缓存了多少个 (主线, 容差) 组合（仅用于监控与测试） */
    public int size() {
        return cache.size();
    }
}
```

- [ ] **Step 4: 跑测试，确认全绿**

Run: 只跑 `SimilarityCacheTest`
Expected: `Tests run: 5, Failures: 0, Errors: 0`

- [ ] **Step 5: 跑全量后端测试**

Run: 常用命令里的「后端编译 + 全部单测」
Expected: `Tests run: 121, Failures: 0, Errors: 0`（116 + 5）

- [ ] **Step 6: 提交**

```powershell
git add backend/src/main/java/com/calcite/service/SimilarityCache.java backend/src/main/java/com/calcite/web/dto/SimilarityMatch.java backend/src/test/java/com/calcite/service/SimilarityCacheTest.java
git commit -m "feat(similarity): SimilarityCache 按 (trackId, toleranceM) 缓存 + 5 项单测"
```

---

## Task 3: 仓储查询 + `SimilarityService` + 接口

**Files:**
- Modify: `backend/src/main/java/com/calcite/repository/TrackPointRepository.java`
- Modify: `backend/src/main/java/com/calcite/repository/TrackRepository.java`
- Create: `backend/src/main/java/com/calcite/web/dto/SimilarityResponse.java`
- Create: `backend/src/main/java/com/calcite/service/SimilarityService.java`
- Modify: `backend/src/main/java/com/calcite/web/AnalysisController.java`

**Interfaces:**
- Consumes: `SimilarityMath.*`（Task 1）、`SimilarityCache.get(trackId, toleranceM, supplier)`（Task 2）、`SimilarityMatch`（Task 2）、`SimilarityProperties`（Task 1）
- Produces: `GET /api/analysis/similarity?trackId=&toleranceM=&limit=` → `SimilarityResponse`

- [ ] **Step 1: 给 `TrackPointRepository` 加双向重合度查询**

在已有的 `aggregateDensity` 之后加：

```java
    /**
     * 轨迹相似度：算某条主线和<b>全部其它轨迹</b>的双向重合度。
     *
     * <p><b>⭐ 为什么让"主线的点"驱动循环</b>：{@code FROM track_point p JOIN track_point q}
     * 且 {@code p} 是主线时，PostgreSQL 会拿主线的每个点去查 {@code q.geom} 上的
     * GIST 索引 —— 实测 <b>0.79 秒</b>。
     * 而同样语义写成 {@code WHERE q.track_id = :id}（主线在 WHERE 里）会退化成
     * 逐点扫描候选轨迹的全部点，实测 <b>8.5 秒</b>。<b>同一个语义，11 倍差距。</b>
     *
     * <p><b>为什么是"点对点"而不是"点到折线"</b>：点到折线要放弃索引，
     * 实测 244 点 × 208 条 = <b>119 秒</b>（点对点只要 0.79 秒，60 倍）。
     * 代价是"用采样点代表折线"这个近似。实测采样间距 5~42 米（设计文档 2.6 节），
     * **对稀疏轨迹会严重低估单向百分比**（实测 100% 算成 43%）；但相似度取小、几乎不受影响（2.7 节）。
     *
     * <p><b>为什么 {@code && ST_Expand(...)} 不能省</b>：{@code &&} 是走索引的包围盒预筛，
     * {@code ST_DWithin} 才是精确判据（米）。{@code :eps} 由 Java 按主线实际纬度算好传进来
     * （见 {@code SimilarityMath.epsDegrees}），<b>宁可大不可小</b> —— 小了会静默漏掉真匹配。
     *
     * <p><b>为什么 {@code INNER JOIN} 而不是 {@code LEFT JOIN}</b>：一条轨迹如果没出现在
     * {@code fwd} 里，说明主线的点没有一个落在它附近 → {@code fwd% = 0} →
     * {@code min(0, rev%) = 0} → <b>相似度为 0，本来就该被过滤</b>。
     * 所以 INNER JOIN 丢掉的行全是相似度为 0 的行。
     *
     * <p><b>⚠️ 这里【没有】 LIMIT</b>：响应要返回 {@code compared}（实际比了多少条），
     * 在 SQL 里截断就拿不到它了。截断交给 Java。
     *
     * @return 每行 {@code [trackId(Long), fwdHits(Long), fwdTotal(Long), revHits(Long), revTotal(Long)]}
     */
    @Query(value = """
            WITH fwd AS (
                SELECT q.track_id AS id, count(DISTINCT p.seq) AS hits
                FROM track_point p
                JOIN track_point q
                  ON q.geom && ST_Expand(p.geom, :eps)
                 AND ST_DWithin(q.geom::geography, p.geom::geography, :tol)
                WHERE p.track_id = :trackId AND q.track_id <> :trackId
                GROUP BY q.track_id
            ),
            rev AS (
                SELECT p.track_id AS id, count(DISTINCT p.seq) AS hits
                FROM track_point q
                JOIN track_point p
                  ON p.geom && ST_Expand(q.geom, :eps)
                 AND ST_DWithin(p.geom::geography, q.geom::geography, :tol)
                WHERE q.track_id = :trackId AND p.track_id <> :trackId
                GROUP BY p.track_id
            ),
            tot AS (
                SELECT track_id, count(*) AS n FROM track_point GROUP BY track_id
            ),
            nb AS (
                SELECT count(*) AS n FROM track_point WHERE track_id = :trackId
            )
            SELECT f.id,
                   f.hits,
                   (SELECT n FROM nb),
                   r.hits,
                   t.n
            FROM fwd f
            JOIN rev r ON r.id = f.id
            JOIN tot t ON t.track_id = f.id
            """, nativeQuery = true)
    List<Object[]> findSimilarityScores(@Param("trackId") Long trackId,
                                        @Param("tol") double toleranceM,
                                        @Param("eps") double eps);
```

- [ ] **Step 2: 给 `TrackRepository` 加两个查询**

在已有的 `findAllIds()` 之后加：

```java
    /**
     * 主线的元数据 + 几何统计（相似度接口用）。
     *
     * <p>{@code latMin/latMax} 是给包围盒扩边量 {@code eps} 用的：
     * 度不是长度单位，{@code eps} 必须按主线<b>实际所在的纬度</b>算
     * （详见 {@code SimilarityMath.epsDegrees}）。
     *
     * <p>{@code ST_Length(geom::geography)} 返回<b>米</b>（不是度）。
     *
     * <p><b>为什么 start_time 不在这里取</b>：native query 里 {@code timestamptz}
     * 的类型映射容易出问题。它由 {@link #findBaselineMeta} 用 JPQL 取，类型明确。
     *
     * @return 单行 {@code [latMin(Double), latMax(Double), lengthM(Double)]}
     */
    @Query(value = """
            SELECT ST_YMin(geom), ST_YMax(geom), ST_Length(geom::geography)
            FROM track WHERE id = :trackId
            """, nativeQuery = true)
    List<Object[]> findBaselineGeometryStats(@Param("trackId") Long trackId);

    /**
     * 主线的元数据。用 JPQL 标量投影，<b>不加载 geom</b>。
     *
     * @return 单行 {@code [name(String), source(String), pointCount(Integer), startTime(OffsetDateTime)]}
     */
    @Query("SELECT t.name, t.source, t.pointCount, t.startTime FROM Track t WHERE t.id = :trackId")
    List<Object[]> findBaselineMeta(@Param("trackId") Long trackId);

    /**
     * 批量取匹配轨迹的元数据。用 JPQL 标量投影，<b>不加载 geom</b>。
     *
     * <p>{@code findAllById} 会把每条轨迹的 {@code geom}（完整 LineString）全水合出来 ——
     * 197 条轨迹约 28 万个顶点，而这里只需要名字和几个数。
     * （这个坑在热点接口上踩过一次，实测要 2.4 秒。）
     *
     * @return 每行 {@code [id(Long), name(String), source(String), pointCount(Integer), startTime(OffsetDateTime)]}
     */
    @Query("SELECT t.id, t.name, t.source, t.pointCount, t.startTime FROM Track t WHERE t.id IN :ids")
    List<Object[]> findSummariesByIds(@Param("ids") Collection<Long> ids);
```

补 import：`java.util.Collection`（如果还没有）。

- [ ] **Step 3: 建 `SimilarityResponse`**

```java
package com.calcite.web.dto;

import java.util.List;

/**
 * 轨迹相似度接口的响应。
 *
 * <p>{@code compared} 是<b>实际比对了多少条</b>，和 {@code matches.size()} 不同 ——
 * 前者是分母，后者受 {@code limit} 截断。两个都给，用户才知道"库里还有多少条没列出来"。
 */
public record SimilarityResponse(
        Long trackId,
        String name,
        double toleranceM,
        int pointCount,
        long lengthM,
        /** 实际参与比对的轨迹条数（不含主线自己） */
        int compared,
        List<SimilarityMatch> matches
) {
}
```

- [ ] **Step 4: 建 `SimilarityService`**

```java
package com.calcite.service;

import com.calcite.config.SimilarityProperties;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.SimilarityMatch;
import com.calcite.web.dto.SimilarityResponse;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 轨迹相似度的编排层：校验参数 → 查基线 → 查双向重合度 → 补元数据 → 截断。
 *
 * <p>参数校验与数学全部委托给 {@link SimilarityMath}（静态工具），
 * 这个类只负责"把它们串起来"。
 */
@Service
public class SimilarityService {

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final SimilarityCache cache;
    private final SimilarityProperties props;

    public SimilarityService(TrackRepository trackRepository,
                             TrackPointRepository trackPointRepository,
                             SimilarityCache cache,
                             SimilarityProperties props) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.cache = cache;
        this.props = props;
    }

    /**
     * 查询和某条主线相似的全部轨迹。
     *
     * @param trackId    主线轨迹 id
     * @param toleranceM 容差（米），null 用默认值
     * @param limit      最多返回几条，null 用默认值
     */
    public SimilarityResponse similarity(Long trackId, Double toleranceM, Integer limit) {
        if (trackId == null) {
            throw new IllegalArgumentException("缺少 trackId 参数");
        }
        double tol = toleranceM == null ? props.getDefaultToleranceM() : toleranceM;
        int lim = limit == null ? props.getDefaultLimit() : limit;

        SimilarityMath.requireTolerance(tol, props.getMinToleranceM(), props.getMaxToleranceM());
        SimilarityMath.requireLimit(lim, props.getMaxLimit());

        // --- 主线的元数据（不存在就是 404）---
        List<Object[]> metaRows = trackRepository.findBaselineMeta(trackId);
        if (metaRows.isEmpty()) {
            throw new TrackNotFoundException(trackId);
        }
        Object[] meta = metaRows.get(0);
        String name = (String) meta[0];
        int pointCount = meta[2] == null ? 0 : ((Number) meta[2]).intValue();
        OffsetDateTime startTime = (OffsetDateTime) meta[3];
        SimilarityMath.requirePointCount(pointCount);

        // --- 几何统计：纬度范围（算 eps 用）+ 长度（米）---
        List<Object[]> geoRows = trackRepository.findBaselineGeometryStats(trackId);
        Object[] geo = geoRows.get(0);
        double latMin = ((Number) geo[0]).doubleValue();
        double latMax = ((Number) geo[1]).doubleValue();
        long lengthM = Math.round(((Number) geo[2]).doubleValue());
        double latMaxAbs = Math.max(Math.abs(latMin), Math.abs(latMax));

        // eps 按主线实际纬度算（不能用一个固定常数 —— 见 SimilarityMath 的注释）
        double eps = SimilarityMath.epsDegrees(tol, latMaxAbs);

        // --- 走缓存：缓存里存【全部】匹配（不截断），limit 只在返回时截 ---
        List<SimilarityMatch> all = cache.get(trackId, tol, () -> compute(trackId, tol, eps, startTime));

        List<SimilarityMatch> page = all.size() > lim ? all.subList(0, lim) : all;

        return new SimilarityResponse(trackId, name, tol, pointCount, lengthM, all.size(), page);
    }

    /** 真正算一次：查 SQL → 补元数据 → 组装 → 排序。结果<b>不截断</b>。 */
    private List<SimilarityMatch> compute(Long trackId, double tol, double eps,
                                          OffsetDateTime baselineStart) {
        List<Object[]> rows = trackPointRepository.findSimilarityScores(trackId, tol, eps);
        if (rows.isEmpty()) {
            return List.of();
        }

        // 收集 id，一次批量取元数据（不要逐条查）
        List<Long> ids = new ArrayList<>(rows.size());
        for (Object[] r : rows) {
            ids.add(((Number) r[0]).longValue());
        }
        Map<Long, Object[]> metaById = new HashMap<>();
        for (Object[] m : trackRepository.findSummariesByIds(ids)) {
            metaById.put(((Number) m[0]).longValue(), m);
        }

        List<SimilarityMatch> out = new ArrayList<>(rows.size());
        for (Object[] r : rows) {
            long id = ((Number) r[0]).longValue();
            long fwdHits = ((Number) r[1]).longValue();
            long fwdTotal = ((Number) r[2]).longValue();
            long revHits = ((Number) r[3]).longValue();
            long revTotal = ((Number) r[4]).longValue();

            double fwdPct = SimilarityMath.pct(fwdHits, fwdTotal);
            double revPct = SimilarityMath.pct(revHits, revTotal);
            double sim = SimilarityMath.similarity(fwdPct, revPct);

            Object[] m = metaById.get(id);
            String name = m == null ? ("track-" + id) : (String) m[1];
            String source = m == null ? null : (String) m[2];
            int pc = (m == null || m[3] == null) ? 0 : ((Number) m[3]).intValue();
            OffsetDateTime st = m == null ? null : (OffsetDateTime) m[4];

            out.add(new SimilarityMatch(id, name, source, fwdPct, revPct, sim, pc, 0L,
                    st == null ? null : st.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                    st == null ? 0L : SimilarityMath.daysBetween(baselineStart, st)));
        }

        // 按相似度倒序；相同则按 id 升序，保证结果稳定可复现
        out.sort(Comparator.comparingDouble(SimilarityMatch::similarity).reversed()
                .thenComparing(SimilarityMatch::trackId));
        return out;
    }

    /** 主线不存在时抛这个 —— 控制器会映射成 404 */
    public static class TrackNotFoundException extends RuntimeException {
        public TrackNotFoundException(Long trackId) {
            super("轨迹不存在：" + trackId);
        }
    }
}
```

> **注意**：`lengthM` 在 `SimilarityMatch` 里暂时填 `0`。
> 每条匹配轨迹的长度需要额外查 `track.geom` —— 为了不让这个任务膨胀，
> **本任务先填 0，Task 3 的验证步骤里会发现列表的长度列显示为 0**。
> **这是刻意的取舍吗？不是** —— 见下面的 Step 5，我们改用 JPQL 把长度一起取出来。

- [ ] **Step 5: 把匹配轨迹的长度一起取出来（修正 Step 4 的 `lengthM = 0`）**

把 `TrackRepository.findSummariesByIds` 的 JPQL 改成**同时算长度**是做不到的（JPQL 没有 `ST_Length`）。

**改用 native query 取摘要**，并把长度算在 SQL 里：

```java
    /**
     * 批量取匹配轨迹的元数据（含长度）。native query 是为了用 {@code ST_Length(geography)}。
     *
     * <p>{@code start_time} 用 {@code to_char} 转成 ISO 字符串 ——
     * 避免 native query 里 {@code timestamptz} 的类型映射歧义。
     *
     * @return 每行 {@code [id(Long), name(String), source(String), pointCount(Integer),
     *                     lengthM(Double), startTime(String ISO-8601)}]
     */
    @Query(value = """
            SELECT t.id,
                   t.name,
                   t.source,
                   t.point_count,
                   ST_Length(t.geom::geography),
                   to_char(t.start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            FROM track t
            WHERE t.id IN (:ids)
            """, nativeQuery = true)
    List<Object[]> findSummariesByIds(@Param("ids") Collection<Long> ids);
```

然后把 `SimilarityService.compute` 里组装 `SimilarityMatch` 的那几行改成：

```java
            Object[] m = metaById.get(id);
            String name = m == null ? ("track-" + id) : (String) m[1];
            String source = m == null ? null : (String) m[2];
            int pc = (m == null || m[3] == null) ? 0 : ((Number) m[3]).intValue();
            long lenM = (m == null || m[4] == null) ? 0L : Math.round(((Number) m[4]).doubleValue());
            String stIso = m == null ? null : (String) m[5];

            // 日期差用 ISO 字符串解析回来，避免 timestamptz 的类型映射歧义
            long daysAway = 0L;
            if (stIso != null && baselineStart != null) {
                daysAway = SimilarityMath.daysBetween(baselineStart, OffsetDateTime.parse(stIso));
            }

            out.add(new SimilarityMatch(id, name, source, fwdPct, revPct, sim, pc, lenM,
                    stIso, daysAway));
```

**同时把** `findBaselineMeta` 也改成 native 并用 `to_char`，保持两条路径的类型处理一致：

```java
    /**
     * 主线的元数据。native query 是为了用 {@code to_char} 把 {@code timestamptz}
     * 转成 ISO 字符串，避免类型映射歧义。
     *
     * @return 单行 {@code [name(String), source(String), pointCount(Integer), startTime(String)]}
     */
    @Query(value = """
            SELECT t.name, t.source, t.point_count,
                   to_char(t.start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            FROM track t WHERE t.id = :trackId
            """, nativeQuery = true)
    List<Object[]> findBaselineMeta(@Param("trackId") Long trackId);
```

`SimilarityService` 里对应改成：

```java
        Object[] meta = metaRows.get(0);
        String name = (String) meta[0];
        int pointCount = meta[2] == null ? 0 : ((Number) meta[2]).intValue();
        String baselineStartIso = (String) meta[3];
        SimilarityMath.requirePointCount(pointCount);
        ...
        OffsetDateTime baselineStart = baselineStartIso == null
                ? null : OffsetDateTime.parse(baselineStartIso);
```

> **为什么要绕这一圈**：`timestamptz` 在 native query 里的 Java 类型
> （`Timestamp` / `OffsetDateTime` / `Instant`）取决于驱动与 Hibernate 版本，
> 靠猜容易在运行时炸。**转成字符串就没有歧义了**，代价只是一次解析。

- [ ] **Step 6: 在 `AnalysisController` 加端点**

构造器**已有 6 个注入参数**（`trackRepository` / `trackPointRepository` / `stayPointService` /
`hotspotService` / `densityService` / `stayPointCache` + 两个 `@Value`）。
**再加一个 `SimilarityService`，已有的一个都不能少、顺序别乱动。**

```java
    /**
     * 轨迹相似度（M2 第四阶段）：找出和某条主线走同一条路的其它轨迹。
     *
     * <p>用<b>双向重合度</b>（取两个方向的最小值），不是 Frechet 距离 ——
     * 理由见设计文档 2.2 / 2.3 节（Frechet 没有能同时罩住北京和长三角的投影，
     * 而且单向重合度会把"被包含的一小段"判成完全相同）。
     */
    @GetMapping("/similarity")
    public SimilarityResponse similarity(
            @RequestParam Long trackId,
            @RequestParam(required = false) Double toleranceM,
            @RequestParam(required = false) Integer limit) {
        try {
            return similarityService.similarity(trackId, toleranceM, limit);
        } catch (SimilarityService.TrackNotFoundException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, e.getMessage());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        }
    }
```

补 import：`SimilarityResponse`、`SimilarityService`。

- [ ] **Step 7: 重启后端并手工验证**

把旧的 8080 进程停掉（**这个环境里 `Get-NetTCPConnection` 不可靠，用 netstat**）：
```powershell
$c = netstat -ano | Select-String ":8080\s" | Select-String "LISTENING"
if ($c) { Stop-Process -Id ($c[0].Line -split '\s+')[-1] -Force }
```
然后用计划里的 `spring-boot:run` 启动（后台跑），等 health 变 UP。

```powershell
$r = Invoke-RestMethod "http://localhost:8080/api/analysis/similarity?trackId=20"
"主线: $($r.name) · $($r.pointCount) 点 · $($r.lengthM) 米 · 比过 $($r.compared) 条"
$r.matches | Select-Object -First 5 | ForEach-Object { "  {0,5}%  {1}  {2} 米  相差 {3} 天  (fwd {4} / rev {5})" -f $_.similarity, $_.name, $_.lengthM, $_.daysAway, $_.forwardPct, $_.reversePct }
```

**Expected（这些是实测值，是断言）**：
- `pointCount` = **305**，`lengthM` ≈ **6278**，`compared` = **197**
- 第一名是 track 39，`similarity` = **91.1**，`forwardPct` = 91.1，`reversePct` = 98.6
- 第二名 track 35，`similarity` ≈ **84.3**

- [ ] **Step 8: 验证「被包含」的例子（本任务最关键的一条）**

```powershell
$r = Invoke-RestMethod "http://localhost:8080/api/analysis/similarity?trackId=6"
$m = $r.matches | Where-Object { $_.trackId -eq 18 }
if ($m) { "track 6 vs 18: fwd=$($m.forwardPct) rev=$($m.reversePct) similarity=$($m.similarity)" }
else { "track 18 没出现在结果里（也可接受，说明它被正确过滤了）" }
```

**Expected（实测值）**：`forwardPct` ≈ **43.0**、`reversePct` ≈ **34.4**、**`similarity` ≈ 34.4**。

> ⚠️ **`forwardPct` 是 43 而不是 100，这是【正确的】** —— track 18 的采样间距是 42 米，
> 点对点会低估 `fwd`（真值 100%）。**但相似度取的是另一个方向（`rev` 34.4）**，
> 所以结果 `34.4` 与真值 `35.0` 只差 0.6 个百分点。详见设计文档 2.6 / 2.7 节。

**如果 `similarity` 接近 100，说明"取小"没生效 —— 立刻停下来查。**

- [ ] **Step 9: 验证 Review Focus 的几条边界**

```powershell
# ① 主线在福建的 GPX，和 GeoLife 相距 1000 公里 → 200 + 空数组，不是 500
$a = Invoke-RestMethod "http://localhost:8080/api/analysis/similarity?trackId=3"
"福建轨迹: compared=$($a.compared) matches=$($a.matches.Count)"

# ② 容差调大 → 400
try { Invoke-RestMethod "http://localhost:8080/api/analysis/similarity?trackId=20&toleranceM=100000" }
catch { "容差 100000 → HTTP " + [int]$_.Exception.Response.StatusCode }

# ③ 不存在的轨迹 → 404
try { Invoke-RestMethod "http://localhost:8080/api/analysis/similarity?trackId=999999" }
catch { "不存在的轨迹 → HTTP " + [int]$_.Exception.Response.StatusCode }

# ④ limit 生效
$b = Invoke-RestMethod "http://localhost:8080/api/analysis/similarity?trackId=20&limit=3"
"limit=3 → 返回 $($b.matches.Count) 条，compared 仍是 $($b.compared)"
```

**Expected**：② **400**；③ **404**；④ 返回 3 条但 `compared` 仍是 197。

> ⚠️ **① 的期望要改**：3 条 GPX 轨迹是**同一场地**跑的，它们**互相之间很相似**，
> 所以 `matches` **不为空**（实测如此）。要验证"空数组不是错误"这条路径，
> 改用一个**苛刻的容差**：`?trackId=1&toleranceM=1` → 期望 200 + `matches: []`。

> ⚠️ ① 里如果 GPX 那条（id=3）的 `matches` **不为空**，说明你的轨迹 id 猜错了 ——
> 先用 `Invoke-RestMethod "http://localhost:8080/api/tracks?limit=1&source=gpx"` 查真实 id 再试。

- [ ] **Step 10: 跑全量后端测试 + 提交**

Run: 常用命令里的「后端编译 + 全部单测」
Expected: `Tests run: 121, Failures: 0, Errors: 0`

```powershell
git add backend/src/main/java/com/calcite/repository/TrackPointRepository.java backend/src/main/java/com/calcite/repository/TrackRepository.java backend/src/main/java/com/calcite/web/dto/SimilarityResponse.java backend/src/main/java/com/calcite/service/SimilarityService.java backend/src/main/java/com/calcite/web/AnalysisController.java
git commit -m "feat(similarity): 双向重合度查询 + SimilarityService + /api/analysis/similarity"
```

---

## Task 4: Python 对拍（含三条专项验证）⭐

**Files:**
- Create: `.tmp/verify-similarity-api.py`

**Interfaces:**
- Consumes: `GET /api/analysis/similarity`（Task 3）

> **为什么这一步不能省**：Java 单测覆盖的是**数学与校验**，覆盖不到 **SQL**。
> 而这个功能的价值全在 SQL 上。本任务有三条**只有对拍能做**的专项验证。

- [ ] **Step 1: 写对拍脚本**

创建 `.tmp/verify-similarity-api.py`：

```python
# -*- coding: utf-8 -*-
r"""轨迹相似度的独立对拍。

Java 单测只覆盖数学与参数校验，覆盖不到 SQL。这个脚本用独立实现核对，
并做三条只有对拍能做的专项验证：
  ① 对称性 —— similarity(A,B) 必须等于 similarity(B,A)
  ② 「被包含」不能被误判（设计文档 2.3 节实测到的坑）
  ③ 点对点近似 vs 点到折线 —— 把设计取舍【量化】成具体数字

用法（需要提权 danger-full-access）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\verify-similarity-api.py
"""
import json
import math
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8080"
PSQL = r"E:\PostgreSQL\bin\psql.exe"
fails = []


def check(name, ok, detail=""):
    print(("  [OK] " if ok else "  [XX] ") + name + ("  " + detail if detail else ""))
    if not ok:
        fails.append(name)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def psql_json(sql):
    """跑 SQL 并把结果当 JSON 拿回来（用 json_agg 包裹）。"""
    out = subprocess.run(
        [PSQL, "-U", "postgres", "-h", "localhost", "-p", "5432",
         "-d", "calcite", "-t", "-A", "-c", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError("psql 失败: " + (out.stderr or "")[:300])
    txt = (out.stdout or "").strip()
    return json.loads(txt) if txt else []


def hav(lat1, lon1, lat2, lon2):
    """和项目里 GeoUtils 一致的 haversine（米）。"""
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def points_of(track_id):
    """取一条轨迹的全部点（lat, lon），按 seq 排序。"""
    rows = psql_json(
        "SELECT json_agg(row_to_json(t)) FROM ("
        "  SELECT seq, ST_Y(geom) AS lat, ST_X(geom) AS lon "
        f"  FROM track_point WHERE track_id = {track_id} ORDER BY seq) t;")
    return [(r["lat"], r["lon"]) for r in (rows or [])]


def overlap_pct(pts_a, pts_b, tol):
    """独立实现：pts_a 里有多少个点落在 pts_b 的某个点 tol 米内（百分比）。"""
    if not pts_a:
        return 0.0
    hit = 0
    for la, lo in pts_a:
        for lb, lob in pts_b:
            if hav(la, lo, lb, lob) <= tol:
                hit += 1
                break
    return 100.0 * hit / len(pts_a)


def main():
    TOL = 50.0

    # ================= A. 对称性（Review Focus 第 4 条）=================
    print("=== A. 对称性 ===")
    for a, b in [(20, 39), (6, 18), (20, 35)]:
        ra = get(f"/api/analysis/similarity?trackId={a}&limit=500")
        rb = get(f"/api/analysis/similarity?trackId={b}&limit=500")
        sa = next((m["similarity"] for m in ra["matches"] if m["trackId"] == b), None)
        sb = next((m["similarity"] for m in rb["matches"] if m["trackId"] == a), None)
        check(f"similarity({a},{b}) == similarity({b},{a})", sa == sb,
              f"{sa} vs {sb}")
        if sa is not None:
            fa = next(m["forwardPct"] for m in ra["matches"] if m["trackId"] == b)
            rbv = next(m["reversePct"] for m in rb["matches"] if m["trackId"] == a)
            check(f"fwd({a},{b}) == rev({b},{a})", fa == rbv, f"{fa} vs {rbv}")

    # ================= B. 「被包含」不能被误判 =================
    print("\n=== B. 被包含的一小段（设计文档 2.3 节的坑）===")
    r6 = get("/api/analysis/similarity?trackId=6&limit=500")
    m18 = next((m for m in r6["matches"] if m["trackId"] == 18), None)
    # 先独立算【点到折线】的真值 —— "被包含"这件事要用真值来证明
    line_truth = psql_json(f"""
        SELECT json_agg(row_to_json(t)) FROM (
          SELECT round(100.0 * count(*) FILTER (
                   WHERE ST_DWithin(p.geom::geography, t18.geom::geography, {TOL}))
                 / count(*), 1) AS pct
          FROM track_point p, track t18
          WHERE p.track_id = 6 AND t18.id = 18) t;""")[0]["pct"]
    check("track 6 的点【全部】落在 track 18 的折线上（所以它确实是被包含）",
          line_truth >= 99.0, f"点到折线真值={line_truth}%")
    if m18 is None:
        print("  info: track 18 没出现在 track 6 的结果里（说明被正确过滤了）")
    else:
        # ⚠️ 这里【不能】断言 m18["forwardPct"] >= 99 ——
        # 接口用的是【点对点】，track 18 采样间距 42 米，会把它低估成 43%。
        # 那是已知且刻意的取舍（见设计文档 2.6/2.7 节），不是 bug。
        # 要断言的是：**双向相似度**被压到 50% 以下（"取小"生效）。
        check("track 6 vs 18 的双向相似度必须 < 50%（取小把'被包含'压下去了）",
              m18["similarity"] < 50.0, f"similarity={m18['similarity']}")
        check("（已知限制）接口的 forwardPct 被点对点低估",
              m18["forwardPct"] < line_truth - 20,
              f"真值 {line_truth}% vs 接口 {m18['forwardPct']}% —— 差异是预期的")
    # 长度对比：证明这一对确实是"被包含"而不是"同一条路"
    lens = psql_json(
        "SELECT json_agg(row_to_json(t)) FROM ("
        "  SELECT id, round(ST_Length(geom::geography)::numeric) AS len_m "
        "  FROM track WHERE id IN (6,18)) t;")
    d = {r["id"]: r["len_m"] for r in lens}
    check("track 6 确实远短于 track 18（这才是被包含）",
          d.get(6, 0) * 3 < d.get(18, 1), f"6={d.get(6)}米 18={d.get(18)}米")

    # ================= C. 点对点近似 vs 点到折线（量化取舍）=================
    print("\n=== C. 相似度【取小】对近似是否稳健 ===")
    # ⚠️ 这里必须比【相似度】，不能比 forwardPct！
    #
    # 实测（设计文档 2.6/2.7 节）：track 6 的点对 track 18
    #   到【折线】：244/244 = 100%   到【采样点】：105/244 = 43%
    # 因为 track 18 的采样间距是 42 米，点对点会严重低估 fwd。
    #
    # 但相似度取的是 min(fwd, rev)，而被低估的方向【恰好是本来更大的那个】——
    # 所以相似度几乎不受影响（六组实测差 ≤ 0.6 个百分点）。
    # 断言必须打在这个性质上，不能打在 forwardPct 上（后者本来就对不上）。
    for a, b in [(20, 39), (6, 18), (20, 35), (6, 16), (6, 24)]:
        truth = psql_json(f"""
            SELECT json_agg(row_to_json(t)) FROM (
              SELECT least(
                (SELECT 100.0 * count(*) FILTER (
                          WHERE ST_DWithin(p.geom::geography, t2.geom::geography, {TOL}))
                        / count(*)
                 FROM track_point p JOIN track t2 ON t2.id = {b} WHERE p.track_id = {a}),
                (SELECT 100.0 * count(*) FILTER (
                          WHERE ST_DWithin(p.geom::geography, t1.geom::geography, {TOL}))
                        / count(*)
                 FROM track_point p JOIN track t1 ON t1.id = {a} WHERE p.track_id = {b})
              ) AS sim) t;""")[0]["sim"]
        api = get(f"/api/analysis/similarity?trackId={a}&limit=500")
        got = next((m["similarity"] for m in api["matches"] if m["trackId"] == b), 0.0)
        diff = abs(truth - got)
        check(f"({a},{b}) 相似度对近似稳健（取小救了我们）", diff <= 2.0,
              f"真值(点到折线)={round(truth,1)}% 接口(点对点)={got}% 差 {round(diff,1)} 个百分点")

    # 顺手把"近似确实很差"这件事也钉住 —— 免得将来有人以为点对点=点到折线
    fwd_line = psql_json(f"""
        SELECT json_agg(row_to_json(t)) FROM (
          SELECT round(100.0 * count(*) FILTER (
                   WHERE ST_DWithin(p.geom::geography, t2.geom::geography, {TOL}))
                 / count(*), 1) AS pct
          FROM track_point p JOIN track t2 ON t2.id = 18
          WHERE p.track_id = 6) t;""")[0]["pct"]
    api6 = get("/api/analysis/similarity?trackId=6&limit=500")
    m18 = next((m for m in api6["matches"] if m["trackId"] == 18), None)
    if m18 is not None:
        check("（已知限制）点对点的 forwardPct 确实远低于真值",
              fwd_line - m18["forwardPct"] > 20,
              f"真值 {fwd_line}% vs 点对点 {m18['forwardPct']}% —— 差异是预期的，不是 bug")

    # ================= D. 与独立实现对拍（逐条）=================
    print("\n=== D. 与独立实现对拍（trackId=20）===")
    r = get("/api/analysis/similarity?trackId=20&limit=500")
    bas = points_of(20)
    check("主线点数与接口一致", r["pointCount"] == len(bas),
          f"接口 {r['pointCount']} / 独立 {len(bas)}")
    mismatched = 0
    for m in r["matches"][:15]:
        other = points_of(m["trackId"])
        fwd = overlap_pct(bas, other, TOL)
        rev = overlap_pct(other, bas, TOL)
        sym = min(fwd, rev)
        if abs(round(fwd, 1) - m["forwardPct"]) > 0.6 or abs(round(sym, 1) - m["similarity"]) > 0.6:
            mismatched += 1
            print(f"    info: track {m['trackId']} 接口 fwd={m['forwardPct']} sym={m['similarity']}"
                  f" / 独立 fwd={round(fwd,1)} sym={round(sym,1)}")
    check("前 15 名逐条与独立实现一致（容差 0.6 个百分点）", mismatched == 0,
          f"不一致 {mismatched} 条")

    # ================= E. compared / limit / 排序 =================
    print("\n=== E. compared / limit / 排序 ===")
    check("compared 是分母，不受 limit 影响", r["compared"] > 50,
          f"compared={r['compared']}")
    small = get("/api/analysis/similarity?trackId=20&limit=3")
    check("limit=3 只截返回条数", len(small["matches"]) == 3 and small["compared"] == r["compared"],
          f"matches={len(small['matches'])} compared={small['compared']}")
    sims = [m["similarity"] for m in r["matches"]]
    check("matches 严格按相似度降序", sims == sorted(sims, reverse=True),
          f"前 5: {sims[:5]}")
    check("similarity == min(fwd, rev)", all(
        abs(m["similarity"] - min(m["forwardPct"], m["reversePct"])) < 1e-9
        for m in r["matches"]))

    # ================= F. 容差真的生效 =================
    print("\n=== F. 容差参数 ===")
    wide = get("/api/analysis/similarity?trackId=20&toleranceM=200&limit=500")
    check("容差 200 米时 compared 不少于 50 米的",
          wide["compared"] >= r["compared"], f"200m={wide['compared']} 50m={r['compared']}")
    top50 = next((m["similarity"] for m in r["matches"] if m["trackId"] == 39), 0)
    top200 = next((m["similarity"] for m in wide["matches"] if m["trackId"] == 39), 0)
    check("容差变大后第一名相似度不会下降", top200 >= top50, f"50m={top50} 200m={top200}")

    # ================= G. 边界与错误 =================
    print("\n=== G. 边界与错误 ===")
    for name, url, want in [
        ("容差 0 → 400", "/api/analysis/similarity?trackId=20&toleranceM=0", 400),
        ("容差 100000 → 400", "/api/analysis/similarity?trackId=20&toleranceM=100000", 400),
        ("limit 0 → 400", "/api/analysis/similarity?trackId=20&limit=0", 400),
        ("不存在的轨迹 → 404", "/api/analysis/similarity?trackId=999999", 404),
        ("缺 trackId → 400", "/api/analysis/similarity", 400),
    ]:
        try:
            get(url)
            check(name, False, "居然返回了 200")
        except urllib.error.HTTPError as ex:
            check(name, ex.code == want, f"HTTP {ex.code}（期望 {want}）")

    # 没有邻居 → 200 + 空数组（Review Focus 第 1 条）
    # ⚠️ 三个坑都踩过：
    #   ① /api/tracks 返回的是 {total, items}，不是 {tracks} —— 键名写错会让这一项
    #      **静默跳过**（输出看着像无害的 info，实际覆盖为 0）。
    #   ② 不能断言"GPX 轨迹必然孤立" —— 3 条 GPX 是同一场地跑的，它们**互相之间是相似的**。
    #   ③ 实测当前 246 条轨迹**每一条都至少有 1 个邻居**，把容差压到 1 米才有个别孤立的。
    #      所以断言要写成"扫描几条、至少有一条返回空数组"，而不是指定某一条。
    listing = get("/api/tracks?limit=200")
    items = listing.get("items", [])
    check("能取到轨迹列表（键名必须是 items）", len(items) > 0,
          f"拿到 {len(items)} 条（total={listing.get('total')}）")
    probe = items[:6]
    empty_n, ok_n = 0, 0
    for t in probe:
        try:
            g = get(f"/api/analysis/similarity?trackId={t['id']}&toleranceM=1")
        except urllib.error.HTTPError as ex:
            print(f"    info: trackId={t['id']} 返回 HTTP {ex.code}")
            continue
        ok_n += 1
        if g["matches"] == []:
            empty_n += 1
    check("苛刻容差下没有一条报错（不是 500）", ok_n == len(probe),
          f"{ok_n}/{len(probe)} 条正常返回")
    check("至少有一条返回空数组（'没有邻居'是正常结果，不是错误）", empty_n >= 1,
          f"{empty_n}/{ok_n} 条为空")
    # 防"假绿"：同一个接口在正常容差下必须能给出结果 ——
    # 否则上面那个"空数组"断言可能被一个永远返回空的 bug 骗过
    if items:
        g2 = get(f"/api/analysis/similarity?trackId={items[0]['id']}&toleranceM=50")
        check("同一接口在正常容差下不是永远返回空", g2["compared"] > 0,
              f"trackId={items[0]['id']} compared={g2['compared']}")
    # ================= H. daysAway =================
    print("\n=== H. daysAway ===")
    m39 = next((m for m in r["matches"] if m["trackId"] == 39), None)
    if m39:
        check("track 20 vs 39 相差 19 天", m39["daysAway"] == 19, str(m39["daysAway"]))
        check("startTime 是 ISO-8601 UTC", m39["startTime"].endswith("Z"), m39["startTime"])

    print(f"\n{'全部通过' if not fails else str(len(fails)) + ' 项失败: ' + ', '.join(fails)}")
    if fails:
        sys.exit(1)


main()
```

- [ ] **Step 2: 跑对拍**

```powershell
$yaml = Get-Content "backend/src/main/resources/application-local.yml" -Raw
if ($yaml -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
$env:PYTHONIOENCODING='utf-8'; $env:LC_MESSAGES='C'
& "E:\python\python_address\python.exe" .tmp/verify-similarity-api.py
```
Expected: 全部 `[OK]`，最后一行 `全部通过`

> ⚠️ **C 部分（点对点 vs 点到折线）如果红了**：不要改断言。
> 它红了说明"用采样点代表折线"这个近似**比我们想的差** ——
> **那是个真发现**，必须报告，可能要把容差调大或改用折线距离。
> 但如果差异只是 2~3 个百分点（断言写的是 ≤2.0），
> 说明近似在预期范围内，**把实测的差距记进设计文档的已知限制**即可。

- [ ] **Step 3: 提交**

```powershell
git add -f .tmp/verify-similarity-api.py
git commit -m "test(similarity): Python 独立对拍（对称性 + 被包含 + 点对点近似量化）"
```
> ⚠️ `.tmp/` 被 gitignore，**必须 `git add -f`**。

---

## Task 5: 前端纯计算 `lib/similarity.js`

**Files:**
- Create: `frontend/src/lib/similarity.js`
- Create: `frontend/scripts/check-similarity.mjs`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: `rampColor` from `./density.js`
- Produces: `SIM_FILTERS`、`simColor(similarity)`、`simRatio(similarity)`、`formatDays(daysAway)`、`filterMatches(matches, minSimilarity)`、`formatPct(v)`

- [ ] **Step 1: 先写测试**

创建 `frontend/scripts/check-similarity.mjs`：

```javascript
/**
 * lib/similarity.js 的回归测试。零依赖，只用 node 自带的 assert。
 * 跑法：node scripts/check-similarity.mjs
 */
import assert from 'node:assert/strict'
import {
  SIM_FILTERS,
  simColor,
  simRatio,
  formatDays,
  formatPct,
  filterMatches,
} from '../src/lib/similarity.js'

let pass = 0
const fails = []

function t(name, fn) {
  try {
    fn()
    pass++
    console.log('  \u2713 ' + name)
  } catch (e) {
    fails.push(name + ' → ' + e.message)
    console.log('  \u2717 ' + name + '  ' + e.message)
  }
}

// ---------------------------------------------------------------- 归一化
t('相似度 0% → 0，100% → 1', () => {
  assert.equal(simRatio(0), 0)
  assert.equal(simRatio(100), 1)
})

t('相似度归一化夹在 [0,1] 内', () => {
  for (const v of [-10, 0, 50, 100, 150, null, undefined, NaN]) {
    const r = simRatio(v)
    assert.ok(r >= 0 && r <= 1, `simRatio(${v}) = ${r}`)
  }
})

t('相似度归一化是线性的（不是对数）', () => {
  // 相似度本身已经是 0~100 的百分比，不需要再压缩 —— 这和无界的密度计数不同
  assert.equal(simRatio(50), 0.5)
  assert.equal(simRatio(25), 0.25)
})

// ---------------------------------------------------------------- 颜色
t('相似度越高颜色越深红', () => {
  const g = (c) => Number(c.split(',')[1])
  assert.ok(g(simColor(100)) < g(simColor(0)), '高的绿分量应更低')
})

t('simColor 在极端输入下不崩，返回 rgb 字符串', () => {
  for (const v of [-5, 0, 50, 100, 999, null, NaN]) {
    const c = simColor(v)
    assert.ok(typeof c === 'string' && c.startsWith('rgb('), `simColor(${v}) → ${c}`)
  }
})

// ---------------------------------------------------------------- 日期差文案
t('相差 0 天显示「同一天」', () => {
  assert.equal(formatDays(0), '同一天')
})

t('相差 1 天显示「相差 1 天」', () => {
  assert.equal(formatDays(1), '相差 1 天')
  assert.equal(formatDays(19), '相差 19 天')
})

t('日期差为空或负数时兜底', () => {
  assert.equal(formatDays(null), '—')
  assert.equal(formatDays(undefined), '—')
  assert.equal(formatDays(NaN), '—')
})

// ---------------------------------------------------------------- 百分比文案
t('百分比保留一位小数', () => {
  assert.equal(formatPct(91.1), '91.1%')
  assert.equal(formatPct(100), '100%')
  assert.equal(formatPct(68.46), '68.5%')
})

t('百分比非法输入兜底', () => {
  assert.equal(formatPct(null), '—')
  assert.equal(formatPct(NaN), '—')
})

// ---------------------------------------------------------------- 筛选
const SAMPLE = [
  { trackId: 39, similarity: 91.1 },
  { trackId: 35, similarity: 84.3 },
  { trackId: 16, similarity: 69.9 },
  { trackId: 24, similarity: 69.4 },
  { trackId: 6, similarity: 63.0 },
  { trackId: 99, similarity: 12.0 },
]

t('筛选 >= 90% 只剩一条', () => {
  assert.deepEqual(filterMatches(SAMPLE, 90).map((m) => m.trackId), [39])
})

t('筛选 >= 50% 保留 5 条', () => {
  assert.equal(filterMatches(SAMPLE, 50).length, 5)
})

t('筛选 >= 0 全部保留', () => {
  assert.equal(filterMatches(SAMPLE, 0).length, SAMPLE.length)
})

t('筛选不会改动原数组', () => {
  const before = JSON.stringify(SAMPLE)
  filterMatches(SAMPLE, 90)
  assert.equal(JSON.stringify(SAMPLE), before)
})

t('筛选结果仍按相似度降序', () => {
  const out = filterMatches(SAMPLE, 0).map((m) => m.similarity)
  assert.deepEqual(out, [...out].sort((a, b) => b - a))
})

t('筛选遇到空数组或非法输入不崩', () => {
  assert.deepEqual(filterMatches([], 50), [])
  assert.deepEqual(filterMatches(null, 50), [])
  assert.deepEqual(filterMatches(SAMPLE, null), SAMPLE)
})

// ---------------------------------------------------------------- 筛选档位
t('筛选档位包含 90/70/50/全部 四档', () => {
  const vals = SIM_FILTERS.map((f) => f.value)
  assert.deepEqual(vals, [90, 70, 50, 0])
})

t('每个筛选档位都有中文标签', () => {
  for (const f of SIM_FILTERS) {
    assert.ok(f.label && f.label.length > 0, `档位 ${f.value} 缺标签`)
  }
})

t('默认档位是 50%（实测 15 条，既不空也不刷屏）', () => {
  const def = SIM_FILTERS.find((f) => f.value === 50)
  assert.ok(def, '必须有 50% 这一档')
})

console.log('')
console.log(`${pass} 项通过，${fails.length} 项失败`)
if (fails.length) {
  fails.forEach((f) => console.log('  - ' + f))
  process.exit(1)
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run（在 `frontend/` 下）：`node scripts/check-similarity.mjs`
Expected: 报 `Cannot find module .../src/lib/similarity.js`

- [ ] **Step 3: 实现 `lib/similarity.js`**

```javascript
/**
 * 轨迹相似度的纯计算模块。
 *
 * 只放「输入 → 输出」的函数，不碰 Vue、不碰 Cesium、不碰浏览器 API，
 * 所以能用 node 直接跑测试（scripts/check-similarity.mjs）。
 */
import { rampColor } from './density.js'

/**
 * 相似度 → [0, 1]。
 *
 * ⚠️ 这里是**线性**的，和密度那边的**对数**色阶不同 —— 因为两者性质不一样：
 * 密度是**无界计数**（中位数 2、最大 152，差 76 倍，线性下等于白纸）；
 * 而相似度本身已经是 **0~100 的百分比**，天然有界、分布也均匀（实测 91/84/70/63/…），
 * 再压一次反而看不出 91% 和 84% 的区别。
 */
export function simRatio(similarity) {
  const v = Number(similarity)
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(1, v / 100))
}

/**
 * 相似度 → 颜色。复用密度那套色带（越红越"热"），语义一致：
 * 越相似越红，一眼就能看出哪几条和主线重合。
 */
export function simColor(similarity) {
  return rampColor(simRatio(similarity))
}

/** 相差天数的文案 */
export function formatDays(daysAway) {
  const v = Number(daysAway)
  if (!Number.isFinite(v) || v < 0) return '—'
  if (v === 0) return '同一天'
  return `相差 ${v} 天`
}

/** 百分比文案，保留一位小数（91.10 → '91.1%'，100.0 → '100%'） */
export function formatPct(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const r = Math.round(n * 10) / 10
  return (Number.isInteger(r) ? String(r) : r.toFixed(1)) + '%'
}

/**
 * 按最低相似度筛选。
 *
 * 返回**新数组**（不改动入参）—— 调用的地方是 Vue 的 computed，
 * 改动原数组会让缓存失效、白白触发重渲染。
 *
 * @param {Array} matches 匹配列表（已按相似度降序）
 * @param {number} minSimilarity 最低相似度（0 表示不过滤）
 */
export function filterMatches(matches, minSimilarity) {
  if (!Array.isArray(matches)) return []
  const min = Number(minSimilarity)
  if (!Number.isFinite(min) || min <= 0) return matches.slice()
  return matches.filter((m) => Number(m?.similarity) >= min)
}

/**
 * 界面上的筛选档位。
 *
 * 实测（track 20 对比 197 条）：≥90% 有 1 条、≥70% 有 3 条、≥50% 有 15 条。
 * 默认给 **50%** —— 既不空、也不至于刷屏。
 */
export const SIM_FILTERS = [
  { value: 90, label: '≥ 90%（几乎重合）' },
  { value: 70, label: '≥ 70%（大部分重合）' },
  { value: 50, label: '≥ 50%（有实质重合）' },
  { value: 0, label: '全部' },
]
```

- [ ] **Step 4: 跑测试，确认全绿**

Run: `node scripts/check-similarity.mjs`
Expected 最后一行：`N 项通过，0 项失败`（**自己数一遍 `t(` 的个数再报告**）

- [ ] **Step 5: 加 `package.json` 别名**

在 `scripts` 里 `check:density` 之后加（注意上一行末尾要有逗号）：
```json
    "check:similarity": "node scripts/check-similarity.mjs"
```

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/lib/similarity.js frontend/scripts/check-similarity.mjs frontend/package.json
git commit -m "feat(similarity): 前端纯计算模块 lib/similarity.js + node 测试"
```

---

## Task 6: `SimilarityList.vue`

**Files:**
- Create: `frontend/src/components/SimilarityList.vue`

**Interfaces:**
- Consumes: `SIM_FILTERS` / `simColor` / `formatDays` / `formatPct` / `filterMatches`（Task 5）
- Produces: 组件 props `matches` / `baseline` / `loading` / `error` / `filter`；事件 `@focus(trackId)` / `@filter(value)`

- [ ] **Step 1: 创建组件**

**纯展示**：props 进、事件出，自己不发请求。照 `HotspotList.vue` / `DensityLegend.vue` 的风格。

```vue
<script setup>
/**
 * 轨迹相似度列表 —— 纯展示组件（和前几个列表一个规矩：不发请求，交互只往外抛事件）。
 */
import { computed } from 'vue'
import { SIM_FILTERS, simColor, formatDays, formatPct, filterMatches } from '../lib/similarity.js'

const props = defineProps({
  matches: { type: Array, default: () => [] },
  /** 主线的信息：{ name, pointCount, lengthM, compared } */
  baseline: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  /** 当前筛选档位（最低相似度） */
  filter: { type: Number, default: 50 },
})

const emit = defineEmits(['focus', 'filter'])

const shown = computed(() => filterMatches(props.matches, props.filter))

function onFilter(ev) {
  emit('filter', Number(ev.target.value))
}
function onPick(id) {
  emit('focus', id)
}
</script>

<template>
  <div class="similarity-list" data-testid="similarity-list">
    <p v-if="loading" class="hint">正在和 {{ baseline.compared ?? '…' }} 条轨迹比对…</p>
    <p v-else-if="error" class="hint bad">{{ error }}</p>

    <template v-else>
      <!-- 主线信息：让人知道"分母有多大" -->
      <p class="baseline" data-testid="similarity-baseline">
        以 <b>{{ baseline.name || '—' }}</b> 为主线 ·
        {{ baseline.pointCount ?? 0 }} 个点 ·
        {{ ((baseline.lengthM ?? 0) / 1000).toFixed(1) }} km
      </p>
      <p class="compared" data-testid="similarity-compared">
        和 {{ baseline.compared ?? 0 }} 条轨迹比过 · 容差 {{ baseline.toleranceM ?? 50 }} 米
      </p>

      <select :value="filter" data-testid="similarity-filter" @change="onFilter">
        <option v-for="f in SIM_FILTERS" :key="f.value" :value="f.value">{{ f.label }}</option>
      </select>

      <p v-if="matches.length === 0" class="hint" data-testid="similarity-empty">
        没有找到相似的轨迹 —— 这条轨迹可能和其它轨迹不在同一个区域。
      </p>
      <p v-else-if="shown.length === 0" class="hint" data-testid="similarity-none-in-filter">
        没有达到 {{ filter }}% 的轨迹，把筛选放宽试试。
      </p>

      <ul v-else class="list">
        <li
          v-for="m in shown"
          :key="m.trackId"
          class="item"
          data-testid="similarity-item"
          @click="onPick(m.trackId)"
        >
          <span class="pct" :style="{ color: simColor(m.similarity) }">
            {{ formatPct(m.similarity) }}
          </span>
          <span class="name">{{ m.name }}</span>
          <span class="meta">{{ (m.lengthM / 1000).toFixed(1) }} km · {{ formatDays(m.daysAway) }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.similarity-list {
  flex: 1 1 0;
  min-height: var(--list-min, 88px);
  overflow-y: auto;
}

.baseline,
.compared {
  margin: 0 0 4px;
  font-size: 11px;
  color: #93a4bb;
}

.baseline b {
  color: #e7eef8;
}

.similarity-list select {
  width: 100%;
  margin: 4px 0 8px;
  padding: 3px 6px;
  border: 1px solid rgba(255, 159, 10, 0.4);
  border-radius: 6px;
  background: rgba(10, 16, 26, 0.9);
  color: #e7eef8;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: grid;
  grid-template-columns: 52px 1fr;
  grid-template-rows: auto auto;
  gap: 0 6px;
  padding: 5px 6px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 11px;
}

.item:hover {
  background: rgba(127, 209, 255, 0.1);
}

.pct {
  grid-row: span 2;
  align-self: center;
  font-size: 14px;
  font-weight: 600;
}

.name {
  color: #e7eef8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  color: #6b7a8d;
  font-size: 10px;
}

.hint {
  margin: 4px 0;
  font-size: 12px;
  color: #93a4bb;
  line-height: 1.5;
}

.bad {
  color: #ff9b9b;
}
</style>
```

- [ ] **Step 2: 静态验证（Vite 构建由主控会话代跑）**

这个沙箱里 Vite 需要 spawn 子进程，**你可能会遇到 `spawn EPERM`**；遇到就**如实报告"构建因沙箱限制未能执行"**，不要反复重试。

**用项目自带的 `@vue/compiler-sfc` 真编译一遍**（不需要 spawn，前面的任务验证过可行）：
`parse` + `compileScript` + `compileTemplate`，有错会直接报出来。
重点确认：三个 SFC 块成对闭合、五个 testid 都在
（`similarity-list` / `similarity-baseline` / `similarity-compared` / `similarity-filter` /
`similarity-item` / `similarity-empty`）。

- [ ] **Step 3: 提交**

```powershell
git add frontend/src/components/SimilarityList.vue
git commit -m "feat(similarity): SimilarityList.vue（主线信息 + 匹配列表 + 相似度筛选）"
```

---

## Task 7: `CesiumGlobe` 画相似轨迹

**Files:**
- Modify: `frontend/src/components/CesiumGlobe.vue`

**Interfaces:**
- Consumes: `simColor` from `../lib/similarity.js`
- Produces: props `similarTracks` / `similarBaseline`；`defineExpose` 已有 `focusOn` / `fitBounds` / `getViewBbox` 等（**一个都不能少**）

- [ ] **Step 1: 加 import 与 prop**

在 `from '../lib/density.js'` 那一行下面加：

```javascript
// 相似度的「颜色」同样是纯函数，组件不自己算
import { simColor } from '../lib/similarity.js'
```

在 `defineProps({...})` 里，紧跟 `densityCellSize` 之后加：

```javascript
  // 相似档：主线（单独画，要醒目）+ 匹配到的轨迹（按相似度上色）
  similarBaseline: { type: Object, default: null },
  similarTracks: { type: Array, default: () => [] },
```

在 `let densityEntities = []` 附近加：

```javascript
let similarEntities = []
```

- [ ] **Step 2: 加 `drawSimilarity()`**

紧跟 `drawDensity()` 之后插入：

```javascript
/**
 * 画相似轨迹：主线用醒目的粗白线画在最上面，匹配到的按相似度上色叠在下面。
 *
 * ⚠️ 和热点/密度一样，这些实体【不】进 clearTrack() 的清理范围 ——
 * 相似是"当前选中轨迹 vs 别的轨迹"的结果，由 selectedTrack 变化驱动，
 * 而 clearTrack() 也是由轨迹点变化触发的，两者会互相打架。
 * 清理统一由 drawSimilarity() 自己负责（它开头清一遍）。
 */
function drawSimilarity(baseline, tracks) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return

  for (const e of similarEntities) v.entities.remove(e)
  similarEntities = []
  if (!baseline && (!tracks || tracks.length === 0)) return

  // 先画匹配的（细、按相似度上色），后画主线（粗、白色）—— 后加的在上层
  for (const t of tracks || []) {
    if (!t.positions || t.positions.length < 2) continue
    similarEntities.push(v.entities.add({
      polyline: {
        positions: t.positions,
        width: 3,
        material: Color.fromCssColorString(simColor(t.similarity)).withAlpha(0.85),
        clampToGround: false,
      },
    }))
  }

  if (baseline && baseline.positions && baseline.positions.length >= 2) {
    similarEntities.push(v.entities.add({
      polyline: {
        positions: baseline.positions,
        width: 6,
        // 主线用亮蓝 —— 和匹配轨迹的暖色系形成对比，一眼能分清谁是谁
        material: Color.fromCssColorString('rgb(127,209,255)'),
        clampToGround: false,
      },
    }))
  }
}
```

> **为什么主线是蓝色而不是"最红"**：红色系已经被"相似度"占用了。
> 主线不是"某个相似度"，它是基准 —— 用对比色才不会让人误读。

- [ ] **Step 3: 加 watch 与 `onMounted` 初始绘制**

在已有的密度 `watch` 之后加：

```javascript
watch(
  () => [props.similarBaseline, props.similarTracks],
  ([b, ts]) => {
    if (ready.value) drawSimilarity(b, ts)
  },
  { deep: true },
)
```

在 `onMounted` 里已有的 `drawDensity(...)` 之后加：

```javascript
  drawSimilarity(props.similarBaseline, props.similarTracks)
```

- [ ] **Step 4: 确认 `defineExpose` 一个都没少**

`defineExpose` 现在有 **六个**：`focusOn` / `fitBounds` / `getViewBbox` / `play` / `pause` / `seekTo`。
**本任务不新增暴露的方法** —— `focusOn` 已经够 App.vue 用来"点一条匹配轨迹就飞过去"。
**跑一遍 grep 确认六个都在**：

```powershell
Select-String -Path frontend/src/components/CesiumGlobe.vue -Pattern 'defineExpose' -Context 0,10
```

- [ ] **Step 5: 静态验证 + 提交**

用 `@vue/compiler-sfc` 编译一遍（同 Task 6 的做法）。

```powershell
git add frontend/src/components/CesiumGlobe.vue
git commit -m "feat(similarity): 地球叠加相似轨迹（主线亮蓝 + 匹配按相似度上色）"
```

---

## Task 8: `App.vue` 集成第四档

**Files:**
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `SimilarityList.vue`（Task 6）、`SIM_FILTERS` / `filterMatches`（Task 5）、地球的 `similarBaseline` / `similarTracks` prop（Task 7）
- Consumes: **已有**的 `selectedTrackId`（选中轨迹）与 `loadTrackPoints()`（把点转成 Cesium 坐标）

- [ ] **Step 1: 先摸清现有的「选中轨迹」与「点转坐标」怎么做的**

```powershell
Select-String -Path frontend/src/App.vue -Pattern 'selectedTrack|selectTrack|trackPoints|Cartesian3' | ForEach-Object { "  $($_.LineNumber): $($_.Line.Trim())" }
Select-String -Path frontend/src/components/CesiumGlobe.vue -Pattern 'trackPoints|props.points|Cartesian3.fromDegrees' | ForEach-Object { "  $($_.LineNumber): $($_.Line.Trim())" }
```

**你要弄清楚两件事**：
1. **主线的 id 存在哪个变量里**（多半是 `selectedTrackId`）—— 相似度就查它
2. **轨迹点是怎么变成 Cesium `Cartesian3` 数组的**。
   `CesiumGlobe` 的 `points` prop 收到的是原始点（`{lon, lat, elevation}` 之类），
   坐标转换**在组件内部做**。

**如果 App.vue 里【没有】现成的"Cesium 坐标数组"可用于 `similarTracks`**，
那就**把原始点传过去，让地球组件自己转**：

- `similarBaseline` 传 `{ positions: <原始点数组>, ... }` 是不行的（地球要 Cartesian3）
- **改法**：`CesiumGlobe` 内部把 `similarTracks` 的每一项当作
  `{ trackId, similarity, points: [{lon, lat, elevation}, ...] }`，
  在 `drawSimilarity()` 里用 `Cartesian3.fromDegrees(lon, lat, elevation)` 转换。

> ⚠️ **这一步必须按现状适配**。上面的 `drawSimilarity()` 假设了 `t.positions` 是
> Cartesian3 数组；如果现状不是这样，**就按现状改 `drawSimilarity()` 的转换逻辑**，
> 并把差异写进报告。**不要为了迁就计划而改 `CesiumGlobe` 已有的数据结构。**

- [ ] **Step 2: 加 import 与状态**

```javascript
import SimilarityList from './components/SimilarityList.vue'
import { filterMatches } from './lib/similarity.js'
```

在「网格密度」那一段状态之后加：

```javascript
/* ============ 轨迹相似度 ============ */
const similarityMatches = ref([])
const similarityInfo = ref({})
const similarityLoading = ref(false)
const similarityError = ref('')
const similarityFilter = ref(50)

/** 防止"切轨迹时旧请求后回来盖掉新结果"——和热点那套同一个问题 */
let similaritySeq = 0

/** 主线的点（给地球画线用）。格式与 CesiumGlobe 的 points prop 一致 */
const similarityBaselinePoints = computed(() => trackPoints.value)

/** 面板上筛选后要显示的条数（列表内部也会筛，这里只为统计） */
const similarityShownCount = computed(
  () => filterMatches(similarityMatches.value, similarityFilter.value).length,
)

/**
 * 地球上要叠画的匹配轨迹（只取前 N 条）。
 *
 * 为什么只画 10 条：再多在屏幕上也分不清哪条是哪条，反而把主线埋掉。
 */
const SIM_DRAW_TOP = 10
const similarityTracks = ref([])

/**
 * 取前 N 条匹配轨迹的点，给地球叠画用。
 *
 * 为什么要逐条取：`/api/analysis/similarity` 只返回**元数据**（相似度、长度、日期），
 * 不返回几何 —— 那是刻意的，否则一次响应要带上十几条轨迹的全部点。
 * 轨迹的点在 `GET /api/tracks/{id}` 里（返回 `TrackDetail`，含 points）。
 */
async function loadSimilarityTracks(matches, seq) {
  const top = matches.slice(0, SIM_DRAW_TOP)
  const loaded = await Promise.all(top.map(async (m) => {
    try {
      const res = await fetch(`/api/tracks/${m.trackId}`)
      if (!res.ok) return null
      const d = await res.json()
      return { trackId: m.trackId, similarity: m.similarity, points: d.points ?? [] }
    } catch {
      return null            // 单条失败不影响其它条
    }
  }))
  if (seq !== similaritySeq) return          // 用户已经切走了，丢弃这批结果
  similarityTracks.value = loaded.filter(Boolean)
}

/**
 * 查相似度。主线就是**当前选中的轨迹**。
 */
async function loadSimilarity() {
  const id = selectedTrackId.value
  if (id == null) {
    similarityMatches.value = []
    similarityInfo.value = {}
    return
  }

  const mine = ++similaritySeq
  similarityLoading.value = true
  similarityError.value = ''
  try {
    const res = await fetch(`/api/analysis/similarity?trackId=${id}&limit=200`)
    if (res.status === 404) throw new Error('这条轨迹不存在')
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    if (mine !== similaritySeq) return          // 已经有更新的请求了，丢弃
    similarityMatches.value = data.matches ?? []
    // 顺手把前 10 条的点也取回来给地球叠画（不阻塞列表显示）
    loadSimilarityTracks(similarityMatches.value, mine)
    similarityInfo.value = {
      name: data.name,
      pointCount: data.pointCount,
      lengthM: data.lengthM,
      compared: data.compared,
      toleranceM: data.toleranceM,
    }
  } catch (e) {
    if (mine !== similaritySeq) return
    similarityMatches.value = []
    similarityError.value = '相似度查询失败：' + e.message
  } finally {
    if (mine === similaritySeq) similarityLoading.value = false
  }
}

/** 点列表里的一条 → 相机飞过去（复用地球暴露的 focusOn） */
function focusSimilar(trackId) {
  // 找到那条轨迹的点，用它的中心飞过去
  const target = similarityTracks.value.find((t) => t.trackId === trackId)
  if (!target || !target.points || target.points.length === 0) return
  const mid = target.points[Math.floor(target.points.length / 2)]
  globe.value?.focusOn(mid.lon, mid.lat, 500)
}
```

- [ ] **Step 3: 换 `switchMode` 支持第四档**

把现有的 `switchMode` 里**追加**一个分支（**前三个分支一个字都不要改**）：

```javascript
  if (mode === 'similar') {
    await nextTick()
    if (viewMode.value !== 'similar') return
    await loadSimilarity()
    return
  }
```

- [ ] **Step 4: 让地球拿到相似数据**

在 `<CesiumGlobe ...>` 上、`:density-cell-size` 之后加：

```html
      :similar-baseline="viewMode === 'similar' && similarityBaselinePoints.length
        ? { positions: similarityBaselinePoints } : null"
      :similar-tracks="viewMode === 'similar' ? similarityTracks : []"
```

其中 `similarityTracks` 是**匹配轨迹的点**组成的数组。**它的来源要按现状决定**：

- **如果 App.vue 已经有"按 id 取点"的能力**（比如 `loadTrackPoints(id)`）：对前 N 条匹配（建议 **10 条**，
  画太多会糊成一团）各取一次点，组装成
  `[{ trackId, similarity, points }, ...]`
- **如果没有**：先只画主线（`similarTracks` 传空数组），并在报告里说明
  "匹配轨迹的点需要新接口，本任务未做" —— **不要为了这个去改后端**。

> ⚠️ **这是一个真实的范围问题**：后端 `/api/analysis/similarity` 只返回**元数据**，
> 不返回匹配轨迹的点。要在地球上把匹配轨迹画出来，前端得**按 id 逐条取点**。
>
> **最小可行做法**：取**前 10 条**（相似度最高的），逐条调 `/api/tracks/{id}/points`
> （或项目里已有的等价接口）。10 次请求、每次几千点，可接受。
> **执行时先 grep 确认这个接口存在**：
> ```powershell
> Select-String -Path backend/src/main/java/com/calcite/web/*.java -Pattern 'points|@GetMapping' | ForEach-Object { "  $($_.LineNumber): $($_.Line.Trim())" }
> ```
> 如果接口形态不同，**按现状适配**并写进报告。

- [ ] **Step 5: 模式开关加第四个按钮**

在「密度」按钮 `</button>` 之后加：

```html
        <button
          type="button"
          :class="{ on: viewMode === 'similar' }"
          data-testid="mode-similar"
          @click="switchMode('similar')"
        >
          相似
        </button>
```

- [ ] **Step 6: 面板模板加第四档**

把现在的：
```html
      <template v-else>                <!-- 密度 -->
```
改成：
```html
      <template v-else-if="viewMode === 'density'">
```
然后在它之后**追加**：

```html
      <template v-else>
        <h2>相似<span v-if="similarityMatches.length"> （{{ similarityShownCount }} 条）</span></h2>
        <p class="tip">越红 = 和主线重合得越多 · 主线是蓝色那条</p>
        <p v-if="selectedTrackId == null" class="tip" data-testid="similarity-need-track">
          先在左边选一条轨迹，才能找和它相似的
        </p>
        <SimilarityList
          v-else
          :matches="similarityMatches"
          :baseline="similarityInfo"
          :loading="similarityLoading"
          :error="similarityError"
          :filter="similarityFilter"
          @filter="similarityFilter = $event"
          @focus="focusSimilar"
        />
      </template>
```

- [ ] **Step 7: 加 CSS 排除规则**

找到那条 `.panel > div:not(...)` 规则，把 `.similarity-list` 也加进去（否则矮窗口下会把列表压扁）：

```css
.panel > div:not(.track-list):not(.stay-list):not(.hotspot-list):not(.density-legend):not(.similarity-list) { flex: 0 0 auto; }
```

- [ ] **Step 8: 让「切换选中轨迹」时重查**

**如果 `selectTrack`（或设置 `selectedTrackId` 的地方）已经会触发别的加载**，
在它里面加一句：**当 `viewMode === 'similar'` 时重查**：

```javascript
  if (viewMode.value === 'similar') await loadSimilarity()
```

> ⚠️ **先 grep 找到真正设置 `selectedTrackId` 的那个函数**（可能是 `selectTrack`），
> 把这一句加在**点已经加载完**之后（否则地球还没拿到主线的点）。

- [ ] **Step 9: 构建 + 手工看效果**

Run（**需要提权 `danger-full-access`**）：`cd frontend; npm run build`
Expected: `built in ...`，无 error

然后浏览器打开 `http://localhost:5173`，选一条轨迹（如 `20081114101436`），点「相似」档：
- 面板显示"以 … 为主线 · 305 个点 · 6.3 km"和"和 197 条轨迹比过"
- 列表第一条是 **91.1%**
- 地球上主线的**蓝色粗线**上叠着**红色的匹配轨迹**（高度重合时几乎看不见蓝线）
- 切筛选到 ≥90% → 列表只剩 1 条
- 点一条匹配 → 相机飞过去
- 切回「停留点」→ 蓝线和红线的叠加消失

- [ ] **Step 10: 提交**

```powershell
git add frontend/src/App.vue frontend/src/components/CesiumGlobe.vue
git commit -m "feat(similarity): App 集成第四档 + 选中轨迹变化时重查 + 乱序请求防护"
```

---

## Task 9: 浏览器像素验收

**Files:**
- Create: `.tmp/check-similarity.py`

> ⚠️ **先读一遍 `.tmp/check-density.py`**（它是上一个阶段写的，已经在跑），
> **照它的结构写**：`check()` / `note()` / `warm_px()` / 面板右边界 / 四视口溢出 / 控制台零报错。
> 本任务只列**相似度特有的检查**，通用的那几项直接照抄。

- [ ] **Step 1: 写验收脚本**

除了照抄 `check-density.py` 的通用结构，**必须包含**这些检查：

| # | 检查 | 判据 |
|---|---|---|
| 1 | **第四档按钮存在且四档不折行** | `mode-similar` 可见；量 `.mode-switch` 的 `scrollWidth <= clientWidth`（**四档挤爆是真实风险**） |
| 2 | **没选轨迹时给出提示** | 用裸 URL `http://localhost:5173` 进（不选轨迹）→ 点相似档 → `[data-testid="similarity-need-track"]` 存在 |
| 3 | 选中轨迹后出现列表 | 用 `?track=20` 进 → 列表条数 = `min(接口 matches 数, 筛后)` |
| 4 | 主线信息正确 | 面板文本含接口返回的 `name` 和 `pointCount` |
| 5 | **筛选生效** | 切到 ≥90% → 条数变少（实测应为 1） |
| 6 | **点一条会飞** | 点第 2 条 → **比较点前后的 trackline 包围盒**（**不要用像素均值** —— 上个阶段的教训） |
| 7 | 切走相似档后叠加消失 | 切到停留点档 → 匹配轨迹的暖色像素归零 |
| 8 | 四视口面板不溢出 | 1600×900 / 1600×600 / 1366×660 / 1280×720 |
| 9 | 控制台零报错 | |

- [ ] **Step 2: 跑验收**

```powershell
$env:PYTHONIOENCODING='utf-8'
& "E:\python\python_address\python.exe" .tmp/check-similarity.py
```
**你需要提权 `danger-full-access`**（Playwright 靠命名管道）。
**如果提不了权，如实报告"没能真跑"**，由主控会话代跑。**不要假装跑过。**

- [ ] **Step 3: 看截图确认视觉效果**

用 `read_image` 读脚本产出的截图，确认：
- 蓝色的主线和红色的匹配轨迹**确实叠在一起**（不是各画各的）
- 高度重合的地方**看起来像一条线**（这正是"同一条路"的视觉证据）

- [ ] **Step 4: 提交**

```powershell
git add -f .tmp/check-similarity.py
git commit -m "test(similarity): 浏览器像素验收"
```

---

## Task 10: 全量回归 + 文档同步

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`
- Modify: `_session_context.md`

- [ ] **Step 1: 跑全部回归，数准总数**

```powershell
# 后端
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" test 2>&1 | Select-String -Pattern '^\[INFO\] Tests run:.*Skipped: \d+$|BUILD' | Select-Object -Last 2
```
```powershell
# 前端 node（五个）
cd frontend
foreach ($s in @('check-playback','check-chart','check-hotspot','check-density','check-similarity')) {
  $o = node "scripts/$s.mjs" 2>&1
  "  {0,-18} {1}" -f $s, (($o | Select-String -Pattern '项通过' | Select-Object -Last 1).Line)
}
cd ..
```
```powershell
# 浏览器 / 接口（需要提权）
$yaml = Get-Content "backend/src/main/resources/application-local.yml" -Raw
if ($yaml -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
$env:PYTHONIOENCODING='utf-8'; $env:LC_MESSAGES='C'
$py = "E:\python\python_address\python.exe"
foreach ($s in @('check-stay-points','check-chart-pixels','check-import-pixels','check-filter','check-hotspots','check-density','check-similarity','verify-hotspot-api','verify-density-api','verify-similarity-api')) {
  $o = & $py ".tmp/$s.py" 2>&1
  "  {0,-24} exit={1}  {2}" -f $s, $LASTEXITCODE, (($o | Select-String -Pattern '项通过|全部通过' | Select-Object -Last 1).Line)
}
```

把每一层的**实际项数**记下来（下一步要写进文档）。
**基线是 346 项**（后端 96 + node 104 + 浏览器/接口 146）。

- [ ] **Step 2: 更新设计文档附录 B**

在 `docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`：

1. 把「M2 轨迹相似度」那行从 ⏳ 改成 ✅，写上真实数字（track 20 的第一名 91.1%、
   `compared` 197、首次约 2 秒、缓存后瞬间）
2. **把第 135 行的 `ST_FrechetDistance` 那一条标注为"实测不可用，已改为双向重合度"**，
   并指向 `docs/superpowers/specs/2026-09-17-m2-similarity-design.md`
3. **在附录 B 顶部加一行「M2 全部完成」的总结**（四个阶段：停留点 → 热点 → 密度 → 相似度）

先 grep 找出所有要改的位置：
```powershell
Select-String -Path docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md -Pattern 'Frechet|轨迹相似度|M2 轨迹相似度'
```

- [ ] **Step 3: 更新 `_session_context.md`**

在「M2 第三阶段」小节之后加 `### M2 第四阶段 · 轨迹相似度（2026-09-17 完成）`，内容要点：

- 交付物：接口 `GET /api/analysis/similarity`、前端第四档「相似」、设计文档与计划路径
- **三个关键设计决定**：
  ① **双向重合度取小**（`min(fwd%, rev%)`）—— 单向会把"被包含的一小段"判成 100%，
     实测 track 6（1.3km）对 track 18（20.7km）单向 100%、双向 35%
  ② **`ST_FrechetDistance` 实测不可用**（没有能同时罩住北京和长三角的投影 + geography 版不存在 + 对 GPS 跳点敏感）
  ③ **让主线的点驱动查询**（走空间索引，0.79s vs 8.5s，11 倍）
- 实现要点：`eps` 按主线纬度算（不能用固定常数）、SQL 不写 LIMIT（要返回 `compared`）、
  缓存键必须带 `toleranceM`
- **M2 到此全部完成**，下一步是 `git push`（67+ 提交）
- 回归基线（实测）

**同时更新「▶ 下次接着做」**：M2 完成 → 推送 + M3（空间范围查询 / 路网匹配）

- [ ] **Step 4: 提交**

```powershell
git add docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md _session_context.md
git commit -m "docs(m2): 轨迹相似度完成——设计文档附录B + 会话记忆同步（M2 全部完成）"
```

---

## Task 11: 生成 Word 文档（用户点名的交付物）

**Files:**
- Create: `docs/learning/2026-09-17-M2-第三阶段网格密度.docx`（或用户偏好的目录）

> **背景**：用户在第三阶段结束时**点名要**一份 Word，
> **重点是「数据扩充对 Calcite 的影响」**。素材已经齐了。

- [ ] **Step 1: 加载 `officecli` 技能**

用 `skill` 工具加载 `officecli`，按它的指引做 `.docx`。

- [ ] **Step 2: 收集素材（都在仓库里，不要编）**

| 素材 | 位置 |
|---|---|
| 第三阶段设计（含数据现状一节） | `docs/superpowers/specs/2026-09-17-m2-density-design.md` |
| **「数据扩充之后」专节** | `docs/learning/2026-09-17-m2-hotspot-notes.md` **第 10 节** |
| 三个阶段的完整决策记录 | `_session_context.md` 的 M2 各小节 |
| 色阶对比图 | `docs/learning/figs/fig-density-scales.png` |

- [ ] **Step 3: 文档结构（按这个写，重点是第 4 节）**

1. **M2 第三阶段做了什么** —— 网格密度、回答场景 3（早高峰哪些路段人最多）；
   带一张真实截图（`.tmp/density-shot.png.reset.png` 或自己重截一张）
2. **四个关键设计决定**（每个都要有实测依据）
   - 按视野裁剪（不然最细档要返回 3.3 MB / 75,970 个格子）
   - 对数色阶（轨迹条数中位数 2、最大 152；线性色阶下下半数格子平均深浅只有 **0.008**，等于白纸）
   - 固定档位阶梯（拖动地图时格子纹丝不动）
   - 两层时段筛选（早高峰让热区从城东变到城西，最深 152 → 40）
3. **实现上的两个"反直觉"发现**
   - `round(ST_X/cell)` 比 `ST_SnapToGrid` 快约 2 倍，但**并非严格等价** ——
     差异 100% 出现在格子边界点（`116.4095/0.001 = 116409.49999999999`）
   - 最粗档必须是 5°（5×80=400° > 地球一圈），否则**用户第一次点密度就 400**
4. ⭐ **数据扩充对 Calcite 的影响**（**这一节要写得最详细**）
   - **变了什么**：25 → **246 条**轨迹、13,720 → **286,019 个点**；
     geoLife 从 user 000（北京 171 条）扩到 **user 001（长三角 71 条）** —— **两个用户、两个城市**，
     数据横跨 **467 km × 1008 km**；热点 3 → **37 个**，最热的从 3 条轨迹变成 **22 条**
   - **数据长大【逼出来】的三个设计问题**（如果只有 25 条，它们会被完全掩盖）：
     | 问题 | 25 条时 | 246 条时 |
     |---|---|---|
     | 格子数爆炸 | 427 个格子，看不出问题 | 最细档 **75,970 个 / 3.3 MB** → 必须按视野裁剪 |
     | 数值极端偏斜 | 偏斜不明显，线性色阶也能看 | 中位数 2 / 最大 152 → **线性等于白纸** |
     | 排序落盘 | 15 ms，看不出问题 | **330 ms + 6.5 MB 临时文件** → 换整数写法 |
   - **热点接口从 0.9 秒慢到 4.9 秒**，以及怎么修的：
     按 `trackId` 缓存停留点（**轨迹导入后不可变 → 缓存永不失效**）+ 不再加载 track 几何
     （246 条 LineString = **28.6 万个顶点**）→ **1.9 秒**
   - **9 处写死的验收判据同时失效** —— 教训：验收判据要**从接口取期望值**，
     不要写死数据量（举 2~3 个具体例子：写死"热点正好 3 条"、"格子数 700~800"、"孤立点 == 1"）
   - **一条没被推翻的旧结论**：用户自采的 3 条 GPX 在福建，**仍然是 0 个停留点** ——
     跑步轨迹不停，这个判断在 10 倍数据量下依然成立
   - **一句给将来的话**：数据量变化会**同时**打破**功能性能**和**验收基线**，这两件事要一起想到
5. **这一阶段暴露的工程教训**（挑 3 条最有价值的）
   - 「两者相同」要用**集合/差集**证明，不要用**计数**证明（这是发现 `round` 与
     `ST_SnapToGrid` 不等价的原因 —— 最初只比 `count(*)`，3867 = 3867 就以为通过了）
   - 写死的数字与**另一个查询条件**混用（我把"窄 bbox + 按来源过滤"的 736
     抄成了"宽 bbox"的验收标准，实测 1335）
   - **验证层抓到了计划里 9 个缺陷** —— 计划再详细也不能替代执行时的实测

- [ ] **Step 4: 生成并检查**

用 `officecli` 生成 `.docx`，然后：
- **用 officecli 读回来检查**（标题层级、表格、图片是否正常）
- 确认字数/篇幅合适（用户要的是"讲述"，不是 API 文档）
- **确认所有数字都对得上**（第 4 节的每个数字都要能在仓库里找到出处）

- [ ] **Step 5: 提交**

```powershell
git add docs/learning/*.docx
git commit -m "docs(m2): M2 第三阶段 Word 文档（重点讲数据扩充对 Calcite 的影响）"
```

---

## 完成标准（Definition of Done）

- [ ] `GET /api/analysis/similarity?trackId=20` 返回 `compared` = **197**，第一名 **91.1%**（track 39）
- [ ] `similarity(6,18)` ≈ **35%**（**不是 100%**）—— 取小生效
- [ ] `similarity(A,B) == similarity(B,A)` —— 度量对称
- [ ] `toleranceM=100000` → **400**；不存在的轨迹 → **404**；福建的 GPX → **200 + 空数组**
- [ ] 后端单测 **121 项**全绿（`mvn test`，**依然不需要数据库**）
- [ ] 前端 node 五个套件全绿（含新的 `check-similarity.mjs`）
- [ ] `.tmp/verify-similarity-api.py` 全绿（**含对称性、被包含、点对点近似量化三条专项**）
- [ ] `.tmp/check-similarity.py` 全绿；截图里蓝主线和红匹配**确实叠在一起**
- [ ] 界面：四档切换正常，**四档按钮不折行**；没选轨迹时给提示；筛选生效
- [ ] 第二次查同一条主线**瞬间返回**（缓存生效）
- [ ] 旧功能全部没坏（346 项基线）
- [ ] 设计文档附录 B、`_session_context.md` 已同步（**含 M2 全部完成**）
- [ ] **Word 文档已生成**，第 4 节"数据扩充的影响"内容完整

---

## 已知陷阱速查（执行时最容易踩的）

| 陷阱 | 症状 | 处理 |
|---|---|---|
| **`eps` 用固定常数** | 高纬地区**静默漏掉真匹配** | 必须按主线实际纬度算，取纬度/经度两个方向里更小的（Task 1） |
| **缓存键漏了 `toleranceM`** | 50 米的结果被 200 米的请求复用 → **返回错的结果** | 键必须是 `(trackId, toleranceM)` |
| **SQL 里写了 `LIMIT`** | `compared` 拿不到（变成和 `matches.size()` 一样） | 截断放 Java 层 |
| **反方向查询写成 `WHERE ... IN (候选) AND EXISTS`** | 慢 11 倍（8.5s vs 0.75s） | 让**主线的点**驱动：`FROM track_point q JOIN track_point p`，`q` 是主线 |
| **`findAllById` 取匹配轨迹的元数据** | 会把 197 条 LineString（28 万顶点）全水合 | 用 JPQL/native **标量投影**，只取需要的列 |
| **native query 直接取 `timestamptz`** | Java 类型映射歧义，运行时才炸 | 用 `to_char(... AT TIME ZONE 'UTC', ...)` 转成 ISO 字符串 |
| **`ST_FrechetDistance` 直接用** | 单位是度不是米；跨两城没有合适投影 | 不用它，用双向重合度 |
| **相似度不取小** | 1.3km 的小段被判成和 21km 的路"完全相同" | `min(fwd, rev)` |
| **四档模式开关挤爆** | 1280px 下按钮折行 | 验收里**单独量** `scrollWidth <= clientWidth` |
| **验收用像素均值判断"飞过去了"** | 上个阶段的教训：带守卫 0.00 / 不带 1.66，判据无齿 | 用 **trackline 包围盒** |
| `.tmp/` 被 gitignore | `git add` 静默失败 | 必须 `git add -f` |
| 改完 Java 没真编译 | 跑的是旧字节码 | 确认 mvn 打印了 `Compiling N source files`，否则 `clean` |
| `Get-NetTCPConnection` 不可靠 | 找不到 8080 的 PID | 用 `netstat -ano \| Select-String ":8080\s"` |
