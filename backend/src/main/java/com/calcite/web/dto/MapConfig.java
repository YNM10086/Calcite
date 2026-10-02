package com.calcite.web.dto;

import com.calcite.config.MapProperties;
import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;

/**
 * {@code GET /api/map/tianditu} 的响应体：把"要不要开在线底图"告诉前端。
 *
 * <p><b>为什么 token 会真的发给浏览器</b>：瓦片 URL 必须在前端拼（浏览器直接向天地图取图），
 * 所以 token 必然到达客户端。这是**本地演示**的取舍 ——
 * 好处是 key 既不进仓库、也不进前端构建产物（相比 {@code VITE_*} 构建期注入），
 * 代价是**不要把带 key 的这个后端暴露到公网**。
 *
 * <p>⚠️ 没配 key 时 {@code token} 为 {@code null}，并被 {@link JsonInclude} 抹掉：
 * 响应里连字段都不出现，前端只认 {@code enabled}，避免"配了但没生效"的误会。
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record MapConfig(boolean enabled, String token, int maxLevel, List<String> subdomains) {

    /**
     * 从配置装配响应。
     *
     * <p>两边的空白会被去掉、只留空白等于没配 —— 粘贴 key 时带空格是很常见的手误，
     * 而它造成的后果（瓦片 403）非常难查。
     */
    public static MapConfig of(MapProperties props) {
        String raw = props.getTiandituToken();
        String token = raw == null ? "" : raw.trim();
        boolean enabled = !token.isEmpty();
        return new MapConfig(enabled, enabled ? token : null,
                props.getTiandituMaxLevel(), props.getSubdomains());
    }
}
