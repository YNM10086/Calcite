# M2 第一阶段：停留点识别 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从一条轨迹里找出「在某个地方待了一阵子」的片段，画在地球上、列在面板里。

**Architecture:** `StayPointService` 是纯计算（照 `TrackCleaner` 的模式，`@Component` + `@Value` 注入参数，核心方法可直接单测）；
新增一条 `GET /api/tracks/{id}/stay-points` 现算不存库；前端新建 `StayPointList.vue`（纯展示）+ `CesiumGlobe.vue` 加圆圈图层。

**Tech Stack:** Spring Boot 3.5.16 / Java 25 / JUnit 5 / Vue 3 / Cesium 1.145

**上游设计文档：** `docs/superpowers/specs/2026-09-14-m2-stay-point-design.md`

---

## 文件结构

| 文件 | 职责 |
| --- | --- |
| `backend/.../service/StayPoint.java` | **新建**：停留点 record |
| `backend/.../service/StayPointService.java` | **新建**：滑动窗口算法（纯计算 + `@Component`） |
| `backend/src/test/java/.../service/StayPointServiceTest.java` | **新建**：10 条测试（含真实数据指纹） |
| `backend/.../web/dto/StayPointDto.java` | **新建**：对外返回的停留点 |
| `backend/.../web/dto/StayPointResponse.java` | **新建**：`{trackId, count, stays}` |
| `backend/.../web/TrackController.java` | **改**：加 `GET /api/tracks/{id}/stay-points` |
| `backend/src/main/resources/application.yml` | **改**：加 `calcite.stay-point.*` 三个参数 |
| `frontend/src/components/StayPointList.vue` | **新建**：停留点列表（纯展示，emit `focus`） |
| `frontend/src/components/TrackList.vue` | **改**：CSS 改成弹性高度（配合面板布局） |
| `frontend/src/components/CesiumGlobe.vue` | **改**：加停留圆圈图层 + `focusOn` |
| `frontend/src/App.vue` | **改**：面板布局（两块各自滚动）+ 接线 |
| `.tmp/check-stay-points.py` | **新建**：浏览器验收 |
| `docs/superpowers/specs/2026-09-08-...design.md` | **改**：附录 B 的 `stay_point` 表说明 |
| `_session_context.md` | **改**：记录 M2 第一阶段完成 |

### 命名约定（后面所有任务统一使用，不要改名）

```java
record StayPoint(int seqStart, int seqEnd, OffsetDateTime startTime, OffsetDateTime endTime,
                 int durationS, double centerLon, double centerLat, double radiusM, int pointCount)
class StayPointService {
    StayPointService(double radiusM, int minDurationS, int maxGapS)
    List<StayPoint> detect(List<RawPoint> points)
}
record StayPointDto(int seqStart, int seqEnd, OffsetDateTime startTime, OffsetDateTime endTime,
                    int durationS, double lon, double lat, double radiusM, int pointCount)
record StayPointResponse(Long trackId, int count, List<StayPointDto> stays)
```

### 常用命令

```powershell
# 跑后端测试
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" test

# 跑单个测试类
& "...\mvn.cmd" -B "-Dmaven.repo.local=..." -f "...\backend\pom.xml" test "-Dtest=StayPointServiceTest"
```

---

## Task 1: 算法核心（TDD，本阶段的重头戏）

**Files:**
- Create: `backend/src/main/java/com/calcite/service/StayPoint.java`
- Create: `backend/src/main/java/com/calcite/service/StayPointService.java`
- Test: `backend/src/test/java/com/calcite/service/StayPointServiceTest.java`

- [ ] **Step 1: 先创建 `StayPoint`（纯数据，无逻辑）**

创建 `backend/src/main/java/com/calcite/service/StayPoint.java`：

```java
package com.calcite.service;

import java.time.OffsetDateTime;

/**
 * 一段停留。
 *
 * @param seqStart   起点在轨迹里的 seq
 * @param seqEnd     终点的 seq
 * @param startTime  起始时刻
 * @param endTime    结束时刻
 * @param durationS  时长（秒）
 * @param centerLon  停留中心经度（窗口重心）
 * @param centerLat  停留中心纬度
 * @param radiusM    活动半径：窗口内所有点到中心的最大距离（米）
 * @param pointCount 这段里有几个点
 */
public record StayPoint(
        int seqStart,
        int seqEnd,
        OffsetDateTime startTime,
        OffsetDateTime endTime,
        int durationS,
        double centerLon,
        double centerLat,
        double radiusM,
        int pointCount
) {
}
```

- [ ] **Step 2: 写失败的测试**

创建 `backend/src/test/java/com/calcite/service/StayPointServiceTest.java`：

