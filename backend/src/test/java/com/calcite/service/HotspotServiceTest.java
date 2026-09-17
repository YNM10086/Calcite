package com.calcite.service;

import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 停留热点聚类的单元测试。
 *
 * <p>{@link HotspotService} 是纯函数：不碰数据库、不碰 Spring，
 * 所以这里直接 {@code new} 出来就能测，整类跑完只要几毫秒。
 */
class HotspotServiceTest {

    private final HotspotService svc = new HotspotService();

    /** 1 度纬度 ≈ 111195 米（和 StayPointServiceTest 用同一个换算） */
    private static final double M_PER_DEG_LAT = 111195.0;

    /** 基准纬度 */
    private static final double LAT0 = 40.0;

    /** 基准经度 */
    private static final double LON0 = 116.0;

    /** 基准时刻 —— 所有合成用例都从这里开始，避免测试依赖运行时间 */
    private static final OffsetDateTime T0 = OffsetDateTime.parse("2008-10-23T09:00:00Z");

    /**
     * 造一个停留点。
     *
     * @param trackId   属于哪条轨迹
     * @param latOffset 纬度偏移（度），用来控制两点之间的距离
     * @param durationS 停留时长（秒）
     * @param startSec  相对 T0 的开始秒数，用来控制先后顺序
     */
    private static TrackedStay stay(long trackId, double latOffset, int durationS, int startSec) {
        OffsetDateTime start = T0.plusSeconds(startSec);
        return new TrackedStay(trackId, new StayPoint(
                0, 0,
                start,
                start.plusSeconds(durationS),
                durationS,
                LON0,                    // centerLon
                LAT0 + latOffset,        // centerLat
                10.0,                    // radiusM
                5));                     // pointCount
    }

    /** 纬度偏移多少度 = 多少米 */
    private static double latFor(double meters) {
        return meters / M_PER_DEG_LAT;
    }

    // ---------------------------------------------------------------- 基本

    @Test
    void 空列表_返回空结果() {
        assertTrue(svc.cluster(List.of(), 200, 2).isEmpty());
        assertTrue(svc.cluster(null, 200, 2).isEmpty());
    }

    @Test
    void 只有一个停留点_不够门槛_返回空() {
        assertTrue(svc.cluster(List.of(stay(1, 0, 300, 0)), 200, 2).isEmpty());
    }

    @Test
    void 两点相距150米_合并成一个热点() {
        List<Hotspot> out = svc.cluster(List.of(
                stay(1, 0, 300, 0),
                stay(2, latFor(150), 400, 600)), 200, 2);

        assertEquals(1, out.size());
        assertEquals(2, out.get(0).visitCount());
    }

    @Test
    void 两点相距250米_超过半径_不算热点() {
        assertTrue(svc.cluster(List.of(
                stay(1, 0, 300, 0),
                stay(2, latFor(250), 400, 600)), 200, 2).isEmpty());
    }

    // ---------------------------------------------------------------- 边界

    @Test
    void 正好等于两点距离_含等号_应该合并() {
        /*
         * 半径判断写的是 <= radiusM，所以"正好相等"也要合并。
         * 这条钉住"含等号"，防止有人把 <= 改成 <。
         *
         * ⚠️ 这里【不能用 200 米这个整数】去测边界：latFor(200) 换算回米是
         * 199.99987，和 200 只差 0.0001 米，浮点误差稍微偏一点就会变成
         * "刚好不相等"，测试变成看运气。正确做法是先用同一个 haversine
         * 把两点的【实际距离】算出来，再拿它当半径 —— 这样 <= 必然成立。
         */
        double d = GeoUtils.haversineMeters(LAT0, LON0, LAT0 + latFor(200), LON0);
        List<Hotspot> out = svc.cluster(List.of(
                stay(1, 0, 300, 0),
                stay(2, latFor(200), 400, 600)), d, 2);

        assertEquals(1, out.size(), "半径正好等于两点距离时应该合并");
    }

