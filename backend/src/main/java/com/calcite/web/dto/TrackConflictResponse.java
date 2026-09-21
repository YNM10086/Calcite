package com.calcite.web.dto;

/**
 * 同名冲突（HTTP 409）的响应体。
 *
 * <p><b>为什么要带上两边的点数</b>：用户做决定时需要知道"要覆盖的是个什么东西" ——
 * "已有『资料一』（456 个点），你上传的这份有 623 个点"比一句"已存在"有用得多。
 */
public record TrackConflictResponse(
        /** 冲突类型：{@code SAME_NAME} 或 {@code SAME_CONTENT} */
        String conflictType,
        Long existingTrackId,
        String existingName,
        Integer existingPointCount,
        /** 这次上传的文件的点数（解析失败时为 null） */
        Integer newPointCount,
        String message
) {
    public static TrackConflictResponse sameName(Long id, String name, Integer existing,
                                                 Integer incoming) {
        return new TrackConflictResponse("SAME_NAME", id, name, existing, incoming,
                "已有同名轨迹「" + name + "」（" + existing + " 个点）");
    }

    public static TrackConflictResponse sameContent(Long id, String name) {
        return new TrackConflictResponse("SAME_CONTENT", id, name, null, null,
                "这个文件的内容已经作为「" + name + "」存在了");
    }
}
