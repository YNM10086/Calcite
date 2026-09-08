package com.calcite.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.locationtech.jts.geom.Point;

import java.time.OffsetDateTime;

/**
 * 一个 GPS 点 —— 原始数据，不可篡改的"真相"。
 *
 * <p>对应数据库表 {@code track_point}。
 *
 * <p>这里用普通的 {@code trackId} 字段而不是 {@code @ManyToOne Track track}：
 * <ul>
 *   <li>轨迹点的量级是百万级，用外键对象容易触发 N+1 查询</li>
 *   <li>查点的时候我们只关心 track_id 这个值，不需要 Track 对象</li>
 *   <li>层级更浅，对新手更友好</li>
 * </ul>
 */
@Entity
@Table(name = "track_point")
public class TrackPoint {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "track_id", nullable = false)
    private Long trackId;

    /** 在轨迹中的顺序，从 0 开始 */
    @Column(name = "seq", nullable = false)
    private Integer seq;

    @Column(name = "recorded_at", nullable = false)
    private OffsetDateTime recordedAt;

    /** 海拔（米），数据源没有就是 null */
    @Column(name = "elevation_m")
    private Double elevationM;

    /** 速度（米/秒），导入时若数据源没给，可由相邻点算出后回填 */
    @Column(name = "speed_mps")
    private Double speedMps;

    /** 点坐标，SRID 4326 */
    @Column(name = "geom", nullable = false, columnDefinition = "geometry(Point,4326)")
    private Point geom;

    protected TrackPoint() {
    }

    public Long getId() {
        return id;
    }

    public Long getTrackId() {
        return trackId;
    }

    public void setTrackId(Long trackId) {
        this.trackId = trackId;
    }

    public Integer getSeq() {
        return seq;
    }

    public void setSeq(Integer seq) {
        this.seq = seq;
    }

    public OffsetDateTime getRecordedAt() {
        return recordedAt;
    }

    public void setRecordedAt(OffsetDateTime recordedAt) {
        this.recordedAt = recordedAt;
    }

    public Double getElevationM() {
        return elevationM;
    }

    public void setElevationM(Double elevationM) {
        this.elevationM = elevationM;
    }

    public Double getSpeedMps() {
        return speedMps;
    }

    public void setSpeedMps(Double speedMps) {
        this.speedMps = speedMps;
    }

    public Point getGeom() {
        return geom;
    }

    public void setGeom(Point geom) {
        this.geom = geom;
    }
}
