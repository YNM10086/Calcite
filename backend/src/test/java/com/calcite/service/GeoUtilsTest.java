package com.calcite.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GeoUtilsTest {

    @Test
    void 同一点距离为零() {
        assertEquals(0.0, GeoUtils.haversineMeters(25.0, 117.0, 25.0, 117.0), 1e-9);
    }

    @Test
    void 赤道上经度差一度约_111_公里() {
        double d = GeoUtils.haversineMeters(0.0, 0.0, 0.0, 1.0);
        assertEquals(111195.0, d, 50.0);
    }

    @Test
    void 真实样本首两点只差_0_078_米() {
        // 用户那份 GPX 的前两个点（间隔 1 秒）—— 起跑前站着不动，所以只挪了 8 厘米。
        // 注意这两点是"文件里最先出现的两个"，不是"纬度最小的两个"。
        double d = GeoUtils.haversineMeters(25.0342562, 117.0204852, 25.0342555, 117.0204852);
        assertEquals(0.078, d, 0.005);
    }

    @Test
    void 距离是对称的() {
        double a = GeoUtils.haversineMeters(25.03, 117.02, 39.98, 116.31);
        double b = GeoUtils.haversineMeters(39.98, 116.31, 25.03, 117.02);
        assertEquals(a, b, 1e-6);
    }
}
