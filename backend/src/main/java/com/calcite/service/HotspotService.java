package com.calcite.service;

import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * 停留热点聚类 —— 把跨轨迹、彼此挨得近的停留点合并成「热点」。
 *
 * <p><b>算法：并查集单链聚类</b>（等价于 {@code minPts = 2} 的 DBSCAN）。
 * 五步：
 * <ol>
 *   <li>两两算球面距离（复用 {@link GeoUtils#haversineMeters}）</li>
 *   <li>距离 ≤ radiusM 的连一条边</li>
 *   <li>并查集求连通分量 —— 每个分量就是一个簇</li>
 *   <li>簇内点数 &lt; minVisits 的判为<b>孤立点</b>，不进结果</li>
 *   <li>每个簇算出重心、三个热度口径、真实散布、首末访问时间</li>
 * </ol>
 *
 * <p><b>⚠️ 传递性（链式效应）</b>：单链聚类是传递的 ——
 * A 挨着 B、B 挨着 C，即使 A 和 C 相距 300 米，三个也会合成<b>一个</b>热点，
 * 于是这个热点横跨 300 米。这是算法定义，不是 bug，
 * {@code minPts=2} 的 DBSCAN 行为完全相同。已经有测试把它钉住。
 *
 * <p><b>复杂度 O(n²)</b>：当前停留点只有几十个，可以忽略；
 * 上万个时需要先按经纬度分桶再比较（见设计文档第 9 节「已知限制」）。
 *
 * <p>这是个<b>无状态</b>的类：参数走方法参数而不是构造器，
 * 因为 {@code radiusM} / {@code minVisits} 允许每次请求不同。
 * 测试里直接 {@code new HotspotService()} 就能跑。
 */
@Component
public class HotspotService {

    /**
     * 把停留点聚成热点。
     *
     * @param stays     所有（已按时间窗筛选过的）停留点，带 trackId 归属
     * @param radiusM   聚类半径（米）：两个停留点在此距离内视为同一地点
     * @param minVisits 至少几个停留点才算热点
     * @return 热点列表，按 trackCount → visitCount → totalDurationS 三级降序
     * @throws IllegalArgumentException 半径不是有限正数，或最少点数小于 1
     */
    public List<Hotspot> cluster(List<TrackedStay> stays, double radiusM, int minVisits) {
        // 注意用 !(radiusM > 0) 而不是 radiusM <= 0：
        // NaN <= 0 是 false，用后者会让 NaN 蒙混过关，之后 d <= NaN 恒为假，
        // 结果是"非法参数却返回 200 + 空列表"（从 HTTP 层 ?radiusM=NaN 可达）。
        // Infinity 也要挡掉：它会让所有停留点并成一个热点。
        if (!(radiusM > 0) || !Double.isFinite(radiusM)) {
            throw new IllegalArgumentException("聚类半径必须是有限正数，实际 " + radiusM);
        }
        if (minVisits < 1) {
            throw new IllegalArgumentException("最少停留点数必须 >= 1，实际 " + minVisits);
        }

        List<Hotspot> out = new ArrayList<>();
        if (stays == null || stays.size() < minVisits) {
            return out;
        }

        // ---- 1~3. 两两比较 + 并查集合并 ----
        int n = stays.size();
        int[] parent = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
        }

        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                StayPoint a = stays.get(i).stay();
                StayPoint b = stays.get(j).stay();
                double d = GeoUtils.haversineMeters(
                        a.centerLat(), a.centerLon(), b.centerLat(), b.centerLon());
                // 含等号：正好等于半径也算同一地点（有测试钉住）
                if (d <= radiusM) {
                    union(parent, i, j);
                }
            }
        }

        // ---- 4. 按根分组 ----
        Map<Integer, List<Integer>> groups = new LinkedHashMap<>();
        for (int i = 0; i < n; i++) {
            groups.computeIfAbsent(find(parent, i), k -> new ArrayList<>()).add(i);
        }
        for (List<Integer> members : groups.values()) {
            if (members.size() >= minVisits) {
                out.add(build(stays, members));
            }
        }

        // ---- 5. 排序：轨迹数优先（最接近"这是个公共地点"的含义），
        //         后面两级保证结果确定；最后用坐标兜底，让排序与输入顺序无关。
        out.sort(Comparator
                .comparingInt(Hotspot::trackCount).reversed()
                .thenComparing(Comparator.comparingInt(Hotspot::visitCount).reversed())
                .thenComparing(Comparator.comparingInt(Hotspot::totalDurationS).reversed())
                .thenComparingDouble(Hotspot::centerLat)
                .thenComparingDouble(Hotspot::centerLon));
        return out;
    }

    /** 并查集查找，带路径压缩（把链拍平，避免长链拖慢后面的查找） */
    private static int find(int[] parent, int x) {
        while (parent[x] != x) {
            parent[x] = parent[parent[x]];
            x = parent[x];
        }
        return x;
    }

    private static void union(int[] parent, int a, int b) {
        int ra = find(parent, a);
        int rb = find(parent, b);
        if (ra != rb) {
            parent[ra] = rb;
        }
    }

    /** 把一个簇（成员下标）汇总成一个 {@link Hotspot} */
    private static Hotspot build(List<TrackedStay> stays, List<Integer> members) {
        int count = members.size();
        double sumLat = 0;
        double sumLon = 0;
        int totalDuration = 0;
        OffsetDateTime first = null;
        OffsetDateTime last = null;
        Set<Long> trackIds = new TreeSet<>();   // TreeSet 顺便保证 trackIds 升序

        for (int idx : members) {
            StayPoint s = stays.get(idx).stay();
            sumLat += s.centerLat();
            sumLon += s.centerLon();
            totalDuration += s.durationS();
            if (first == null || s.startTime().isBefore(first)) {
                first = s.startTime();
            }
            if (last == null || s.endTime().isAfter(last)) {
                last = s.endTime();
            }
            trackIds.add(stays.get(idx).trackId());
        }

        double cLat = sumLat / count;
        double cLon = sumLon / count;

        // 真实散布：离重心最远的那个点多远（不是画出来的圈）
        double maxR = 0;
        for (int idx : members) {
            StayPoint s = stays.get(idx).stay();
            double d = GeoUtils.haversineMeters(cLat, cLon, s.centerLat(), s.centerLon());
            if (d > maxR) {
                maxR = d;
            }
        }

        return new Hotspot(cLat, cLon, count, trackIds.size(), totalDuration, maxR,
                first, last, new ArrayList<>(trackIds));
    }
}
