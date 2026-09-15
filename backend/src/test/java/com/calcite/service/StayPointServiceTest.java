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

    /** 走 60 秒（每秒 3 米）之后所处的位置纬度，测试里当常量用 */
    private static final double LAT_60_STEPS = 25.0 + 60 * 3.0 * DEG_PER_METER_LAT;

    @Test
    void 匀速移动的轨迹_没有任何停留() {
        // 每秒走 3 米走 600 秒：每一步都在动，任何窗口都撑不到 25 米半径以外再停下
        assertTrue(svc.detect(walk(25.0, 0, 600, 3.0)).isEmpty());
    }

    @Test
    void 中间停了一段_正好识别出_1_个停留() {
        List<RawPoint> pts = new ArrayList<>();
        pts.addAll(walk(25.0, 0, 60, 3.0));               // 先走 60 秒（下标 0..59）
        pts.addAll(stay(LAT_60_STEPS, 117.0, 60, 660, 10)); // 在原地停 600 秒（下标 60..120）
        pts.addAll(walk(LAT_60_STEPS, 660, 60, 3.0));     // 再走

        List<StayPoint> stays = svc.detect(pts);

        assertEquals(1, stays.size());
        StayPoint s = stays.get(0);
        /*
         * 起点会**早于**下标 60（真正停下来的那一刻）：走过来的最后几秒还在 25 米半径内，
         * 算法会把它们一起算进这段 —— 这是经典滑动窗口的正常行为（"多吃"接近的几秒）。
         * 这里只断言它不会跑到更早的地方去。
         */
        assertTrue(s.seqStart() >= 45 && s.seqStart() <= 60,
                "起点应落在停留开始前后几秒内，实际 " + s.seqStart());
        /*
         * 时长是 579 秒而不是整 600 秒 —— 同样是"从最左可行点贪心扩窗"的固有特性：
         * 起点早了，重心就被接近的那几个点往北拉，能容纳的停留点数就变少，于是结束得也早。
         * 真实数据上的偏差很小（见最后那条指纹测试），这里把它钉住，
         * 以后谁改了扩窗策略，这条会立刻红。
         */
        assertEquals(579, s.durationS());
        assertTrue(s.radiusM() <= 25.5, "活动半径不该超过上限，实际 " + s.radiusM());
        assertEquals(LAT_60_STEPS, s.centerLat(), 1e-4);
    }

    @Test
    void 停了两次_识别出_2_个停留() {
        List<RawPoint> pts = new ArrayList<>();
        pts.addAll(stay(25.0, 117.0, 0, 400, 10));          // 第 1 次停留
        pts.addAll(walk(25.0, 400, 120, 3.0));              // 走 120 秒（走出 360 米，远超半径）
        pts.addAll(stay(LAT_60_STEPS * 2, 117.0, 520, 920, 10)); // 第 2 次停留
        pts.addAll(walk(LAT_60_STEPS * 2, 920, 120, 3.0));  // 再走

        List<StayPoint> stays = svc.detect(pts);

        assertEquals(2, stays.size(), "两次分开的停留不能合并，也不能漏掉第二次");
        assertTrue(stays.get(0).durationS() >= 400, "第 1 段实际 " + stays.get(0).durationS());
        assertTrue(stays.get(1).durationS() >= 400, "第 2 段实际 " + stays.get(1).durationS());
    }

    @Test
    void 采样断档_不会被拼成超长停留() {
        // 场景来自真实数据：停 1 分钟 -> 断档 1 小时 -> 在原地恢复
        List<RawPoint> pts = new ArrayList<>();
        pts.addAll(stay(25.0, 117.0, 0, 60, 20));          // 停 60 秒（本来就不够 T）
        pts.addAll(stay(25.0, 117.0, 3660, 3720, 20));     // 断档 1 小时后又停 60 秒

        assertTrue(svc.detect(pts).isEmpty(),
                "断档两边的停留各自都不够时长，不该被拼成一段超长停留");
    }

    @Test
    void 采样断档_两边各自够长时各算一段() {
        // 这一条是上个测试的反面：两边都够长，应该切成两段，而不是丢掉后一段
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
        // 两点相距 48 米 -> 重心在中点 -> 半径 24 米 < 25。
        // 注意间隔必须 <= G(300)，否则会被断档规则切开
        List<RawPoint> pts = List.of(
                at(25.0, 117.0, 0),
                at(25.0 + 48 * DEG_PER_METER_LAT, 117.0, 300));
        assertEquals(1, svc.detect(pts).size());
    }

    @Test
    void 半径超出阈值_不该被识别() {
        // 两点相距 52 米 -> 半径 26 米 > 25
        List<RawPoint> pts = List.of(
                at(25.0, 117.0, 0),
                at(25.0 + 52 * DEG_PER_METER_LAT, 117.0, 300));
        assertTrue(svc.detect(pts).isEmpty());
    }

    @Test
    void 点数不足两个_返回空列表而不是报错() {
        assertTrue(svc.detect(null).isEmpty());
        assertTrue(svc.detect(List.of()).isEmpty());
        assertTrue(svc.detect(List.of(at(25.0, 117.0, 0))).isEmpty());
    }

    @Test
    void 全部点在同一位置_识别为一段停留且半径接近零() {
        List<StayPoint> stays = svc.detect(stay(25.0, 117.0, 0, 900, 30));
        assertEquals(1, stays.size());
        assertEquals(0.0, stays.get(0).radiusM(), 0.5);
        assertEquals(31, stays.get(0).pointCount());
        assertEquals(900, stays.get(0).durationS());
    }

    /**
     * 真实数据指纹：用已导入的真实 GeoLife 文件（{@code 20081023025304}）。
     *
     * <p>这四个数字（1 段 / 306 秒 / 半径 24.2 米 / 71 点）是先用 Python 独立算出来的，
     * 而且**离两个阈值都很近**（时长只超阈值 6 秒、半径离上限只差 0.8 米）——
     * 算法一旦被改动，这条测试会立刻变红。<b>这就是它的价值。</b>
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
