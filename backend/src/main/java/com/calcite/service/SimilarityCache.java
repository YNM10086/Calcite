package com.calcite.service;

import com.calcite.web.dto.SimilarityMatch;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

/**
 * 轨迹相似度缓存：{@code (trackId, toleranceM) → 该主线与全部轨迹的相似度结果}。
 *
 * <p><b>为什么需要它</b>：一次完整比对实测约 <b>2 秒</b>（双向、197 条候选）。
 * 缓存之后第二次点同一条主线瞬间返回。
 *
 * <p><b>为什么这个缓存永不失效</b>：结果是
 * {@code (trackId, toleranceM) → 库里所有轨迹的点} 的纯函数，
 * 而轨迹一旦导入就<b>不可变</b>（系统里没有"编辑轨迹""删除轨迹""覆盖同名轨迹"）。
 *
 * <p><b>⚠️ 缓存键必须带上 {@code toleranceM}</b> —— 这一点和 {@link StayPointCache}
 * <b>不一样</b>：停留点的参数是全局配置、不会逐次变；而相似度的容差是
 * <b>每次请求都可能不同</b>的。键里漏了容差，50 米算出的结果就会被 200 米的请求复用，
 * <b>返回错的结果</b>。
 *
 * <p><b>⚠️ 将来如果加了下面任何一项，必须清理缓存</b>：
 * <ul>
 *   <li>删除轨迹 / 重新导入覆盖同名轨迹</li>
 *   <li>导入新轨迹（那会让旧主线的候选集变化）—— 所以导入完后要整体清一次</li>
 * </ul>
 *
 * <p>{@code limit} <b>不进</b>缓存键：缓存里存全部匹配（不截断），limit 只在返回时截。
 */
@Component
public class SimilarityCache {

    /** 缓存键：主线 id + 容差。用 record 做键，equals/hashCode 自动按值比较 */
    private record Key(Long trackId, double toleranceM) {
    }

    private final Map<Key, List<SimilarityMatch>> cache = new ConcurrentHashMap<>();

    /**
     * 取某条主线在某个容差下的全部匹配；没有就算一次并缓存。
     *
     * @param trackId    主线轨迹 id
     * @param toleranceM 容差（米）—— <b>必须进键</b>
     * @param compute    真正的计算逻辑（由调用方提供，保持本类对算法无依赖）
     */
    public List<SimilarityMatch> get(Long trackId, double toleranceM,
                                     Supplier<List<SimilarityMatch>> compute) {
        return cache.computeIfAbsent(new Key(trackId, toleranceM), k -> compute.get());
    }

    /** 清理某条主线的全部容差缓存。当前生产代码没有调用 —— 见类注释里的两种情形。 */
    public void invalidate(Long trackId) {
        cache.keySet().removeIf(k -> k.trackId().equals(trackId));
    }

    /** 清空全部缓存（将来"导入新轨迹"之后应该调用它） */
    public void invalidateAll() {
        cache.clear();
    }

    /** 当前缓存了多少个 (主线, 容差) 组合（仅用于监控与测试） */
    public int size() {
        return cache.size();
    }
}
