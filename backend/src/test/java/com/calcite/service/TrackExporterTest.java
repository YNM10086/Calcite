package com.calcite.service;

import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link TrackExporter} 的单元测试。
 *
 * <p>重点测 <b>纯函数</b> {@code buildGeoJson} —— 它不碰数据库、不碰文件系统，
 * 所以整个类跑完只要几毫秒，{@code mvn test} 依然不需要数据库。
 */
class TrackExporterTest {

    private static final OffsetDateTime T0 = OffsetDateTime.parse("2008-09-13T11:19:29Z");

    /** 三个点，经纬度 + 海拔 + 时间 */
    private static List<TrackExporter.Point3D> samplePoints() {
        return List.of(
                new TrackExporter.Point3D(116.3, 40.0, 50.0, T0),
                new TrackExporter.Point3D(116.301, 40.001, 51.0, T0.plusSeconds(5)),
                new TrackExporter.Point3D(116.302, 40.002, 52.0, T0.plusSeconds(10)));
    }

    private static String build(List<TrackExporter.Point3D> pts) {
        return TrackExporter.buildGeoJson(3L, "资料一", "gpx", "abc123", T0,
                T0.plusSeconds(10), pts.size(), 715.0, pts);
    }

    @Test
    void 生成的是合法的GeoJSON_FeatureCollection() {
        String json = build(samplePoints());
        assertTrue(json.contains("\"type\": \"FeatureCollection\""), json.substring(0, 120));
        assertTrue(json.contains("\"type\": \"Feature\""));
        assertTrue(json.contains("\"type\": \"LineString\""));
    }

    @Test
    void 坐标是经度在前纬度在后_且带海拔() {
        String json = build(samplePoints());
        // GeoJSON 规范：coordinates 是 [经度, 纬度, 海拔]
        assertTrue(json.contains("[116.3, 40.0, 50.0]"), "没找到第一个点，实际：" + json);
        assertTrue(json.contains("[116.302, 40.002, 52.0]"), "没找到最后一个点");
    }

    /**
     * 这条很关键：**没有时间就还原不回来**。
     * 回收站的目的不只是"看一眼删的是哪条"，而是"真想要能找回来" ——
     * 而轨迹点的价值一半在时间上（速度、停留、时段分析全靠它）。
     */
    @Test
    void 每个点的时间都要导出() {
        String json = build(samplePoints());
        assertTrue(json.contains("2008-09-13T11:19:29Z"), "第一个点的时间没导出");
        assertTrue(json.contains("2008-09-13T11:19:39Z"), "最后一个点的时间没导出");
    }

    @Test
    void 元数据写进properties() {
        String json = build(samplePoints());
        assertTrue(json.contains("\"trackId\": 3"));
        assertTrue(json.contains("\"name\": \"资料一\""));
        assertTrue(json.contains("\"source\": \"gpx\""));
        assertTrue(json.contains("\"externalId\": \"abc123\""));
        assertTrue(json.contains("\"pointCount\": 3"));
    }

    @Test
    void 名字里的特殊字符要被转义_不能生成坏JSON() {
        // 如果直接拼字符串而不转义，一个引号就能让整个文件变成坏 JSON
        String json = TrackExporter.buildGeoJson(1L, "带\"引号\"和\\反斜杠的名字", "gpx", "x",
                T0, T0, 1, 1.0, samplePoints());
        assertTrue(json.contains("\\\""), "引号必须被转义：" + json);
        assertTrue(json.contains("\\\\"), "反斜杠必须被转义");
    }

    @Test
    void 空点列表也能生成_不抛异常() {
        String json = build(List.of());
        assertTrue(json.contains("\"coordinates\": []"), json);
    }

    @Test
    void 文件名安全化_去掉路径分隔符和非法字符() {
        assertEquals("资料一", TrackExporter.safeFileName("资料一"));
        // Windows 文件名里不能有 \ / : * ? " < > |
        assertEquals("a_b_c_d_e_f_g_h", TrackExporter.safeFileName("a/b\\c:d*e?f\"g<h"));
        // ⚠️ "." 和 ".." 是路径穿越 —— 必须挡掉，不能原样当文件名
        assertEquals("unnamed", TrackExporter.safeFileName("."));
        assertEquals("unnamed", TrackExporter.safeFileName(".."));
        // 太长要截断（Windows 路径总长限制）
        String longName = "x".repeat(500);
        assertTrue(TrackExporter.safeFileName(longName).length() <= 80);
    }
}
