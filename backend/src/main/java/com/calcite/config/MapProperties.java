package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 在线底图（天地图）配置，对应 {@code application.yml} 里的 {@code calcite.map.*}。
 *
 * <p>用 {@code @ConfigurationProperties} 而不是 {@code @Value}，与
 * {@link DensityProperties} / {@link SimilarityProperties} / {@link WithinProperties} 保持一致
 * （{@code @Value} 绑不了 YAML 列表，这个坑在轨迹导入时踩过）。
 *
 * <p>⚠️ <b>token 不要写进 {@code application.yml}</b>（那个文件要入库）——
 * 写进 {@code application-local.yml}，它已在 {@code .gitignore} 里，和数据库密码同一套路。
 * 本类里的默认值一律是"没配"。
 */
@Component
@ConfigurationProperties(prefix = "calcite.map")
public class MapProperties {

    /** 天地图 key。空（或只有空白）= 没配 → 前端开关打开时给一句提示，而不是发一堆注定 403 的瓦片请求 */
    private String tiandituToken = "";

    /** 最大层级。街道矢量图要 18 级才看得到建筑轮廓（低于 16 级基本只有路网） */
    private int tiandituMaxLevel = 18;

    /** 瓦片子域（天地图是 t0~t7）。多子域让浏览器能并发取瓦片 */
    private List<String> subdomains = List.of("0", "1", "2", "3", "4", "5", "6", "7");

    public String getTiandituToken() {
        return tiandituToken;
    }

    public void setTiandituToken(String tiandituToken) {
        this.tiandituToken = tiandituToken;
    }

    public int getTiandituMaxLevel() {
        return tiandituMaxLevel;
    }

    public void setTiandituMaxLevel(int tiandituMaxLevel) {
        this.tiandituMaxLevel = tiandituMaxLevel;
    }

    public List<String> getSubdomains() {
        return subdomains;
    }

    public void setSubdomains(List<String> subdomains) {
        this.subdomains = subdomains;
    }
}
