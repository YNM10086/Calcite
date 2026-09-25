package com.calcite.service;

import com.calcite.config.WithinProperties;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.WithinRequest;
import com.calcite.web.dto.WithinResponse;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 空间范围查询的编排层：结构校验 → 区域准备（含拓扑校验）→ 命中 id → 统计 → items → 截断。
 *
 * <p><b>为什么"区域内没有轨迹"要提前返回</b>：没有命中轨迹时，那条最贵的点统计
 * （180~456 ms）必然返回 0 —— 直接跳过它，空区域就变成一次几乎不花时间的请求。
 * 这个推理成立的前提是：点落在区域内 ⇒ 它所在的轨迹线必然穿过该区域 ⇒ 该轨迹一定在命中集合里。
 */
@Service
public class WithinService {

    /** 无限宽时间窗的边界：我们的数据是 2008~2009，这个范围远超它 */
    private static final OffsetDateTime MIN_TIME = OffsetDateTime.of(1900, 1, 1, 0, 0, 0, 0, ZoneOffset.UTC);
    private static final OffsetDateTime MAX_TIME = OffsetDateTime.of(2999, 12, 31, 23, 59, 59, 0, ZoneOffset.UTC);

    private static final ObjectMapper JSON = new ObjectMapper();

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final WithinProperties props;

    public WithinService(TrackRepository trackRepository,
                         TrackPointRepository trackPointRepository,
                         WithinProperties props) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.props = props;
    }

    public WithinResponse within(WithinRequest req) {
        // ── 1. 结构校验（纯 Java，全部能变成 400）────────────────────────────
        RegionGeometry.Region region =
                RegionGeometry.parse(req.geometry(), req.bufferM(), props.getMaxVertices(), props.getMaxBufferM());

        int limit = req.limit() == null ? props.getDefaultLimit() : req.limit();
        if (limit < 1 || limit > props.getMaxLimit()) {
            throw new IllegalArgumentException("limit 必须在 1 ~ " + props.getMaxLimit() + " 之间，收到：" + limit);
        }
        if (req.from() != null && req.to() != null && req.from().isAfter(req.to())) {
            throw new IllegalArgumentException("from 不能晚于 to");
        }

        // ── 2. 区域准备 + 拓扑校验（同一条查询给出 valid / geojson / wkt）──────
        List<Object[]> prepared = region.buffered()
                ? trackRepository.prepareBufferRegion(region.wkt(), req.bufferM())
                : trackRepository.prepareRegion(region.wkt());
        Object[] row = prepared.get(0);
        if (!Boolean.TRUE.equals(row[0])) {
            // 实测：自交多边形不会让 PostGIS 报错，而是给出一个静默错误的答案（设计文档 2.9）
            throw new IllegalArgumentException("区域有交叉或面积为 0，请重画");
        }
        JsonNode regionNode = readJson((String) row[1]);
        String queryWkt = (String) row[2];

        WithinResponse.Params params = new WithinResponse.Params(req.bufferM(), req.from(), req.to(), limit);

        // ── 3. 命中轨迹 id ──────────────────────────────────────────────
        List<Long> ids = trackRepository.findIdsIntersecting(
                queryWkt,
                req.from() == null ? MIN_TIME : req.from(),
                req.to() == null ? MAX_TIME : req.to());

        if (ids.isEmpty()) {
            return new WithinResponse(regionNode,
                    new WithinResponse.Stats(0, 0, 0.0, Map.of(), null, null),
                    List.of(), 0, false, params);
        }

        // ── 4. 区域内点数（总数与每条，同一个查询，必然自洽）────────────────
        Map<Long, Long> insideByTrack = new HashMap<>();
        long pointCount = 0;
        for (Object[] r : trackPointRepository.countPointsInsideGrouped(queryWkt)) {
            long trackId = ((Number) r[0]).longValue();
            long inside = ((Number) r[1]).longValue();
            insideByTrack.put(trackId, inside);
            pointCount += inside;
        }

        // ── 5. 统计（按来源分组 + 时间跨度；全量，不受 limit 影响）────────────
        Map<String, Long> sourceCounts = new LinkedHashMap<>();
        double totalDistance = 0;
        String earliest = null;
        String latest = null;
        for (Object[] r : trackRepository.aggregateWithinStats(ids)) {
            sourceCounts.put((String) r[0], ((Number) r[1]).longValue());
            totalDistance += ((Number) r[2]).doubleValue();
            String e = (String) r[3];
            String l = (String) r[4];
            // 同格式的 ISO-8601 字符串可以直接比大小
            if (e != null && (earliest == null || e.compareTo(earliest) < 0)) {
                earliest = e;
            }
            if (l != null && (latest == null || l.compareTo(latest) > 0)) {
                latest = l;
            }
        }

        // ── 6. items：排序 → 截断（limit 在 Java 侧截，SQL 里截就拿不到 total 了）──
        // ⚠️ 列序必须与 Task 3 的 SQL 逐字对齐：
        //    [0]=id [1]=name [2]=source [3]=point_count [4]=duration_s
        //    [5]=distance_m [6]=start_time [7]=end_time
        List<WithinResponse.Item> all = new ArrayList<>();
        for (Object[] r : trackRepository.findWithinSummariesByIds(ids)) {
            long trackId = ((Number) r[0]).longValue();
            all.add(new WithinResponse.Item(
                    trackId,
                    (String) r[1],
                    (String) r[2],
                    r[5] == null ? 0.0 : ((Number) r[5]).doubleValue(),   // distance_m
                    r[4] == null ? null : ((Number) r[4]).intValue(),     // duration_s
                    nullOrInt(r[3]),                                      // point_count
                    insideByTrack.getOrDefault(trackId, 0L),
                    (String) r[6],
                    (String) r[7]));
        }
        all.sort(Comparator.comparingLong(WithinResponse.Item::insidePointCount).reversed()
                .thenComparingLong(WithinResponse.Item::trackId));

        boolean truncated = all.size() > limit;
        List<WithinResponse.Item> items = truncated ? new ArrayList<>(all.subList(0, limit)) : all;

        var stats = new WithinResponse.Stats(
                ids.size(), pointCount, totalDistance, sourceCounts, earliest, latest);
        return new WithinResponse(regionNode, stats, items, ids.size(), truncated, params);
    }

    private static Integer nullOrInt(Object v) {
        return v == null ? null : ((Number) v).intValue();
    }

    private static JsonNode readJson(String s) {
        try {
            return JSON.readTree(s);
        } catch (Exception e) {
            throw new IllegalStateException("PostGIS 返回的 GeoJSON 解析失败: " + s, e);
        }
    }
}
