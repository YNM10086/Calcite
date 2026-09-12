package com.calcite.service.importer;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * GeoLife 数据集的 {@code .plt} 解析器。
 *
 * <p>每行 7 个逗号分隔字段：
 * <pre>
 * 39.984702,116.318417,0,492,39744.1201851852,2008-10-23,02:53:04
 *   纬度      经度   占位 海拔(英尺) 1899年以来的天数   日期      时间(UTC)
 * </pre>
 *
 * <p>两个容易踩的坑：
 * <ol>
 *   <li><b>海拔单位是英尺</b>，必须 × 0.3048 才是米</li>
 *   <li>第 5 个字段是「自 1899-12-30 UTC 起的天数（含小数）」，它和第 6/7 字段是**自洽的**
 *       （{@code 0.1201851852 天 × 86400 = 10384 秒 = 02:53:04}）。
 *       这里用第 6/7 字段（可读、无浮点误差），第 5 个字段在测试里做交叉校验。</li>
 * </ol>
 */
public class GeoLifeImporter implements Importer {

    /** 英尺 → 米 */
    private static final double FEET_TO_METER = 0.3048;

    @Override
    public String format() {
        return "geolife";
    }

    @Override
    public ParsedTrack parse(InputStream in) throws Exception {
        List<RawPoint> points = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                String s = line.trim();
                if (s.isEmpty()) {
                    continue;
                }
                String[] f = s.split(",");
                if (f.length < 7) {
                    continue; // 字段不足，跳过
                }
                try {
                    double lat = Double.parseDouble(f[0].trim());
                    double lon = Double.parseDouble(f[1].trim());
                    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
                        continue;
                    }
                    Double ele = parseFeet(f[3].trim());
                    OffsetDateTime t = OffsetDateTime.parse(f[5].trim() + "T" + f[6].trim() + "Z");
                    points.add(new RawPoint(lat, lon, ele, t));
                } catch (RuntimeException ignored) {
                    // 单个坏行跳过，不影响整条轨迹
                }
            }
        }

        if (points.isEmpty()) {
            throw new IllegalArgumentException("文件里没有有效的轨迹点");
        }
        return new ParsedTrack(null, points);
    }

    private static Double parseFeet(String s) {
        try {
            return Double.parseDouble(s) * FEET_TO_METER;
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
