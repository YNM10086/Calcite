package com.calcite.service;

import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * 把前端传来的 GeoJSON 几何转成 PostGIS 能吃的 WKT —— <b>只做结构校验，不做拓扑校验</b>。
 *
 * <p><b>为什么只做结构校验</b>：「多边形自交 / 面积为 0」这类<b>拓扑</b>问题要靠 PostGIS 的
 * {@code ST_IsValid}（见 {@code WithinService}）。本类是纯函数、零依赖，故意不碰数据库 ——
 * 于是所有"能把 500 变成 400"的输入检查都能用 JUnit 直接覆盖。
 *
 * <p><b>为什么自己拼 WKT 而不是让 PostGIS 解析 GeoJSON</b>：
 * 校验必须发生在 Java 侧，否则用户看到的是 PostGIS 的裸异常而不是"哪里画错了"。
 */
public final class RegionGeometry {

    private static final Set<String> ALLOWED = Set.of("Polygon", "MultiPolygon", "Point");

    /** 无限宽时间窗的边界（PostgreSQL 的 timestamptz 能表示这个范围，而我们的数据是 2008~2009） */
    public static final String WKT_TAG = "REGION";

    private RegionGeometry() {
    }

    /**
     * @param wkt         给 {@code ST_GeomFromText(:wkt, 4326)} 用
     * @param buffered    true = 形状是 Point 且要按 bufferM 做球面缓冲
     * @param vertexCount 顶点总数（MultiPolygon 是所有环之和）
     */
    public record Region(String wkt, boolean buffered, int vertexCount) {
    }

    public static Region parse(JsonNode geometry, Double bufferM, int maxVertices, double maxBufferM) {
        if (geometry == null || geometry.isNull()) {
            throw new IllegalArgumentException("缺少 geometry");
        }
        String type = geometry.path("type").asText("");
        if (!ALLOWED.contains(type)) {
            throw new IllegalArgumentException(
                    "geometry.type 只支持 Polygon / MultiPolygon / Point，收到：" + (type.isEmpty() ? "(空)" : type));
        }

        JsonNode coords = geometry.path("coordinates");
        if (!coords.isArray() || coords.isEmpty()) {
            throw new IllegalArgumentException("geometry.coordinates 必须是非空数组");
        }

        if ("Point".equals(type)) {
            double[] p = position(coords);
            double buf = requireBuffer(bufferM, maxBufferM);
            return new Region("POINT(" + num(p[0]) + " " + num(p[1]) + ")", true, 1);
        }

        // ── 多边形 / 多多边形 ───────────────────────────────────────────
        // 结构统一成 List<多边形>，每个多边形是 List<环>，每个环是 List<double[lon,lat]>
        // ⚠️ 必须保留「哪个环属于哪个多边形」这一层：把 MultiPolygon 的所有环拍平成一个列表，
        //    会把"带洞的多边形"错写成两个独立多边形（WKT 语义就变了）。
        List<List<List<double[]>>> polygons = new ArrayList<>();
        if ("Polygon".equals(type)) {
            polygons.add(ringsOf(coords));
        } else {
            for (JsonNode polygon : coords) {
                polygons.add(ringsOf(polygon));
            }
        }
        if (polygons.isEmpty()) {
            throw new IllegalArgumentException("geometry 里没有任何多边形");
        }

        int total = 0;
        for (List<List<double[]>> rings : polygons) {
            if (rings.isEmpty()) {
                throw new IllegalArgumentException("多边形至少要有一个环");
            }
            for (List<double[]> ring : rings) {
                if (ring.size() < 4) {
                    throw new IllegalArgumentException("多边形的每个环至少要 4 个点（含闭合点），收到 " + ring.size() + " 个");
                }
                double[] first = ring.get(0);
                double[] last = ring.get(ring.size() - 1);
                if (first[0] != last[0] || first[1] != last[1]) {
                    throw new IllegalArgumentException("多边形没有闭合：第一个点必须与最后一个点相同");
                }
                total += ring.size();
            }
        }
        if (total > maxVertices) {
            throw new IllegalArgumentException("区域太复杂：顶点数 " + total + " 超过上限 " + maxVertices + "，请简化");
        }

        StringBuilder sb = new StringBuilder("Polygon".equals(type) ? "POLYGON(" : "MULTIPOLYGON(");
        for (int i = 0; i < polygons.size(); i++) {
            if (i > 0) {
                sb.append(',');
            }
            if (!"Polygon".equals(type)) {
                sb.append('(');           // MultiPolygon：每个多边形额外一层括号
            }
            appendRings(sb, polygons.get(i));
            if (!"Polygon".equals(type)) {
                sb.append(')');
            }
        }
        sb.append(')');
        return new Region(sb.toString(), false, total);
    }

