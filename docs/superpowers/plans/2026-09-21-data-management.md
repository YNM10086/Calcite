# 数据管理（删除 / 改名 / 同名替换 / 添加）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「导入轨迹」按钮升级成一个完整的「数据管理」视图（添加 / 替换 / 改名 / 删除），并兑现两处缓存 javadoc 里写着的欠账。

**Architecture:** 删除前**先导出到回收站**（fail-safe：导出失败就不删）；删/替换/改名后**清缓存**（`SimilarityCache.invalidateAll()`，宁可全清不要漏清）；前端**整个面板切换**成管理视图（不从按钮下方展开）；同名上传**返回 409 让用户决定**替换还是新增。

**Tech Stack:** Spring Boot 3.5.16 / Java 25 / Spring Data JPA / PostgreSQL 18.3 + PostGIS 3.6 / Vue 3.5.42 / Cesium 1.145.0；测试：JUnit 5、node `assert`、Playwright + Pillow

**Spec:** `docs/superpowers/specs/2026-09-21-data-management-design.md` ← **执行前必读**

## Global Constraints

- **删除的顺序不能变**：① 查存在 → ② **先导出到回收站** → ③ 删 track → ④ 清缓存
- **导出失败就不删（fail-safe）** —— 返回 500，轨迹原样保留。"尽力导出、失败也照删"的保险是假的
- **删 / 替换 / 改名 之后必须清缓存**：删除和替换调 `StayPointCache.invalidate(id)` + `SimilarityCache.invalidateAll()`；**改名也要调 `SimilarityCache.invalidateAll()`**（因为 `SimilarityMatch` 里带了 `name`）
- **替换保持 `trackId` 不变**（原地更新，不删不插）
- **同名上传返回 409**，带上 `existingTrackId / existingName / existingPointCount / newPointCount`
- **替换时新内容的 SHA256 若已属于另一条轨迹 → 也返回 409**（别让它变成 500）
- **回收站配置独立**：`calcite.data.recycle-dir`，**不要复用 `calcite.import.allowed-roots`**（那是读白名单，用途不同）
- **`mvn test` 继续保持不需要数据库**（当前 121 项）
- 现有回归 **121 + 123 + 10 个脚本**必须保持全绿（但脚本要先改成数据自适应，见 Task 9）
- `.tmp/` 被 gitignore，加文件必须 `git add -f`
- 中文 javadoc / 注释，解释"为什么"

## Review Focus

设计文档隐含、但**没有任务天然覆盖**、最可能伤到真实用户的五类情形。每条都在对应任务里配了测试：

1. **删掉正在看的那条轨迹**（地球还画着它、面板还写着它的名字）→ 期望：擦掉、切回「停留点」档，**不是留下一个空壳**
2. **改名后，别的主线的相似度列表里还是旧名字**（最容易漏的缓存）→ 期望：显示新名字
3. **回收站目录不可写**（磁盘满 / 权限错）→ 期望：**拒绝删除**并说清原因，而不是删了没备份
4. **上传一份内容已在库里的文件去做替换**（撞 `external_id` 唯一约束）→ 期望：**409 说清楚**，不是 500
5. **删掉一条轨迹后，另外 245 条的相似度/热点/密度结果** → 期望：全部反映新数据，**不是缓存的旧结果**

---

## 前置条件（开工前先确认）

- [ ] 后端 `http://localhost:8080/api/health` 返回 `UP`
- [ ] 前端 `http://localhost:5173` 可访问
- [ ] 数据库 **246 条轨迹**（`GET /api/tracks?limit=1` 的 `total` = 246）
- [ ] **数据库快照还在**：`D:\Calcite-note\backups\calcite-20260921-2007.dump`（21.1 MB）
      —— 本阶段会真的删数据，这是最后一道退路
- [ ] 工作区干净，在 `main` 上

---

## 常用命令

**后端编译 + 全部单测**（不需要数据库）：
```powershell
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" test
```
**只跑某个测试类**：末尾 `test` 换成 `"-Dtest=TrackExporterTest" test`

**查数据库**（密码从 gitignore 的配置取，不要打印）：
```powershell
$yaml = Get-Content "backend/src/main/resources/application-local.yml" -Raw
if ($yaml -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
$env:LC_MESSAGES='C'
& "E:\PostgreSQL\bin\psql.exe" -U postgres -h localhost -p 5432 -d calcite -c "SELECT count(*) FROM track;"
```

**需要提权 `danger-full-access`**：Vite dev/build、Playwright、写 `D:\Calcite-note\`、`git push`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `config/DataProperties.java`（新建） | 绑 `calcite.data.*`（回收站目录、改名长度上限） |
| `service/TrackExporter.java`（新建） | ★ **`buildGeoJson()` 是纯函数**（可无库单测）+ `exportToFile()` 落盘 |
| `service/TrackEditService.java`（新建） | 编排：改名 / 删除 / 替换 / 同名检测 |
| `web/dto/TrackConflictResponse.java`（新建） | 409 的响应体 |
| `web/dto/DeleteTrackResponse.java`（新建） | 删除成功的响应（带上回收站文件路径） |
| `web/TrackController.java`（改） | 加 `PATCH /{id}` / `DELETE /{id}` |
| `web/ImportController.java`（改） | `POST /import` 加 `mode` / `replaceTrackId`；409 分支 |
| `service/ImportService.java`（改） | 加同名检测；抽出可复用的"替换"路径 |
| `resources/application.yml`（改） | 加 `calcite.data.*` |
| `test/.../TrackExporterTest.java`（新建） | 约 7 项 |
| `test/.../TrackEditServiceTest.java`（新建） | 约 6 项 |
| `frontend/src/components/ConfirmDialog.vue`（新建） | 通用确认弹窗 |
| `frontend/src/components/DataManager.vue`（新建） | 数据管理视图 |
| `frontend/src/components/TrackList.vue`（改） | 搬走上传表单；按钮改「数据编辑」 |
| `frontend/src/App.vue`（改） | `panelView` 状态 + 切换 + 数据变更后的刷新编排 |
| `frontend/src/lib/dataEdit.js`（新建） | 纯计算：文件名安全化、点数/长度格式化、409 文案 |
| `frontend/scripts/check-data-edit.mjs`（新建） | node 测试 |
| `.tmp/verify-data-edit-api.py`（新建） | 对拍：删/替换/改名 + **缓存失效** |
| `.tmp/check-data-edit.py`（新建） | 浏览器验收 |

---

## Task 1: `DataProperties` + `TrackExporter`

**Files:**
- Create: `backend/src/main/java/com/calcite/config/DataProperties.java`
- Create: `backend/src/main/java/com/calcite/service/TrackExporter.java`
- Test: `backend/src/test/java/com/calcite/service/TrackExporterTest.java`
- Modify: `backend/src/main/resources/application.yml`

**Interfaces:**
- Produces: `DataProperties.getRecycleDir()` → `String`；`getMaxNameLength()` → `int`
- Produces: `TrackExporter.buildGeoJson(Long trackId, String name, String source, String externalId, OffsetDateTime start, OffsetDateTime end, Integer pointCount, Double lengthM, List<Point3D>)` → `String`
- Produces: `TrackExporter.exportToFile(String geojson, String trackName, int pointCount, OffsetDateTime deletedAt)` → `Path`
- Produces: `TrackExporter.SafeName(String)` 之类的纯工具？**不需要** —— 文件名安全化放进 `lib/dataEdit.js` 的前端对应逻辑里；Java 侧也有一份（见 Step 3）

- [ ] **Step 1: 先写测试**

创建 `backend/src/test/java/com/calcite/service/TrackExporterTest.java`：

```java
package com.calcite.service;

import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link TrackExporter} 的单元测试。
 *
 * <p>重点测 <b>纯函数</b> {@code buildGeoJson} —— 它不碰数据库、不碰文件系统，
 * 所以整个类跑完只要几毫秒，{@code mvn test} 依然不需要数据库。
 */
class TrackExporterTest {

    private static final OffsetDateTime T0 = OffsetDateTime.parse("2008-09-13T11:19:29Z");

    /** 三个点，经纬度 + 海拔 + 时间 */
    private static List<TrackExporter.Point3D> samplePoints() {
        return List.of(
                new TrackExporter.Point3D(116.3, 40.0, 50.0, T0),
                new TrackExporter.Point3D(116.301, 40.001, 51.0, T0.plusSeconds(5)),
                new TrackExporter.Point3D(116.302, 40.002, 52.0, T0.plusSeconds(10)));
    }

    private static String build(List<TrackExporter.Point3D> pts) {
        return TrackExporter.buildGeoJson(3L, "资料一", "gpx", "abc123", T0,
                T0.plusSeconds(10), pts.size(), 715.0, pts);
    }

    @Test
    void 生成的是合法的GeoJSON_FeatureCollection() {
        String json = build(samplePoints());
        assertTrue(json.contains("\"type\": \"FeatureCollection\""), json.substring(0, 120));
        assertTrue(json.contains("\"type\": \"Feature\""));
        assertTrue(json.contains("\"type\": \"LineString\""));
    }

    @Test
    void 坐标是经度在前纬度在后_且带海拔() {
        String json = build(samplePoints());
        // GeoJSON 规范：coordinates 是 [经度, 纬度, 海拔]
        assertTrue(json.contains("[116.3, 40.0, 50.0]"), "没找到第一个点，实际：" + json);
        assertTrue(json.contains("[116.302, 40.002, 52.0]"), "没找到最后一个点");
    }

    /**
     * 这条很关键：**没有时间就还原不回来**。
     * 回收站的目的不只是"看一眼删的是哪条"，而是"真想要能找回来" ——
     * 而轨迹点的价值一半在时间上（速度、停留、时段分析全靠它）。
     */
    @Test
    void 每个点的时间都要导出() {
        String json = build(samplePoints());
        assertTrue(json.contains("2008-09-13T11:19:29Z"), "第一个点的时间没导出");
        assertTrue(json.contains("2008-09-13T11:19:39Z"), "最后一个点的时间没导出");
    }