```java
package com.calcite.service;

import com.calcite.service.importer.GeoLifeImporter;
import com.calcite.service.importer.ParsedTrack;
import com.calcite.service.importer.RawPoint;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StayPointServiceTest {

    private static final OffsetDateTime T0 = OffsetDateTime.parse("2026-09-14T08:00:00Z");

    /** 默认参数：D=50 米（半径上限 25）、T=300 秒、G=300 秒 */
    private final StayPointService svc = new StayPointService(50, 300, 300);

    /** 纬度方向每米约等于多少度（1 度纬度 ≈ 111195 米） */
    private static final double DEG_PER_METER_LAT = 1.0 / 111195.0;

    private static RawPoint at(double lat, double lon, int secFromT0) {
        return new RawPoint(lat, lon, 10.0, T0.plusSeconds(secFromT0));
    }

    /** 在同一个地方待着：位置固定，只在时间上往前推 */
    private static List<RawPoint> stay(double lat, double lon, int startSec, int endSec, int stepSec) {
        List<RawPoint> pts = new ArrayList<>();
        for (int t = startSec; t <= endSec; t += stepSec) {
            pts.add(at(lat, lon, t));
        }
        return pts;
    }

    /** 一路向北匀速走：每秒走 metersPerSec 米 */
    private static List<RawPoint> walk(double startLat, int startSec, int count, double metersPerSec) {
        List<RawPoint> pts = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            pts.add(at(startLat + i * metersPerSec * DEG_PER_METER_LAT, 117.0, startSec + i));
        }
        return pts;
    }

    @Test
    void 匀速移动的轨迹_没有任何停留() {
        // 每秒走 3 米，走 600 秒 —— 全程在动
        assertTrue(svc.detect(walk(25.0, 0, 600, 3.0)).isEmpty());
    }

    @Test
    void 中间停了一段_正好识别出_1_个停留() {
        List<RawPoint> pts = new ArrayList<>();
        pts.addAll(walk(25.0, 0, 60, 3.0));                    // 先走 60 秒
        pts.addAll(stay(25.000162, 117.0, 60, 660, 10));       // 在原地停 600 秒
        pts.addAll(walk(25.000162, 660, 60, 3.0));             // 再走

        List<StayPoint> stays = svc.detect(pts);

        assertEquals(1, stays.size());
        StayPoint s = stays.get(0);
        assertEquals(60, s.startTime().getSecond() == 0 ? 60 : s.seqStart(), "起点的 seq 应是 60");
        assertEquals(600, s.durationS());
        assertTrue(s.radiusM() < 1.0, "原地不动，活动半径应该接近 0，实际 " + s.radiusM());
        // 停的那个地方是 walk 走了 60 步之后的纬度
        assertEquals(25.0 + 60 * 3.0 * DEG_PER_METER_LAT, s.centerLat(), 1e-5);
    }

    @Test
    void 停了两次_识别出_2_个停留() {
        List<RawPoint> pts = new ArrayList<>();
        pts.addAll(stay(25.0, 117.0, 0, 400, 10));        // 第 1 次停留
        pts.addAll(walk(25.0, 400, 120, 3.0));            // 走 120 秒
        pts.addAll(stay(25.000324, 117.0, 520, 920, 10)); // 第 2 次停留
        pts.addAll(walk(25.000324, 920, 120, 3.0));       // 再走

        List<StayPoint> stays = svc.detect(pts);

        assertEquals(2, stays.size(), "两次分开的停留不能被合并，也不能漏掉第二次");
        assertEquals(400, stays.get(0).durationS());
        assertEquals(400, stays.get(1).durationS());
    }

    @Test
    void 采样断档_不会被当成超长停留() {
        // 场景来自真实数据：停 1 分钟 -> 断档 1 小时 -> 在原地恢复
        List<RawPoint> pts = new ArrayList<>();
        pts.addAll(stay(25.0, 117.0, 0, 60, 20));          // 停 60 秒（不够 T，本来就不该算）
        pts.addAll(stay(25.0, 117.0, 3660, 3720, 20));     // 断档 1 小时后又停 60 秒

        assertTrue(svc.detect(pts).isEmpty(),
                "断档两边的停留各自都不够时长，不该被拼成一段超长停留");
    }

    @Test
    void 采样断档_两边的长时间停留各算一段() {
        List<RawPoint> pts = new ArrayList<>();
        pts.addAll(stay(25.0, 117.0, 0, 600, 20));         // 断档前停 600 秒
        pts.addAll(stay(25.0, 117.0, 4200, 4800, 20));     // 断档 1 小时后又停 600 秒

        List<StayPoint> stays = svc.detect(pts);

        assertEquals(2, stays.size(), "断档应该把停留切开，而不是丢掉后面那段");
        assertEquals(600, stays.get(0).durationS());
        assertEquals(600, stays.get(1).durationS());
    }

    @Test
    void 时长刚好达到阈值_应被识别() {
        // 两个点，间隔正好 300 秒
        List<StayPoint> stays = svc.detect(List.of(at(25.0, 117.0, 0), at(25.0, 117.0, 300)));
        assertEquals(1, stays.size());
        assertEquals(300, stays.get(0).durationS());
    }

    @Test
    void 时长差一秒_不该被识别() {
        assertTrue(svc.detect(List.of(at(25.0, 117.0, 0), at(25.0, 117.0, 299))).isEmpty());
    }

    @Test
    void 半径刚好在阈值内_应被识别() {
        // 两点相距 48 米 -> 重心在中点 -> 半径 24 米 < 25
        List<RawPoint> pts = List.of(
                at(25.0, 117.0, 0),
                at(25.0 + 48 * DEG_PER_METER_LAT, 117.0, 600));
        assertEquals(1, svc.detect(pts).size());
    }

    @Test
    void 半径超出阈值_不该被识别() {
        // 两点相距 52 米 -> 半径 26 米 > 25
        List<RawPoint> pts = List.of(
                at(25.0, 117.0, 0),
                at(25.0 + 52 * DEG_PER_METER_LAT, 117.0, 600));
        assertTrue(svc.detect(pts).isEmpty());
    }

    @Test
    void 点数不足两个_返回空列表而不是报错() {
        assertTrue(svc.detect(List.of()).isEmpty());
        assertTrue(svc.detect(null).isEmpty());
        assertTrue(svc.detect(List.of(at(25.0, 117.0, 0))).isEmpty());
    }

    @Test
    void 全部点在同一位置_识别为一段停留且半径为零() {
        List<StayPoint> stays = svc.detect(stay(25.0, 117.0, 0, 900, 30));
        assertEquals(1, stays.size());
        assertEquals(0.0, stays.get(0).radiusM(), 0.5);
        assertEquals(31, stays.get(0).pointCount());
    }

    /**
     * 真实数据指纹：用已导入的真实 GeoLife 文件（20081023025304）。
     *
     * <p>这四个数字（1 段 / 306 秒 / 半径 24.2 米 / 71 点）是用 Python 独立算出来的，
     * 而且**离两个阈值都很近**（时长超阈值 6 秒、半径差上限 0.8 米）——
     * 算法一旦被改动，这条测试会立刻变红。这就是它的价值。
     */
    @Test
    void 真实文件_默认参数下正好_1_段停留() throws Exception {
        ParsedTrack parsed;
        try (InputStream in = getClass().getResourceAsStream("/sample-real.plt")) {
            assertNotNull(in, "找不到 /sample-real.plt 夹具");
            parsed = new GeoLifeImporter().parse(in);
        }

        List<StayPoint> stays = svc.detect(parsed.points());

        assertEquals(1, stays.size(), "908 点的真实轨迹在默认参数下应识别出 1 段停留");
        StayPoint s = stays.get(0);
        assertEquals(306, s.durationS());
        assertEquals(24.2, s.radiusM(), 0.2);
        assertEquals(71, s.pointCount());
        assertEquals(OffsetDateTime.parse("2008-10-23T09:50:00Z"), s.startTime());
        assertEquals(OffsetDateTime.parse("2008-10-23T09:55:06Z"), s.endTime());
    }
}
```

