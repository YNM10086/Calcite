package com.calcite.repository;

import com.calcite.domain.Track;
import org.springframework.data.jpa.repository.JpaRepository;

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
}
