package com.calcite.service.importer;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class FormatDetectorTest {

    private static byte[] bytes(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    @Test
    void 识别_gpx_即使声明用单引号且带独立属性() {
        String gpx = "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n"
                + "<gpx creator=\"vivo运动健康\"><trk><trkseg>"
                + "<trkpt lat=\"25.03\" lon=\"117.02\"/></trkseg></trk></gpx>";
        assertEquals("gpx", FormatDetector.detect(bytes(gpx)));
    }

    @Test
    void 识别_gpx_无_xml_声明() {
        assertEquals("gpx", FormatDetector.detect(bytes("<gpx version=\"1.0\"></gpx>")));
    }

    @Test
    void 识别_geolife_plt() {
        String plt = "39.984702,116.318417,0,492,39744.1201851852,2008-10-23,02:53:04\n"
                + "39.984683,116.318450,0,492,39744.1202546296,2008-10-23,02:53:05";
        assertEquals("geolife", FormatDetector.detect(bytes(plt)));
    }

    @Test
    void 无法识别时返回_unknown() {
        assertEquals("unknown", FormatDetector.detect(bytes("这不是轨迹数据")));
        assertEquals("unknown", FormatDetector.detect(bytes("name,age\n张三,20")));
        assertEquals("unknown", FormatDetector.detect(new byte[0]));
    }

    @Test
    void 按内容识别而不是扩展名_真实样本的扩展名是_bin_tmp() {
        // 用户那份文件的扩展名是 .gpx.bin_tmp，检测只看内容，所以照样识别成 gpx
        String gpx = "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><gpx></gpx>";
        assertEquals("gpx", FormatDetector.detect(bytes(gpx)));
    }

    /**
     * 真实 GeoLife .plt 文件开头有 6 行文件头，**第一行不是数据**。
     *
     * <p>这条测试是补的漏：之前只测了"自造的无头夹具"，识别器就一直有 bug ——
     * 2026-09-14 导入真实数据时 171 个文件全部失败，就是因为只看第一行。
     */
    @Test
    void 识别真实_geolife_文件_它开头有六行文件头() throws Exception {
        byte[] content;
        try (java.io.InputStream in = getClass().getResourceAsStream("/sample-real.plt")) {
            assertNotNull(in, "找不到 /sample-real.plt 夹具");
            content = in.readAllBytes();
        }
        byte[] head = java.util.Arrays.copyOf(content, Math.min(4096, content.length));
        assertEquals("geolife", FormatDetector.detect(head));
    }

    @Test
    void 只有文件头时返回_unknown() {
        String headerOnly = "Geolife trajectory\nWGS 84\nAltitude is in Feet\nReserved 3\n"
                + "0,2,255,My Track,0,0,2,8421376\n0\n";
        assertEquals("unknown", FormatDetector.detect(bytes(headerOnly)));
    }

    @Test
    void 七列数字的普通_csv_不会被误判成_plt() {
        // 7 个字段、前两个是数字，但没有日期/时间列 —— 靠日期时间格式把它排除掉
        assertEquals("unknown", FormatDetector.detect(bytes("1,2,3,4,5,6,7\n8,9,10,11,12,13,14")));
    }
}