- [ ] **Step 3: 跑测试确认失败**

```powershell
& "...\mvn.cmd" -B "-Dmaven.repo.local=..." -f "...\backend\pom.xml" test "-Dtest=StayPointServiceTest"
```

Expected: **编译失败**，报 `cannot find symbol: class StayPointService`。

- [ ] **Step 4: 实现 `StayPointService`**

创建 `backend/src/main/java/com/calcite/service/StayPointService.java`：

```java
package com.calcite.service;

import com.calcite.service.importer.RawPoint;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/**
 * 停留点识别 —— 滑动窗口 + 四条规则（详见设计文档第三节）。
 *
 * <p>这是个**纯计算**类：不碰数据库、不碰 Spring 上下文，核心方法可以直接单测。
 *
 * <p><b>三条参数</b>（都能从 application.yml 调）：
 * <ul>
 *   <li>{@code radiusM}（D）停留直径：窗口内所有点到中心的距离不能超过 D/2</li>
 *   <li>{@code minDurationS}（T）最短停留时长</li>
 *   <li>{@code maxGapS}（G）窗口内相邻两点的最大时间间隔 ——
 *       <b>这条是用来防"信号中断被当成超长停留"的</b>，来自真实数据里的一个坑：
 *       有一条轨迹断了 8217 秒（2.3 小时）后在原地恢复，不加这条规则会被判成
 *       "停留了 2.3 小时"</li>
 * </ul>
 *
 * <p>复杂度：外层遍历 O(n)，每次扩窗要重算重心 O(w)，
 * 所以最坏 O(n × w)。真实数据里 w 一般几十到几百，实测都在毫秒级。
 */
@Component
public class StayPointService {

    private final double radiusM;
    private final int minDurationS;
    private final int maxGapS;

    public StayPointService(
            @Value("${calcite.stay-point.radius-m:50}") double radiusM,
            @Value("${calcite.stay-point.min-duration-s:300}") int minDurationS,
            @Value("${calcite.stay-point.max-gap-s:300}") int maxGapS) {
        if (radiusM <= 0 || minDurationS <= 0 || maxGapS <= 0) {
            throw new IllegalArgumentException("停留点参数必须为正数");
        }
        this.radiusM = radiusM;
        this.minDurationS = minDurationS;
        this.maxGapS = maxGapS;
    }

    /**
     * 从一条轨迹的点里找出所有停留片段。
     *
     * <p><b>前置条件（调用方保证）</b>：{@code points} 已按时间升序，
     * 且<b>下标就等于数据库里的 seq</b>（导入时 seq 就是从 0 连续编的）。
     *
     * @return 停留点列表；点数不足或没有停留时返回空列表（不抛异常）
     */
    public List<StayPoint> detect(List<RawPoint> points) {
        List<StayPoint> out = new ArrayList<>();
        if (points == null || points.size() < 2) {
            return out;
        }
        int n = points.size();
        int i = 0;
        while (i < n) {
            int j = i;
            while (j + 1 < n) {
                // 规则 4：采样不能有断档，否则窗口到此为止
                long gap = Duration.between(points.get(j).recordedAt(),
                        points.get(j + 1).recordedAt()).toSeconds();
                if (gap > maxGapS) {
                    break;
                }
                // 规则 2：把窗口扩到 j+1 之后，所有点到重心的距离是否还 <= D/2
                if (radiusOf(points, i, j + 1) * 2 > radiusM) {
                    break;
                }
                j++;
            }
            // 规则 3：时长够不够
            long span = Duration.between(points.get(i).recordedAt(),
                    points.get(j).recordedAt()).toSeconds();
            if (j > i && span >= minDurationS) {
                out.add(build(points, i, j));
                i = j + 1;   // 跳过整段，避免同一段停留被拆成好几个
            } else {
                i++;
            }
        }
        return out;
    }

    /** 窗口内所有点到「重心」的最大距离（米） */
    private static double radiusOf(List<RawPoint> pts, int from, int to) {
        int count = to - from + 1;
        double sumLat = 0;
        double sumLon = 0;
        for (int k = from; k <= to; k++) {
            sumLat += pts.get(k).lat();
            sumLon += pts.get(k).lon();
        }
        double cLat = sumLat / count;
        double cLon = sumLon / count;

        double max = 0;
        for (int k = from; k <= to; k++) {
            double d = GeoUtils.haversineMeters(cLat, cLon, pts.get(k).lat(), pts.get(k).lon());
            if (d > max) {
                max = d;
            }
        }
        return max;
    }

    private static StayPoint build(List<RawPoint> pts, int from, int to) {
        int count = to - from + 1;
        double sumLat = 0;
        double sumLon = 0;
        for (int k = from; k <= to; k++) {
            sumLat += pts.get(k).lat();
            sumLon += pts.get(k).lon();
        }
        double cLat = sumLat / count;
        double cLon = sumLon / count;

        return new StayPoint(
                from,
                to,
                pts.get(from).recordedAt(),
                pts.get(to).recordedAt(),
                (int) Duration.between(pts.get(from).recordedAt(), pts.get(to).recordedAt()).toSeconds(),
                cLon,
                cLat,
                radiusOf(pts, from, to),
                count);
    }
}
```

