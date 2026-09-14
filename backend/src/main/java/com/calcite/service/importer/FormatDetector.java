package com.calcite.service.importer;

import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

/**
 * 按【文件内容】识别格式 —— 不看扩展名。
 *
 * <p>为什么强调这一点：实测样本的文件名是 {@code 2026年6月22日户外跑步.gpx.bin_tmp}，
 * 扩展名根本不是 .gpx。按扩展名判断会把它直接拒掉。
 */
public final class FormatDetector {

    /** .plt 数据行的日期 / 时间字段格式，用来和"随便一个 7 列数字 CSV"区分开 */
    private static final Pattern DATE = Pattern.compile("\\d{4}-\\d{2}-\\d{2}");
    private static final Pattern TIME = Pattern.compile("\\d{2}:\\d{2}:\\d{2}");

    /**
     * 最多往下扫多少个非空行。
     *
     * <p><b>为什么必须往下扫、不能只看第一行</b>：真实 GeoLife {@code .plt} 文件开头有 6 行文件头
     * （第一行是标题 {@code Geolife trajectory}），数据要到第 7 行才出现。
     * 只看第一行会把每一个真实文件都判成"无法识别"——这个坑在 2026-09-14 真的踩过：
     * 导入 171 个文件全部失败，耗时 388 ms（每个 2.3 ms，说明在解析之前就被拒了）。
     */
    private static final int MAX_SCAN_LINES = 50;

    private FormatDetector() {
    }

    /**
     * @param head 文件开头的一段字节（见 ImportService.HEAD_BYTES，默认 4096）
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

        // GeoLife .plt：往下扫若干行找数据行（文件头可能有几行，甚至几行都不定）
        int scanned = 0;
        for (String line : text.split("\\R")) {
            String s = line.trim();
            if (s.isEmpty()) {
                continue;
            }
            if (++scanned > MAX_SCAN_LINES) {
                break;
            }
            if (looksLikePltRow(s)) {
                return "geolife";
            }
        }

        return "unknown";
    }

    /**
     * 像不像一行 .plt 数据：
     * {@code 纬度,经度,占位,海拔(英尺),1899年以来的天数,日期,时间}
     */
    private static boolean looksLikePltRow(String s) {
        String[] f = s.split(",");
        return f.length == 7
                && isNumber(f[0])
                && isNumber(f[1])
                && isNumber(f[3])
                && DATE.matcher(f[5].trim()).matches()
                && TIME.matcher(f[6].trim()).matches();
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
