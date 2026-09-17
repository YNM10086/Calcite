package com.calcite.service;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

/**
 * 停留点缓存：{@code trackId → 该轨迹的停留点}。
 *
 * <p><b>为什么需要它</b>：导入数据后 {@code /api/analysis/hotspots} 从 0.9 秒涨到 4.5 秒，
 * 因为它每次请求都要把全部 28.6 万个点读进内存、逐条轨迹重算停留点。
 *
 * <p><b>为什么这个缓存永远不会失效</b>：停留点是
 * {@code trackId → 该轨迹的全部点} 的纯函数，而轨迹一旦导入就<b>不可变</b> ——
 * 系统里没有"编辑轨迹""删除轨迹""覆盖同名轨迹"这些功能。所以同一个 trackId 的结果恒定。
 *
 * <p><b>⚠️ 将来如果加了下面任何一项，必须调用 {@link #invalidate} 清理</b>：
 * <ul>
 *   <li>删除轨迹</li>
 *   <li>重新导入并覆盖同名轨迹</li>
 *   <li>停留点参数变成"每条轨迹可不同"</li>
 * </ul>
 *
 * <p><b>为什么不塞进 {@link HotspotService}</b>：那个类被特意设计成<b>无状态</b>
 * （参数走方法参数、测试里直接 {@code new} 就能跑），而且有 14 个单元测试建立在
 * 这个前提上。往里加一个 Map 会破坏那个设计。
 *
 * <p>用 {@link ConcurrentHashMap#computeIfAbsent} 保证并发下同一个 trackId 只算一次。
 */
@Component
public class StayPointCache {

    private final Map<Long, List<StayPoint>> cache = new ConcurrentHashMap<>();

    /**
     * 取某条轨迹的停留点；没有就调 {@code compute} 算一次并缓存。
     *
     * @param trackId 轨迹 id
     * @param compute 真正的计算逻辑（由调用方提供，保持本类对算法无依赖）
     */
    public List<StayPoint> get(Long trackId, Supplier<List<StayPoint>> compute) {
        return cache.computeIfAbsent(trackId, k -> compute.get());
    }

    /** 清理某条轨迹的缓存。当前生产代码没有调用 —— 见类注释里的三种情形。 */
    public void invalidate(Long trackId) {
        cache.remove(trackId);
    }

    /** 当前缓存了多少条轨迹（仅用于监控与测试） */
    public int size() {
        return cache.size();
    }
}
