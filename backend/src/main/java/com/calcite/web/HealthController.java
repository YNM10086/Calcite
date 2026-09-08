package com.calcite.web;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 健康检查接口：用来验证「应用能启动」且「能连上 PostGIS」。
 *
 * <p>@RestController = @Controller + @ResponseBody，方法返回值会直接序列化成 JSON。
 * <p>JdbcTemplate 是 Spring 提供的数据库操作模板，这里用它跑一句原生 SQL。
 */
@RestController
@RequestMapping("/api/health")
public class HealthController {

    private final JdbcTemplate jdbcTemplate;

    // 构造器注入：Spring 会自动把容器里的 JdbcTemplate 传进来
    public HealthController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @GetMapping
    public Map<String, Object> health() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "UP");
        result.put("application", "calcite-backend");

        // 真正访问数据库：能查到版本说明 PostgreSQL + PostGIS 都通了
        String dbVersion = jdbcTemplate.queryForObject("SELECT version()", String.class);
        String postgisVersion = jdbcTemplate.queryForObject("SELECT PostGIS_Version()", String.class);
        result.put("database", dbVersion);
        result.put("postgis", postgisVersion);

        return result;
    }
}
