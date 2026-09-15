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
 *   <li>{@code radiusM}（D）停留直径：窗口内所有点到中心的距离不能超过它的一半</li>
 *   <li>{@code minDurationS}（T）最短停留时长</li>
 *   <li>{@code maxGapS}（G）窗口内相邻两点的最大时间间隔 ——
 *       <b>这条是用来防「信号中断被当成超长停留」的</b>。它来自真实数据里的一个坑：
 *       有一条轨迹断了 8217 秒（2.3 小时）之后在原地恢复，不加这条规则会被判成
 *       「停留了 2.3 小时」，21 条轨迹的停留段数也会从正确的 10 虚高到 23</li>
 * </ul>
 *
 * <p>复杂度：外层遍历 O(n)，每次扩窗要重算重心 O(w)，所以最坏 O(n × w)。
 * 真实数据里 w 一般是几十到几百，实测都在毫秒级。
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
