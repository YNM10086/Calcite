package com.calcite.web.dto;

import com.calcite.service.Hotspot;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 对外的单个热点。比 {@link Hotspot} 多一个 {@code rank}。
 *
 * <p>坐标拆成独立的 {@code centerLat} / {@code centerLon} 两个数字，
 * 和 {@link StayPointDto} / {@link TrackPointDto} 保持一致的风格。
 */
public record HotspotDto(
        int rank,
        double centerLat,
        double centerLon,
        int visitCount,
        int trackCount,
        int totalDurationS,
        double radiusM,
        OffsetDateTime firstVisit,
        OffsetDateTime lastVisit,
        List<Long> trackIds
) {

    /** rank 从 1 开始（第 1 名、第 2 名……），由调用方按顺序传入 */
    public static HotspotDto of(int rank, Hotspot h) {
        return new HotspotDto(
                rank,
                h.centerLat(),
                h.centerLon(),
                h.visitCount(),
                h.trackCount(),
                h.totalDurationS(),
                h.radiusM(),
                h.firstVisit(),
                h.lastVisit(),
                h.trackIds());
    }
}
