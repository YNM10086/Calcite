package com.calcite.web.dto;

import java.util.List;

/**
 * 停留点接口的响应。
 *
 * <p>为什么要 {@code count} 和 {@code stays} 两层：前端要显示「停留点（3 处）」
 * 这个标题，直接给数组的话还得自己取 {@code length}；而且这样和
 * {@link TrackPage} 的 {@code {total, items}} 风格一致。
 *
 * @param trackId 这条轨迹的 id
 * @param count   停留段数
 * @param stays   停留点列表（已按时间升序）
 */
public record StayPointResponse(Long trackId, int count, List<StayPointDto> stays) {
}
