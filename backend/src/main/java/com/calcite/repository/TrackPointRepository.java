package com.calcite.repository;

import com.calcite.domain.TrackPoint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.OffsetDateTime;
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

    /**
     * 网格密度聚合：把视野内的点按方格分桶，一次算出两个口径。
     *
     * <p><b>为什么用 {@code round(ST_X(geom)/:cell)::int} 而不是 {@code ST_SnapToGrid(geom, :cell)}</b>：
     * 两者<b>语义完全相同</b>（都是"把坐标就近取整到 cell 的整数倍"），
     * 实测格子集合逐个相同（全量 3867 = 3867、北京 736 = 736），
     * 但整数写法快 <b>3.5 倍</b>（92ms vs 330ms），而且不需要排序、不会落盘临时文件。
     * 这个等价关系由 {@code .tmp/verify-density-api.py} 断言钉住。
     *
     * <p><b>为什么 {@code AT TIME ZONE} 要显式写</b>：{@code recorded_at} 存的是 UTC，
     * 而"早高峰"是人理解的北京时间。不显式转换的话，结果会随数据库会话时区变化 ——
     * 换台机器同一个 {@code hourFrom=7} 就查出别的结果。
     *
     * <p>{@code [hourFrom, hourTo]} 与 {@code [from, to]} 都由调用方填成"无过滤的宽范围"
     * （见 {@code DensityGrid.passThroughHourRange}），所以这里不需要写 {@code IS NULL} 判断 ——
     * native query 里的可空参数类型推断很容易出问题。
     *
     * @return 每行 {@code [nx(Integer), ny(Integer), points(Long), tracks(Long)]}
     */
    @Query(value = """
            SELECT round(ST_X(geom) / :cell)::int AS nx,
                   round(ST_Y(geom) / :cell)::int AS ny,
                   count(*)                       AS points,
                   count(DISTINCT track_id)       AS tracks
            FROM track_point
            WHERE geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
              AND extract(hour FROM recorded_at AT TIME ZONE :tz) BETWEEN :hourFrom AND :hourTo
              AND recorded_at >= :from
              AND recorded_at <= :to
            GROUP BY 1, 2
            """, nativeQuery = true)
    List<Object[]> aggregateDensity(@Param("west") double west,
                                    @Param("south") double south,
                                    @Param("east") double east,
                                    @Param("north") double north,
                                    @Param("cell") double cell,
                                    @Param("tz") String timeZone,
                                    @Param("hourFrom") int hourFrom,
                                    @Param("hourTo") int hourTo,
                                    @Param("from") OffsetDateTime from,
                                    @Param("to") OffsetDateTime to);
}
