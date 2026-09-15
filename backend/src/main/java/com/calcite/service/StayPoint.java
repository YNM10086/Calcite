package com.calcite.service;

import java.time.OffsetDateTime;

/**
 * 一段停留。
 *
 * @param seqStart   起点在轨迹里的 seq
 * @param seqEnd     终点的 seq
 * @param startTime  起始时刻
 * @param endTime    结束时刻
 * @param durationS  时长（秒）
 * @param centerLon  停留中心经度（窗口重心）
 * @param centerLat  停留中心纬度
 * @param radiusM    活动半径：窗口内所有点到中心的最大距离（米）
 * @param pointCount 这段里有几个点
 */
public record StayPoint(
        int seqStart,
        int seqEnd,
        OffsetDateTime startTime,
        OffsetDateTime endTime,
        int durationS,
        double centerLon,
        double centerLat,
        double radiusM,
        int pointCount
) {
}