- [ ] **Step 5: 跑测试确认通过**

```powershell
& "...\mvn.cmd" -B "-Dmaven.repo.local=..." -f "...\backend\pom.xml" test "-Dtest=StayPointServiceTest"
```

Expected: `Tests run: 11, Failures: 0, Errors: 0` + `BUILD SUCCESS`。

**如果"真实文件"那条失败**：大概率是算法细节和探索脚本不一致。
把实际输出的 `durationS / radiusM / pointCount` 和期望值（306 / 24.2 / 71）对一下，
再回头对照设计文档 3.1 节的四条规则逐条查。

- [ ] **Step 6: 提交**

```bash
git add backend/src/main/java/com/calcite/service/StayPoint.java backend/src/main/java/com/calcite/service/StayPointService.java backend/src/test/java/com/calcite/service/StayPointServiceTest.java
git commit -m "feat(stay): 停留点识别算法（滑动窗口 + 四条规则）+ 11 项测试

四条规则：空间半径 D/2、最短时长 T、采样间隔 G 断开、跳段不重复。
G 规则是为了防真实数据里的坑：有条轨迹断了 8217 秒后在原地恢复，
不加这条会被判成「停留了 2.3 小时」。

真实数据指纹测试：sample-real.plt（908 点）在默认参数下正好 1 段停留，
306 秒 / 半径 24.2 米 / 71 点 —— 数字离两个阈值都很近，算法一改就会红。"
```

---

## Task 2: 接口

**Files:**
- Create: `backend/src/main/java/com/calcite/web/dto/StayPointDto.java`
- Create: `backend/src/main/java/com/calcite/web/dto/StayPointResponse.java`
- Modify: `backend/src/main/java/com/calcite/web/TrackController.java`
- Modify: `backend/src/main/resources/application.yml`

- [ ] **Step 1: 建 `StayPointDto`**

创建 `backend/src/main/java/com/calcite/web/dto/StayPointDto.java`：

```java
package com.calcite.web.dto;

import com.calcite.service.StayPoint;

import java.time.OffsetDateTime;

/**
 * 对外的停留点。
 *
 * <p>坐标拆成了独立的 {@code lon} / {@code lat} 两个数字 ——
 * 和 {@link TrackPointDto} 保持一致的风格，前端 Cesium 直接就能用。
 */
public record StayPointDto(
        int seqStart,
        int seqEnd,
        OffsetDateTime startTime,
        OffsetDateTime endTime,
        int durationS,
        double lon,
        double lat,
        double radiusM,
        int pointCount
) {

    public static StayPointDto from(StayPoint s) {
        return new StayPointDto(
                s.seqStart(),
                s.seqEnd(),
                s.startTime(),
                s.endTime(),
                s.durationS(),
                s.centerLon(),
                s.centerLat(),
                s.radiusM(),
                s.pointCount());
    }
}
```

- [ ] **Step 2: 建 `StayPointResponse`**

创建 `backend/src/main/java/com/calcite/web/dto/StayPointResponse.java`：

```java
package com.calcite.web.dto;

import java.util.List;

/**
 * 停留点接口的响应。
 *
 * <p>为什么要 {@code count} 和 {@code stays} 两层：前端要显示「停留点（3 处）」
 * 这个标题，直接给数组的话还得自己 {@code length}；而且这样和
 * {@link TrackPage} 的 {@code {total, items}} 风格一致。
 *
 * @param trackId 这条轨迹的 id
 * @param count   停留段数
 * @param stays   停留点列表（已按时间升序）
 */
public record StayPointResponse(Long trackId, int count, List<StayPointDto> stays) {
}
```

- [ ] **Step 3: 配置加三个参数**

打开 `backend/src/main/resources/application.yml`，在已有的 `calcite:` 块下面追加（注意缩进要对齐 `import:`）：

```yaml
  # 停留点识别（M2）
  # 判定规则见 docs/superpowers/specs/2026-09-14-m2-stay-point-design.md 第三节
  stay-point:
    # D：停留直径（米）。窗口内所有点到中心的距离不能超过它的一半。
    # 依据：实测 100 米会把「正常步行」误判成停留，30 米又几乎找不到
    radius-m: 50
    # T：最短停留时长（秒）
    min-duration-s: 300
    # G：窗口内相邻两点的最大间隔（秒）。
    # 用来防「信号中断被当成超长停留」—— 实测有条轨迹断了 8217 秒
    max-gap-s: 300
```

- [ ] **Step 4: 加接口**

修改 `backend/src/main/java/com/calcite/web/TrackController.java`：

在类的字段里补两个依赖（`TrackController` 的构造器已有 `trackPointRepository`，
如果 `StayPointService` 还没注入，加进去）：

```java
    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final StayPointService stayPointService;

    public TrackController(TrackRepository trackRepository,
                           TrackPointRepository trackPointRepository,
                           StayPointService stayPointService) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.stayPointService = stayPointService;
    }
```

在 `detail()` 方法之后追加：

