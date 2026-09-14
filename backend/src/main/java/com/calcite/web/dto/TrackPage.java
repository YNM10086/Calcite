package com.calcite.web.dto;

import java.util.List;

/**
 * 轨迹列表的一页。
 *
 * <p>{@code total} 是**符合条件的总数**，不是本页条数 —— 前端要显示
 * "共 171 条，显示前 50 条"这种信息，光有 items 是不够的。
 *
 * @param total 符合条件的轨迹总数
 * @param items 本页的轨迹摘要（最多 limit 条）
 */
public record TrackPage(long total, List<TrackSummary> items) {
}
