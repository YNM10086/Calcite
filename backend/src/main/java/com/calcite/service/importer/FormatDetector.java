package com.calcite.service.importer;

import java.nio.charset.StandardCharsets;

/**
 * 按【文件内容】识别格式 —— 不看扩展名。
 *
 * <p>为什么强调这一点：实测样本的文件名是 {@code 2026年6月22日户外跑步.gpx.bin_tmp}，
 * 扩展名根本不是 .gpx。按扩展名判断会把它直接拒掉。
 */
public final class FormatDetector {

    private FormatDetector() {
    }

    /**
     * @param head 文件开头的一段字节（几百字节就够，见 ImportService.HEAD_BYTES）
     * @return {@code "gpx"} / {@code "geolife"} / {@code "unknown"}
     */
    public static String detect(byte[] head) {
        if (head == null || head.length == 0) {
            return "unknown";
        }
        String text = new String(head, StandardCharsets.UTF_8).trim();
        if (text.isEmpty()) {
            return "unknown";
        }

        // GPX：XML 文档，可能带 <?xml 声明，也可能直接以 <gpx 开头
        if (text.startsWith("<?xml") || text.startsWith("<gpx") || text.contains("<gpx")) {
            return "gpx";
        }

        // GeoLife .plt：每行 7 个逗号分隔字段，前两个是纬度和经度
        for (String line : text.split("\\R")) {
            String s = line.trim();
            if (s.isEmpty()) {
                continue;
            }
            String[] f = s.split(",");
            if (f.length == 7 && isNumber(f[0]) && isNumber(f[1])) {
                return "geolife";
            }
            break; // 只看第一行有效内容
        }

        return "unknown";
    }

    private static boolean isNumber(String s) {
        try {
            Double.parseDouble(s.trim());
            return true;
        } catch (NumberFormatException e) {
            return false;
        }
    }
}