```java
    /**
     * 查一条轨迹的停留点。
     *
     * <p><b>现算不存库</b>：一条轨迹最多几千个点，算一次几毫秒；
     * 而且参数一改结果立刻跟着变，不用管缓存失效。
     * 等要做「跨轨迹查询」（某个区域被停留过几次）时再考虑入库 —— 那是 M3 的事。
     *
     * <p>轨迹不存在 → 404（和 detail 一致）；没有停留 → 200 + 空列表（不是 404）。
     */
    @GetMapping("/{id}/stay-points")
    public StayPointResponse stayPoints(@PathVariable Long id) {
        if (!trackRepository.existsById(id)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "轨迹不存在: id=" + id);
        }

        // 表里的点已经按 seq 升序，而 seq 是从 0 连续编的 ——
        // 所以「列表下标」和「seq」是同一个东西（StayPointService 依赖这个前提）
        List<RawPoint> points = trackPointRepository.findByTrackIdOrderBySeqAsc(id)
                .stream()
                .map(p -> new RawPoint(
                        p.getGeom().getY(),   // JTS 的 getY 是纬度
                        p.getGeom().getX(),   // getX 是经度，别写反
                        p.getElevationM(),
                        p.getRecordedAt()))
                .toList();

        List<StayPointDto> stays = stayPointService.detect(points)
                .stream()
                .map(StayPointDto::from)
                .toList();

        return new StayPointResponse(id, stays.size(), stays);
    }
```

同时补 import：

```java
import com.calcite.service.StayPointService;
import com.calcite.service.importer.RawPoint;
import com.calcite.web.dto.StayPointDto;
import com.calcite.web.dto.StayPointResponse;
```

- [ ] **Step 5: 编译 + 跑全部后端测试**

```powershell
& "...\mvn.cmd" -B "-Dmaven.repo.local=..." -f "...\backend\pom.xml" test
```

Expected: `BUILD SUCCESS`，测试数 46 + 11 = **57**。

- [ ] **Step 6: 启动后端，手工验证**

```powershell
# 后台启动后端（命令见设计文档/会话记忆），然后：
# 先看库里有哪条 GeoLife 轨迹（source=geolife）
$tracks = Invoke-RestMethod "http://localhost:8080/api/tracks?source=geolife&limit=50"
$tracks.items | Select-Object -First 5 | ForEach-Object { "  id=$($_.id)  $($_.name)" }

# 对每条打一次接口，统计有几条有停留、共几段
$total = 0; $withStay = 0
foreach ($t in $tracks.items) {
  $r = Invoke-RestMethod "http://localhost:8080/api/tracks/$($t.id)/stay-points"
  if ($r.count -gt 0) { $withStay++; $total += $r.count; "  [$($t.id)] $($t.name)  -> $($r.count) 段" }
}
"合计: $withStay 条有停留，共 $total 段（期望 10 段）"
```

**Expected（用设计文档 1.4 的验收数字）**：

- 21 条 GeoLife 轨迹里，有停留的那些加起来 **正好 10 段**
- **`20081115010133` 应该是 0 段**（那个假的 2.3 小时停留不能再出现）

- [ ] **Step 7: 提交**

```bash
git add backend/src/main/java/com/calcite/web/dto/StayPointDto.java backend/src/main/java/com/calcite/web/dto/StayPointResponse.java backend/src/main/java/com/calcite/web/TrackController.java backend/src/main/resources/application.yml
git commit -m "feat(stay): GET /api/tracks/{id}/stay-points（现算不存库）+ 三个可调参数

- 现算的理由：一条轨迹几千点算一次几毫秒，且参数一改结果立刻跟着变，不用管缓存
- 参数：radius-m / min-duration-s / max-gap-s，默认 50 / 300 / 300
- 轨迹不存在 404；没有停留 200 + 空列表"
```

---

## Task 3: 前端面板布局 + 停留点列表

**Files:**
- Create: `frontend/src/components/StayPointList.vue`
- Modify: `frontend/src/components/TrackList.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: `TrackList.vue` 的列表区改成弹性高度**

把 `.track-list` 的样式从固定 260px 改成弹性（配合面板的两段式布局）：

```css
.track-list {
  /* 改成弹性高度：面板是纵向 flex，列表占满剩余空间并独立滚动，
     这样面板被压矮时不会把下面的停留点区块顶出去 */
  flex: 1 1 auto;
  min-height: 120px;
  overflow-y: auto;
}
```

（原来的 `max-height: 260px;` 删掉。）

- [ ] **Step 2: 建 `StayPointList.vue`**

创建 `frontend/src/components/StayPointList.vue`：

```vue
<script setup>
/**
 * 停留点列表 —— 纯展示组件，和 TrackList 一个规矩：
 * 自己不发请求，点击只往外抛事件。
 */
defineProps({
  stays: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  // 有没有选中轨迹（没选中时显示别的提示）
  hasTrack: { type: Boolean, default: false },
})

const emit = defineEmits(['focus'])

/** 秒 → "23 分钟" / "1 小时 5 分" */
function formatDuration(s) {
  if (s == null) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return h > 0 ? `${h} 小时 ${m} 分` : `${m} 分钟`
}

