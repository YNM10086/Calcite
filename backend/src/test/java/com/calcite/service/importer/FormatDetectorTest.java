package com.calcite.service.importer;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;

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
}
