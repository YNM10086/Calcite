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
     * 删掉某条轨迹的全部点（"替换"时先清空旧的）。
     *
     * <p>派生删除：Spring Data 按方法名翻译出 {@code WHERE track_id = ?} 的删除条件。
     *
     * <p><b>⚠️ 必须在一个事务里调用</b>（调用它的 {@code ImportService.replaceInPlace}
     * 上已经有 {@code @Transactional}）—— 删除类方法没有事务会直接抛异常。
     */
    void deleteByTrackId(Long trackId);

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
     * 两种写法在<b>非边界点</b>上完全等价 —— 实测「所有归属不同的点都恰好落在格子边界上」
 * （8 组断言全部满足 diff_points == tie_points），且 round 的格子集合是 ST_SnapToGrid 的子集。
 * <b>边界点的归属不同</b>：round 走 ST_X/cell 的浮点除法
 * （116.4095/0.001 = 116409.49999999999），ST_SnapToGrid 走乘法后按「取偶」规则，
 * 于是在恰好半格的点上会分到相邻格子。
 * 影响面：默认档 0.002 上两种写法<b>严格相同</b>（3916 = 3916、1335 = 1335，集合逐个相同），
 * 只有 14 个格子的点数因此差 1（视觉不可见）；0.001 / 0.0005 档还会多出 1~2 个格子。
 * 由 .tmp/verify-density-api.py 的四条断言钉住。
     *
     * <p>整数写法比 ST_SnapToGrid 快约 <b>2 倍</b>（psql 自带计时：93ms vs 188ms），
     * 而且不需要排序、不会落盘临时文件。
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

    /**
     * 轨迹相似度：算某条主线和<b>全部其它轨迹</b>的双向重合度。
     *
     * <p><b>⭐ 为什么让"主线的点"驱动循环</b>：{@code FROM track_point p JOIN track_point q}
     * 且 {@code p} 是主线时，PostgreSQL 会拿主线的每个点去查 {@code q.geom} 上的
     * GIST 索引 —— 实测 <b>0.75 秒</b>。
     * 而同样语义写成 {@code WHERE q.track_id IN (候选)} + {@code EXISTS}（主线在 WHERE 里）
     * 会退化成逐点扫描候选轨迹的全部点，实测 <b>8.5 秒</b>。<b>同一个语义，11 倍差距。</b>
     *
     * <p><b>为什么是"点对点"而不是"点到折线"</b>：点到折线要放弃索引，
     * 实测 244 点 × 208 条 = <b>119 秒</b>（点对点只要 0.75 秒，约 160 倍）。
     * 代价是"用采样点代表折线"这个近似。实测采样间距是 5~42 米（见设计文档 2.6 节），
     * 所以<b>对稀疏轨迹会严重低估单向百分比</b>（实测 100% 被算成 43%）。
     * 但<b>相似度取两个方向的最小值，几乎不受影响</b> —— 被低估的方向恰好是本来更大的那个
     * （六组实测与真值差 ≤ 0.6 个百分点，见 2.7 节）。这个取舍写进了设计文档的已知限制。
     *
     * <p><b>为什么 {@code && ST_Expand(...)} 不能省</b>：{@code &&} 是走索引的包围盒预筛，
     * {@code ST_DWithin} 才是精确判据（米）。{@code :eps} 由 Java 按主线实际纬度算好传进来
     * （见 {@code SimilarityMath.epsDegrees}），<b>宁可大不可小</b> —— 小了会静默漏掉真匹配。
     *
     * <p><b>为什么 {@code INNER JOIN} 而不是 {@code LEFT JOIN}</b>：一条轨迹如果没出现在
     * {@code fwd} 里，说明主线的点没有一个落在它附近 → {@code fwd% = 0} →
     * {@code min(0, rev%) = 0} → <b>相似度为 0，本来就该被过滤</b>。
     * 所以 INNER JOIN 丢掉的行全是相似度为 0 的行。
     *
     * <p><b>⚠️ 这里【没有】 LIMIT</b>：响应要返回 {@code compared}（实际比了多少条），
     * 在 SQL 里截断就拿不到它了。截断交给 Java。
     *
     * @return 每行 {@code [trackId(Long), fwdHits(Long), fwdTotal(Long), revHits(Long), revTotal(Long)]}
     */
    @Query(value = """
            WITH fwd AS (
                SELECT q.track_id AS id, count(DISTINCT p.seq) AS hits
                FROM track_point p
                JOIN track_point q
                  ON q.geom && ST_Expand(p.geom, :eps)
                 AND ST_DWithin(q.geom::geography, p.geom::geography, :tol)
                WHERE p.track_id = :trackId AND q.track_id <> :trackId
                GROUP BY q.track_id
            ),
            rev AS (
                SELECT p.track_id AS id, count(DISTINCT p.seq) AS hits
                FROM track_point q
                JOIN track_point p
                  ON p.geom && ST_Expand(q.geom, :eps)
                 AND ST_DWithin(p.geom::geography, q.geom::geography, :tol)
                WHERE q.track_id = :trackId AND p.track_id <> :trackId
                GROUP BY p.track_id
            ),
            tot AS (
                SELECT track_id, count(*) AS n FROM track_point GROUP BY track_id
            ),
            nb AS (
                SELECT count(*) AS n FROM track_point WHERE track_id = :trackId
            )
            SELECT f.id,
                   f.hits,
                   (SELECT n FROM nb),
                   r.hits,
                   t.n
            FROM fwd f
            JOIN rev r ON r.id = f.id
            JOIN tot t ON t.track_id = f.id
            """, nativeQuery = true)
    List<Object[]> findSimilarityScores(@Param("trackId") Long trackId,
                                        @Param("tol") double toleranceM,
                                        @Param("eps") double eps);
}
