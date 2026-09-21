package com.calcite.service;

import com.calcite.config.DataProperties;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 把一条轨迹导出成 <b>GeoJSON</b>，作为删除前的"回收站"。
 *
 * <p><b>为什么是 GeoJSON</b>：
 * <ul>
 *   <li>标准格式 —— QGIS / geojson.io / Python 都能直接打开（用户想手工看一眼删的是哪条，拖进去就行）</li>
 *   <li>文本格式 —— 出问题了肉眼能读</li>
 *   <li>元数据放 {@code properties} 里，不丢信息</li>
 * </ul>
 *
 * <p><b>为什么 {@code buildGeoJson} 和 {@code exportToFile} 要分开</b>：
 * 前者是<b>纯函数</b>（输入 → 字符串），不碰文件系统、不碰数据库 ——
 * 所以能喂假数据单测，{@code mvn test} 依然不需要数据库。
 * 后者才做真正的落盘。
 */
@Component
public class TrackExporter {

    /** 一个轨迹点：经度、纬度、海拔、时间 */
    public record Point3D(double lon, double lat, double elevationM, OffsetDateTime recordedAt) {
    }

    private static final DateTimeFormatter FILE_STAMP =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");

    private final DataProperties props;

    public TrackExporter(DataProperties props) {
        this.props = props;
    }

    /**
     * 生成 GeoJSON 文本（<b>纯函数</b>）。
     *
     * <p>坐标按 GeoJSON 规范是 <b>[经度, 纬度, 海拔]</b>（经度在前，别写反）。
     * 每个点的时间另存一份到 {@code properties.times} —— GeoJSON 规范里没有放时间的地方，
     * 而<b>没有时间就还原不回来</b>（速度、停留、时段分析全靠它）。
     */
    public static String buildGeoJson(Long trackId, String name, String source, String externalId,
                                      OffsetDateTime startTime, OffsetDateTime endTime,
                                      Integer pointCount, Double lengthM,
                                      List<Point3D> points) {
        StringBuilder coords = new StringBuilder();
        StringBuilder times = new StringBuilder();
        for (int i = 0; i < points.size(); i++) {
            Point3D p = points.get(i);
            if (i > 0) {
                coords.append(", ");
                times.append(", ");
            }
            coords.append('[').append(p.lon()).append(", ").append(p.lat())
                  .append(", ").append(p.elevationM()).append(']');
            times.append('"').append(escape(p.recordedAt() == null ? "" : p.recordedAt().toString())).append('"');
        }

        return """
                {
                  "type": "FeatureCollection",
                  "features": [
                    {
                      "type": "Feature",
                      "geometry": {
                        "type": "LineString",
                        "coordinates": [%s]
                      },
                      "properties": {
                        "trackId": %s,
                        "name": "%s",
                        "source": "%s",
                        "externalId": "%s",
                        "startTime": "%s",
                        "endTime": "%s",
                        "pointCount": %s,
                        "lengthM": %s,
                        "times": [%s]
                      }
                    }
                  ]
                }
                """.formatted(
                coords,
                trackId,
                escape(name),
                escape(source),
                escape(externalId),
                startTime == null ? "" : escape(startTime.toString()),
                endTime == null ? "" : escape(endTime.toString()),
                pointCount == null ? 0 : pointCount,
                lengthM == null ? 0 : lengthM,
                times);
    }

    /**
     * 把 GeoJSON 写到回收站目录，返回写出的文件路径。
     *
     * <p><b>⚠️ 调用方必须遵守 fail-safe</b>：这个方法抛异常时，
     * <b>不要执行删除</b>。见 {@code TrackEditService.delete}。
     *
     * @throws IOException 目录建不出来、磁盘满、没权限 —— 一律往上抛，由调用方决定不删
     */
    public Path exportToFile(String geojson, String trackName, int pointCount,
                             OffsetDateTime deletedAt) throws IOException {
        Path dir = Path.of(props.getRecycleDir());
        Files.createDirectories(dir);

        String stamp = deletedAt.format(FILE_STAMP);
        String fileName = stamp + "_" + safeFileName(trackName) + "_" + pointCount + "点.geojson";
        Path target = dir.resolve(fileName);

        Files.writeString(target, geojson, StandardCharsets.UTF_8);
        return target;
    }

    /**
     * 把任意字符串变成安全的文件名片段（<b>纯函数</b>）。
     *
     * <p>去掉 Windows 不允许的 {@code \ / : * ? " < > |} 和空白，
     * 并把长度截到 80（Windows 有路径总长限制）。
     */
    public static String safeFileName(String raw) {
        if (raw == null || raw.isBlank()) {
            return "unnamed";
        }
        String s = raw.replaceAll("[\\\\/:*?\"<>|\\s]+", "_");
        // ⚠️ "." 和 ".." 是【路径穿越】—— resolve 之后会跑到上一级目录。
        // 它们不包含上面那组非法字符，所以必须单独挡。
        if (s.equals(".") || s.equals("..")) {
            return "unnamed";
        }
        if (s.length() > 80) {
            s = s.substring(0, 80);
        }
        return s;
    }

    /** JSON 字符串转义。不转义的话，名字里一个引号就能让整个文件变成坏 JSON。 */
    private static String escape(String s) {
        if (s == null) {
            return "";
        }
        StringBuilder out = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> out.append(c);
            }
        }
        return out.toString();
    }
}
