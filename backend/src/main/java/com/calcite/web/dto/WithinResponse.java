package com.calcite.web.dto;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * {@code POST /api/analysis/within} 的响应。
 *
 * <p>⭐ {@code region} 是<b>后端真正拿去查询的那个几何</b>（缓冲区已由 PostGIS 算成圆多边形）。
 * 前端照着它画，于是"看到的圈 = 查的范围"成为结构保证，而不是纪律。
 *
 * <p>统计口径（写死，见设计文档 4.1）：只有 {@code stats.pointCount} 与
 * {@code items[].insidePointCount} 是"区域内的"，其余数字都是<b>整条轨迹</b>的。
 * 这里<b>没有</b> stayCount —— 加它会把接口从 0.2 秒拖到 2.5 秒（设计文档 5.9）。
 */
public record WithinResponse(
        JsonNode region,
        Stats stats,
        List<Item> items,
        long total,
        boolean truncated,
        Params params) {

    public record Stats(
            long trackCount,
            long pointCount,
            double distanceM,
            Map<String, Long> sourceCounts,
            String earliest,
            String latest) {
    }

    public record Item(
            long trackId,
            String name,
            String source,
            double distanceM,
            Integer durationS,
            Integer pointCount,
            long insidePointCount,
            String startTime,
            String endTime) {
    }

    public record Params(Double bufferM, OffsetDateTime from, OffsetDateTime to, int limit) {
    }
}
