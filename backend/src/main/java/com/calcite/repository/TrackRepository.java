package com.calcite.repository;

import com.calcite.domain.Track;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

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
}
