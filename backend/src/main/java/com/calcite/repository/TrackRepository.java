package com.calcite.repository;

import com.calcite.domain.Track;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.OffsetDateTime;
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

    /**
     * 区域准备（拉框 / 自由多边形）：一条小查询同时拿到<b>合法性</b>、<b>回显用的 GeoJSON</b>、
     * <b>查询用的 WKT</b>。
     *
     * <p><b>为什么三件事必须同一条查询</b>：这样"被校验的几何""查询用的几何""回显的几何"
     * 必然是同一个对象 —— "看到的圈 = 查的范围"就成了结构保证。
     *
     * <p><b>为什么必须查 ST_IsValid</b>：实测（设计文档 2.9）自交的"蝴蝶结"多边形
     * {@code ST_Intersects} <b>不报错</b>，而是返回 237 条（比它的外接矩形还多）——
     * 静默错误比报错危险得多。不合法一律由上层转成 400。
     *
     * @return 单行 {@code [Boolean valid, String geojson, String wkt]}
     */
    @Query(value = """
            SELECT ST_IsValid(g), ST_AsGeoJSON(g), ST_AsText(g)
            FROM (SELECT ST_GeomFromText(:wkt, 4326) AS g) s
            """, nativeQuery = true)
    List<Object[]> prepareRegion(@Param("wkt") String wkt);

    /**
     * 区域准备（缓冲区）：<b>由 PostGIS 把圆算成多边形</b>，之后判定与"拉框/多边形"完全相同。
     *
     * <p><b>为什么不用 {@code ST_DWithin(geom::geography, ...)}</b>：实测 303 ms 且顺序扫描 ——
     * 瓶颈是对每条候选轨迹的每个顶点算椭球距离（北京有 228 条候选，粗筛减不掉）。
     * 算成多边形后只要 7.9 ms，而且命中 {@code idx_track_geom}（设计文档 2.3）。
     *
     * <p>⚠️ {@code ::geography} 不能漏：不加就是"按度缓冲 500 度"。
     *
     * @return 单行 {@code [Boolean valid, String geojson, String wkt]}
     */
    @Query(value = """
            SELECT ST_IsValid(g), ST_AsGeoJSON(g), ST_AsText(g)
            FROM (SELECT ST_Buffer(ST_GeomFromText(:wkt, 4326)::geography, :bufferM)::geometry AS g) s
            """, nativeQuery = true)
    List<Object[]> prepareBufferRegion(@Param("wkt") String wkt, @Param("bufferM") double bufferM);

    /**
     * 命中轨迹的 id：轨迹<b>线</b>与区域相交，且<b>时间窗重叠</b>。
     *
     * <p>时间语义（设计文档 5.7）：{@code [start_time, end_time]} 与 {@code [from, to]} 有重叠就算"经过"。
     * <b>不按 track_point.recorded_at 过滤</b> —— 那会把判定谓词从"线"降级成"点"（点比线稀，
     * 采样间距 5~42 米），漏判；更糟的是"有没有时间过滤"会变成两套不同的判定谓词。
     *
     * <p>⚠️ 调用方必须把 null 的 from/to 换成<b>无限宽的边界值</b> —— native query 里不写
     * {@code IS NULL} 判断（可空参数的类型推断很容易出问题，见 {@code aggregateDensity} 的注释）。
     *
     * <p>{@code ST_Intersects} 自带包围盒预筛 → 命中 {@code idx_track_geom}（实测 10~24 ms）。
     */
    @Query(value = """
            SELECT t.id FROM track t
            WHERE ST_Intersects(t.geom, ST_GeomFromText(:wkt, 4326))
              AND t.start_time <= :to
              AND t.end_time   >= :from
            """, nativeQuery = true)
    List<Long> findIdsIntersecting(@Param("wkt") String wkt,
                                   @Param("from") OffsetDateTime from,
                                   @Param("to") OffsetDateTime to);

    /**
     * items 的摘要。<b>故意不用</b> {@code findSummariesByIds}：那个正被相似度接口使用，
     * 为两个字段去改它等于拿 M2 的回归冒险；而且它还多算了一个 {@code ST_Length(geom::geography)}。
     *
     * <p>⭐ 里程直接用<b>已存好的派生列</b> {@code t.distance_m}（导入时算好的）——
     * 不在查询时把整条 LineString 转成 geography 逐顶点算椭球长度。同样的数字，一个要算一个要读。
     *
     * @return 每行 {@code [Long id, String name, String source, Integer pointCount,
     *                     Integer durationS, Double distanceM, String startTime, String endTime]}
     */
    @Query(value = """
            SELECT t.id, t.name, t.source, t.point_count, t.duration_s, t.distance_m,
                   to_char(t.start_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                   to_char(t.end_time   AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            FROM track t WHERE t.id IN (:ids)
            """, nativeQuery = true)
    List<Object[]> findWithinSummariesByIds(@Param("ids") Collection<Long> ids);

    /**
     * 区域统计：按来源分组的条数/里程，以及整个命中集合的时间跨度。
     *
     * <p>为什么不复用 items 的查询：items 会被 limit 截断，而统计<b>必须全量</b>。
     * 一行 SQL 同时给出 5 个统计数字，Java 侧只做求和与取首尾。
     *
     * <p>ISO-8601 字符串可以直接比大小（同格式定长），所以 Java 侧用 min/max 选首尾是安全的。
     *
     * @return 每行 {@code [String source, Long tracks, Double distanceM, String earliest, String latest]}
     */
    @Query(value = """
            SELECT t.source,
                   count(*)                                        AS tracks,
                   coalesce(sum(t.distance_m), 0)                  AS distance_m,
                   to_char(min(t.start_time) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                   to_char(max(t.end_time)   AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            FROM track t
            WHERE t.id IN (:ids)
            GROUP BY t.source
            """, nativeQuery = true)
    List<Object[]> aggregateWithinStats(@Param("ids") Collection<Long> ids);
}
