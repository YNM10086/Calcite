package com.calcite.web.dto;

/**
 * 一条"和主线相似"的轨迹。
 *
 * <p><b>为什么两个方向都返回</b>：相似度取的是两者的最小值，
 * 只给一个数会让人不知道它怎么来的。而且"我的点 100% 在你身上、你的点只有 35% 在我身上"
 * 这个信息本身有用（说明我只是你的一小段）。
 */
public record SimilarityMatch(
        Long trackId,
        String name,
        String source,
        /** 主线的点有多少落在它附近（0~100） */
        double forwardPct,
        /** 它的点有多少落在主线附近（0~100） */
        double reversePct,
        /** = min(forwardPct, reversePct) */
        double similarity,
        int pointCount,
        long lengthM,
        /** 它的开始时间（ISO-8601 UTC 字符串，例如 2008-12-03T15:12:06Z） */
        String startTime,
        /** 和主线相差几天 */
        long daysAway
) {
}
