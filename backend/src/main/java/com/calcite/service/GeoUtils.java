package com.calcite.service;

/**
 * 地理计算小工具。
 *
 * <p>为什么在 Java 里算距离，而不是丢给 PostGIS？
 * 因为清洗阶段还没入库，需要用距离判断"这段速度是否异常"，必须在内存里算。
 *
 * <p>入库后算总距离仍然用 PostGIS（{@code ST_Length(geom::geography)}）。
 * 两者球面模型不完全相同，同一条轨迹会差一点（实测约 1.9%），这是正常的。
 */
public final class GeoUtils {

    /** 地球平均半径（米），与 PostGIS geography 用的球面模型一致 */
    private static final double EARTH_RADIUS_M = 6371008.8;

    private GeoUtils() {
    }

    /** 两点间的球面距离（米），Haversine 公式 */
    public static double haversineMeters(double lat1, double lon1, double lat2, double lon2) {
        double p1 = Math.toRadians(lat1);
        double p2 = Math.toRadians(lat2);
        double dp = p2 - p1;
        double dl = Math.toRadians(lon2 - lon1);

        double a = Math.sin(dp / 2) * Math.sin(dp / 2)
                + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2);
        // 浮点误差可能让 a 略微大于 1，asin 会返回 NaN，所以夹一下
        return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1.0, Math.sqrt(a)));
    }
}
