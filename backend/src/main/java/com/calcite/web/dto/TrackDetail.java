package com.calcite.web.dto;

import com.calcite.domain.Track;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 轨迹详情 = 轨迹元数据 + 全部轨迹点。
 *
 * <p>M1 阶段点数不多（示例轨迹 121 个），一次性返回最简单。
 * 等接入 GeoLife 真实数据（单条几千上万点）后，
 * 这里要改成"简化后的线 + 分页点"两套接口。
 */
public record TrackDetail(
        Long id,
        String name,
        String source,
        String externalId,
        OffsetDateTime startTime,
        OffsetDateTime endTime,
        Double distanceM,
        Integer durationS,
        Integer pointCount,
        List<TrackPointDto> points
) {

    public static TrackDetail from(Track track, List<TrackPointDto> points) {
        return new TrackDetail(
                track.getId(),
                track.getName(),
                track.getSource(),
                track.getExternalId(),
                track.getStartTime(),
                track.getEndTime(),
                track.getDistanceM(),
                track.getDurationS(),
                track.getPointCount(),
                points
        );
    }
}
