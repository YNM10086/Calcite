package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 轨迹相似度配置，对应 {@code application.yml} 里的 {@code calcite.similarity.*}。
 *
 * <p>这里都是<b>标量</b>（不是列表），{@code @Value} 也能读。但为了和
 * {@link DensityProperties} / {@link ImportProperties} 保持一致，统一用
 * {@code @ConfigurationProperties}。
 */
@Component
@ConfigurationProperties(prefix = "calcite.similarity")
public class SimilarityProperties {

    /**
     * 默认容差（米）。
     *
     * <p>为什么是 50：<b>实测采样间距是 5~42 米</b>（不是设计时以为的 3~15 米 —— 见设计文档 2.6 节）。
     * 对密采样的轨迹（5~21 米）50 米是合适的；对稀疏轨迹（42 米）会低估单向百分比，
     * 但<b>相似度取两个方向的最小值，不受影响</b>（被低估的方向恰好是本来更大的那个，见 2.7 节）。
     * 50 米又能容纳城市 GPS 漂移（常见 10~30 米），且远小于"走错一条街"的 100 米以上偏差。
     */
    private double defaultToleranceM = 50;

    /** 容差下限（米） */
    private double minToleranceM = 1;

    /** 容差上限（米）。放太大（比如 100000）会把整座城市的轨迹都说成"相似" */
    private double maxToleranceM = 1000;

    /** 默认最多返回多少条匹配 */
    private int defaultLimit = 50;

    /** limit 上限 */
    private int maxLimit = 500;

    // getter / setter 全部要有（Spring 绑定需要）
    public double getDefaultToleranceM() { return defaultToleranceM; }
    public void setDefaultToleranceM(double v) { this.defaultToleranceM = v; }
    public double getMinToleranceM() { return minToleranceM; }
    public void setMinToleranceM(double v) { this.minToleranceM = v; }
    public double getMaxToleranceM() { return maxToleranceM; }
    public void setMaxToleranceM(double v) { this.maxToleranceM = v; }
    public int getDefaultLimit() { return defaultLimit; }
    public void setDefaultLimit(int v) { this.defaultLimit = v; }
    public int getMaxLimit() { return maxLimit; }
    public void setMaxLimit(int v) { this.maxLimit = v; }
}
