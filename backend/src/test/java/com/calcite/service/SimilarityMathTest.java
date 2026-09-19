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
