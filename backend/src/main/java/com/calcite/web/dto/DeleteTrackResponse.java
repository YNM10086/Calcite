package com.calcite.web.dto;

/**
 * 删除成功后的响应。
 *
 * <p><b>为什么要把 {@code recyclePath} 返回给前端</b>：让用户当场就知道
 * "东西在哪、需要的话去哪找" —— 比事后去翻目录强得多。
 */
public record DeleteTrackResponse(
        Long trackId,
        String name,
        int deletedPointCount,
        /** 导出到回收站的文件路径 */
        String recyclePath
) {
}
