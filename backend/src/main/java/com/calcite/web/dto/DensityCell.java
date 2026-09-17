package com.calcite.web.dto;

/**
 * 一个网格格子。
 *
 * <p>{@code lon}/{@code lat} 是<b>格子中心</b>（就是 {@code ST_SnapToGrid} 的节点），
 * 前端用中心 ± {@code cellSize}/2 画出方格。
 *
 * <p><b>为什么两个口径都带上</b>：实测「点数」和「轨迹条数」的最热格子<b>完全不同</b>
 * （一个格子里 12,562 个点但只有 63 条轨迹，另一个 1,618 个点却有 140 条轨迹）。
 * 两个都返回，前端切口径就<b>不用重新请求</b>；而 {@code value} 是按 {@code metric}
 * 选出来的那个，让渲染逻辑保持简单。
 */
public record DensityCell(
        double lon,
        double lat,
        long points,
        long tracks,
        long value
) {
}
