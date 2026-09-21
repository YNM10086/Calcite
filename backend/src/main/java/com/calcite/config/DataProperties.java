package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 数据管理配置，对应 {@code application.yml} 里的 {@code calcite.data.*}。
 *
 * <p><b>为什么不复用 {@code calcite.import.allowed-roots}</b>：那个是
 * <b>导入时的读白名单</b>（只允许从 GeoLife 目录读），用途完全不同。
 * 混在一起会让两个安全策略互相牵制。
 */
@Component
@ConfigurationProperties(prefix = "calcite.data")
public class DataProperties {

    /**
     * 删除前的自动导出目录。
     *
     * <p><b>删之前先导出，导出失败就不删</b> —— 见 TrackEditService。
     */
    private String recycleDir = "D:\\Calcite-note\\backups\\deleted";

    /** 轨迹显示名的长度上限 */
    private int maxNameLength = 200;

    public String getRecycleDir() { return recycleDir; }
    public void setRecycleDir(String v) { this.recycleDir = v; }
    public int getMaxNameLength() { return maxNameLength; }
    public void setMaxNameLength(int v) { this.maxNameLength = v; }
}