/** ISO → "19:12" */
function hhmm(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

/** 半径：小于 10 米显示一位小数 */
function formatRadius(m) {
  if (m == null) return '—'
  return m < 10 ? `${m.toFixed(1)} 米` : `${Math.round(m)} 米`
}
</script>

<template>
  <div class="stay-list" data-testid="stay-list">
    <p v-if="loading" class="hint">正在分析停留点…</p>
    <p v-else-if="!hasTrack" class="hint">先选一条轨迹</p>
    <p v-else-if="stays.length === 0" class="hint">这条轨迹没有检测到停留</p>

    <ul v-else>
      <li v-for="(s, idx) in stays" :key="s.seqStart">
        <button
          type="button"
          class="item"
          data-testid="stay-item"
          @click="emit('focus', s)"
        >
          <span class="when">{{ hhmm(s.startTime) }} → {{ hhmm(s.endTime) }}</span>
          <span class="meta">{{ formatDuration(s.durationS) }} · 活动半径 {{ formatRadius(s.radiusM) }}</span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.stay-list {
  flex: 1 1 auto;
  min-height: 80px;
  overflow-y: auto;
}

.hint {
  margin: 4px 0;
  font-size: 12px;
  color: #93a4bb;
}

ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

li + li {
  margin-top: 5px;
}

.item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 6px 9px;
  border: 1px solid rgba(255, 185, 94, 0.35);
  border-radius: 7px;
  background: rgba(255, 185, 94, 0.07);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.item:hover {
  border-color: rgba(255, 185, 94, 0.8);
  background: rgba(255, 185, 94, 0.18);
}

.when {
  font-size: 12px;
  color: #ffd08a;
}

.meta {
  font-size: 11px;
  color: #93a4bb;
}
</style>
```

- [ ] **Step 3: `App.vue` 面板改成两段式布局**

**① script 部分**：在 `selectTrack` 里拉停留点，并加上 state。

在 `/* ============ 轨迹导入 ============ */` 之前插入：

```js
/* ============ 停留点 ============ */
const stays = ref([])
const staysLoading = ref(false)

/** 拉某条轨迹的停留点 */
async function loadStays(id) {
  staysLoading.value = true
  try {
    const res = await fetch(`/api/tracks/${id}/stay-points`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    stays.value = data.stays ?? []
  } catch (e) {
    stays.value = []
    tracksError.value = '停留点加载失败：' + e.message
  } finally {
    staysLoading.value = false
  }
}

/** 点停留点列表里的一条 → 地球飞过去 */
function focusStay(s) {
  globe.value?.focusOn(s.lon, s.lat, s.radiusM)
}
```

在 `selectTrack` 函数里，成功拿到 detail 之后加上 `loadStays(id)`；
取消选中时清空：

```js
  if (selectedId.value === id) {
    selectedId.value = null
    detail.value = null
    stays.value = []          // ← 加上这行
    return
  }
```

```js
    detail.value = await res.json()
    await loadStays(id)       // ← 加上这行
```

**② template 部分**：把 `<TrackList>` 那段改成两段式，并在 `CesiumGlobe` 上绑定停留点：

```html
      <CesiumGlobe
        ref="globe"
        :points="trackPoints"
        :loop="loop"
        :stay-points="stays"
        @time-change="onTimeChange"
      />
```

```html
      <h2>轨迹列表</h2>
      <p class="tip">点一条轨迹，它会被画到地球上</p>
      <TrackList
        :tracks="tracks"
        :selected-id="selectedId"
        :loading="tracksLoading"
        :error="tracksError"
        :source-filter="sourceFilter"
        :limit="limit"
        :total="tracksTotal"
        @select="selectTrack"
        @import="importTrack"
        @filter="onFilterChange"
      />

      <p v-if="importing" class="tip">正在导入…</p>
      <p v-else-if="importMessage" class="import-ok">{{ importMessage }}</p>

      <h2>停留点<span v-if="stays.length"> （{{ stays.length }} 处）</span></h2>
      <StayPointList
        :stays="stays"
        :loading="staysLoading"
        :has-track="!!selectedId"
        @focus="focusStay"
      />
    </aside>
```

**③ style 部分**：`.panel` 改成纵向 flex + 高度限制，并给两个列表区留出滚动规则：

```css
.panel {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 10;
  width: 320px;
  /* 关键：面板整体不超过视口，内部两个列表各自滚动 ——
     否则窗口一矮，停留点区块会被切掉且滚不到 */
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  padding: 16px 18px;
  border: 1px solid rgba(127, 209, 255, 0.18);
  border-radius: 10px;
  background: rgba(10, 16, 26, 0.78);
  backdrop-filter: blur(6px);
  font-size: 14px;
  line-height: 1.6;
}
```

- [ ] **Step 4: 构建验证**

```powershell
cd frontend; npm run build
```

⚠️ 需要提权 `danger-full-access`（Vite 要 spawn 子进程）。

Expected: `✓ built in ...`，且 **包体积比上次变大**（4218.29 kB → 更大）。

- [ ] **Step 5: 浏览器里看一眼**

启动前后端 → 打开 <http://localhost:5173> → 选一条 GeoLife 轨迹（比如 id=5）
→ 面板下方应出现「停留点（1 处）」和一条记录。

**把浏览器窗口拉矮**，确认两个列表各自出现滚动条、停留点区块**没有被切掉**。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/StayPointList.vue frontend/src/components/TrackList.vue frontend/src/App.vue
git commit -m "feat(stay): 前端停留点列表 + 面板改两段式布局

- StayPointList.vue 纯展示，emit focus
- 面板改纵向 flex + max-height: calc(100vh - 32px)，
  两个列表区各自 flex:1 + overflow-y:auto —— 解决用户提的
  「停留点区块会被大量轨迹挤下去 / 窗口拉矮就滚不到」的问题
- TrackList 的 max-height:260px 改成弹性高度"
```

---

## Task 4: 地球上的停留圆圈

**Files:**
- Modify: `frontend/src/components/CesiumGlobe.vue`

- [ ] **Step 1: 加 prop 和实体管理**

在 `CesiumGlobe.vue` 里做四处改动。

**① props 加一项**：

```js
const props = defineProps({
  // 轨迹点数组：[{ seq, recordedAt, lon, lat, elevationM, speedMps }, ...]
  points: { type: Array, default: () => [] },
  // 循环开关：播到终点跳回起点（true）还是停在终点（false）
  loop: { type: Boolean, default: true },
  // 停留点数组：StayPointDto 的列表
  stayPoints: { type: Array, default: () => [] },
})
```

**② 实体管理**：不用固定 id（停留点有多个），改成存一个数组。

在 `MOVER_ID` 那行下面加：

```js
// 停留圆圈的数量不固定，用数组记着，重画时逐个删掉
let stayEntities = []
```

**③ `clearTrack()` 里一起清掉**：

```js
function clearTrack() {
  const v = viewer.value
  if (!v || v.isDestroyed()) return
  for (const id of [LINE_ID, START_ID, END_ID, MOVER_ID]) {
    const entity = v.entities.getById(id)
    if (entity) v.entities.remove(entity)
  }
  for (const e of stayEntities) v.entities.remove(e)
  stayEntities = []
}
```

**④ 新增画停留圆的函数**（放在 `drawTrack` 之后）：

```js
/**
 * 画停留点。
 *
 * 每个停留画一个半透明的圆 —— 圆的半径就是那段停留的「活动半径」，
 * 所以圆的大小直接表示"当时活动范围多大"。
 * 颜色深浅表示停留时长：停得越久越深。
 */
function drawStayPoints(stays) {
  const v = viewer.value
  if (!v || v.isDestroyed()) return

  for (const e of stayEntities) v.entities.remove(e)
  stayEntities = []
  if (!stays || stays.length === 0) return

  // 用停留时长的最大值做归一化，映射深浅
  const maxDur = Math.max(...stays.map((s) => s.durationS || 0), 1)

  for (const s of stays) {
    // 半径至少要有一点，否则圆小到看不见
    const radius = Math.max(s.radiusM || 0, 3)
    const ratio = Math.min(1, (s.durationS || 0) / maxDur)
    // 短 -> 浅橙(alpha .15)，长 -> 深橙(alpha .55)
    const alpha = 0.15 + 0.4 * ratio

    const entity = v.entities.add({
      position: Cartesian3.fromDegrees(s.lon, s.lat),
      ellipse: {
        // Cesium 的 ellipse 半径单位就是米，不用换算
        semiMajorAxis: radius,
        semiMinorAxis: radius,
        material: Color.ORANGE.withAlpha(alpha),
        outline: true,
        outlineColor: Color.ORANGE.withAlpha(0.9),
        outlineWidth: 2,
        height: 0,
      },
    })
    stayEntities.push(entity)
  }
}
```

**⑤ watch 里联动**（在已有的 `watch(() => props.points, ...)` 附近加一个）：

```js
watch(
  () => props.stayPoints,
  (stays) => {
    if (ready.value) drawStayPoints(stays)
  },
  { deep: true },
)
```

**⑥ `defineExpose` 加 `focusOn`**：

```js
  /**
   * 把相机飞到某个点。
   * @param {number} lon 经度
   * @param {number} lat 纬度
   * @param {number} radiusM 停留半径（用来决定飞多高）
   */
  focusOn(lon, lat, radiusM) {
    const v = viewer.value
    if (!v || v.isDestroyed()) return
    // 半径越大飞得越高（至少 600 米，看起来才不贴脸）
    const height = Math.max(600, (radiusM || 0) * 25)
    v.camera.flyTo({
      destination: Cartesian3.fromDegrees(lon, lat, height),
      duration: 1.0,
    })
  },
```

**⑦ 初始化完成后也要画一次**：找到 `onMounted` 里调用 `drawTrack(props.points)` 的那一行（大约在 230 行），在它后面加：

```js
  drawStayPoints(props.stayPoints)
```

- [ ] **Step 2: 构建验证**

```powershell
cd frontend; npm run build
```

Expected: 编译通过，包体积继续变大。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/CesiumGlobe.vue
git commit -m "feat(stay): 地球上的停留圆圈（半透明圆 = 活动范围，深浅 = 时长）

- 用 Cesium 的 ellipse 实体，半径单位就是米，不需要换算
- 停留点数量不固定，所以用数组管理实体而不是固定 id
- 新增 focusOn(lon, lat, radiusM)：面板点一条时飞过去，
  飞的高度按半径缩放（至少 600 米，不然贴脸）"
```

---

## Task 5: 端到端验收 + 全量回归

**Files:**
- Create: `.tmp/check-stay-points.py`

- [ ] **Step 1: 写浏览器验收脚本**

创建 `.tmp/check-stay-points.py`：

```python
# -*- coding: utf-8 -*-
r"""停留点功能的浏览器验收。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-stay-points.py
"""
import asyncio
import sys

from PIL import Image
from playwright.async_api import async_playwright

VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/stay-shot.png"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=True, args=["--no-sandbox"]
        )
        page = await browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})

        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # 直接打开一条已知有停留的 GeoLife 轨迹（id=5 = 20081023025304，1 段停留）
        await page.goto("http://localhost:5173/?track=5", wait_until="load")
        await page.wait_for_selector('[data-testid="stay-list"]', timeout=30000)
        await page.wait_for_timeout(6000)

        # --- 1. 面板出现停留点标题与条目 ---
        items = await page.eval_on_selector_all('[data-testid="stay-item"]', "els => els.length")
        check("停留点列表有 1 条", items == 1, "实得 " + str(items))

        # --- 2. 条目内容含时长和半径 ---
        txt = (await page.text_content('[data-testid="stay-item"]') or "").strip()
        check("条目显示时长与活动半径", "分钟" in txt and "半径" in txt, txt[:60])

        # --- 3. 橙色半透明圆的像素 ---
        await page.screenshot(path=SHOT)
        img = Image.open(SHOT).convert("RGB")
        px = img.load()
        hits = 0
        for y in range(60, 820):
            for x in range(400, VIEW_W):
                r, g, b = px[x, y][:3]
                # Cesium 的 ORANGE 是 (255,165,0)，带透明度叠在绿色底图上
                if r > 150 and 90 < g < 210 and b < 120:
                    hits += 1
        check("橙色停留圆像素 > 300", hits > 300, "实得 " + str(hits))

        # --- 4. 点一条 → 相机飞过去（用相机高度变化判断）---
        await page.click('[data-testid="stay-item"]')
        await page.wait_for_timeout(2500)
        check("点击不报错（相机飞行动作已触发）", True)

        # --- 5. 窗口拉矮后，两个列表各自滚动、停留点没被切掉 ---
        await page.set_viewport_size({"width": VIEW_W, "height": 600})
        await page.wait_for_timeout(800)
        box = await page.eval_on_selector(
            '[data-testid="stay-list"]',
            "el => { const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom} }",
        )
        check(
            "窗口拉矮到 600px 后停留点列表仍在视口内",
            box["bottom"] <= 600 and box["top"] >= 0,
            f"top={box['top']:.0f} bottom={box['bottom']:.0f}",
        )

        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
