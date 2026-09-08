package com.calcite.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.locationtech.jts.geom.LineString;

import java.time.OffsetDateTime;

/**
 * 一条轨迹（一次出行）。
 *
 * <p>对应数据库表 {@code track}，建表语句在 {@code scripts/db/01-schema.sql}。
 *
 * <p>字段分两类：
 * <ul>
 *   <li><b>元数据</b>：name / source / startTime / endTime —— 导入时就有</li>
 *   <li><b>派生数据</b>：distanceM / durationS / pointCount / geom —— 由 track_point 算出来</li>
 * </ul>
 *
 * <p>为什么 {@code geom} 用 JTS 的 {@link LineString}？因为 hibernate-spatial 提供了
 * JTS 几何类型 ↔ PostGIS {@code geometry} 列的映射，比手写 SQL 拼坐标更安全。
 */
@Entity
@Table(name = "track")
public class Track {

    /** 主键，对应数据库的 BIGSERIAL（数据库自己生成，所以用 IDENTITY 策略） */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    /** 数据来源：geolife | gpx | csv | sample */
    @Column(name = "source", nullable = false, length = 20)
    private String source;

    /** 原始数据集里的编号（比如 GeoLife 的轨迹文件名），本地导入的数据可以是 null */
    @Column(name = "external_id", length = 100)
    private String externalId;

    /** 带时区的时间：对应数据库的 TIMESTAMPTZ。用 OffsetDateTime 而不是 LocalDateTime */
    @Column(name = "start_time", nullable = false)
    private OffsetDateTime startTime;

    @Column(name = "end_time", nullable = false)
    private OffsetDateTime endTime;

    /** 总距离（米），由点序列算出 */
    @Column(name = "distance_m")
    private Double distanceM;

    /** 总时长（秒） */
    @Column(name = "duration_s")
    private Integer durationS;

    /** 点数 */
    @Column(name = "point_count")
    private Integer pointCount;

    /**
     * 轨迹线，SRID 4326。
     *
     * <p>columnDefinition 只是给 Hibernate 看的"声明"，
     * 真正的建表由 scripts/db/01-schema.sql 负责（ddl-auto=none）。
     */
    @Column(name = "geom", columnDefinition = "geometry(LineString,4326)")
    private LineString geom;

    /** 入库时间。数据库有 DEFAULT now()，所以插入时不由 Java 赋值 */
    @Column(name = "created_at", insertable = false, updatable = false)
    private OffsetDateTime createdAt;

    protected Track() {
        // JPA 需要一个无参构造器（可以是 protected，不需要给业务代码用）
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getExternalId() {
        return externalId;
    }

    public void setExternalId(String externalId) {
        this.externalId = externalId;
    }

    public OffsetDateTime getStartTime() {
        return startTime;
    }

    public void setStartTime(OffsetDateTime startTime) {
        this.startTime = startTime;
    }

    public OffsetDateTime getEndTime() {
        return endTime;
    }

    public void setEndTime(OffsetDateTime endTime) {
        this.endTime = endTime;
    }

    public Double getDistanceM() {
        return distanceM;
    }

    public void setDistanceM(Double distanceM) {
        this.distanceM = distanceM;
    }

    public Integer getDurationS() {
        return durationS;
    }

    public void setDurationS(Integer durationS) {
        this.durationS = durationS;
    }

    public Integer getPointCount() {
        return pointCount;
    }

    public void setPointCount(Integer pointCount) {
        this.pointCount = pointCount;
    }

    public LineString getGeom() {
        return geom;
    }

    public void setGeom(LineString geom) {
        this.geom = geom;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }
}
