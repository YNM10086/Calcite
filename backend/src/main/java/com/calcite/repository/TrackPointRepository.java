package com.calcite.repository;

import com.calcite.domain.TrackPoint;
import org.springframework.data.jpa.repository.JpaRepository;

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
}