    private static double requireBuffer(Double bufferM, double maxBufferM) {
        if (bufferM == null) {
            throw new IllegalArgumentException("Point 几何必须给 bufferM（缓冲半径，米）");
        }
        // 用 !(x > 0) 而不是 x <= 0：NaN 是无序的，NaN <= 0 为 false，会绕过检查
        if (!(bufferM > 0) || !Double.isFinite(bufferM)) {
            throw new IllegalArgumentException("bufferM 必须是有限正数，收到：" + bufferM);
        }
        if (bufferM > maxBufferM) {
            throw new IllegalArgumentException("bufferM 超过上限 " + (long) maxBufferM + " 米");
        }
        return bufferM;
    }

    /**
     * 把「一个多边形的 coordinates」解析成若干环。
     *
     * <p>Polygon 与 MultiPolygon 里的<b>单个多边形</b>都是 {@code [[x,y],...]}（环的数组），
     * 所以两种类型共用这一个解析器 —— 区别只在外面那层（Polygon 只有一层，MultiPolygon 有多层）。
     */
    private static List<List<double[]>> ringsOf(JsonNode polygonCoords) {
        if (!polygonCoords.isArray() || polygonCoords.isEmpty()) {
            throw new IllegalArgumentException("多边形的 coordinates 必须是非空数组");
        }
        // 标准写法是 [[[x,y],...]]（环的数组）；也容忍省略一层的 [[x,y],...]
        boolean isRingList = polygonCoords.get(0).isArray()
                && !polygonCoords.get(0).isEmpty()
                && polygonCoords.get(0).get(0).isArray();
        List<List<double[]>> out = new ArrayList<>();
        if (isRingList) {
            for (JsonNode ringNode : polygonCoords) {
                out.add(ring(ringNode));
            }
        } else {
            out.add(ring(polygonCoords));
        }
        return out;
    }

    private static List<double[]> ring(JsonNode ringNode) {
        if (!ringNode.isArray() || ringNode.isEmpty()) {
            throw new IllegalArgumentException("多边形的环必须是非空数组");
        }
        List<double[]> ring = new ArrayList<>(ringNode.size());
        for (JsonNode pos : ringNode) {
            ring.add(position(pos));
        }
        return ring;
    }

    /** @return [lon, lat] */
    private static double[] position(JsonNode pos) {
        if (pos == null || !pos.isArray() || pos.size() < 2 || !pos.get(0).isNumber() || !pos.get(1).isNumber()) {
            throw new IllegalArgumentException("坐标必须是 [经度, 纬度] 两个数字，收到：" + pos);
        }
        double lon = pos.get(0).asDouble();
        double lat = pos.get(1).asDouble();
        if (!Double.isFinite(lon) || !Double.isFinite(lat)) {
            throw new IllegalArgumentException("坐标必须是有限数字，收到：" + pos);
        }
        if (lat < -90 || lat > 90) {
            throw new IllegalArgumentException("纬度必须在 -90 ~ 90 之间，收到：" + lat);
        }
        if (lon < -180 || lon > 180) {
            throw new IllegalArgumentException("经度必须在 -180 ~ 180 之间，收到：" + lon);
        }
        return new double[]{lon, lat};
    }

    private static void appendRings(StringBuilder sb, List<List<double[]>> rings) {
        for (int i = 0; i < rings.size(); i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append('(');
            appendRing(sb, rings.get(i));
            sb.append(')');
        }
    }

    private static void appendRing(StringBuilder sb, List<double[]> ring) {
        for (int i = 0; i < ring.size(); i++) {
            if (i > 0) {
                sb.append(',');
            }
            double[] p = ring.get(i);
            sb.append(num(p[0])).append(' ').append(num(p[1]));
        }
    }

    /**
     * ⚠️ 不能用 {@code String.valueOf(double)}：极小/极大值会输出科学计数法（{@code 1.0E-5}），
     * 虽然 PostGIS 多半也认，但没必要赌 —— {@code BigDecimal.toPlainString} 永远给普通小数。
     */
    private static String num(double v) {
        return BigDecimal.valueOf(v).stripTrailingZeros().toPlainString();
    }
}