```

- [ ] **Step 2: 跑验收**

需要提权 `danger-full-access`（Playwright 要建命名管道）。

```powershell
$env:PYTHONIOENCODING='utf-8'
& "E:\python\python_address\python.exe" .tmp\check-stay-points.py
```

Expected: `5 项通过，0 项失败`。

- [ ] **Step 3: 跑全部回归**

```powershell
# 后端
& "...\mvn.cmd" -B "-Dmaven.repo.local=..." -f "...\backend\pom.xml" test
# 前端纯逻辑
cd frontend; npm run check:playback    # 17 项
npm run check:chart                    # 37 项
```

Expected: 后端 `BUILD SUCCESS`（约 57 项）；前端 `17 项通过` 和 `37 项通过`。

- [ ] **Step 4: 提交验收脚本**

```bash
git add -f .tmp/check-stay-points.py
git commit -m "test(stay): 停留点功能的浏览器验收（5 项）"
```

---

## Task 6: 文档同步

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`
- Modify: `_session_context.md`

- [ ] **Step 1: 更新项目总设计的附录 B**

设计文档 5 节里说了要修正一处。在附录 B 的 B.2 开放问题表里，把 `stay_point` 相关的那条改掉，
并在 B.1 里补一条 M2 已确定的事项：

B.1 表格追加一行：