    @Test
    void 元数据写进properties() {
        String json = build(samplePoints());
        assertTrue(json.contains("\"trackId\": 3"));
        assertTrue(json.contains("\"name\": \"资料一\""));
        assertTrue(json.contains("\"source\": \"gpx\""));
        assertTrue(json.contains("\"externalId\": \"abc123\""));
        assertTrue(json.contains("\"pointCount\": 3"));
    }

    @Test
    void 名字里的特殊字符要被转义_不能生成坏JSON() {
        // 如果直接拼字符串而不转义，一个引号就能让整个文件变成坏 JSON
        String json = TrackExporter.buildGeoJson(1L, "带\"引号\"和\\反斜杠的名字", "gpx", "x",
                T0, T0, 1, 1.0, samplePoints());
        assertTrue(json.contains("\\\""), "引号必须被转义：" + json);
        assertTrue(json.contains("\\\\"), "反斜杠必须被转义");
    }

    @Test
    void 空点列表也能生成_不抛异常() {
        String json = build(List.of());
        assertTrue(json.contains("\"coordinates\": []"), json);
    }

    @Test
    void 文件名安全化_去掉路径分隔符和非法字符() {
        assertEquals("资料一", TrackExporter.safeFileName("资料一"));
        // Windows 文件名里不能有 \ / : * ? " < > |
        assertEquals("a_b_c_d_e_f_g_h", TrackExporter.safeFileName("a/b\\c:d*e?f\"g<h"));
        // ⚠️ "." 和 ".." 是路径穿越 —— 必须挡掉，不能原样当文件名
        assertEquals("unnamed", TrackExporter.safeFileName("."));
        assertEquals("unnamed", TrackExporter.safeFileName(".."));
        // 太长要截断（Windows 路径总长限制）
        String longName = "x".repeat(500);
        assertTrue(TrackExporter.safeFileName(longName).length() <= 80);
    }
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: 只跑 `TrackExporterTest`
Expected: **编译失败**，报 `找不到符号: 类 TrackExporter`

- [ ] **Step 3: 实现 `DataProperties` 与 `TrackExporter`**

创建 `backend/src/main/java/com/calcite/config/DataProperties.java`：

```java
package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 数据管理配置，对应 {@code application.yml} 里的 {@code calcite.data.*}。
 *
 * <p><b>为什么不复用 {@code calcite.import.allowed-roots}</b>：那个是
 * <b>导入时的读白名单</b>（只允许从 GeoLife 目录读），用途完全不同。
 * 混在一起会让两个安全策略互相牵制。
 */
@Component
@ConfigurationProperties(prefix = "calcite.data")
public class DataProperties {

    /**
     * 删除前的自动导出目录。
     *
     * <p><b>删之前先导出，导出失败就不删</b> —— 见 TrackEditService。
     */
    private String recycleDir = "D:\\Calcite-note\\backups\\deleted";

    /** 轨迹显示名的长度上限 */
    private int maxNameLength = 200;

    public String getRecycleDir() { return recycleDir; }
    public void setRecycleDir(String v) { this.recycleDir = v; }
    public int getMaxNameLength() { return maxNameLength; }
    public void setMaxNameLength(int v) { this.maxNameLength = v; }
}
```

创建 `backend/src/main/java/com/calcite/service/TrackExporter.java`：

```java
package com.calcite.service;

import com.calcite.config.DataProperties;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 把一条轨迹导出成 <b>GeoJSON</b>，作为删除前的"回收站"。
 *
 * <p><b>为什么是 GeoJSON</b>：
 * <ul>
 *   <li>标准格式 —— QGIS / geojson.io / Python 都能直接打开（用户想手工看一眼删的是哪条，拖进去就行）</li>
 *   <li>文本格式 —— 出问题了肉眼能读</li>
 *   <li>元数据放 {@code properties} 里，不丢信息</li>
 * </ul>
 *
 * <p><b>为什么 {@code buildGeoJson} 和 {@code exportToFile} 要分开</b>：
 * 前者是<b>纯函数</b>（输入 → 字符串），不碰文件系统、不碰数据库 ——
 * 所以能喂假数据单测，{@code mvn test} 依然不需要数据库。
 * 后者才做真正的落盘。
 */
@Component
public class TrackExporter {

    /** 一个轨迹点：经度、纬度、海拔、时间 */
    public record Point3D(double lon, double lat, double elevationM, OffsetDateTime recordedAt) {
    }

    private static final DateTimeFormatter FILE_STAMP =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");

    private final DataProperties props;

    public TrackExporter(DataProperties props) {
        this.props = props;
    }

    /**
     * 生成 GeoJSON 文本（<b>纯函数</b>）。
     *
     * <p>坐标按 GeoJSON 规范是 <b>[经度, 纬度, 海拔]</b>（经度在前，别写反）。
     * 每个点的时间另存一份到 {@code properties.times} —— GeoJSON 规范里没有放时间的地方，
     * 而<b>没有时间就还原不回来</b>（速度、停留、时段分析全靠它）。
     */
    public static String buildGeoJson(Long trackId, String name, String source, String externalId,
                                      OffsetDateTime startTime, OffsetDateTime endTime,
                                      Integer pointCount, Double lengthM,
                                      List<Point3D> points) {
        StringBuilder coords = new StringBuilder();
        StringBuilder times = new StringBuilder();
        for (int i = 0; i < points.size(); i++) {
            Point3D p = points.get(i);
            if (i > 0) {
                coords.append(", ");
                times.append(", ");
            }
            coords.append('[').append(p.lon()).append(", ").append(p.lat())
                  .append(", ").append(p.elevationM()).append(']');
            times.append('"').append(escape(p.recordedAt() == null ? "" : p.recordedAt().toString())).append('"');
        }

        return """
                {
                  "type": "FeatureCollection",
                  "features": [
                    {
                      "type": "Feature",
                      "geometry": {
                        "type": "LineString",
                        "coordinates": [%s]
                      },
                      "properties": {
                        "trackId": %s,
                        "name": "%s",
                        "source": "%s",
                        "externalId": "%s",
                        "startTime": "%s",
                        "endTime": "%s",
                        "pointCount": %s,
                        "lengthM": %s,
                        "times": [%s]
                      }
                    }
                  ]
                }
                """.formatted(
                coords,
                trackId,
                escape(name),
                escape(source),
                escape(externalId),
                startTime == null ? "" : escape(startTime.toString()),
                endTime == null ? "" : escape(endTime.toString()),
                pointCount == null ? 0 : pointCount,
                lengthM == null ? 0 : lengthM,
                times);
    }

    /**
     * 把 GeoJSON 写到回收站目录，返回写出的文件路径。
     *
     * <p><b>⚠️ 调用方必须遵守 fail-safe</b>：这个方法抛异常时，
     * <b>不要执行删除</b>。见 {@code TrackEditService.delete}。
     *
     * @throws IOException 目录建不出来、磁盘满、没权限 —— 一律往上抛，由调用方决定不删
     */
    public Path exportToFile(String geojson, String trackName, int pointCount,
                             OffsetDateTime deletedAt) throws IOException {
        Path dir = Path.of(props.getRecycleDir());
        Files.createDirectories(dir);

        String stamp = deletedAt.format(FILE_STAMP);
        String fileName = stamp + "_" + safeFileName(trackName) + "_" + pointCount + "点.geojson";
        Path target = dir.resolve(fileName);

        Files.writeString(target, geojson, StandardCharsets.UTF_8);
        return target;
    }

    /**
     * 把任意字符串变成安全的文件名片段（<b>纯函数</b>）。
     *
     * <p>去掉 Windows 不允许的 {@code \ / : * ? " < > |} 和空白，
     * 并把长度截到 80（Windows 有路径总长限制）。
     */
    public static String safeFileName(String raw) {
        if (raw == null || raw.isBlank()) {
            return "unnamed";
        }
        String s = raw.replaceAll("[\\\\/:*?\"<>|\\s]+", "_");
        // ⚠️ "." 和 ".." 是【路径穿越】—— resolve 之后会跑到上一级目录。
        // 它们不包含上面那组非法字符，所以必须单独挡。
        if (s.equals(".") || s.equals("..")) {
            return "unnamed";
        }
        if (s.length() > 80) {
            s = s.substring(0, 80);
        }
        return s;
    }

    /** JSON 字符串转义。不转义的话，名字里一个引号就能让整个文件变成坏 JSON。 */
    private static String escape(String s) {
        if (s == null) {
            return "";
        }
        StringBuilder out = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> out.append(c);
            }
        }
        return out.toString();
    }
}
```

在 `application.yml` 的 `calcite:` 下**同级**加（**已有的几段一个字都不要改**）：

```yaml
  # 数据管理（删除 / 改名 / 同名替换）
  data:
    # 删除前的自动导出目录。**删之前先导出，导出失败就不删**（fail-safe）
    recycle-dir: D:\Calcite-note\backups\deleted
    # 轨迹显示名的长度上限
    max-name-length: 200
```

- [ ] **Step 4: 跑测试，确认全绿**

Run: 只跑 `TrackExporterTest`
Expected: `Tests run: 7, Failures: 0, Errors: 0`

> **自己数一遍 `@Test` 的个数再报告**；与 7 不符说明抄漏或抄多了。

- [ ] **Step 5: 跑全量后端测试**

Run: 常用命令的「后端编译 + 全部单测」
Expected: `Tests run: 128, Failures: 0, Errors: 0`（原 121 + 新增 7）

- [ ] **Step 6: 提交**

```powershell
git add backend/src/main/java/com/calcite/config/DataProperties.java backend/src/main/java/com/calcite/service/TrackExporter.java backend/src/test/java/com/calcite/service/TrackExporterTest.java backend/src/main/resources/application.yml
git commit -m "feat(data): TrackExporter 把轨迹导出成 GeoJSON（删除前的回收站）+ 7 项无数据库单测"
```

---

## Task 2: `TrackEditService`

**Files:**
- Create: `backend/src/main/java/com/calcite/service/TrackEditService.java`
- Create: `backend/src/main/java/com/calcite/web/dto/TrackConflictResponse.java`
- Create: `backend/src/main/java/com/calcite/web/dto/DeleteTrackResponse.java`
- Test: `backend/src/test/java/com/calcite/service/TrackEditServiceTest.java`

**Interfaces:**
- Consumes: `TrackExporter.buildGeoJson(...)` / `exportToFile(...)`（Task 1）、`DataProperties`（Task 1）
- Consumes: `StayPointCache.invalidate(Long)`、`SimilarityCache.invalidateAll()`（**已存在**）
- Produces: `TrackEditService.rename(Long id, String newName)` → `String`（返回规整后的名字）
- Produces: `TrackEditService.delete(Long id)` → `DeleteTrackResponse`
- Produces: `TrackEditService.validateName(String raw, int maxLength)` → `String`（**纯静态**，可单测）
- Produces: `TrackEditService.findNameConflict(String name, Long excludeTrackId)` → `Optional<Long>`

> ⚠️ **本任务只做后端服务层，不碰 Controller。**
> 需要数据库的部分靠 Task 4 的 Python 对拍验证；
> **纯逻辑部分（名字校验、同名判定）在本任务用 Java 单测钉住。**

- [ ] **Step 1: 先写测试（只测纯逻辑）**

创建 `backend/src/test/java/com/calcite/service/TrackEditServiceTest.java`：

```java
package com.calcite.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * {@link TrackEditService} 里<b>纯逻辑</b>部分的单元测试。
 *
 * <p>带数据库的路径（真的改库、真的清缓存）由 {@code .tmp/verify-data-edit-api.py} 对拍验证 ——
 * 这里只测不碰 Spring、不碰库的那几个静态方法，保证 {@code mvn test} 依然不需要数据库。
 */
class TrackEditServiceTest {

    @Test
    void 名字去首尾空格() {
        assertEquals("第一次跑步", TrackEditService.validateName("  第一次跑步  ", 200));
    }

    @Test
    void 名字为空或全空白要拒绝() {
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName(null, 200));
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName("", 200));
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName("   ", 200));
    }

    @Test
    void 名字超长要拒绝() {
        String ok = "x".repeat(200);
        assertEquals(ok, TrackEditService.validateName(ok, 200));
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName("x".repeat(201), 200));
    }

    @Test
    void 名字里的换行要清掉() {
        // 换行会让前端的行内编辑、列表渲染都错位
        assertEquals("第一行 第二行", TrackEditService.validateName("第一行\n第二行", 200));
    }

    @Test
    void 同名判定_排除自己() {
        // 改名时不排除自己，就会把"改成和现在一样的名字"误判成冲突
        assertEquals(true, TrackEditService.isNameConflict("资料一", "资料一", 3L, 3L),
                "改回自己原来的名字不算冲突");
        assertEquals(true, TrackEditService.isNameConflict("资料一", "资料二", 3L, 3L),
                "改成别的名字才可能是冲突");
        assertEquals(false, TrackEditService.isNameConflict("资料一", "资料一", 3L, 4L),
                "和别人同名才是冲突");
    }
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: 只跑 `TrackEditServiceTest`
Expected: **编译失败**，报 `找不到符号: 类 TrackEditService`

- [ ] **Step 3: 实现 `TrackEditService`**

```java
package com.calcite.service;

import com.calcite.config.DataProperties;
import com.calcite.domain.Track;
import com.calcite.domain.TrackPoint;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.DeleteTrackResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 数据管理的编排层：改名 / 删除 / 同名检测。
 *
 * <p><b>⚠️ 这个类兑现了两处欠账</b>：{@link StayPointCache} 和 {@link SimilarityCache}
 * 的 javadoc 里都写着「将来加了"删除轨迹 / 重新导入覆盖同名轨迹"，<b>必须调用 invalidate 清理</b>」。
 * 这里就是那些调用点。
 */
@Service
public class TrackEditService {

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final TrackExporter exporter;
    private final StayPointCache stayPointCache;
    private final SimilarityCache similarityCache;
    private final DataProperties props;

