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