    @Test
    void 半径差一点没过_不应该合并() {
        // 两点相距约 201 米，半径 200 米 → 分成两个孤立点
        assertTrue(svc.cluster(List.of(
                stay(1, 0, 300, 0),
                stay(2, latFor(201), 400, 600)), 200.0, 2).isEmpty());
    }

    // ---------------------------------------------------------------- 传递性（最重要）

    @Test
    void 传递性_链式效应_A到C虽远但仍合成一个热点() {
        /*
         * 单链聚类的固有行为：
         *   A ──150m── B ──150m── C      但 A 和 C 相距 300 米
         * 三个会合并成【一个】热点，这个热点横跨 300 米。
         *
         * 这不是 bug，是单链聚类（以及 minPts=2 的 DBSCAN）的定义。
         * 这条测试把它【钉住】：将来谁改了聚类策略，这里会立刻红。
         */
        List<Hotspot> out = svc.cluster(List.of(
                stay(1, 0, 300, 0),
                stay(2, latFor(150), 300, 600),
                stay(3, latFor(300), 300, 1200)), 200, 2);

        assertEquals(1, out.size(), "链式效应：应该合并成一个");
        assertEquals(3, out.get(0).visitCount());
        // 真实散布应该接近 150 米（重心在 B 上，A 和 C 各离 150 米）
        assertEquals(150, out.get(0).radiusM(), 2.0);
    }

    // ---------------------------------------------------------------- 统计正确性

    @Test
    void 同一条轨迹的三个点_visitCount为3但trackCount为1() {
        List<Hotspot> out = svc.cluster(List.of(
                stay(7, 0, 200, 0),
                stay(7, latFor(20), 300, 300),
                stay(7, latFor(-20), 400, 600)), 200, 2);

        assertEquals(1, out.size());
        assertEquals(3, out.get(0).visitCount(), "三个停留点");
        assertEquals(1, out.get(0).trackCount(), "但只来自 1 条轨迹");
        assertEquals(List.of(7L), out.get(0).trackIds());
    }

    @Test
    void 累计时长与首末访问时间正确() {
        List<Hotspot> out = svc.cluster(List.of(
                stay(1, 0, 300, 0),          // 09:00:00 → 09:05:00
                stay(2, latFor(50), 400, 3600), // 10:00:00 → 10:06:40
                stay(3, latFor(-50), 200, 7200)), // 11:00:00 → 11:03:20
                200, 2);

        Hotspot h = out.get(0);
        assertEquals(900, h.totalDurationS(), "300 + 400 + 200");
        assertEquals(T0, h.firstVisit());
        assertEquals(T0.plusSeconds(7200 + 200), h.lastVisit());
        assertEquals(3, h.trackCount());
    }

    @Test
    void 重心是三个点的平均位置() {
        List<Hotspot> out = svc.cluster(List.of(
                stay(1, 0, 300, 0),
                stay(2, latFor(60), 300, 600),
                stay(3, latFor(-60), 300, 1200)), 200, 2);

        Hotspot h = out.get(0);
        // 三个点的纬度偏移是 0、+60m、-60m，重心应该回到基准纬度
        assertEquals(LAT0, h.centerLat(), 1e-9);
        assertEquals(LON0, h.centerLon(), 1e-9);
    }

    // ---------------------------------------------------------------- 排序

