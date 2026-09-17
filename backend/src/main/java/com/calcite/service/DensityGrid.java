package com.calcite.service;

/**
 * 网格密度的<b>纯静态工具</b>：参数解析与校验、挑档、格子数估算、格子索引 ↔ 经纬度换算。
 *
 * <p><b>为什么单独抽一个类，而不是写在 {@link DensityService} 里</b>：
 * 那样为了测"格边长非法要报 400"，就得启动 Spring 上下文 + 连数据库。
 * 而本项目现有的 72 个测试<b>全都不需要数据库</b>，不能让第一个破例。
 * 抽成静态工具之后，这一整类测试跑完只要几毫秒。
 *
 * <p>命名和职责对齐 {@code GeoUtils}（同样是静态地理工具，被两个 service 复用）。
 */
public final class DensityGrid {

    private DensityGrid() {
    }

    /** 一个视野包围盒（度）。字段顺序与 OGC bbox 一致：西, 南, 东, 北 */
    public record Bbox(double west, double south, double east, double north) {

        public double widthDeg() {
            return east - west;
        }

        public double heightDeg() {
            return north - south;
        }
    }

    /**
     * 解析 {@code "西经,南纬,东经,北纬"} 形式的 bbox。
     *
     * <p>解析失败一律抛 {@link IllegalArgumentException}（控制器会映射成 400）——
     * 不要返回 null 让调用方去猜。
     */
    public static Bbox parseBbox(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("缺少 bbox 参数（格式：西经,南纬,东经,北纬）");
        }
        String[] parts = raw.split(",", -1);
        if (parts.length != 4) {
            throw new IllegalArgumentException(
                    "bbox 需要 4 个数字（西经,南纬,东经,北纬），实际收到 " + parts.length + " 个：" + raw);
        }
        double[] v = new double[4];
        String[] names = {"西经", "南纬", "东经", "北纬"};
        for (int i = 0; i < 4; i++) {
            try {
                v[i] = Double.parseDouble(parts[i].trim());
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("bbox 的第 " + (i + 1) + " 项（" + names[i]
                        + "）不是数字：" + parts[i]);
            }
            if (!Double.isFinite(v[i])) {
                throw new IllegalArgumentException("bbox 的第 " + (i + 1) + " 项（" + names[i]
                        + "）不是有限数：" + parts[i]);
            }
        }
        if (v[0] < -180 || v[2] > 180) {
            throw new IllegalArgumentException("经度必须在 -180 ~ 180 之间");
        }
        if (v[1] < -90 || v[3] > 90) {
            throw new IllegalArgumentException("纬度必须在 -90 ~ 90 之间");
        }
        if (v[0] >= v[2]) {
            throw new IllegalArgumentException("西经必须小于东经（实得 " + v[0] + " >= " + v[2] + "）");
        }
        if (v[1] >= v[3]) {
            throw new IllegalArgumentException("南纬必须小于北纬（实得 " + v[1] + " >= " + v[3] + "）");
        }
        return new Bbox(v[0], v[1], v[2], v[3]);
    }

    /**
     * 校验格边长必须是阶梯里的某一个值。
     *
     * <p><b>⚠️ 必须用 {@link Double#compare}，不能用 {@code ==}。</b>
     * {@code 0.001} 这类十进制小数在二进制浮点里不精确，两个"看起来一样"的
     * {@code double} 用 {@code ==} 有可能比不中。这是浮点比较的经典坑。
     */
    public static void requireKnownCellSize(double cellSize, double[] ladder) {
        for (double v : ladder) {
            if (Double.compare(v, cellSize) == 0) {
                return;
            }
        }
        throw new IllegalArgumentException(
                "cellSize 必须是阶梯里的值 " + java.util.Arrays.toString(ladder) + "，收到 " + cellSize);
    }

    /**
     * 按视野宽度挑一档格边长：<b>阶梯里 ≥ (视野宽度 ÷ 目标格数) 的最小那一档</b>。
     *
     * <p>找不到（视野比最粗那档还宽）就退回最粗档 —— 宁可格子粗，也不要算出一堆格子。
     */
    public static double pickCellSize(double viewWidthDeg, double[] ladder, int targetAcross) {
        if (targetAcross < 1) {
            throw new IllegalArgumentException("目标格数必须 >= 1");
        }
        double need = viewWidthDeg / targetAcross;
        double best = -1;
        // 阶梯是【从粗到细】排的，一路往下找；一旦某档装不下就停
        for (double v : ladder) {
            if (v >= need) {
                best = v;
            } else {
                break;
            }
        }
        return best > 0 ? best : ladder[0];
    }

    /**
     * 估算格子数（<b>上界</b>，不管有没有数据）。
     *
     * <p>这是本项目防止"全球 bbox + 最细格子"把服务打死的手段：
     * 它是上界，所以实际返回的格子数一定不会超过它。
     */
    public static long estimateCells(Bbox b, double cellSize) {
        long nx = (long) Math.ceil(b.widthDeg() / cellSize);
        long ny = (long) Math.ceil(b.heightDeg() / cellSize);
        return nx * ny;
    }

    // ---------------------------------------------------------------- 格子索引 ↔ 经纬度
    //
    // 这里的换算必须和 SQL 里的 round(ST_X(geom)/cell) 完全一致，
    // 否则前端画的格子和数据库算出来的格子会错位。

    /** 经度 → 格子索引。等价于 {@code ST_SnapToGrid} 的"就近取整到 cell 的整数倍" */
    public static long lonToIndex(double lon, double cellSize) {
        return Math.round(lon / cellSize);
    }

    /** 纬度 → 格子索引 */
    public static long latToIndex(double lat, double cellSize) {
        return Math.round(lat / cellSize);
    }

    /** 格子索引 → 格子中心经度 */
    public static double indexToLon(long nx, double cellSize) {
        return nx * cellSize;
    }

    /** 格子索引 → 格子中心纬度 */
    public static double indexToLat(long ny, double cellSize) {
        return ny * cellSize;
    }

    // ---------------------------------------------------------------- 时段与口径

    /**
     * 校验"一天内时段"参数：要么都不传，要么都传、且 0 ≤ from ≤ to ≤ 23。
     */
    public static void requireHourRange(Integer hourFrom, Integer hourTo) {
        if (hourFrom == null && hourTo == null) {
            return;
        }
        if (hourFrom == null || hourTo == null) {
            throw new IllegalArgumentException("hourFrom 和 hourTo 必须成对出现");
        }
        if (hourFrom < 0 || hourFrom > 23 || hourTo < 0 || hourTo > 23) {
            throw new IllegalArgumentException("小时必须在 0 ~ 23 之间");
        }
        if (hourFrom > hourTo) {
            throw new IllegalArgumentException("hourFrom 不能大于 hourTo");
        }
    }

    /**
     * 把可选时段规整成 SQL 用的 {@code [from, to]}。
     *
     * <p><b>⚠️ 这里【不做】任何时区换算。</b> 时区由 SQL 的
     * {@code recorded_at AT TIME ZONE 'Asia/Shanghai'} 负责。
     * 如果 Java 这边也换算一次，就会双重换算，查出来的时段完全错 ——
     * 有专门的测试钉住"原样透传"这件事。
     *
     * <p>不传时段时用 {@code [0, 23]} 兜底，这样 SQL 里不需要写 {@code IS NULL} 判断
     * （native query 里的可空参数类型推断很麻烦）。
     */
    public static int[] passThroughHourRange(Integer hourFrom, Integer hourTo) {
        requireHourRange(hourFrom, hourTo);
        return new int[]{hourFrom == null ? 0 : hourFrom, hourTo == null ? 23 : hourTo};
    }

    /** 校验口径参数，返回规整后的值（默认 tracks） */
    public static String requireMetric(String metric) {
        if (metric == null || metric.isBlank()) {
            return "tracks";
        }
        if (!"tracks".equals(metric) && !"points".equals(metric)) {
            throw new IllegalArgumentException("metric 只能是 tracks 或 points，收到 " + metric);
        }
        return metric;
    }
}