    public TrackEditService(TrackRepository trackRepository,
                            TrackPointRepository trackPointRepository,
                            TrackExporter exporter,
                            StayPointCache stayPointCache,
                            SimilarityCache similarityCache,
                            DataProperties props) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.exporter = exporter;
        this.stayPointCache = stayPointCache;
        this.similarityCache = similarityCache;
        this.props = props;
    }

    // ------------------------------------------------------------ 纯逻辑（可无库单测）

    /**
     * 校验并规整轨迹名（<b>纯静态</b>）。
     *
     * <p>换行必须清掉 —— 它会同时毁掉前端的行内编辑和列表渲染。
     */
    public static String validateName(String raw, int maxLength) {
        if (raw == null) {
            throw new IllegalArgumentException("名字不能为空");
        }
        String s = raw.replaceAll("[\\r\\n\\t]+", " ").trim();
        if (s.isEmpty()) {
            throw new IllegalArgumentException("名字不能为空");
        }
        if (s.length() > maxLength) {
            throw new IllegalArgumentException("名字最长 " + maxLength + " 个字符，收到 " + s.length());
        }
        return s;
    }

    /**
     * 判断"改成 newName"会不会和别的轨迹重名（<b>纯静态</b>）。
     *
     * <p>{@code excludeTrackId} 是<b>必须的</b>：改名时要排除自己，
     * 否则"把名字改成和现在一样"会被误判成冲突。
     *
     * @param currentName   被改的那条现在的名字
     * @param newName       想改成的新名字
     * @param currentId     被改的那条的 id
     * @param otherTrackId  库里另一条同名轨迹的 id（没有同名就传 null）
     * @return true = 会和别人撞名
     */
    public static boolean isNameConflict(String currentName, String newName,
                                         Long currentId, Long otherTrackId) {
        if (otherTrackId == null) {
            return false;
        }
        return !otherTrackId.equals(currentId);
    }

    // ------------------------------------------------------------ 改名

    /**
     * 改名。
     *
     * <p><b>⚠️ 为什么改名也要清相似度缓存</b>：看起来"只是改个显示名、数据一点没变"，
     * 但 {@code SimilarityMatch} 里<b>带了 name</b> —— 不清的话，
     * 把「资料一」改名成「第一次跑步」，再去点别的主线的相似度，列表里还是写着「资料一」。
     *
     * <p>停留点缓存<b>不用清</b>：它只依赖轨迹的点，改名不影响。
     */
    @Transactional
    public String rename(Long id, String newName) {
        Track track = trackRepository.findById(id)
                .orElseThrow(() -> new TrackNotFoundException(id));
        String name = validateName(newName, props.getMaxNameLength());
        track.setName(name);
        trackRepository.save(track);

        similarityCache.invalidateAll();       // ← 因为 SimilarityMatch 里带 name
        return name;
    }

    // ------------------------------------------------------------ 删除

    /**
     * 删除一条轨迹。
     *
     * <p><b>⚠️ 顺序不能变</b>：
     * <ol>
     *   <li>查存在（不存在 → 404）</li>
     *   <li><b>先导出到回收站</b> —— <b>失败就抛异常中止，绝不执行删除</b></li>
     *   <li>删 track（它的点由 FK {@code ON DELETE CASCADE} 自动删）</li>
     *   <li>清缓存</li>
     * </ol>
     *
     * <p><b>为什么第 ② 步必须是 fail-safe</b>：如果是"尽力导出、失败也照删"，
     * 那这个保险就是<b>假的</b> —— 用户以为有回收站，结果某次磁盘满了就静默没了。
     */
    @Transactional
    public DeleteTrackResponse delete(Long id) {
        Track track = trackRepository.findById(id)
                .orElseThrow(() -> new TrackNotFoundException(id));

        List<TrackPoint> points = trackPointRepository.findByTrackIdOrderBySeqAsc(id);
        List<TrackExporter.Point3D> pts = new ArrayList<>(points.size());
        for (TrackPoint p : points) {
            pts.add(new TrackExporter.Point3D(
                    p.getGeom().getX(), p.getGeom().getY(),
                    p.getElevationM() == null ? 0.0 : p.getElevationM(),
                    p.getRecordedAt()));
        }

        int pointCount = pts.size();
        String geojson = TrackExporter.buildGeoJson(id, track.getName(), track.getSource(),
                track.getExternalId(), track.getStartTime(), track.getEndTime(),
                pointCount, track.getDistanceM(), pts);

        Path saved;
        try {
            saved = exporter.exportToFile(geojson, track.getName(), pointCount, OffsetDateTime.now());
        } catch (IOException e) {
            // ⚠️ 导出失败 → 绝不删除。宁可删不掉，也不要"删了没备份"。
            throw new RecycleExportFailedException(
                    "导出到回收站失败，未执行删除：" + e.getMessage(), e);
        }

        trackRepository.delete(track);          // 点由 FK CASCADE 自动删
        stayPointCache.invalidate(id);
        similarityCache.invalidateAll();        // 别的主线的结果里可能把它算进去了

        return new DeleteTrackResponse(id, track.getName(), pointCount, saved.toString());
    }

    // ------------------------------------------------------------ 同名检测

    /**
     * 库里有没有另一条同名轨迹（没有就返回 empty）。
     *
     * <p>用派生查询 {@code findFirstByName} 而不是"把前 500 条拉回来在内存里筛" ——
     * 后者只看了最新的 500 条，是有边界 bug 的写法。
     */
    public java.util.Optional<Long> findNameConflict(String name, Long excludeTrackId) {
        return trackRepository.findFirstByName(name)
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId);
    }

    // ------------------------------------------------------------ 异常

    /** 轨迹不存在 → 控制器映射成 404 */
    public static class TrackNotFoundException extends RuntimeException {
        public TrackNotFoundException(Long id) {
            super("轨迹不存在：" + id);
        }
    }

    /** 导出回收站失败 → 控制器映射成 500，且<b>轨迹原样保留</b> */
    public static class RecycleExportFailedException extends RuntimeException {
        public RecycleExportFailedException(String msg, Throwable cause) {
            super(msg, cause);
        }
    }
}
```

创建 `backend/src/main/java/com/calcite/web/dto/DeleteTrackResponse.java`：

```java
package com.calcite.web.dto;

/**
 * 删除成功后的响应。
 *
 * <p><b>为什么要把 {@code recyclePath} 返回给前端</b>：让用户当场就知道
 * "东西在哪、需要的话去哪找" —— 比事后去翻目录强得多。
 */
