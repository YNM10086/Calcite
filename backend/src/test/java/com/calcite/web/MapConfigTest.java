package com.calcite.web;

import com.calcite.config.MapProperties;
import com.calcite.web.dto.MapConfig;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 天地图配置接口的契约测试。
 *
 * <p>为什么不启 Spring：这条接口没有任何依赖（不碰数据库、不碰 service），
 * 它的全部风险都在**响应长什么样** —— 所以直接测 {@link MapConfig#of} 与它的 JSON 序列化，
 * 既不需要容器也不需要数据库（和本项目"单测一律不依赖数据库"的纪律一致）。
 *
 * <p>⚠️ 这里钉住的最重要一条：**没配 key 时，响应里不能出现 token 字段**（哪怕是 null/空串）。
 * 前端靠 `enabled` 判断要不要开图层，多一个空 token 字段只会让人误以为"配了但没生效"。
 */
class MapConfigTest {

    private final ObjectMapper json = new ObjectMapper();

    @Test
    void 没配key时enabled为false且JSON里不出现token字段() throws Exception {
        MapProperties props = new MapProperties();   // 默认就是空 token

        MapConfig config = MapConfig.of(props);
        assertFalse(config.enabled(), "空 token 必须视为未配置");
        assertNull(config.token(), "未配置时 token 应为 null（不是空串）");

        String text = json.writeValueAsString(config);
        assertFalse(text.contains("\"token\""), "未配置时 JSON 里不应出现 token 字段，实际：" + text);
        assertTrue(text.contains("\"enabled\":false"), "应带出 enabled=false，实际：" + text);
        assertTrue(text.contains("\"maxLevel\":18"), "层级上限应有默认值，实际：" + text);
    }

    @Test
    void 配了key时原样带出token与层级和子域() throws Exception {
        MapProperties props = new MapProperties();
        props.setTiandituToken("abc123def456");
        props.setTiandituMaxLevel(17);
        props.setSubdomains(List.of("0", "1"));

        MapConfig config = MapConfig.of(props);
        assertTrue(config.enabled());
        assertEquals("abc123def456", config.token());
        assertEquals(17, config.maxLevel());
        assertEquals(List.of("0", "1"), config.subdomains());

        String text = json.writeValueAsString(config);
        assertTrue(text.contains("\"token\":\"abc123def456\""), "实际：" + text);
    }

    @Test
    void key两边的空白会去掉只有空白也算没配() {
        MapProperties props = new MapProperties();

        props.setTiandituToken("   ");
        assertFalse(MapConfig.of(props).enabled(), "只有空白 = 没配（粘贴时很容易带空格）");

        props.setTiandituToken("  real-key-here  ");
        assertEquals("real-key-here", MapConfig.of(props).token(), "两边的空白必须去掉");
    }

    @Test
    void 子域与层级有可用默认值() {
        MapProperties props = new MapProperties();

        assertEquals(18, props.getTiandituMaxLevel(), "街道矢量图要 18 级才看得到建筑轮廓");
        assertEquals(List.of("0", "1", "2", "3", "4", "5", "6", "7"), props.getSubdomains(),
                "天地图瓦片子域是 t0~t7");
        assertEquals("", props.getTiandituToken(), "默认不配 key —— 默认关，不拖性能");
    }
}
