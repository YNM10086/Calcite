package com.calcite.service;

import com.calcite.service.importer.RawPoint;

import java.util.List;

/**
 * 清洗结果。
 *
 * <p>{@code speeds} 和 {@code outliers} 与 {@code points} **等长且一一对应**。
 *
 * @param points    已按时间升序排序、海拔已归一化的点
 * @param speeds    每点的速度（米/秒）。第 0 个恒为 null（没有前一个点），
 *                  相邻时间差 &lt;= 0 时也为 null
 * @param outliers  每点是否疑似 GPS 漂移
 * @param distanceM 总距离（米，球面公式）
 * @param durationS 总时长（秒）
 */
public record CleanedTrack(
        List<RawPoint> points,
        List<Double> speeds,
        List<Boolean> outliers,
        double distanceM,
        int durationS
) {
}