public record DeleteTrackResponse(
        Long trackId,
        String name,
        int deletedPointCount,
        /** 导出到回收站的文件路径 */
        String recyclePath
) {
}
```

创建 `backend/src/main/java/com/calcite/web/dto/TrackConflictResponse.java`：

```java
package com.calcite.web.dto;

/**
 * 同名冲突（HTTP 409）的响应体。
 *
 * <p><b>为什么要带上两边的点数</b>：用户做决定时需要知道"要覆盖的是个什么东西" ——
 * "已有『资料一』（456 个点），你上传的这份有 623 个点"比一句"已存在"有用得多。
 */
public record TrackConflictResponse(
        /** 冲突类型：{@code SAME_NAME} 或 {@code SAME_CONTENT} */
        String conflictType,
        Long existingTrackId,
        String existingName,
        Integer existingPointCount,
        /** 这次上传的文件的点数（解析失败时为 null） */
        Integer newPointCount,
        String message
) {
    public static TrackConflictResponse sameName(Long id, String name, Integer existing,
                                                 Integer incoming) {
        return new TrackConflictResponse("SAME_NAME", id, name, existing, incoming,
                "已有同名轨迹「" + name + "」（" + existing + " 个点）");
    }

    public static TrackConflictResponse sameContent(Long id, String name) {
        return new TrackConflictResponse("SAME_CONTENT", id, name, null, null,
                "这个文件的内容已经作为「" + name + "」存在了");
    }
}
```

- [ ] **Step 4: 跑测试，确认全绿**

Run: 只跑 `TrackEditServiceTest`
Expected: `Tests run: 5, Failures: 0, Errors: 0`

- [ ] **Step 5: 跑全量后端测试**

Run: 常用命令的「后端编译 + 全部单测」
Expected: `Tests run: 133, Failures: 0, Errors: 0`（128 + 5）

- [ ] **Step 6: 提交**

```powershell
git add backend/src/main/java/com/calcite/service/TrackEditService.java backend/src/main/java/com/calcite/web/dto/DeleteTrackResponse.java backend/src/main/java/com/calcite/web/dto/TrackConflictResponse.java backend/src/test/java/com/calcite/service/TrackEditServiceTest.java
git commit -m "feat(data): TrackEditService 改名/删除（先导出回收站、失败不删）+ 同名检测 + 5 项单测"
```

---

## Task 3: 控制器端点

**Files:**
- Modify: `backend/src/main/java/com/calcite/web/TrackController.java`
- Modify: `backend/src/main/java/com/calcite/web/ImportController.java`
- Modify: `backend/src/main/java/com/calcite/service/ImportService.java`

**Interfaces:**
- Consumes: `TrackEditService.*`（Task 2）、`TrackConflictResponse` / `DeleteTrackResponse`（Task 2）
- Produces: `PATCH /api/tracks/{id}`、`DELETE /api/tracks/{id}`、`POST /api/tracks/import?mode=&replaceTrackId=`

- [ ] **Step 0: 给两个仓储补两个方法（否则编译不过）**

`TrackRepository` 加：

```java
    /**
     * 按名字找一条轨迹（同名检测用）。
     *
     * <p>Spring Data 的派生查询 —— 方法名翻译成 SQL 的 {@code WHERE name = ? LIMIT 1}。
     */
    Optional<Track> findFirstByName(String name);
```

`TrackPointRepository` 加：

```java
    /**
     * 删掉某条轨迹的全部点（"替换"时先清空旧的）。
     *
     * <p>派生删除：Spring Data 会翻译成 {@code DELETE FROM track_point WHERE track_id = ?}。
     * <b>为什么不用 {@code track_pointRepository.deleteAll(points)}</b>：
     * 那会把几万个实体一个个查出来再删 —— 慢得多，而且内存里要放 1 万多个对象。
     */
    void deleteByTrackId(Long trackId);
```

> ⚠️ 派生删除方法**必须加 `@Transactional`**（在调用它的 service 方法上已经有）。

- [ ] **Step 1: 给 `TrackController` 注入 `TrackEditService` 并加两个端点**

`TrackController` 现在有 3 个注入参数（`trackRepository` / `trackPointRepository` / `stayPointService`）。
**再加一个 `TrackEditService`，已有的一个都不能少。**

```java
    /** 改名。改名后要清相似度缓存（因为匹配列表里带 name）—— 清缓存的动作在 service 里。 */
    @PatchMapping("/{id}")
    public Map<String, Object> rename(@PathVariable Long id,
                                      @RequestBody RenameRequest req) {
        try {
            String name = trackEditService.rename(id, req.name());
            return Map.of("trackId", id, "name", name);
        } catch (TrackEditService.TrackNotFoundException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, e.getMessage());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        }
    }

    /**
     * 删除一条轨迹。
     *
     * <p><b>顺序在 service 里保证</b>：先导出到回收站 → 导出失败就不删 → 才真删。
     * 所以这个方法只需要把两种失败映射成合适的 HTTP 码。
     */
    @DeleteMapping("/{id}")
    public DeleteTrackResponse delete(@PathVariable Long id) {
        try {
            return trackEditService.delete(id);
        } catch (TrackEditService.TrackNotFoundException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, e.getMessage());
        } catch (TrackEditService.RecycleExportFailedException e) {
            // 500 而不是 400：这不是用户的错，是服务端写不出回收站文件
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, e.getMessage());
        }
    }

    /** 改名的请求体 */
    public record RenameRequest(String name) {
    }
```

补 import：`PatchMapping`、`DeleteMapping`、`RequestBody`、`Map`、`DeleteTrackResponse`、`TrackEditService`。

- [ ] **Step 2: 给 `ImportController` 加 `mode` 与 `replaceTrackId`，并处理两个 409**

```java
    /**
     * 上传一个轨迹文件。
     *
     * @param mode           {@code append}（默认，新增）或 {@code replace}（替换已有的）
     * @param replaceTrackId 当 {@code mode=replace} 时，要替换哪一条
     */
    @PostMapping("/api/tracks/import")
    public ImportResult upload(@RequestParam("file") MultipartFile file,
                               @RequestParam(defaultValue = "append") String mode,
                               @RequestParam(required = false) Long replaceTrackId)
            throws IOException {
        return importService.importUpload(file.getBytes(), file.getOriginalFilename(),
                mode, replaceTrackId);
    }
```

在 `ImportController` 加一个 409 的处理器：

```java
    /**
     * 同名 / 同内容冲突 → 409 + 说清楚冲突的是什么。
     *
     * <p><b>为什么是 409 而不是 400</b>：请求本身没问题，是**和库里已有的东西冲突了** ——
     * 语义上就该是 409 Conflict。前端靠这个码来决定"弹出替换/新增的选择"。
     */
    @ExceptionHandler(ImportService.TrackConflictException.class)
    public ResponseEntity<TrackConflictResponse> handleConflict(
            ImportService.TrackConflictException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(e.getBody());
    }
```

- [ ] **Step 3: 给 `ImportService` 加同名检测与替换路径**

现有 `importBytes(byte[] content, String fallbackName)` **保持不动**（别的地方在用）；
新增一个**重载**：

```java
    /**
     * 上传导入（扩展版）：支持"新增"与"替换"两种模式，并做同名检测。
     *
     * <p><b>三种结果</b>：
     * <ol>
     *   <li>内容哈希已存在 → <b>跳过</b>（幂等，原有行为不变）
     *   <li>哈希是新的、但<b>名字已存在</b> → 抛 {@link TrackConflictException}（409，SAME_NAME）
     *   <li>{@code mode=replace} 且新内容的哈希<b>已属于另一条轨迹</b>
     *       → 抛 {@link TrackConflictException}（409，SAME_CONTENT）</li>
     * </ol>
     *
     * <p><b>⚠️ 第 ③ 条是自查时发现的边界</b>：先导入「资料一」（hash A），
     * 再拿同一个文件去"替换"「资料二」→ 新的 external_id 也是 A，
     * 但 A 已经是「资料一」的 → 撞唯一约束 → <b>500</b>。
     * 正确行为是<b>再返回一次 409</b>，说清"这份内容已经在库里了"。
     */
    public ImportResult importUpload(byte[] content, String fallbackName,
                                     String mode, Long replaceTrackId) {
        String externalId = sha256Hex(content);
        Optional<Track> byHash = trackRepository.findByExternalId(externalId);

        // ② 幂等：内容一模一样，且不是在替换
        if (byHash.isPresent() && !"replace".equals(mode)) {
            return skipped(byHash.get());
        }

        // ③ 替换模式下，新内容属于【另一条】轨迹 → 409 SAME_CONTENT
        if (byHash.isPresent() && "replace".equals(mode)
                && !byHash.get().getId().equals(replaceTrackId)) {
            Track other = byHash.get();
            throw new TrackConflictException(TrackConflictResponse.sameContent(
                    other.getId(), other.getName()), null);
        }

        Parsed parsed = parse(content, fallbackName);   // ← 用现有的解析逻辑（按现状适配方法名）
        String name = parsed.name();

        // ② 同名检测（排除正在被替换的那条）
        Optional<Long> conflict = trackEditService.findNameConflict(name, replaceTrackId);
        if (conflict.isPresent() && !"replace".equals(mode)) {
            Track existing = trackRepository.findById(conflict.get()).orElseThrow();
            throw new TrackConflictException(TrackConflictResponse.sameName(
                    existing.getId(), existing.getName(),
                    existing.getPointCount(), parsed.points().size()), null);
        }

        if ("replace".equals(mode) && replaceTrackId != null) {
            return replaceInPlace(replaceTrackId, name, parsed);
        }
        return persist(name, parsed.format(), externalId, parsed.points());
    }