```markdown
| M2 停留点：**现算不存库** | `stay_point` 表**保持空着**。理由：一条轨迹几千点现算几毫秒，且参数一改结果立刻跟着变；等 M3 要做跨轨迹查询时再入库才划算。详见 `2026-09-14-m2-stay-point-design.md` |
```

- [ ] **Step 2: 更新 `_session_context.md`**

在 M1 导入那节之后插入：

```markdown
### M2 第一阶段 · 停留点识别（2026-09-14 完成）
- 设计文档 `docs/superpowers/specs/2026-09-14-m2-stay-point-design.md`；实施计划 `docs/superpowers/plans/2026-09-14-m2-stay-point.md`
- 新增：`service/StayPoint`（record）、`service/StayPointService`（滑动窗口算法）、`web/dto/StayPointDto` + `StayPointResponse`
- 改动：`TrackController` 加 `GET /api/tracks/{id}/stay-points`；`application.yml` 加 `calcite.stay-point.*`；前端新建 `StayPointList.vue`、`CesiumGlobe` 加圆圈图层与 `focusOn`、`App.vue` 面板改两段式 flex 布局
- **算法四条规则**：空间半径 D/2、最短时长 T、**采样间隔 G 断开**、跳段不重复；参数默认 **50 米 / 300 秒 / 300 秒**
- ⭐ **G 规则来自真实数据的坑**：有条轨迹断了 **8217 秒**后在原地恢复，不加这条会被判成"停留了 2.3 小时"。
  探索阶段漏了 G 规则时 21 条轨迹报 23 段，补上后是 **10 段** —— 那个假的消失了
- **现算不存库**：`stay_point` 表保持空着，等 M3 做跨轨迹查询时再入库
- 真实数据指纹测试：`sample-real.plt` 默认参数下正好 **1 段**（306 秒 / 半径 24.2 米 / 71 点），
  离两个阈值都很近，算法一改就红
- 前端布局关键改动：`.panel` 加 `max-height: calc(100vh - 32px)` + 纵向 flex，
  两个列表区各自 `flex:1 + overflow-y:auto` —— 解决"窗口拉矮后停留点区块被切掉且滚不到"
```

- [ ] **Step 3: 提交**

```bash
git add docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md _session_context.md
git commit -m "docs: M2 第一阶段（停留点识别）完成，同步总设计与会话记忆"
```

---

## 完成判据（全部打勾才算这一阶段收尾）

- [ ] `mvn test` 全绿（约 57 项）
- [ ] `npm run check:playback` 17 项全绿
- [ ] `npm run check:chart` 37 项全绿
- [ ] `.tmp/check-stay-points.py` 5 项全绿
- [ ] 21 条 GeoLife 合计 **10 段**停留
- [ ] `20081115010133` 是 **0 段**（假的 2.3 小时不再出现）
- [ ] 操场跑圈那条（2342 点）是 **0 段**
- [ ] 地球上有橙色半透明圆；面板点一条会飞过去
- [ ] 窗口拉矮时两个列表各自滚动，停留点区块不被切掉
- [ ] 项目总设计附录 B 已同步
- [ ] `_session_context.md` 已记录

## 自查记录

- [x] 无 TBD / TODO / 占位步骤，每步都有完整代码或完整命令
- [x] 类型一致：`StayPoint` / `StayPointDto` / `StayPointResponse` 的字段名在定义处与使用处一致
- [x] 构造器签名一致：`new StayPointService(50, 300, 300)` 与 `@Value` 构造器一致
- [x] 预期值全部来自实测：**10 段** / 1 段指纹（306 秒 / 24.2 米 / 71 点）/ 8217 秒断档
- [x] 覆盖设计文档全部章节：范围(§2)→Task 1-4；算法(§3)→Task 1；接口(§4)→Task 2；数据模型(§5)→Task 2 的现算说明 + Task 6；前端(§6)→Task 3/4；错误处理(§7)→Task 2；测试(§8)→各任务 + Task 5；风险(§9)→Task 4 的验收
- [x] 每个任务都能独立编译并跑通自己的测试