    @Test
    void 按轨迹数_次数_时长的三级降序排列() {
        /*
         * 造三个互不相干的热点，故意让三种口径的排序不一致，
         * 检验排序键的优先级是 trackCount > visitCount > totalDurationS。
         *
         *   热点甲：2 条轨迹、2 次、时长 1000  → trackCount=2 最高
         *   热点乙：1 条轨迹、3 次、时长 3000  → 次数和时长都最高，但只有 1 条轨迹
         *   热点丙：1 条轨迹、2 次、时长  600
         *
         * 期望顺序：甲、乙、丙
         * （乙排丙前面，是因为同为 1 条轨迹时比 visitCount：3 > 2）
         */
        double far = latFor(5000);   // 各热点之间隔 5 公里，绝不互连
        List<TrackedStay> stays = new ArrayList<>();
        stays.add(stay(1, 0, 500, 0));
        stays.add(stay(2, latFor(30), 500, 100));        // 甲：轨迹 1 + 2，2 次，1000 秒
        stays.add(stay(3, far, 1000, 200));
        stays.add(stay(3, far + latFor(30), 1000, 300));
        stays.add(stay(3, far - latFor(30), 1000, 400)); // 乙：轨迹 3 三次，3000 秒
        stays.add(stay(4, far * 2, 300, 500));
        stays.add(stay(4, far * 2 + latFor(30), 300, 600)); // 丙：轨迹 4 两次，600 秒

        List<Hotspot> out = svc.cluster(stays, 200, 2);

        assertEquals(3, out.size());
        assertEquals(2, out.get(0).trackCount(), "甲：2 条轨迹，trackCount 最高应排第一");
        assertEquals(1, out.get(1).trackCount());
        assertEquals(3, out.get(1).visitCount(), "乙：同为 1 条轨迹，3 次多于丙的 2 次");
        assertEquals(1, out.get(2).trackCount());
        assertEquals(2, out.get(2).visitCount(), "丙：1 条轨迹、2 次，排最后");
    }

    // ---------------------------------------------------------------- 参数校验

    @Test
    void 非法参数_抛异常() {
        List<TrackedStay> one = List.of(stay(1, 0, 300, 0));
        assertThrows(IllegalArgumentException.class, () -> svc.cluster(one, 0, 2));
        assertThrows(IllegalArgumentException.class, () -> svc.cluster(one, -1, 2));
        assertThrows(IllegalArgumentException.class, () -> svc.cluster(one, 200, 0));
    }

    // ---------------------------------------------------------------- 真实数据指纹

    /**
     * 真实数据指纹 —— 本设计最强的一道防线。
     *
     * <p>这 10 个停留点是第一阶段算法跑在<b>真实 GeoLife 数据</b>上的实际输出
     * （25 条轨迹 → 10 个停留点，来自 6 条轨迹）。把它们固化成夹具，
     * 于是这个测试<b>不需要连数据库</b>，却仍然钉住了真实数据上的行为。
     *
     * <p>坐标是<b>全精度</b>的：只保留 5 位小数会带来约 1 米误差，
     * 下面 1e-6 的容差会直接失败。
     */
    @Test
    void 真实数据指纹_25条轨迹的10个停留点_聚出3个热点() {
        List<Hotspot> out = svc.cluster(realStays(), 200.0, 2);

        assertEquals(3, out.size(), "10 个停留点应聚成 3 个热点（第 4 个是孤立点）");

        // ---- 第 1 名：同一个人三周内去了 4 次，真实散布只有 9.4 米 ----
        Hotspot h1 = out.get(0);
        assertEquals(4, h1.visitCount());
        assertEquals(3, h1.trackCount());
        assertEquals(1730, h1.totalDurationS());
        assertEquals(40.011572079862056, h1.centerLat(), 1e-6);
        assertEquals(116.29685339946353, h1.centerLon(), 1e-6);
        assertEquals(9.4, h1.radiusM(), 0.2);
        assertEquals(List.of(9L, 13L, 15L), h1.trackIds());
        assertEquals(OffsetDateTime.parse("2008-10-28T00:50:51Z"), h1.firstVisit());
        assertEquals(OffsetDateTime.parse("2008-11-11T00:47:19Z"), h1.lastVisit());

        // ---- 第 2 名：3 条不同轨迹 ----
        Hotspot h2 = out.get(1);
        assertEquals(3, h2.visitCount());
        assertEquals(3, h2.trackCount());
        assertEquals(1228, h2.totalDurationS());
        assertEquals(40.008947523765194, h2.centerLat(), 1e-6);
        assertEquals(116.32179345650702, h2.centerLon(), 1e-6);
        assertEquals(58.1, h2.radiusM(), 0.2);
        assertEquals(List.of(5L, 6L, 20L), h2.trackIds());

        // ---- 第 3 名：同一个人去了两次（visitCount=2 但 trackCount=1）----
        Hotspot h3 = out.get(2);
        assertEquals(2, h3.visitCount());
        assertEquals(1, h3.trackCount(), "热点③是同一条轨迹去的两次");
        assertEquals(650, h3.totalDurationS());
        assertEquals(40.006718938490216, h3.centerLat(), 1e-6);
        assertEquals(116.29656240959926, h3.centerLon(), 1e-6);
        assertEquals(59.1, h3.radiusM(), 0.2);
        assertEquals(List.of(13L), h3.trackIds());

        // ---- 三个热点的停留次数之和 = 9，说明有 1 个孤立点被正确排除 ----
        int counted = out.stream().mapToInt(Hotspot::visitCount).sum();
        assertEquals(9, counted, "10 个停留点里有 1 个是孤立点，不该出现在结果里");
    }