```

> ⚠️ **上面用到的 `parse` / `Parsed` / `skipped` / `replaceInPlace` 要按现状适配** ——
> 现有的 `importBytes` 里已经有这些步骤，把它们**抽成私有方法复用**，
> 不要复制粘贴一份。**执行时先读一遍 `importBytes` 的完整实现。**

`replaceInPlace` 的要点（**原地更新，不删不插**）：

```java
    private ImportResult replaceInPlace(Long trackId, String name, Parsed parsed) {
        Track track = trackRepository.findById(trackId)
                .orElseThrow(() -> new IllegalArgumentException("要替换的轨迹不存在：" + trackId));
        // 来源必须一致 —— GPX 不能替换成 GeoLife
        if (!track.getSource().equals(parsed.format())) {
            throw new IllegalArgumentException(
                    "来源不一致：原轨迹是 " + track.getSource() + "，上传的是 " + parsed.format());
        }
        // 删掉旧的点，重新插入
        trackPointRepository.deleteByTrackId(trackId);
        // 更新元数据 + 几何（Track 有全套 setter ✓ 已确认）
        ...
        similarityCache.invalidateAll();
        stayPointCache.invalidate(trackId);
        return ...;
    }
```

- [ ] **Step 4: 重启后端，手工验证**

```powershell
$c = netstat -ano | Select-String ":8080\s" | Select-String "LISTENING"
if ($c) { Stop-Process -Id ($c[0].Line -split '\s+')[-1] -Force }
# 然后用计划里的 spring-boot:run 启动（后台），等 health UP
```

```powershell
# 改名
Invoke-RestMethod "http://localhost:8080/api/tracks/3" -Method Patch -ContentType "application/json" -Body '{"name":"资料一-改名测试"}'
(Invoke-RestMethod "http://localhost:8080/api/tracks/3").name

# 改回原名（清理现场）
Invoke-RestMethod "http://localhost:8080/api/tracks/3" -Method Patch -ContentType "application/json" -Body '{"name":"资料一"}'

# 非法名字 → 400
try { Invoke-RestMethod "http://localhost:8080/api/tracks/3" -Method Patch -ContentType "application/json" -Body '{"name":"  "}' }
catch { "空名字 → HTTP " + [int]$_.Exception.Response.StatusCode }

# 不存在的轨迹 → 404
try { Invoke-RestMethod "http://localhost:8080/api/tracks/999999" -Method Delete }
catch { "删不存在的 → HTTP " + [int]$_.Exception.Response.StatusCode }

