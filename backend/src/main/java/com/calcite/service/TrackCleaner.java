package com.calcite.service;

import com.calcite.service.importer.RawPoint;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * 轨迹清洗 —— **所有清洗规则只写在这一处**。
 *
 * <p>规则（详见设计文档第六节）：
 * <ol>
 *   <li>按时间升序排序</li>
 *   <li>算每点速度（第 0 点、以及时间差 &lt;= 0 的点为 null）</li>
 *   <li>海拔整条全同 → 全部置 null（"没记录"而不是"海拔 0"）</li>
 *   <li>速度超阈值 → 把该段**两端**都标记为疑似漂移</li>
 * </ol>
 *
 * <p>阈值是**自适应**的：{@code max(绝对下限, 倍数 × 该轨迹速度中位数)}。
 * 因为 GeoLife 里有汽车（20 m/s）甚至火车（80 m/s）轨迹，
 * 固定阈值会把它们全部误标成异常。
 */
public class TrackCleaner {

    private final double maxSpeedMps;
    private final double speedMedianFactor;

    public TrackCleaner(double maxSpeedMps, double speedMedianFactor) {
        this.maxSpeedMps = maxSpeedMps;
        this.speedMedianFactor = speedMedianFactor;
    }

    public CleanedTrack clean(List<RawPoint> raw) {
        if (raw == null || raw.size() < 2) {
            throw new IllegalArgumentException("至少需要 2 个轨迹点");
        }

        // ① 排序
        List<RawPoint> pts = new ArrayList<>(raw);
        pts.sort(Comparator.comparing(RawPoint::recordedAt));
        int n = pts.size();

        // ② 每点速度（第 i 点的速度 = 从 i-1 走到 i 的速度）
        List<Double> speeds = new ArrayList<>(n);
        double totalDistance = 0;
        for (int i = 0; i < n; i++) {
            if (i == 0) {
                speeds.add(null);
                continue;
            }
            RawPoint a = pts.get(i - 1);
            RawPoint b = pts.get(i);
            double d = GeoUtils.haversineMeters(a.lat(), a.lon(), b.lat(), b.lon());
            totalDistance += d;
            double dt = Duration.between(a.recordedAt(), b.recordedAt()).toMillis() / 1000.0;
            speeds.add(dt > 0 ? d / dt : null);
        }

        // ③ 自适应阈值 + 标记
        double threshold = thresholdFor(speeds);
        List<Boolean> outliers = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            outliers.add(false);
        }
        for (int i = 1; i < n; i++) {
            Double v = speeds.get(i);
            if (v != null && v > threshold) {
                // 无法判断是段的哪一端漂了，两端都标（宁可多标，不可漏标）
                outliers.set(i - 1, true);
                outliers.set(i, true);
            }
        }

        // ④ 海拔归一化
        List<RawPoint> fixed = normalizeElevation(pts);

        int durationS = (int) Duration.between(
                pts.get(0).recordedAt(), pts.get(n - 1).recordedAt()).toSeconds();
        return new CleanedTrack(fixed, speeds, outliers, totalDistance, durationS);
    }

    /** 阈值 = max(绝对下限, 倍数 × 中位数)；没有任何有效速度时只用绝对下限 */
    private double thresholdFor(List<Double> speeds) {
        List<Double> valid = new ArrayList<>();
        for (Double v : speeds) {
            if (v != null && v > 0) {
                valid.add(v);
            }
        }
        if (valid.isEmpty()) {
            return maxSpeedMps;
        }
        valid.sort(Comparator.naturalOrder());
        int m = valid.size();
        double median = (m % 2 == 1)
                ? valid.get(m / 2)
                : (valid.get(m / 2 - 1) + valid.get(m / 2)) / 2.0;
        return Math.max(maxSpeedMps, speedMedianFactor * median);
    }

    /**
     * 海拔全同（含全部为 null）时，一律当成"没有海拔数据"。
     *
     * <p>实测样本 ele 全是 0.0 —— 存 0 会让前端画出一条贴着底边的直线，
     * 而福建校园实际海拔约 300 米，0 表示"没记录"。
     * 前端已经有"这条轨迹没有海拔数据"的降级显示。
     */
    private static List<RawPoint> normalizeElevation(List<RawPoint> pts) {
        Double first = pts.get(0).elevationM();
        boolean allSame = true;
        for (RawPoint p : pts) {
            Double e = p.elevationM();
            if (first == null ? e != null : !first.equals(e)) {
                allSame = false;
                break;
            }
        }
        if (!allSame) {
            return pts;
        }
        List<RawPoint> out = new ArrayList<>(pts.size());
        for (RawPoint p : pts) {
            out.add(new RawPoint(p.lat(), p.lon(), null, p.recordedAt()));
        }
        return out;
    }
}
