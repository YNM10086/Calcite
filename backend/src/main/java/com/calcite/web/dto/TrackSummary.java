package com.calcite.web.dto;

import com.calcite.domain.Track;

import java.time.OffsetDateTime;

/**
 * 轨迹列表项 —— 只给列表页需要的字段，不含坐标。
 *
 * <p>为什么不让接口直接返回 {@code Track} 实体？
 * <ol>
 *   <li>实体里的 {@code geom} 是 JTS 对象，Jackson 直接序列化会输出一堆内部结构，前端没法用</li>
 *   <li>列表页不需要坐标，返回它是浪费带宽</li>
 *   <li>实体是"数据库的样子"，DTO 是"接口的样子"，分开后改数据库不会直接破坏前端</li>
 * </ol>
 *
 * <p>{@code record} 是 Java 16+ 的语法：一行声明不可变数据类，
 * 自动生成构造器、getter（{@code id()} 而不是 {@code getId()}）、equals、hashCode、toString。
 */
public record TrackSummary(
        Long id,
        String name,
        String source,
        String externalId,
        OffsetDateTime startTime,
        OffsetDateTime endTime,
        Double distanceM,
        Integer durationS,
        Integer pointCount
) {

    /** 把实体转成 DTO —— 这类转换方法通常叫 {@code from} 或 {@code of} */
    public static TrackSummary from(Track track) {
        return new TrackSummary(
                track.getId(),
                track.getName(),
                track.getSource(),
                track.getExternalId(),
                track.getStartTime(),
                track.getEndTime(),
                track.getDistanceM(),
                track.getDurationS(),
                track.getPointCount()
        );
    }
}
