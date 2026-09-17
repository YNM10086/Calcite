package com.calcite.service;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 一个热点 —— 若干条轨迹在同一个地点留下的停留点的集合。
 *
 * <p>三个「热度口径」都保留，因为它们回答的问题不一样：
 * <ul>
 *   <li>{@code visitCount}    被停留过几次（同一个人来两次算两次）</li>
 *   <li>{@code trackCount}    有几条<b>不同</b>的轨迹来过（"多少人"的近似）</li>
 *   <li>{@code totalDurationS} 累计停留时长</li>
 * </ul>
 * 实测数据里这三个指标的排序<b>并不一致</b>：有个热点 visitCount=2 但 trackCount=1
 * （同一个人去了两次），按次数它排第 3，按轨迹数它和孤立点一样冷。
 *
 * @param centerLat      簇内所有停留点的重心纬度
 * @param centerLon      重心经度
 * @param visitCount     停留点个数
 * @param trackCount     去重后的轨迹条数
 * @param totalDurationS 累计停留秒数
 * @param radiusM        离重心最远的那个点多远（<b>真实散布</b>，不是画出来的圈）
 * @param firstVisit     最早一次停留的开始时刻
 * @param lastVisit      最晚一次停留的结束时刻
 * @param trackIds       涉及到的轨迹 id，升序
 */
public record Hotspot(
        double centerLat,
        double centerLon,
        int visitCount,
        int trackCount,
        int totalDurationS,
        double radiusM,
        OffsetDateTime firstVisit,
        OffsetDateTime lastVisit,
        List<Long> trackIds
) {
}
