package com.calcite.repository;

import com.calcite.domain.TrackPoint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Collection;
import java.util.List;

/**
 * 轨迹点表的持久层。
 *
 * <p>{@code findByTrackIdOrderBySeqAsc} 这个名字拆开读就是 SQL：
 * {@code WHERE track_id = ? ORDER BY seq ASC}。
 */
public interface TrackPointRepository extends JpaRepository<TrackPoint, Long> {

    List<TrackPoint> findByTrackIdOrderBySeqAsc(Long trackId);

    long countByTrackId(Long trackId);

    /**
     * 一次查出多条轨迹的全部点（热点分析用）。
     *
     * <p><b>⚠️ {@code ORDER BY p.trackId ASC, p.seq ASC} 不能省。</b>
     * {@code StayPointService.detect()} 的前置条件是「点按时间升序、且列表下标等于 seq」。
     * 批量查出来的结果必须按 trackId 分组后<b>各自保持 seq 升序</b>，
     * 否则算出来的停留点是错的。这里排好序，Java 侧按 trackId 分组时不用再排。
     *
     * <p><b>⚠️ {@code IN} 子句的规模</b>：轨迹上千条时参数会很多、SQL 会变慢。
     * 这是设计文档 10.2 里「轨迹超过 500 条就把停留点入库」那条触发条件的另一个理由。
     */
    @Query("SELECT p FROM TrackPoint p WHERE p.trackId IN :trackIds ORDER BY p.trackId ASC, p.seq ASC")
    List<TrackPoint> findAllByTrackIds(@Param("trackIds") Collection<Long> trackIds);
}
