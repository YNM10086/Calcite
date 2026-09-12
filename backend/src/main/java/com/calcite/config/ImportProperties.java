package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 轨迹导入配置，对应 {@code application.yml} 里的 {@code calcite.import.*}。
 *
 * <p>为什么用 {@code @ConfigurationProperties} 而不是 {@code @Value}？
 * 因为 {@code allowed-roots} 是 YAML **列表**，而 {@code @Value} 只能读单个标量属性 ——
 * YAML 列表在 Spring 里是 {@code calcite.import.allowed-roots[0]}、{@code [1]} 这种形式，
 * 写 {@code @Value("${calcite.import.allowed-roots}")} 会直接报占位符解析失败。
 */
@Component
@ConfigurationProperties(prefix = "calcite.import")
public class ImportProperties {

    /** 允许批量导入的根目录白名单（接口收到的 path 必须落在其中之一） */
    private List<String> allowedRoots = new ArrayList<>();

    /** 单次批量导入最多处理多少条轨迹 */
    private int maxTracksPerCall = 50;

    // Spring 绑定需要 setter（getter 给业务代码用）

    public List<String> getAllowedRoots() {
        return allowedRoots;
    }

    public void setAllowedRoots(List<String> allowedRoots) {
        this.allowedRoots = allowedRoots;
    }

    public int getMaxTracksPerCall() {
        return maxTracksPerCall;
    }

    public void setMaxTracksPerCall(int maxTracksPerCall) {
        this.maxTracksPerCall = maxTracksPerCall;
    }
}
