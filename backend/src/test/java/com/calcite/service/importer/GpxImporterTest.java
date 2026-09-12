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

class GpxImporterTest {

    private ParsedTrack parseSample() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/sample.gpx")) {
            assertNotNull(in, "找不到 /sample.gpx 夹具");
            return new GpxImporter().parse(in);
        }
    }

    private static ParsedTrack parseText(String gpx) throws Exception {
        return new GpxImporter().parse(new ByteArrayInputStream(gpx.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void 解析真实样本_点数与首末时间正确() throws Exception {
        List<RawPoint> pts = parseSample().points();

        assertEquals(2342, pts.size(), "真实样本应有 2342 个点");
        assertEquals(OffsetDateTime.parse("2026-06-22T11:00:08Z"), pts.get(0).recordedAt());
        assertEquals(OffsetDateTime.parse("2026-06-22T11:39:16Z"), pts.get(pts.size() - 1).recordedAt());
    }

    @Test
    void 真实样本的首点坐标与海拔() throws Exception {
        List<RawPoint> pts = parseSample().points();

        // 注意：这是"第一个点"，不是"纬度最小的点"——两者不是一回事
        assertEquals(25.0342562, pts.get(0).lat(), 1e-6);
        assertEquals(117.0204852, pts.get(0).lon(), 1e-6);
        // vivo 这份数据海拔全是 0.0（是"没记录"，不是解析失败）
        assertNotNull(pts.get(0).elevationM());
        assertEquals(0.0, pts.get(0).elevationM(), 1e-9);
    }

    @Test
    void 样本没有_name_所以名字为_null_由服务层兜底() throws Exception {
        assertNull(parseSample().name());
    }

    @Test
    void 能解析带_name_的_gpx() throws Exception {
        String gpx = "<?xml version='1.0' encoding='UTF-8'?>"
                + "<gpx xmlns=\"http://www.topografix.com/GPX/1/0\">"
                + "<trk><name>晨跑</name><trkseg>"
                + "<trkpt lat=\"39.9\" lon=\"116.3\"><ele>50.5</ele><time>2008-10-23T02:53:04Z</time></trkpt>"
                + "<trkpt lat=\"39.8\" lon=\"116.4\"><ele>52.0</ele><time>2008-10-23T02:53:05Z</time></trkpt>"
                + "</trkseg></trk></gpx>";
        ParsedTrack t = parseText(gpx);

        assertEquals("晨跑", t.name());
        assertEquals(2, t.points().size());
        assertEquals(50.5, t.points().get(0).elevationM(), 1e-9);
        assertEquals(39.9, t.points().get(0).lat(), 1e-9);
    }

    @Test
    void 单个坏点被跳过_不影响整体() throws Exception {
        String gpx = "<?xml version='1.0' encoding='UTF-8'?>"
                + "<gpx><trk><trkseg>"
                + "<trkpt lat=\"39.9\" lon=\"116.3\"><time>2008-10-23T02:53:04Z</time></trkpt>"
                + "<trkpt lat=\"BAD\" lon=\"116.4\"><time>2008-10-23T02:53:05Z</time></trkpt>"
                + "<trkpt lat=\"39.7\" lon=\"116.5\"><time>2008-10-23T02:53:06Z</time></trkpt>"
                + "</trkseg></trk></gpx>";
        ParsedTrack t = parseText(gpx);

        assertEquals(2, t.points().size());
    }

    @Test
    void 坐标越界的点被跳过() throws Exception {
        String gpx = "<?xml version='1.0' encoding='UTF-8'?>"
                + "<gpx><trk><trkseg>"
                + "<trkpt lat=\"39.9\" lon=\"116.3\"><time>2008-10-23T02:53:04Z</time></trkpt>"
                + "<trkpt lat=\"999.0\" lon=\"116.4\"><time>2008-10-23T02:53:05Z</time></trkpt>"
                + "</trkseg></trk></gpx>";
        ParsedTrack t = parseText(gpx);

        assertEquals(1, t.points().size());
    }

    @Test
    void 不是_gpx_时抛异常() {
        String bad = "{\"not\":\"gpx\"}";
        assertThrows(Exception.class,
                () -> parseText(bad));
    }

    @Test
    void 没有任何有效点时抛异常() {
        String empty = "<?xml version='1.0' encoding='UTF-8'?><gpx><trk><trkseg></trkseg></trk></gpx>";
        assertThrows(IllegalArgumentException.class, () -> parseText(empty));
    }
}
