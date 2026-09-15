package com.calcite.web.dto;

import com.calcite.service.StayPoint;

import java.time.OffsetDateTime;

/**
 * 对外的停留点。
 *
 * <p>坐标拆成了独立的 {@code lon} / {@code lat} 两个数字 ——
 * 和 {@link TrackPointDto} 保持一致的风格，前端 Cesium 直接就能用。
 */
public record StayPointDto(
        int seqStart,
        int seqEnd,
        OffsetDateTime startTime,
        OffsetDateTime endTime,
        int durationS,
        double lon,
        double lat,
        double radiusM,
        int pointCount
) {

    public static StayPointDto from(StayPoint s) {
        return new StayPointDto(
                s.seqStart(),
                s.seqEnd(),
                s.startTime(),
                s.endTime(),
                s.durationS(),
                s.centerLon(),
                s.centerLat(),
                s.radiusM(),
                s.pointCount());
    }
}
