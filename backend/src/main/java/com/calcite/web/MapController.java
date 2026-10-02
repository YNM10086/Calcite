package com.calcite.web;

import com.calcite.config.MapProperties;
import com.calcite.web.dto.MapConfig;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 在线底图（天地图）配置接口：只回答"能不能开、用什么参数开"，不做任何别的事。
 *
 * <p>为什么不把 key 编进前端产物：Vite 的 {@code VITE_*} 是**构建期**注入，
 * 会把 key 写进最终 JS 里（谁都能按 F12 看到）；改成运行时向本接口要，
 * key 只留在你本机的 {@code application-local.yml}。
 *
 * <p>前端**只在开关打开的那一刻**才调它 —— 默认关 ⇒ 这个接口一次都不会被访问。
 */
@RestController
@RequestMapping("/api/map")
public class MapController {

    private final MapProperties properties;

    public MapController(MapProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/tianditu")
    public MapConfig tianditu() {
        return MapConfig.of(properties);
    }
}
