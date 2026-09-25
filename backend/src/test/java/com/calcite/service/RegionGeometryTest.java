package com.calcite.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class RegionGeometryTest {

    private static final ObjectMapper M = new ObjectMapper();
    private static final int MAXV = 2000;
    private static final double MAXB = 50000;

    private static JsonNode json(String s) {
        try { return M.readTree(s); } catch (Exception e) { throw new RuntimeException(e); }
    }

    /** 116.30,39.90 ~ 116.40,40.00 的矩形（5 个点，首尾闭合） */
    private static JsonNode rect() {
        return json("""
            {"type":"Polygon","coordinates":[[[116.30,39.90],[116.40,39.90],[116.40,40.00],[116.30,40.00],[116.30,39.90]]]}
            """);
    }

    @Test
    void 矩形解析成功且WKT经纬度顺序正确() {
        var r = RegionGeometry.parse(rect(), null, MAXV, MAXB);
        assertFalse(r.buffered());
        assertEquals(5, r.vertexCount());
        assertEquals("POLYGON((116.3 39.9,116.4 39.9,116.4 40,116.3 40,116.3 39.9))", r.wkt());
    }

    @Test
    void 数值不用科学计数法() {
        var r = RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[[[0.00001,0.00002],[1,0],[1,1],[0,1],[0.00001,0.00002]]]}
            """), null, MAXV, MAXB);
        assertTrue(r.wkt().contains("0.00001 0.00002"), r.wkt());
        assertFalse(r.wkt().contains("E-"), r.wkt());
    }

    @Test
    void Point加bufferM成功() {
        // ⚠️ 任务书原文这里是单行文本块 json("""{...}""")，Java 规定文本块开定界符后必须换行，单行写法编不过；
        //    语义完全等价，改用普通字符串字面量（转义双引号）。
        var r = RegionGeometry.parse(json("{\"type\":\"Point\",\"coordinates\":[116.32,40.00]}"), 500.0, MAXV, MAXB);
        assertTrue(r.buffered());
        assertEquals(1, r.vertexCount());
        assertEquals("POINT(116.32 40)", r.wkt());
    }

    @Test
    void Point没有bufferM要拒绝() {
        var e = assertThrows(IllegalArgumentException.class,
                () -> RegionGeometry.parse(json("{\"type\":\"Point\",\"coordinates\":[116.32,40.00]}"), null, MAXV, MAXB));
        assertTrue(e.getMessage().contains("bufferM"), e.getMessage());
    }

    @Test
    void bufferM为零或负数或NaN都要拒绝() {
        for (Double bad : new Double[]{0.0, -1.0, Double.NaN, Double.POSITIVE_INFINITY}) {
            assertThrows(IllegalArgumentException.class,
                    () -> RegionGeometry.parse(json("{\"type\":\"Point\",\"coordinates\":[116.32,40.00]}"), bad, MAXV, MAXB),
                    "bufferM=" + bad + " 应该被拒绝");
        }
    }

    @Test
    void bufferM超过上限要拒绝() {
        assertThrows(IllegalArgumentException.class,
                () -> RegionGeometry.parse(json("{\"type\":\"Point\",\"coordinates\":[116.32,40.00]}"), MAXB + 1, MAXV, MAXB));
    }

    @Test
    void MultiPolygon的顶点数是所有环之和() {
        var r = RegionGeometry.parse(json("""
            {"type":"MultiPolygon","coordinates":[
              [[[0,0],[1,0],[1,1],[0,1],[0,0]]],
              [[[2,2],[3,2],[3,3],[2,3],[2,2]]]]}
            """), null, MAXV, MAXB);
        assertEquals(10, r.vertexCount());
        assertTrue(r.wkt().startsWith("MULTIPOLYGON((("), r.wkt());
    }

    @Test
    void 带洞多边形两个环都进WKT() {
        var r = RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[
              [[0,0],[10,0],[10,10],[0,10],[0,0]],
              [[2,2],[4,2],[4,4],[2,4],[2,2]]]}
            """), null, MAXV, MAXB);
        assertEquals(10, r.vertexCount());
        assertEquals(2, r.wkt().split("\\),\\(").length);
    }

    @Test
    void 环未闭合要拒绝() {
        var e = assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1]]]}
            """), null, MAXV, MAXB));
        assertTrue(e.getMessage().contains("闭合"), e.getMessage());
    }

    @Test
    void 环点数少于四点要拒绝() {
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[[[0,0],[1,0],[0,0]]]}
            """), null, MAXV, MAXB));
    }

    @Test
    void 类型不在白名单要拒绝() {
        for (String t : new String[]{"LineString", "Feature", "GeometryCollection", "polygon", "unknown"}) {
            assertThrows(IllegalArgumentException.class,
                    () -> RegionGeometry.parse(json("{\"type\":\"" + t + "\",\"coordinates\":[]}"), null, MAXV, MAXB),
                    t + " 应该被拒绝");
        }
    }

    @Test
    void 缺geometry或type要拒绝() {
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(null, null, MAXV, MAXB));
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("{}"), null, MAXV, MAXB));
    }

    @Test
    void 坐标越界要拒绝() {
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[[[0,0],[1,0],[1,91],[0,91],[0,0]]]}
            """), null, MAXV, MAXB));
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[[[0,0],[181,0],[181,1],[0,1],[0,0]]]}
            """), null, MAXV, MAXB));
    }

    @Test
    void 顶点数边界值两侧都要对() {
        // 恰好 5 个点（外环最少）= 允许
        RegionGeometry.parse(rect(), null, 5, MAXB);
        // 上限 +1 = 拒绝
        var e = assertThrows(IllegalArgumentException.class,
                () -> RegionGeometry.parse(rect(), null, 4, MAXB));
        assertTrue(e.getMessage().contains("顶点"), e.getMessage());
    }

    @Test
    void coordinates不是数组或为空要拒绝() {
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[]}
            """), null, MAXV, MAXB));
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":"nope"}
            """), null, MAXV, MAXB));
    }

    @Test
    void 坐标含NaN要拒绝() {
        assertThrows(IllegalArgumentException.class, () -> RegionGeometry.parse(json("""
            {"type":"Polygon","coordinates":[[[0,0],[1,0],[1,null],[0,1],[0,0]]]}
            """), null, MAXV, MAXB));
    }
}
