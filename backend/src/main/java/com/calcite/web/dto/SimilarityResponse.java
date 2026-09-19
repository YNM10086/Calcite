package com.calcite.web.dto;

import java.util.List;

/**
 * 轨迹相似度接口的响应。
 *
 * <p>{@code compared} 是<b>实际比对了多少条</b>，和 {@code matches.size()} 不同 ——
 * 前者是分母，后者受 {@code limit} 截断。两个都给，用户才知道"库里还有多少条没列出来"。
 */
public record SimilarityResponse(
        Long trackId,
        String name,
        double toleranceM,
        int pointCount,
        long lengthM,
        /** 实际参与比对的轨迹条数（不含主线自己） */
        int compared,
        List<SimilarityMatch> matches
) {
}
