package com.calcite.service;

/**
 * 一个「有归属的停留点」—— 把 {@link StayPoint} 和它所属的 trackId 绑在一起。
 *
 * <p>为什么不让 {@code StayPoint} 直接带上 trackId：那样会让第一阶段的算法
 * 被迫知道"轨迹"这个概念。现在这样 {@code StayPointService} 完全不用改，
 * 归属信息在跨轨迹分析这一层才引入。
 *
 * @param trackId 这个停留点来自哪条轨迹
 * @param stay    第一阶段算出来的停留段
 */
public record TrackedStay(long trackId, StayPoint stay) {
}
