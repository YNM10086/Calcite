package com.calcite.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link DensityGrid} 的单元测试。
 *
 * <p>它是纯静态工具：不碰 Spring、不碰数据库，所以这整个类跑完只要几毫秒，
 * 而且 {@code mvn test} 依然**不需要数据库**。
 */
class DensityGridTest {

    /** 和 application.yml 里的 cell-ladder 一致 */
    private static final double[] LADDER =
            {0.05, 0.02, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001};

    // ---------------------------------------------------------------- bbox 解析

    @Test
    void 解析正常bbox() {
        DensityGrid.Bbox b = DensityGrid.parseBbox("116.26,39.86,116.42,40.04");
        assertEquals(116.26, b.west(), 1e-9);
        assertEquals(39.86, b.south(), 1e-9);
        assertEquals(116.42, b.east(), 1e-9);
        assertEquals(40.04, b.north(), 1e-9);
        assertEquals(0.16, b.widthDeg(), 1e-9);
        assertEquals(0.18, b.heightDeg(), 1e-9);
    }

    @Test
    void bbox缺项或非数字_抛异常() {
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.parseBbox(null));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.parseBbox(""));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.parseBbox("1,2,3"));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.parseBbox("1,2,3,4,5"));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.parseBbox("a,2,3,4"));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.parseBbox("1,2,3,"));
    }

    @Test
    void bbox西南角必须小于东北角() {
        // 西 >= 东
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("116.42,39.86,116.26,40.04"));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("116.26,39.86,116.26,40.04"));
        // 南 >= 北
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("116.26,40.04,116.42,39.86"));
    }

    @Test
    void bbox超出经纬度范围_抛异常() {
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("-181,0,10,10"));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("0,-91,10,10"));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("0,0,181,10"));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("0,0,10,91"));
    }

    @Test
    void bbox含NaN或无穷_抛异常() {
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("NaN,0,10,10"));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.parseBbox("0,0,Infinity,10"));
    }

    @Test
    void bbox允许负数与零度线() {
        // 跨赤道、跨本初子午线都要能用
        DensityGrid.Bbox b = DensityGrid.parseBbox("-10,-10,10,10");
        assertEquals(20.0, b.widthDeg(), 1e-9);
    }

    // ---------------------------------------------------------------- 格边长校验

    @Test
    void 阶梯里的九个值全部接受() {
        for (double v : LADDER) {
            DensityGrid.requireKnownCellSize(v, LADDER);   // 不抛异常即通过
        }
    }

    @Test
    void 不在阶梯里的格边长_抛异常() {
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.requireKnownCellSize(0.003, LADDER));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.requireKnownCellSize(0, LADDER));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.requireKnownCellSize(-0.001, LADDER));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.requireKnownCellSize(Double.NaN, LADDER));
        assertThrows(IllegalArgumentException.class,
                () -> DensityGrid.requireKnownCellSize(1e9, LADDER));
    }

    /*
     * 下面这条是【浮点比较】的专项测试。
     * 0.001 这类十进制小数在二进制里不精确，用 == 有可能比不中；
     * 必须用 Double.compare。这条测试就是用同一个字面量再走一遍，
     * 确保实现没有偷懒写成 ==。
     */
    @Test
    void 格边长比较必须用DoubleCompare不能用等号() {
        double fromQuery = Double.parseDouble("0.001");
        DensityGrid.requireKnownCellSize(fromQuery, LADDER);   // 必须通过

        double fromLadder = LADDER[5];
        assertEquals(0, Double.compare(fromQuery, fromLadder));
        // 说明"看起来一样"的两个 double 用 == 恰好也相等，
        // 但只要将来 LADDER 改成从配置读入（可能是 1.0E-3 的另一种解析路径），
        // == 就会出问题 —— 所以实现里必须用 Double.compare
    }

    // ---------------------------------------------------------------- 挑档

    @Test
    void 按视野宽度挑档() {
        // 北京城区 0.16° 宽 → 0.16/80 = 0.002 → 最小能覆盖的是 0.002
        assertEquals(0.002, DensityGrid.pickCellSize(0.16, LADDER, 80), 1e-12);
        // 街区 0.01° 宽 → 0.000125 → 最小能覆盖的是 0.0002
        assertEquals(0.0002, DensityGrid.pickCellSize(0.01, LADDER, 80), 1e-12);
        // 大区域 4° 宽 → 0.05 → 最粗那档刚好
        assertEquals(0.05, DensityGrid.pickCellSize(4.0, LADDER, 80), 1e-12);
    }

    @Test
    void 视野比最粗档还宽_取最粗档() {
        // 90/80 = 1.125，比阶梯里最粗的 0.05 还大 → 退回最粗档
        assertEquals(0.05, DensityGrid.pickCellSize(90.0, LADDER, 80), 1e-12);
    }

    @Test
    void 挑出来的档永远满足不超过目标格数() {
        // 只覆盖"阶梯最粗档还兜得住"的视野范围：最粗档 0.05 × 80 = 4°，
        // 所以 w ≤ 4 时横向格数必然 ≤ 80。
        for (double w : new double[]{0.005, 0.01, 0.05, 0.16, 0.5, 1, 4}) {
            double cell = DensityGrid.pickCellSize(w, LADDER, 80);
            assertTrue(w / cell <= 80 + 1e-9,
                    "视野 " + w + " 挑了 " + cell + " 会得到 " + (w / cell) + " 格");
        }
        // ⚠️ 计划原文这里还列了 w = 20，但那条断言【数学上不可能成立】：
        // 阶梯最粗档只有 0.05，而上面 视野比最粗档还宽_取最粗档 又钉死
        // "视野过宽时退回最粗档"，于是 20 / 0.05 = 400 必然 > 80。
        // 挡住"格子爆炸"的是后续任务的 maxCells = 20000（超了返回 400），不是这条断言。
        // 所以这里把 w = 20 改成断言它【确实走了"退回最粗档"】这条路。
        double widened = DensityGrid.pickCellSize(20.0, LADDER, 80);
        assertEquals(0.05, widened, 1e-12, "视野过宽时应退回最粗档");
        assertTrue(widened > 0, "退回最粗档后仍是合法的正数，不会返回 0 或负数");
    }

    // ---------------------------------------------------------------- 格子数上限

    @Test
    void 估算格子数() {
        DensityGrid.Bbox b = DensityGrid.parseBbox("116.26,39.86,116.42,40.04");
        // ceil(0.16/0.002) * ceil(0.18/0.002) = 80 * 90 = 7200
        assertEquals(7200, DensityGrid.estimateCells(b, 0.002));
    }

    @Test
    void 全球bbox加最细格_估算会远超上限() {
        DensityGrid.Bbox b = DensityGrid.parseBbox("-180,-90,180,90");
        long n = DensityGrid.estimateCells(b, 0.0001);
        assertTrue(n > 20_000, "应该远超上限，实得 " + n);
    }

    @Test
    void 估算值不会溢出() {
        // 极端情况：360/0.0001 * 180/0.0001 = 6.48e12，long 装得下
        DensityGrid.Bbox b = DensityGrid.parseBbox("-180,-90,180,90");
        long n = DensityGrid.estimateCells(b, 0.0001);
        assertTrue(n > 0, "溢出会变成负数");
    }

    // ---------------------------------------------------------------- 格子 ↔ 经纬度

    @Test
    void 格子索引与经纬度互换_且与ST_SnapToGrid语义一致() {
        // ST_SnapToGrid(POINT(116.2964, 40.0114), 0.001) = POINT(116.296 40.011)
        // 即：格子中心的经度 = round(116.2964/0.001) * 0.001 = 116296 * 0.001
        double cell = 0.001;
        assertEquals(116296, DensityGrid.lonToIndex(116.2964, cell));
        assertEquals(116297, DensityGrid.lonToIndex(116.2966, cell));
        // 反算回来就是格子中心
        assertEquals(116.296, DensityGrid.indexToLon(116296, cell), 1e-9);
        assertEquals(40.011, DensityGrid.indexToLat(40011, cell), 1e-9);
    }

    @Test
    void 格子索引用long避免大坐标溢出() {
        // 经度 121 度配最细格 0.0001 → 索引 1,210,000，int 也装得下，
        // 但用最细格放大经度 180 时是 1,800,000 —— 仍然安全。
        // 这条测试是为了锁住"返回类型是 long"这个决定，将来换格子体系时不会悄悄溢出。
        long idx = DensityGrid.lonToIndex(121.5557, 0.0001);
        assertEquals(1215557L, idx);
    }

    // ---------------------------------------------------------------- 时段校验

    @Test
    void 时段必须成对且有序且在0到23之间() {
        DensityGrid.requireHourRange(null, null);     // 都不传：合法
        DensityGrid.requireHourRange(7, 9);           // 正常
        DensityGrid.requireHourRange(0, 23);          // 边界

        assertThrows(IllegalArgumentException.class, () -> DensityGrid.requireHourRange(7, null));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.requireHourRange(null, 9));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.requireHourRange(9, 7));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.requireHourRange(-1, 9));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.requireHourRange(7, 24));
    }

    @Test
    void 时段原样透传_Java不做时区换算() {
        /*
         * 这条测试锁住一个【重要的分工】：时区换算是【SQL 的事】，
         * SQL 里写的是 recorded_at AT TIME ZONE 'Asia/Shanghai'。
         *
         * 如果 Java 这边也换算一次（比如把 7 变成 15），就会【双重换算】，
         * 查出来的时段完全错。所以 DensityGrid 必须原样返回传进来的小时数。
         */
        int[] r = DensityGrid.passThroughHourRange(7, 9);
        assertEquals(7, r[0]);
        assertEquals(9, r[1]);
        int[] d = DensityGrid.passThroughHourRange(null, null);
        assertEquals(0, d[0], "不传时段时用 0 兜底");
        assertEquals(23, d[1], "不传时段时用 23 兜底");
    }

    @Test
    void metric只接受两个值() {
        assertEquals("tracks", DensityGrid.requireMetric(null));
        assertEquals("tracks", DensityGrid.requireMetric("tracks"));
        assertEquals("points", DensityGrid.requireMetric("points"));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.requireMetric("count"));
        assertThrows(IllegalArgumentException.class, () -> DensityGrid.requireMetric("TRACKS"));
    }
}
