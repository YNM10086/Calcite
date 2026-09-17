package com.calcite.web.dto;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 热点接口的完整响应。
 *
 * <p>{@code scannedTracks} / {@code scannedStays} 是<b>为了能自证</b>：
 * 前端可以显示"扫了 10 个停留点，识别出 3 个热点"，
 * 两者之差就是被排除的孤立点个数，不用额外查询就能解释结果。
 *
 * <p>{@code params} 把本次生效的参数原样回显 —— 调参调试时能立刻看出
 * "我传的 300 米到底生效没有"。
 */
public record HotspotResponse(
        int scannedTracks,
        int scannedStays,
        Params params,
        List<HotspotDto> hotspots
) {

    public record Params(double radiusM, int minVisits, OffsetDateTime from, OffsetDateTime to) {
    }
}
