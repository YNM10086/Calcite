package com.calcite.web.dto;

import java.util.List;

/**
 * 网格密度接口的响应。
 *
 * <p>{@code scanned} 让前端能显示"1335 个格子 / 227945 个点"（参照视野的实测值），
 * 也让调用方一眼看出这次查询实际扫到什么。
 *
 * <p>{@code maxTracks} 是<b>单格里最多的轨迹条数</b>（不是全库轨迹数）——
 * 名字特意带上 max，免得被误读。
 *
 * <p>{@code params} 把本次生效的参数原样回显，调试时能立刻看出"我传的 7-9 点到底生效没有"。
 */
public record DensityResponse(
        double[] bbox,
        double cellSize,
        String metric,
        Scanned scanned,
        Params params,
        List<DensityCell> cells
) {

    public record Scanned(long cells, long points, long maxTracks) {
    }

    public record Params(String metric, Integer hourFrom, Integer hourTo,
                         String from, String to) {
    }
}
