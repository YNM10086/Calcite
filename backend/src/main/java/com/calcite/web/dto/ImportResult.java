package com.calcite.web.dto;

/**
 * 导入结果 —— 前端拿它显示摘要。
 *
 * @param id               轨迹主键
 * @param name             轨迹名
 * @param pointCount       点数
 * @param distanceM        总距离（米，Java 按球面公式算）
 * @param durationS        总时长（秒）
 * @param outlierCount     疑似 GPS 漂移点数
 * @param skippedDuplicate 是否是"已经导入过"（true 时没有新建轨迹）
 * @param message          给人看的一句话
 */
public record ImportResult(
        Long id,
        String name,
        int pointCount,
        double distanceM,
        int durationS,
        long outlierCount,
        boolean skippedDuplicate,
        String message
) {
}
