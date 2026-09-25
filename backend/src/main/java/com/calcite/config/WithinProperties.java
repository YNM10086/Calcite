package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 空间范围查询配置，对应 {@code application.yml} 里的 {@code calcite.within.*}。
 *
 * <p>用 {@code @ConfigurationProperties} 而不是 {@code @Value} 保持与
 * {@link DensityProperties} / {@link SimilarityProperties} 一致
 * （{@code @Value} 绑不了 YAML 列表，这个坑在轨迹导入时踩过）。
 */
@Component
@ConfigurationProperties(prefix = "calcite.within")
public class WithinProperties {

    /** 用户手画几何的顶点数上限（MultiPolygon 是所有环之和）。服务端生成的缓冲区固定 33 个顶点，不受此限 */
    private int maxVertices = 2000;

    /** 缓冲区默认半径（米） */
    private double defaultBufferM = 500;

    /** 缓冲区半径上限（米）。再大就不该用"缓冲区"这个交互了，直接拉框更直观 */
    private double maxBufferM = 50_000;

    /** items 默认返回条数 */
    private int defaultLimit = 50;

    /** items 条数上限（统计不受它影响，永远是全量） */
    private int maxLimit = 500;

    public int getMaxVertices() {
        return maxVertices;
    }

    public void setMaxVertices(int maxVertices) {
        this.maxVertices = maxVertices;
    }

    public double getDefaultBufferM() {
        return defaultBufferM;
    }

    public void setDefaultBufferM(double defaultBufferM) {
        this.defaultBufferM = defaultBufferM;
    }

    public double getMaxBufferM() {
        return maxBufferM;
    }

    public void setMaxBufferM(double maxBufferM) {
        this.maxBufferM = maxBufferM;
    }

    public int getDefaultLimit() {
        return defaultLimit;
    }

    public void setDefaultLimit(int defaultLimit) {
        this.defaultLimit = defaultLimit;
    }

    public int getMaxLimit() {
        return maxLimit;
    }

    public void setMaxLimit(int maxLimit) {
        this.maxLimit = maxLimit;
    }
}
