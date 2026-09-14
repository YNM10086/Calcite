package com.calcite.service.importer;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GeoLifeImporterTest {

    private ParsedTrack parseFixture() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/sample.plt")) {
            assertNotNull(in, "找不到 /sample.plt 夹具");
            return new GeoLifeImporter().parse(in);
        }
    }

    private static ParsedTrack parseText(String plt) throws Exception {
        return new GeoLifeImporter().parse(
                new ByteArrayInputStream(plt.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void 解析样本_点数与首点内容正确() throws Exception {
        List<RawPoint> pts = parseFixture().points();

        assertEquals(4, pts.size());
        RawPoint p0 = pts.get(0);
        assertEquals(39.984702, p0.lat(), 1e-9);
        assertEquals(116.318417, p0.lon(), 1e-9);
        assertEquals(OffsetDateTime.parse("2008-10-23T02:53:04Z"), p0.recordedAt());
    }

    @Test
    void 海拔从英尺换算成米() throws Exception {
        List<RawPoint> pts = parseFixture().points();

        // 492 英尺 × 0.3048 = 149.9616 米
        assertEquals(149.9616, pts.get(0).elevationM(), 1e-4);
        // 第四行是 520 英尺
        assertEquals(158.496, pts.get(3).elevationM(), 1e-4);
    }

    @Test
    void 日期时间字段与天数字段自洽() throws Exception {
        // 第 5 个字段 39744.1201851852 天（自 1899-12-30 UTC 起）应等于 2008-10-23T02:53:04Z
        OffsetDateTime fromDays = OffsetDateTime.parse("1899-12-30T00:00:00Z")
                .plusSeconds(Math.round(39744.1201851852 * 86400));
        assertEquals(fromDays, parseFixture().points().get(0).recordedAt());
    }

    @Test
    void plt_没有轨迹名_名字为_null() throws Exception {
        assertNull(parseFixture().name());
    }

    @Test
    void 空行和字段不足的行被跳过() throws Exception {
        String plt = "\n"
                + "39.984702,116.318417,0,492,39744.1201851852,2008-10-23,02:53:04\n"
                + "坏行\n"
                + "39.984683,116.318450,0,492,39744.1202546296,2008-10-23,02:53:05\n"
                + "\n";
        ParsedTrack t = parseText(plt);

        assertEquals(2, t.points().size());
    }

    @Test
    void 全空文件抛异常() {
        assertThrows(IllegalArgumentException.class, () -> parseText("\n\n"));
    }

    /**
     * 真实 GeoLife 文件与自造夹具的关键差异：**文件开头有 6 行文件头**！
     *
     * <pre>
     * Geolife trajectory
     * WGS 84
     * Altitude is in Feet
     * Reserved 3
     * 0,2,255,My Track,0,0,2,8421376
     * 0
     * </pre>
     *
     * <p>注意第 5 行有 8 个字段、前两个还是数字（0 和 2），所以"字段数够不够"拦不住它 ——
     * 实际是被"时间字段解析不出来"才跳过的。这条测试就是把这个行为钉死，
     * 免得以后有人"优化"解析逻辑时把它弄坏。
     */
    @Test
    void 真实文件_能跳过六行文件头() throws Exception {
        ParsedTrack t;
        try (InputStream in = getClass().getResourceAsStream("/sample-real.plt")) {
            assertNotNull(in, "找不到 /sample-real.plt 夹具");
            t = new GeoLifeImporter().parse(in);
        }
        List<RawPoint> pts = t.points();

        assertEquals(908, pts.size(), "6 行文件头 + 908 行数据");

        RawPoint first = pts.get(0);
        assertEquals(39.984702, first.lat(), 1e-9);
        assertEquals(116.318417, first.lon(), 1e-9);
        assertEquals(492 * 0.3048, first.elevationM(), 1e-4);
        assertEquals(OffsetDateTime.parse("2008-10-23T02:53:04Z"), first.recordedAt());

        RawPoint last = pts.get(pts.size() - 1);
        assertEquals(40.009328, last.lat(), 1e-9);
        assertEquals(116.320887, last.lon(), 1e-9);
        assertEquals(83 * 0.3048, last.elevationM(), 1e-4);
        assertEquals(OffsetDateTime.parse("2008-10-23T11:11:12Z"), last.recordedAt());
    }

    @Test
    void 第二个真实文件也正确() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/sample-real2.plt")) {
            assertNotNull(in, "找不到 /sample-real2.plt 夹具");
            assertEquals(244, new GeoLifeImporter().parse(in).points().size());
        }
    }
}