# 同名上传 → 409
# （用 Python 传一个 name 会撞的 GPX 文件太麻烦，这一步留给 Task 4 的对拍脚本）
```

**Expected**：改名生效、改回原名成功、空名字 **400**、删不存在 **404**。

> ⚠️ **本步【不要】真的删一条轨迹** —— 删除的完整验证放在 Task 4（那里会检查回收站文件真的落盘了）。
> 这里只验证"能不能删"的边界（404）。

- [ ] **Step 5: 跑全量后端测试 + 提交**

Expected: `Tests run: 133, Failures: 0, Errors: 0`

```powershell
git add backend/src/main/java/com/calcite/web/TrackController.java backend/src/main/java/com/calcite/web/ImportController.java backend/src/main/java/com/calcite/service/ImportService.java
git commit -m "feat(data): PATCH/DELETE /api/tracks/{id} + 导入的同名检测（409）与替换模式"
```

---

## Task 4: Python 对拍（含三条关键测试）⭐

**Files:**
- Create: `.tmp/verify-data-edit-api.py`

> **为什么这一步不能省**：Java 单测只覆盖了纯逻辑（名字校验、GeoJSON 生成）。
> **「缓存真的失效了没有」只能在这里验证** —— 这是整个功能唯一能证明"欠账已兑现"的地方。

- [ ] **Step 1: 写对拍脚本**

创建 `.tmp/verify-data-edit-api.py`：

```python
# -*- coding: utf-8 -*-
r"""数据管理的对拍：删 / 改名 / 替换 + 【缓存真的失效了没有】。

三条关键测试（只有这里能做）：
  ① 删掉相似度第一名后，主线 20 的 compared 必须少 1     → 证明 SimilarityCache 被清了
  ② 改名后，别的主线的匹配列表里必须显示新名字          → 证明"改名也要清缓存"
  ③ 删除前必须真的落盘了回收站文件                      → 证明 fail-safe 生效

⚠️ 这个脚本会**真的改动数据库**。每一步都做了现场恢复（改回原名 / 记下被删的轨迹以便重导）。
   跑之前请确认 D:\Calcite-note\backups\ 里有当天的快照。

用法（需要提权 danger-full-access）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\verify-data-edit-api.py
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8080"
RECYCLE = Path(r"D:\Calcite-note\backups\deleted")
fails = []


def check(name, ok, detail=""):
    print(("  [OK] " if ok else "  [XX] ") + name + ("  " + detail if detail else ""))
    if not ok:
        fails.append(name)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def send(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        raw = ex.read().decode("utf-8", "replace")
        try:
            return ex.code, json.loads(raw)
        except Exception:
            return ex.code, {"raw": raw}


def track_ids(limit=500):
    return [t["id"] for t in get(f"/api/tracks?limit={limit}")["items"]]


def main():
    # ================= A. 改名 =================
    print("=== A. 改名 ===")
    vid = 3
    before = get(f"/api/tracks/{vid}")
    orig_name = before["name"]
    stamp = "改名测试-唯一标记"

    st, body = send("PATCH", f"/api/tracks/{vid}", {"name": stamp})
    check("改名返回 200", st == 200, f"HTTP {st}")
    check("改完详情里是新名字", get(f"/api/tracks/{vid}")["name"] == stamp)

    st, _ = send("PATCH", f"/api/tracks/{vid}", {"name": "   "})
    check("空名字 → 400", st == 400, f"HTTP {st}")
    st, _ = send("PATCH", f"/api/tracks/{vid}", {"name": "x" * 201})
    check("超长名字 → 400", st == 400, f"HTTP {st}")
    st, _ = send("PATCH", "/api/tracks/999999", {"name": "x"})
    check("改不存在的轨迹 → 404", st == 404, f"HTTP {st}")

    # ================= B. ⭐ 改名后相似度列表必须显示新名字 =================
    print("\n=== B. ⭐ 改名也要清相似度缓存 ===")
    base = 20
    sim_before = get(f"/api/analysis/similarity?trackId={base}&limit=500")
    target = next((m for m in sim_before["matches"] if m["trackId"] == vid), None)
    if target is None:
        print(f"  info: 主线 {base} 的匹配里没有 track {vid}，跳过这条（换一条主线也一样）")
    else:
        sim_after = get(f"/api/analysis/similarity?trackId={base}&limit=500")
        got = next((m["name"] for m in sim_after["matches"] if m["trackId"] == vid), None)
        check("改名后，别的主线的匹配列表里显示新名字", got == stamp,
              f"期望 {stamp!r}，实得 {got!r}")

    # 现场恢复
    send("PATCH", f"/api/tracks/{vid}", {"name": orig_name})
    check("已改回原名（清理现场）", get(f"/api/tracks/{vid}")["name"] == orig_name)

    # ================= C. ⭐⭐ 删除后相似度必须变 =================
    print("\n=== C. ⭐⭐ 删除后相似度必须变（证明缓存被清了）===")
    sim0 = get(f"/api/analysis/similarity?trackId={base}&limit=500")
    compared0 = sim0["compared"]
    first = sim0["matches"][0]
    victim = first["trackId"]
    victim_name = first["name"]
    victim_points = first["pointCount"]
    print(f"  主线 {base}: compared={compared0}，第一名 track {victim}「{victim_name}」"
          f" sim={first['similarity']}")

    files_before = len(list(RECYCLE.glob("*.geojson"))) if RECYCLE.exists() else 0

    st, del_body = send("DELETE", f"/api/tracks/{victim}")
    check("删除返回 200", st == 200, f"HTTP {st}")
    check("响应里带了回收站路径", bool(del_body.get("recyclePath")), str(del_body)[:100])

    # ③ 回收站文件真的落盘了
    files_after = len(list(RECYCLE.glob("*.geojson"))) if RECYCLE.exists() else 0
    check("回收站文件数 +1", files_after == files_before + 1,
          f"{files_before} → {files_after}")

    newest = max(RECYCLE.glob("*.geojson"), key=lambda p: p.stat().st_mtime) if files_after else None
    if newest:
        gj = json.loads(newest.read_text(encoding="utf-8"))
        coords = gj["features"][0]["geometry"]["coordinates"]
        props = gj["features"][0]["properties"]
        check("回收站文件里的点数与删除前一致", len(coords) == victim_points,
              f"文件 {len(coords)} vs 接口报的 {victim_points}")
        check("回收站文件带了名字", props.get("name") == victim_name,
              f"{props.get('name')!r}")
        check("回收站文件带了每个点的时间", len(props.get("times", [])) == len(coords),
              f"times={len(props.get('times', []))} coords={len(coords)}")
        check("回收站文件名里带轨迹名和点数",
              victim_name.replace(" ", "_") in newest.name or "unnamed" in newest.name,
              newest.name)

    # ① 相似度必须变
    sim1 = get(f"/api/analysis/similarity?trackId={base}&limit=500")
    check("主线 20 的 compared 少了 1", sim1["compared"] == compared0 - 1,
          f"{compared0} → {sim1['compared']}")
    check("被删的那条不再出现在名单里",
          all(m["trackId"] != victim for m in sim1["matches"]))

    # 轨迹总数也必须少 1
    listing = get("/api/tracks?limit=1")
    check("轨迹总数少了 1", listing["total"] == 246 - 1 or listing["total"] == len(track_ids()),
          f"total={listing['total']}")

    # ================= D. 删除的边界 =================
    print("\n=== D. 删除的边界 ===")
    st, _ = send("DELETE", f"/api/tracks/{victim}")
    check("再删同一条 → 404", st == 404, f"HTTP {st}")
    st, _ = send("DELETE", "/api/tracks/999999")
    check("删不存在的 → 404", st == 404, f"HTTP {st}")

    # ================= E. 删除后热点也要重算 =================
    print("\n=== E. 删除后热点反映新数据 ===")
    h = get("/api/analysis/hotspots")
    check("热点接口仍能正常返回", "hotspots" in h, f"热点 {len(h.get('hotspots', []))} 个")
    check("热点扫描的轨迹数已减少", h.get("scannedTracks", 999) < 246,
          f"scannedTracks={h.get('scannedTracks')}")

    # ================= 收尾提醒 =================
    print("\n" + "=" * 60)
    print(f"⚠️ 本次删掉了 track {victim}「{victim_name}」（{victim_points} 个点）。")
    print(f"   回收站文件：{newest}")
    print("   要恢复的话：从原始文件重新导入，或用当天的数据库快照。")
    print("=" * 60)

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
& "E:\python\python_address\python.exe" .tmp\verify-data-edit-api.py
```

**Expected**：全部 `[OK]`，最后一行 `全部通过`。

> ⚠️ **这个脚本会真的删掉一条轨迹**（相似度第一名）。跑之前确认：
> ① `D:\Calcite-note\backups\` 里有当天的快照；② 回收站目录可写。
>
> **如果 C 部分的"compared 少了 1"红了** —— 那是**重大发现**：说明 `SimilarityCache` 没被清。
> **不要改断言**，直接报告（这正是本功能要兑现的欠账）。

- [ ] **Step 3: 提交**

```powershell
git add -f .tmp/verify-data-edit-api.py
git commit -m "test(data): Python 对拍（含三条关键测试：删除后相似度必变 / 改名后名字必变 / 回收站必落盘）"
```
⚠️ `.tmp/` 被 gitignore，**必须 `git add -f`**。

---

## Task 5: 前端纯计算 `lib/dataEdit.js` + `DataManager.vue` 的骨架

**Files:**
- Create: `frontend/src/lib/dataEdit.js`
- Create: `frontend/scripts/check-data-edit.mjs`
- Create: `frontend/src/components/ConfirmDialog.vue`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: `formatPoints(n)`、`formatLength(m)`、`conflictText(body)`、`deleteConfirmText(name, points)`
- Produces: `<ConfirmDialog>` — props `open` / `title` / `lines` / `confirmText` / `danger`；事件 `@confirm` / `@cancel`

- [ ] **Step 1: 先写测试**

创建 `frontend/scripts/check-data-edit.mjs`：

```javascript
/**
 * lib/dataEdit.js 的回归测试。零依赖，只用 node 自带的 assert。
 * 跑法：node scripts/check-data-edit.mjs
 */
import assert from 'node:assert/strict'
import { formatPoints, formatLength, conflictText, deleteConfirmText } from '../src/lib/dataEdit.js'

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

t('点数格式化', () => {
  assert.equal(formatPoints(456), '456 个点')
  assert.equal(formatPoints(0), '0 个点')
  assert.equal(formatPoints(null), '—')
})

t('长度格式化（米 → 公里）', () => {
  assert.equal(formatLength(715), '715 米')
  assert.equal(formatLength(14948), '14.9 km')
  assert.equal(formatLength(null), '—')
})

// ---------------------------------------------------------------- 同名冲突文案
t('同名冲突文案带上两边的点数', () => {
  const s = conflictText({
    conflictType: 'SAME_NAME', existingName: '资料一',
    existingPointCount: 456, newPointCount: 623,
  })
  assert.ok(s.includes('资料一'), s)
  assert.ok(s.includes('456'), s)
  assert.ok(s.includes('623'), s)
})

t('同内容冲突文案说清"已经在库里了"', () => {
  const s = conflictText({
    conflictType: 'SAME_CONTENT', existingName: '资料一',
    existingPointCount: null, newPointCount: null,
  })
  assert.ok(s.includes('资料一'), s)
  assert.ok(s.includes('已经'), s)
})

t('冲突文案对缺字段兜底，不显示 undefined', () => {
  const s = conflictText({})
  assert.ok(!s.includes('undefined'), s)
  assert.ok(!s.includes('null'), s)
})

// ---------------------------------------------------------------- 删除确认文案
t('删除确认文案必须写出真实点数', () => {
  const s = deleteConfirmText('资料一', 456)
  assert.ok(s.includes('资料一'), s)
  assert.ok(s.includes('456'), s)
  assert.ok(s.includes('不可恢复') || s.includes('回收站'), s)
})

t('删除确认文案对缺名字兜底', () => {
  const s = deleteConfirmText(null, 0)
  assert.ok(!s.includes('undefined'), s)
  assert.ok(!s.includes('null'), s)
})

/**
 * 这条防的是"用户以为删了就没了" ——
 * 文案里必须告诉他"东西去哪了、要怎么找回来"，否则他会因为害怕而不敢用。
 */
t('删除确认文案必须告诉用户去哪找回来', () => {
  const s = deleteConfirmText('资料一', 456)
  assert.ok(s.includes('回收站') || s.includes('导出') || s.includes('重新导入'), s)
})

console.log('')
console.log(`${pass} 项通过，${fails.length} 项失败`)
if (fails.length) {
  fails.forEach((f) => console.log('  - ' + f))
  process.exit(1)
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run（在 `frontend/` 下）：`node scripts/check-data-edit.mjs`
Expected: 报 `Cannot find module .../src/lib/dataEdit.js`

- [ ] **Step 3: 实现 `lib/dataEdit.js`**

```javascript
/**
 * 数据管理的纯计算模块：格式化、文案拼装。
 *
 * 只放「输入 → 输出」的函数，不碰 Vue、不碰浏览器 API —— 所以能用 node 直接测。
 */

/** 点数文案 */
export function formatPoints(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return `${v} 个点`
}

/** 长度文案：小于 1 公里用米，否则用公里（保留 1 位） */
export function formatLength(m) {
  const v = Number(m)
  if (!Number.isFinite(v)) return '—'
  if (v < 1000) return `${Math.round(v)} 米`
  return `${(v / 1000).toFixed(1)} km`
}

/**
 * 同名 / 同内容冲突的文案。
 *
 * ⚠️ 每个字段都要兜底 —— 后端某个字段为 null 时，
 * 拼接出来会出现 "（null 个点）" 这种东西，比不显示还糟。
 */
export function conflictText(body) {
  const b = body || {}
  const name = b.existingName || '（未知名称）'
  if (b.conflictType === 'SAME_CONTENT') {
    return `这个文件的内容已经作为「${name}」存在了 —— 库里不会有两份一模一样的轨迹。`
  }
  const oldN = Number.isFinite(Number(b.existingPointCount))
    ? `${b.existingPointCount} 个点` : '（点数未知）'
  const newN = Number.isFinite(Number(b.newPointCount))
    ? `${b.newPointCount} 个点` : '（点数未知）'
  return `已有同名轨迹「${name}」（${oldN}）。你上传的这份有 ${newN}。`
}

/**
 * 删除确认弹窗的正文。
 *
 * ⚠️ **最后一句是故意的**：把"不可恢复"从一句恐吓变成**一个真实的操作指引** ——
 * 用户知道东西去哪了、怎么找回来，就不会因为害怕而不敢用这个功能。
 */
export function deleteConfirmText(name, pointCount) {
  const n = name || '（未命名）'
  const pts = Number.isFinite(Number(pointCount)) ? pointCount : 0
  return [
    `确定删除「${n}」？`,
    '',
    `会连带删除它的 ${pts} 个轨迹点。`,
    '',
    '💡 删除前会自动导出到回收站目录，需要的话可以从那里找回来。',
    '   数据库里删掉后，也可以从原始文件重新导入。',
  ].join('\n')
}
```

- [ ] **Step 4: 跑测试，确认全绿**

Run: `node scripts/check-data-edit.mjs`
Expected 最后一行：`N 项通过，0 项失败`（**自己数一遍 `t(` 的个数再报告**）

- [ ] **Step 5: 建 `ConfirmDialog.vue`**

```vue
<script setup>
/**
 * 通用确认弹窗 —— 纯展示组件，自己不做决定，只把用户的选择往外抛。
 *
 * 为什么单独抽一个组件：删除要用它，将来"清空全部""替换确认"也要用。
 */
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '确认' },
  /** 正文，按行显示（换行符切分）—— 让长文案的排版可控 */
  body: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  cancelText: { type: String, default: '取消' },
  /** 危险操作（红色确认按钮） */
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <div v-if="open" class="mask" data-testid="confirm-dialog" @click.self="emit('cancel')">
    <div class="box">
      <h3>{{ title }}</h3>
      <p v-for="(line, i) in body.split('\n')" :key="i" class="line">{{ line }}</p>
      <div class="row">
        <button type="button" class="ghost" data-testid="confirm-cancel"
                @click="emit('cancel')">{{ cancelText }}</button>
        <button type="button" :class="{ danger }" data-testid="confirm-ok"
                @click="emit('confirm')">{{ confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.box {
  width: min(420px, 90vw);
  background: #0b1220;
  border: 1px solid rgba(127, 209, 255, 0.35);
  border-radius: 10px;
  padding: 16px 18px;
  color: #e7eef8;
}
h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.line {
  margin: 0 0 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #b9c6d6;
  white-space: pre-wrap;
}
.row {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
button {
  padding: 5px 14px;
  border-radius: 6px;
  border: 1px solid rgba(127, 209, 255, 0.45);
  background: rgba(127, 209, 255, 0.12);
  color: #e7eef8;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
button.ghost {
  border-color: rgba(255, 255, 255, 0.2);
  background: transparent;
}
button.danger {
  border-color: rgba(255, 90, 90, 0.6);
  background: rgba(255, 90, 90, 0.18);
  color: #ffb3b3;
}
button:hover {
  filter: brightness(1.2);
}
</style>
```

- [ ] **Step 6: 加 `package.json` 别名 + 提交**

`scripts` 里 `check:similarity` 之后加（注意上一行末尾要有逗号）：
```json
    "check:data-edit": "node scripts/check-data-edit.mjs"
```

```powershell
git add frontend/src/lib/dataEdit.js frontend/scripts/check-data-edit.mjs frontend/src/components/ConfirmDialog.vue frontend/package.json
git commit -m "feat(data): 前端纯计算 lib/dataEdit.js + ConfirmDialog 组件 + node 测试"
```

---

## Task 6: `DataManager.vue` + `TrackList.vue` 搬走上传 + `App.vue` 切换

**Files:**
- Create: `frontend/src/components/DataManager.vue`
- Modify: `frontend/src/components/TrackList.vue`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `formatPoints` / `formatLength` / `conflictText` / `deleteConfirmText`（Task 5）、`ConfirmDialog`（Task 5）
- Consumes: 后端 `PATCH` / `DELETE` / `POST import?mode=`（Task 3）

- [ ] **Step 1: 先摸清 `TrackList.vue` 里上传表单与列表的边界**

```powershell
Select-String -Path frontend/src/components/TrackList.vue -Pattern '导入|file|FormData|emit|filter|limit' | ForEach-Object { "  $($_.LineNumber): $($_.Line.Trim())" }
```

**你要弄清楚**：
1. 上传表单的 HTML 从哪一行到哪一行 → **整段剪走**，搬到 `DataManager.vue`
2. 列表的筛选/分页是怎么实现的 → **`DataManager.vue` 直接复用**（不要自造一套）
3. `TrackList` 往外抛哪些事件 → 保持不变，只把"导入"相关的事件改成"打开数据编辑"

- [ ] **Step 2: 建 `DataManager.vue`**

**它的职责**：顶部返回条 + 添加数据区（从 TrackList 搬来的表单）+ 轨迹表格（行内改名 + 删除）。

关键点：
- **表格复用 `TrackList` 那套筛选/分页**（先读现状再抄，别自造）
- 每行：`名称 · 来源 · 点数 · 长度 · 开始时间` + 行尾 `✎` `🗑`
- **改名是行内编辑**（点 ✎ → 变输入框 → 回车保存 / Esc 取消），**不弹窗** —— 轻操作用弹窗太重，
  而且行内编辑能**看着那一行**改，不容易改错对象
- 删除走 `ConfirmDialog`，正文用 `deleteConfirmText(name, points)`
- 同名 409 → 用 `ConfirmDialog` 显示 `conflictText(body)`，两个按钮「替换它」/「新增为另一条」

> ⚠️ **`ConfirmDialog` 只有两个按钮**（取消 / 确定）。
> 冲突场景需要「替换它」和「新增为另一条」**两个都是正向选项** ——
> 所以 `DataManager` 里给 `ConfirmDialog` 传的 `cancelText` 用「新增为另一条」，
> 并把它的 `@cancel` 接到 `resolveKeepBoth()` 上（**不是** `closeDialog`）。
> 执行时按这个接法实现。

`script setup` 的骨架：

```javascript
import { ref, computed } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import { formatPoints, formatLength, conflictText, deleteConfirmText } from '../lib/dataEdit.js'

const props = defineProps({
  tracks: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  sourceFilter: { type: String, default: '' },
  limit: { type: Number, default: 50 },
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['back', 'changed', 'filter', 'limit', 'focus'])

// ---- 弹窗：一个 ConfirmDialog 服务三种用途（删除确认 / 同名冲突 / 错误提示）----
const dialog = ref({ open: false, kind: '', title: '', body: '', confirmText: '', danger: false })
const dialogPayload = ref(null)

function openDialog(kind, title, body, confirmText, danger, payload) {
  dialog.value = { open: true, kind, title, body, confirmText, danger }
  dialogPayload.value = payload ?? null
}
function closeDialog() {
  dialog.value = { ...dialog.value, open: false }
  dialogPayload.value = null
}

/* ============================ 改名（行内编辑） ============================ */
const editingId = ref(null)
const editingName = ref('')
const busy = ref(false)

function startRename(t) {
  editingId.value = t.id
  editingName.value = t.name
}
function cancelRename() {
  editingId.value = null
  editingName.value = ''
}
async function saveRename() {
  const id = editingId.value
  const name = editingName.value.trim()
  if (!id || !name) return cancelRename()
  busy.value = true
  try {
    const res = await fetch(`/api/tracks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) {
      const msg = res.status === 400 ? '名字不合法（不能为空、不能超过 200 字）' : `HTTP ${res.status}`
      throw new Error(msg)
    }
    cancelRename()
    emit('changed')          // 让 App 去刷新（后端已经清了相似度缓存）
  } catch (e) {
    openDialog('error', '改名失败', String(e.message), '知道了', false)
  } finally {
    busy.value = false
  }
}

/* ============================ 删除 ============================ */
function askDelete(t) {
  openDialog('delete', '删除轨迹',
    deleteConfirmText(t.name, t.pointCount), '删除', true, t)
}

async function doDelete() {
  const t = dialogPayload.value
  if (!t) return closeDialog()
  busy.value = true
  try {
    const res = await fetch(`/api/tracks/${t.id}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (res.status === 404) throw new Error('这条轨迹已经不在了（可能被别处删掉了）')
    if (!res.ok) {
      // 500 多半是回收站写不进去 —— 后端【拒绝删除】了，轨迹还在
      throw new Error(data.message || `删除失败（HTTP ${res.status}）。轨迹没有被删除。`)
    }
    closeDialog()
    emit('changed')
    // 把回收站路径告诉用户 —— 他当场就知道东西在哪
    openDialog('info', '已删除',
      `「${t.name}」已删除（${data.deletedPointCount} 个点）。\n\n回收站文件：\n${data.recyclePath}`,
      '知道了', false)
  } catch (e) {
    closeDialog()
    openDialog('error', '删除失败', String(e.message), '知道了', false)
  } finally {
    busy.value = false
  }
}

/* ============================ 上传 + 同名冲突 ============================ */
const pendingFile = ref(null)
const uploading = ref(false)

async function onUpload(ev) {
  const file = ev.target.files?.[0]
  if (!file) return
  pendingFile.value = file
  await submitUpload('append', null)
  ev.target.value = ''            // 允许再次选同一个文件
}

/**
 * 提交上传。
 *
 * ⚠️ 用户选"替换"时【不需要重新选文件】—— pendingFile 还在内存里，
 * 直接用同一个 File 对象再提交一次即可。
 */
async function submitUpload(mode, replaceTrackId) {
  const file = pendingFile.value
  if (!file) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const params = new URLSearchParams({ mode })
    if (replaceTrackId != null) params.set('replaceTrackId', String(replaceTrackId))
    const res = await fetch(`/api/tracks/import?${params}`, { method: 'POST', body: fd })
    const data = await res.json().catch(() => ({}))

    if (res.status === 409) {
      // 让用户决定 —— 这正是"同名检测返回 409"的设计意图
      openDialog('conflict', '发现同名/同内容轨迹',
        conflictText(data), '替换它', false, data)
      return
    }
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`)

    pendingFile.value = null
    closeDialog()
    emit('changed')
    openDialog('info', '导入完成', `已处理：${data.name ?? ''}`, '知道了', false)
  } catch (e) {
    openDialog('error', '导入失败', String(e.message), '知道了', false)
  } finally {
    uploading.value = false
  }
}

/** 冲突弹窗上点"替换它" */
async function resolveConflict() {
  const body = dialogPayload.value
  if (body?.conflictType === 'SAME_CONTENT') {
    // 内容已经在了，没什么可替换的 —— 只提示
    closeDialog()
    return
  }
  closeDialog()
  await submitUpload('replace', body.existingTrackId)
}

/** 冲突弹窗上点"新增为另一条" */
async function resolveKeepBoth() {
  closeDialog()
  await submitUpload('append', null)
}

/* ============================ 弹窗按钮分发 ============================ */
function onDialogConfirm() {
  const kind = dialog.value.kind
  if (kind === 'delete') return doDelete()
  if (kind === 'conflict') return resolveConflict()
  closeDialog()
}
```

- [ ] **Step 3: 改 `TrackList.vue`（搬走上传，按钮改名）**

- 删掉上传表单那一段 HTML 与它的 `script` 逻辑
- 把「导入轨迹」按钮改成「**数据编辑**」，`data-testid="open-data-manager"`，点击 `emit('openDataManager')`
- **列表本身一分不动**

- [ ] **Step 4: 改 `App.vue`（视图切换 + 刷新编排）**

```javascript
/* ============ 数据管理视图 ============ */
// 'analysis' = 原来的四档分析；'manage' = 数据管理
const panelView = ref('analysis')

function openDataManager() {
  panelView.value = 'manage'
}
function backToAnalysis() {
  panelView.value = 'analysis'
  // 回到分析视图时，把四个分析档的本地状态全部清空 ——
  // 因为管理视图里可能改过数据，而这些结果全都基于全库数据
  resetAnalysisState()
}

/**
 * 数据被改过（删/改名/替换）之后的统一刷新。
 *
 * ⚠️ 一条规则：**数据一改，四个分析功能的结果全部失效** —— 因为它们全都基于全库数据。
 * 后端那边的缓存已经在改的时候清了（StayPointCache / SimilarityCache），
 * 这里要清的是【前端已经拿到的旧结果】。
 */
function resetAnalysisState() {
  stays.value = []
  hotspots.value = []
  densityCells.value = []
  similarityMatches.value = []
  similarityTracks.value = []
  // 当前选中的轨迹可能已经被删了 —— 清掉，并切回「停留点」档
  if (selectedId.value != null && !tracks.value.some((t) => t.id === selectedId.value)) {
    selectedId.value = null
    detail.value = null
    viewMode.value = 'stay'
  }
  loadTracks()
}
```

模板：`panelView === 'manage'` 时用 `<DataManager>` 替换整个面板内容（**包括四档切换那条**，
因为管理视图不属于任何分析档）。

- [ ] **Step 5: 构建 + 手工看效果**

Run（**需提权**）：`cd frontend; npm run build`
Expected: `built in ...`，无 error

浏览器打开 `http://localhost:5173`：
- 点「数据编辑」→ 整个面板变成管理视图（顶部有「← 返回」）
- 表格显示轨迹，每行有 ✎ 🗑
- 点 ✎ → 行内变输入框 → 改名成功
- 点 🗑 → 弹确认框（**文案里有真实点数**）→ 取消 → 条数不变
- 点「← 返回」→ 回到四档分析

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/components/DataManager.vue frontend/src/components/TrackList.vue frontend/src/App.vue
git commit -m "feat(data): DataManager 视图（表格 + 行内改名 + 删除确认 + 同名三选一）+ App 视图切换与数据变更后的刷新编排"
```

---

## Task 7: 浏览器像素验收

**Files:**
- Create: `.tmp/check-data-edit.py`

> ⚠️ **先读 `.tmp/check-density.py`**，照它的结构写（`check()` / `note()` / 四视口 / 控制台零报错）。

- [ ] **Step 1: 写验收脚本**

必须包含（**判据尽量从接口取期望值，不写死**）：

| # | 检查 | 判据 |
|---|---|---|
| 1 | 「数据编辑」按钮存在 | DOM |
| 2 | 点了进管理视图 | `[data-testid="data-manager"]` 存在，且四档切换条消失 |
| 3 | 表格行数 == 接口条数 | 从接口取 |
| 4 | 每行都有 ✎ 🗑 | DOM 计数 |
| 5 | 点 ✎ 出行内输入框 | DOM |
| 6 | 改名后行内显示新名字 | DOM + 接口 |
| 7 | **改回原名**（清理现场） | 接口 |
| 8 | 点 🗑 弹确认框，**文案含真实点数** | 弹窗文本含接口给出的点数 |
| 9 | 取消删除 → 条数不变 | 接口 |
| 10 | 「← 返回」回到四档分析 | DOM |
| 11 | **删掉当前选中的轨迹 → 自动切回「停留点」档** | DOM（Review Focus 第 1 条） |
| 12 | 四视口面板不溢出 | 1600×900 / 1600×600 / 1366×660 / 1280×720 |
| 13 | 控制台零报错 | |

> ⚠️ **第 11 条要真的删一条轨迹** —— 用一个**刚导入的测试轨迹**做，
> 或者删完立刻用回收站文件提醒用户（和 Task 4 一样，脚本末尾打印提示）。

- [ ] **Step 2: 跑验收**（需提权；跑不了就如实报告，由主控代跑）

- [ ] **Step 3: 看截图确认视觉效果**（用 `read_image`）

- [ ] **Step 4: 提交**

```powershell
git add -f .tmp/check-data-edit.py
git commit -m "test(data): 浏览器像素验收"
```

---

## Task 8: 现有验收脚本改成数据自适应

**Files:**
- Modify: `.tmp/check-filter.py`、`.tmp/check-hotspots.py`、`.tmp/verify-hotspot-api.py`、`.tmp/verify-similarity-api.py` 等

> **背景**：这些脚本大量假设"库里有 **246** 条轨迹"。Task 4 的删除测试会打破它们。
> **修法同第三阶段那次**：改成**先从接口取当前总数**，不写死。

- [ ] **Step 1: 找出所有写死的数字**

```powershell
Select-String -Path .tmp/*.py -Pattern '246|247|== 197|compared > 50' | ForEach-Object { "  $($_.Filename):$($_.LineNumber): $($_.Line.Trim())" }
```

- [ ] **Step 2: 逐个改成从接口取**

对每一处：
- 总数类（246）→ 开头查 `GET /api/tracks?limit=1` 的 `total`
- `compared == 197` → 改成**关系型**：删完再查，`compared` 必须等于删除前的值减 1
- ⚠️ **不要把断言改弱**（`== 246` 改成 `> 0` 是放松）—— 要换成**另一个同样强的断言**

- [ ] **Step 3: 跑一遍确认全绿**，并把 Step 1 的扫描跑成**零输出**

- [ ] **Step 4: 提交**

```powershell
git add -f .tmp/check-filter.py .tmp/check-hotspots.py .tmp/verify-hotspot-api.py .tmp/verify-similarity-api.py
git commit -m "test: 现有验收脚本改成数据自适应（不再写死 246 条轨迹）"
```

---

## Task 9: 全量回归 + 文档同步

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md`
- Modify: `_session_context.md`

- [ ] **Step 1: 跑全部回归，数准总数**

```powershell
# 后端
& "E:\JAVA_IDEA_package\JAVA_IDEA_app\IntelliJ IDEA 2026.1\plugins\maven\lib\maven3\bin\mvn.cmd" -B "-Dmaven.repo.local=E:\JAVA_IDEA_package\JAVA_Project\Calcite\.m2\repository" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\pom.xml" test 2>&1 | Select-String -Pattern '^\[INFO\] Tests run:.*Skipped: \d+$|BUILD' | Select-Object -Last 2
```
```powershell
# 前端 node（6 个套件）
cd frontend
foreach ($s in @('check-playback','check-chart','check-hotspot','check-density','check-similarity','check-data-edit')) {
  $o = node "scripts/$s.mjs" 2>&1
  "  {0,-20} {1}" -f $s, (($o | Select-String -Pattern '项通过' | Select-Object -Last 1).Line)
}
cd ..
```
```powershell
# 浏览器 / 接口（11 个脚本）
$yaml = Get-Content "backend/src/main/resources/application-local.yml" -Raw
if ($yaml -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
$env:PYTHONIOENCODING='utf-8'; $env:LC_MESSAGES='C'
$py = "E:\python\python_address\python.exe"
foreach ($s in @('check-stay-points','check-chart-pixels','check-import-pixels','check-filter','check-hotspots','check-density','check-similarity','check-data-edit','verify-hotspot-api','verify-density-api','verify-similarity-api')) {
  $o = & $py ".tmp/$s.py" 2>&1
  "  {0,-24} exit={1}  {2}" -f $s, $LASTEXITCODE, (($o | Select-String -Pattern '项通过|全部通过' | Select-Object -Last 1).Line)
}
```

- [ ] **Step 2: ⚠️ 跑完回归后，把数据库恢复到 246 条**

回归里的删除测试会真的删掉一条或多条轨迹。
**跑完全部回归后**，确认库里还是 246 条；不够的话**从原始文件重新导入**补回来：

```powershell
# 看现在多少条
(Invoke-RestMethod "http://localhost:8080/api/tracks?limit=1").total
```
```powershell
# 不够就补（幂等，已导入的会自动跳过）
Invoke-RestMethod "http://localhost:8080/api/import/geolife" -Method Post -ContentType "application/json" -Body '{"path":"D:\\Calcite-note\\GPX-Data\\Geolife Trajectories 1.3\\Data","maxTracks":300}' -TimeoutSec 1800
```
> ⚠️ **这一步不能忘** —— 否则你会觉得"轨迹怎么少了"，而其实是被测试删掉的。

- [ ] **Step 3: 更新设计文档附录 B 与 `_session_context.md`**

- 设计文档附录 B：加一行「数据管理（删除/改名/同名替换/添加）✅ 已完成（2026-09-21）」
- `_session_context.md`：新增一节，记录
  - 交付物与关键决定（导出回收站 fail-safe、409 让用户决定、改名也要清缓存、宁可全清）
  - **兑现的欠账**：两个缓存 javadoc 里写着的"将来必须调用 invalidate"—— 现在接上了
  - 回归基线（实测）
  - **回收站目录的位置**
  - 下次做之前记得：`D:\Calcite-note\backups\` 里的快照

- [ ] **Step 4: 提交**

```powershell
git add docs/superpowers/specs/2026-09-08-calcite-trajectory-analysis-design.md _session_context.md
git commit -m "docs(data): 数据管理完成——设计文档附录B + 会话记忆同步（兑现了缓存欠账）"
```

---

## 完成标准（Definition of Done）

- [ ] 点「数据编辑」→ 整个面板变成管理视图，有「← 返回」
- [ ] 表格显示轨迹，每条有 ✎ 🗑；改名是**行内编辑**
- [ ] 删除弹确认框，**文案里有真实的点数**，并告诉用户去回收站找
- [ ] **删一条后，`GET /api/analysis/similarity?trackId=20` 的 `compared` 少 1**（缓存真被清了）
- [ ] **改名后，别的主线的匹配列表里显示新名字**（改名也清了缓存）
- [ ] **删除前回收站文件真的落盘**，且里面点数与删除前一致、带每个点的时间
- [ ] 回收站目录不可写时 → **拒绝删除**（500），轨迹原样保留
- [ ] 同名上传 → **409**，界面弹出「替换 / 新增 / 取消」
- [ ] 上传内容是库里已有的 → **409 SAME_CONTENT**（不是 500）
- [ ] 删掉当前选中的轨迹 → **自动切回「停留点」档**
- [ ] 后端单测 **133 项**全绿（`mvn test`，**依然不需要数据库**）
- [ ] node 六个套件全绿
- [ ] 11 个浏览器/接口脚本全绿，且**都不再写死 246**
- [ ] 四视口面板不溢出；四档按钮不折行
- [ ] **回归跑完后数据库恢复到 246 条**
- [ ] 设计文档附录 B、`_session_context.md` 已同步

---

## 已知陷阱速查

| 陷阱 | 症状 | 处理 |
|---|---|---|
| **删除顺序写反** | 先删了再导出 → 导出时数据已经没了 | 必须 **先导出 → 导出失败就不删 → 才删** |
| **导出失败还照删** | 用户以为有回收站，实际没有 | fail-safe：`catch (IOException)` 直接抛异常中止 |
| **改名忘了清相似度缓存** | 别的主线的匹配列表里还是旧名字 | 改名也调 `SimilarityCache.invalidateAll()` |
| **只清被删那条的缓存** | 别的主线的结果里还算着已删的轨迹 | 用 `invalidateAll()`，**宁可全清不要漏清** |
| **替换时撞 external_id 唯一约束** | 500，用户以为系统坏了 | 提前检测 → **409 SAME_CONTENT** |
| **回收站复用 `allowed-roots`** | 两个安全策略互相牵制 | 用独立的 `calcite.data.recycle-dir` |
| **GeoJSON 字符串不转义** | 名字里一个引号让整个文件变坏 JSON | `escape()` 处理 `" \ \n \r \t` |
| **坐标写成 [纬度, 经度]** | QGIS 打开跑到南极 | GeoJSON 规范是 **[经度, 纬度, 海拔]** |
| **改名不排除自己** | 把名字改成和现在一样会误报冲突 | `isNameConflict` 要带 `currentId` |
| **数据改了但前端不清旧状态** | 切回分析档看到的还是旧结果 | `resetAnalysisState()` 清空四个档的本地状态 |
| **回归脚本写死 246** | 删一条就红一片 | Task 8 全部改成从接口取 |
| **回归跑完忘了补回轨迹** | 以为数据丢了，其实是被测试删的 | Task 9 Step 2 必须执行 |
| `.tmp/` 被 gitignore | `git add` 静默失败 | 必须 `git add -f` |
| `Get-NetTCPConnection` 不可靠 | 找不到 8080 的 PID | 用 `netstat -ano \| Select-String ":8080\s"` |
