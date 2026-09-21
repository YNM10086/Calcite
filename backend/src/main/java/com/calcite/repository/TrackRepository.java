package com.calcite.repository;

import com.calcite.domain.Track;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

/**
 * 轨迹表的持久层。
 *
 * <p>继承 {@link JpaRepository} 就白拿了一整套 CRUD 方法：
 * {@code findAll()}、{@code findById()}、{@code save()}、{@code deleteById()}、{@code count()}……
 * 不用写一行实现。
 *
 * <p>方法名遵循 Spring Data 的"查询方法命名规则"：
 * {@code findByXxx} / {@code findAllByOrderByXxxDesc} 等，框架自动生成 SQL。
 */
public interface TrackRepository extends JpaRepository<Track, Long> {

    /** 按原始数据编号查（导入时用来判重） */
    Optional<Track> findByExternalId(String externalId);

    /**
     * 按名字找一条轨迹（同名检测用）。
     *
     * <p>Spring Data 的派生查询 —— 方法名翻译成 SQL 的 {@code WHERE name = ? LIMIT 1}。
     */
    List<Track> findAllByName(String name);

    /**
     * 按开始时间倒序取一批（最新的在前）。
     *
     * <p>为什么这里用 {@code @Query} 而不是靠方法名派生：方法名里同时写 {@code OrderBy}
     * 和 {@code Pageable} 容易产生歧义，写成 JPQL 更直白 —— 分页的 {@code LIMIT}
     * 由 Spring Data 根据 {@link Pageable} 自动加上。
     */
    @Query("SELECT t FROM Track t ORDER BY t.startTime DESC")
    List<Track> findRecent(Pageable pageable);

    /** 按来源过滤 + 开始时间倒序 */
    @Query("SELECT t FROM Track t WHERE t.source = :source ORDER BY t.startTime DESC")
    List<Track> findRecentBySource(@Param("source") String source, Pageable pageable);

    /** 某个来源的轨迹总数（前端显示"共 N 条"用） */
    long countBySource(String source);

    /**
     * 只取所有轨迹的 id（热点接口用）。
     *
     * <p><b>为什么不能用 {@code findAll()}</b>：{@code Track} 实体带着 {@code geom}
     * （完整的 LineString），246 条轨迹一共约 <b>28.6 万个顶点</b> ——
     * 而热点接口只需要 id 和条数。实测这正是热点接口"缓存之后还要 2.4 秒"的主因：
     * 每次请求都要把 32 MB 载荷水合成实体。
     */
    @Query("SELECT t.id FROM Track t")
    List<Long> findAllIds();

    /**
     * 主线的元数据 + 几何统计（相似度接口用）。
     *
     * <p>{@code latMin/latMax} 是给包围盒扩边量 {@code eps} 用的：
     * 度不是长度单位，{@code eps} 必须按主线<b>实际所在的纬度</b>算
     * （详见 {@code SimilarityMath.epsDegrees}）。
     *
     * <p>{@code ST_Length(geom::geography)} 返回<b>米</b>（不是度）。
     *
     * @return 单行 {@code [latMin(Double), latMax(Double), lengthM(Double)]}
     */
    @Query(value = """
            SELECT ST_YMin(geom), ST_YMax(geom), ST_Length(geom::geography)
            FROM track WHERE id = :trackId
            """, nativeQuery = true)
    List<Object[]> findBaselineGeometryStats(@Param("trackId") Long trackId);

    /**
     * 主线的元数据。native query 是为了用 {@code to_char} 把 {@code timestamptz}
     * 转成 ISO 字符串，避免类型映射歧义。
     *
     * <p>{@code timestamptz} 在 native query 里映射成哪个 Java 类型
     * （{@code Timestamp} / {@code OffsetDateTime} / {@code Instant}）取决于驱动与
     * Hibernate 版本，靠猜容易在运行时炸。转成字符串就没有歧义了，代价只是一次解析。
     *
     * @return 单行 {@code [name(String), source(String), pointCount(Integer), startTime(String)]}
     */
    @Query(value = """
            SELECT t.name, t.source, t.point_count,
                   to_char(t.start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            FROM track t WHERE t.id = :trackId
            """, nativeQuery = true)
    List<Object[]> findBaselineMeta(@Param("trackId") Long trackId);

    /**
     * 批量取匹配轨迹的元数据（含长度）。native query 是为了用 {@code ST_Length(geography)}。
     *
     * <p><b>为什么不用 JPQL</b>：JPQL 没有 {@code ST_Length}，取不到米制长度。
     *
     * <p><b>为什么不用 {@code findAllById}</b>：那会把每条轨迹的 {@code geom}
     * （完整 LineString）全水合出来 —— 197 条轨迹约 28 万个顶点，而这里只需要名字和几个数。
     * （这个坑在热点接口上踩过一次，实测要 2.4 秒。）
     *
     * <p>{@code start_time} 用 {@code to_char} 转成 ISO 字符串 ——
     * 避免 native query 里 {@code timestamptz} 的类型映射歧义（同 {@link #findBaselineMeta}）。
     *
     * @return 每行 {@code [id(Long), name(String), source(String), pointCount(Integer),
     *                     lengthM(Double), startTime(String ISO-8601)]}
     */
    @Query(value = """
            SELECT t.id,
                   t.name,
                   t.source,
                   t.point_count,
                   ST_Length(t.geom::geography),
                   to_char(t.start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            FROM track t
            WHERE t.id IN (:ids)
            """, nativeQuery = true)
    List<Object[]> findSummariesByIds(@Param("ids") Collection<Long> ids);
}