    /**
     * 真实数据夹具：第一阶段算法在真实 GeoLife 数据上的输出。
     * 顺序按 (trackId, seqStart) 升序，保证每次运行完全一致。
     */
    private static List<TrackedStay> realStays() {
        return List.of(
                stay(5L, 40.00906266197183, 116.32149105633802, 306, "2008-10-23T09:50:00Z", "2008-10-23T09:55:06Z", 519, 589, 24.215799510639496, 71),
                stay(6L, 40.008726843750004, 116.32241185416665, 402, "2008-10-24T02:22:44Z", "2008-10-24T02:29:26Z", 80, 175, 22.167435476202346, 96),
                stay(9L, 40.01161354729732, 116.29689937837843, 660, "2008-10-28T00:50:51Z", "2008-10-28T01:01:51Z", 46, 193, 24.59633808047982, 148),
                stay(9L, 40.00944270588235, 116.29635011764705, 340, "2008-10-28T01:15:56Z", "2008-10-28T01:21:36Z", 340, 356, 24.987748189554406, 17),
                stay(13L, 40.01159970786516, 116.29682875280899, 385, "2008-11-04T00:52:33Z", "2008-11-04T00:58:58Z", 646, 734, 20.29234811820001, 89),
                stay(13L, 40.006805945945956, 116.2958774054054, 335, "2008-11-04T01:47:48Z", "2008-11-04T01:53:23Z", 1232, 1268, 24.798514782692745, 37),
                stay(13L, 40.00663193103448, 116.2972474137931, 315, "2008-11-04T02:07:38Z", "2008-11-04T02:12:53Z", 1417, 1445, 24.94529300120479, 29),
                stay(15L, 40.011487528571436, 116.29686108571428, 315, "2008-11-11T00:34:29Z", "2008-11-11T00:39:44Z", 68, 137, 24.676304667785836, 70),
                stay(15L, 40.0115875357143, 116.2968243809524, 370, "2008-11-11T00:41:09Z", "2008-11-11T00:47:19Z", 156, 239, 22.460169311980707, 84),
                stay(20L, 40.00905306557375, 116.32147745901645, 520, "2008-11-14T11:19:39Z", "2008-11-14T11:28:19Z", 161, 221, 21.3308383968773, 61)
        );
    }

    /** 真实数据夹具专用的重载：经纬度直接给，时间直接给字符串 */
    private static TrackedStay stay(long trackId, double lat, double lon, int durationS,
                                    String start, String end,
                                    int seqStart, int seqEnd, double radiusM, int pointCount) {
        return new TrackedStay(trackId, new StayPoint(
                seqStart, seqEnd,
                OffsetDateTime.parse(start),
                OffsetDateTime.parse(end),
                durationS,
                lon, lat, radiusM, pointCount));
    }
}
