package com.calcite.web.dto;

import com.calcite.domain.TrackPoint;
import org.locationtech.jts.geom.Point;

import java.time.OffsetDateTime;

/**
 * 一个轨迹点，坐标已经拆成独立的 lon / lat 数字。
 *
 * <p>为什么要拆？前端 Cesium 需要的是 {@code [经度, 纬度]} 这种纯数字数组，
 * 而 PostGIS 的 {@code POINT(116.39 39.90)} 是一个对象。
 * 在后端拆好，前端就能直接 {@code Cesium.Cartesian3.fromDegrees(lon, lat)}。
 */
public record TrackPointDto(
        Integer seq,
        OffsetDateTime recordedAt,
        double lon,
        double lat,
        Double elevationM,
        Double speedMps,
        boolean outlier
) {

    public static TrackPointDto from(TrackPoint point) {
        Point geom = point.getGeom();
        return new TrackPointDto(
                point.getSeq(),
                point.getRecordedAt(),
                // JTS 里 getX() 是经度、getY() 是纬度（注意别写反）
                geom == null ? 0d : geom.getX(),
                geom == null ? 0d : geom.getY(),
                point.getElevationM(),
                point.getSpeedMps(),
                point.isOutlier()
        );
    }
}
