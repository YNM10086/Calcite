package com.calcite.service;

import com.calcite.service.importer.GpxImporter;
import com.calcite.service.importer.ParsedTrack;
import com.calcite.service.importer.RawPoint;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrackCleanerTest {

    private static final OffsetDateTime T0 = OffsetDateTime.parse("2026-06-22T11:00:00Z");

    private final TrackCleaner cleaner = new TrackCleaner(8.0, 3.0);

    private static RawPoint p(double lat, double lon, Double ele, int secondsFromT0) {
        return new RawPoint(lat, lon, ele, T0.plusSeconds(secondsFromT0));
    }

    /** 造一条匀速向北的轨迹：每点约 3 米/秒 */
    private static List<RawPoint> straightLine(int count, double ele) {
        List<RawPoint> pts = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            pts.add(p(25.0 + i * 0.000027, 117.0, ele, i));
        }
        return pts;
    }

    @Test
    void 按时间排序() {
        List<RawPoint> raw = List.of(
                p(25.0, 117.0, 10.0, 2),
                p(25.0, 117.0, 10.0, 0),
                p(25.0, 117.0, 10.0, 1));
        CleanedTrack c = cleaner.clean(raw);

        assertEquals(T0, c.points().get(0).recordedAt());
        assertEquals(T0.plusSeconds(1), c.points().get(1).recordedAt());
        assertEquals(T0.plusSeconds(2), c.points().get(2).recordedAt());
    }

    @Test
    void 第一个点没有速度_因为没有前一个点() {
        CleanedTrack c = cleaner.clean(straightLine(5, 10.0));
        assertNull(c.speeds().get(0));
        assertNotNull(c.speeds().get(1));
    }

    @Test
    void 匀速轨迹没有任何异常点() {
        CleanedTrack c = cleaner.clean(straightLine(20, 10.0));
        assertTrue(c.outliers().stream().noneMatch(Boolean::booleanValue), "不该有异常点");
    }

    @Test
    void 海拔全相同时整条轨迹的海拔都变成_null() {
        // 用户那份数据的真实情况：2342 个点 ele 全是 0.0
        CleanedTrack c = cleaner.clean(straightLine(10, 0.0));
        assertTrue(c.points().stream().allMatch(x -> x.elevationM() == null),
                "全同的海拔应视为没有数据");
    }

    @Test
    void 海拔有变化时原样保留() {
        List<RawPoint> raw = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            raw.add(p(25.0 + i * 0.000027, 117.0, 30.0 + i, i));
        }
        CleanedTrack c = cleaner.clean(raw);
        assertEquals(30.0, c.points().get(0).elevationM(), 1e-9);
        assertEquals(34.0, c.points().get(4).elevationM(), 1e-9);
    }

    @Test
    void 单个海拔点缺失不会触发全部归_null() {
        List<RawPoint> raw = new ArrayList<>();
        raw.add(p(25.0, 117.0, 30.0, 0));
        raw.add(p(25.000027, 117.0, null, 1));
        raw.add(p(25.000054, 117.0, 32.0, 2));
        CleanedTrack c = cleaner.clean(raw);
        assertEquals(30.0, c.points().get(0).elevationM(), 1e-9);
        assertNull(c.points().get(1).elevationM());
    }

    @Test
    void 慢速轨迹里的跳点被标成异常_且两端都标() {
        // 前 10 个点约 3 米/秒，然后突然跳回起点附近，再跳回去 —— 造成两段超速
        List<RawPoint> raw = new ArrayList<>(straightLine(10, 10.0));
        raw.add(p(25.0, 117.0, 10.0, 10));
        raw.add(p(25.000270, 117.0, 10.0, 11));

        CleanedTrack c = cleaner.clean(raw);
        long outlierCount = c.outliers().stream().filter(Boolean::booleanValue).count();
        assertTrue(outlierCount >= 2, "跳点和它相邻的点都该被标记，实际标了 " + outlierCount);
    }

    @Test
    void 快速但平稳的轨迹不会被误标() {
        // 模拟 GeoLife 汽车轨迹：每点约 20 米/秒（72 km/h），中位数也是 20。
        // 阈值 = max(8, 3 × 20) = 60，所以 20 不该被标 —— 这就是"自适应"的意义。
        List<RawPoint> raw = new ArrayList<>();
        for (int i = 0; i < 30; i++) {
            raw.add(p(25.0 + i * 0.00018, 117.0, 10.0, i));
        }
        CleanedTrack c = cleaner.clean(raw);
        assertTrue(c.outliers().stream().noneMatch(Boolean::booleanValue),
                "高速但平稳的轨迹不该被标记");
    }

    @Test
    void 时间重复的点速度存_null() {
        List<RawPoint> raw = List.of(
                p(25.0, 117.0, 10.0, 0),
                p(25.000027, 117.0, 10.0, 0));
        CleanedTrack c = cleaner.clean(raw);
        assertNull(c.speeds().get(1), "时间差为 0 时速度无法计算，应为 null");
    }

    @Test
    void 总距离和总时长() {
        CleanedTrack c = cleaner.clean(straightLine(11, 10.0));
        assertEquals(10, c.durationS());
        assertTrue(c.distanceM() > 20 && c.distanceM() < 40,
                "10 段 × 约 3 米 ≈ 30 米，实际 " + c.distanceM());
    }

    /**
     * 真实数据端到端：用用户那份 2342 点的 GPX 跑完整清洗链。
     *
     * <p>期望值是先用 Python 独立算出来的（速度中位数 1.627 m/s → 阈值 max(8, 4.88) = 8.00
     * → 4 段超阈值 → 两端都标 → 8 个点）。**如果实现有偏差，这条测试会精确指出位置。**
     */
    @Test
    void 真实样本_标记正好_8_个异常点且位置精确() throws Exception {
        ParsedTrack parsed;
        try (InputStream in = getClass().getResourceAsStream("/sample.gpx")) {
            assertNotNull(in, "找不到 /sample.gpx 夹具");
            parsed = new GpxImporter().parse(in);
        }

        CleanedTrack c = cleaner.clean(parsed.points());

        assertEquals(2342, c.points().size());
        assertEquals(3933.5, c.distanceM(), 1.0, "总距离应与独立算出的 3933.5 米一致");

        List<Integer> flagged = new ArrayList<>();
        for (int i = 0; i < c.outliers().size(); i++) {
            if (Boolean.TRUE.equals(c.outliers().get(i))) {
                flagged.add(i);
            }
        }
        assertEquals(List.of(1128, 1129, 1135, 1136, 1144, 1145, 1585, 1586), flagged);

        // 海拔全是 0.0 → 应全部归 NULL
        assertTrue(c.points().stream().allMatch(x -> x.elevationM() == null));
    }
}
