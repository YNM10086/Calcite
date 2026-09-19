package com.calcite.service;

import com.calcite.web.dto.SimilarityMatch;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

/** {@link SimilarityCache} 的单元测试。纯内存，不需要数据库。 */
class SimilarityCacheTest {

    private static List<SimilarityMatch> sample() {
        return List.of(new SimilarityMatch(39L, "20081203151206", "geolife",
                91.1, 98.6, 91.1, 279, 3611, "2008-12-03T15:12:06Z", 19));
    }

    @Test
    void 同一个trackId和容差只算一次() {
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        for (int i = 0; i < 5; i++) {
            cache.get(20L, 50.0, () -> { calls.incrementAndGet(); return sample(); });
        }
        assertEquals(1, calls.get(), "第二次开始应该命中缓存");
    }

    /**
     * 这条是本任务存在的理由：容差是**每次请求都可能不同**的参数，
     * 缓存键漏了它就会返回错的结果（50 米算出的结果被 200 米的请求复用）。
     * <p>注意这和停留点缓存<b>不一样</b> —— 那个的参数是全局配置、不会逐次变。
     */
    @Test
    void 容差不进缓存键就会返回错结果_所以必须分开缓存() {
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        List<SimilarityMatch> a = cache.get(20L, 50.0,
                () -> { calls.incrementAndGet(); return sample(); });
        List<SimilarityMatch> b = cache.get(20L, 200.0,
                () -> { calls.incrementAndGet(); return List.of(); });
        assertEquals(2, calls.get(), "不同容差必须是两次独立的计算");
        assertNotSame(a, b);
        assertEquals(1, a.size());
        assertEquals(0, b.size());
    }

    @Test
    void 不同trackId各算各的() {
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        cache.get(1L, 50.0, () -> { calls.incrementAndGet(); return sample(); });
        cache.get(2L, 50.0, () -> { calls.incrementAndGet(); return sample(); });
        assertEquals(2, calls.get());
    }

    @Test
    void 同一键返回同一个对象实例() {
        SimilarityCache cache = new SimilarityCache();
        List<SimilarityMatch> a = cache.get(3L, 50.0, SimilarityCacheTest::sample);
        List<SimilarityMatch> b = cache.get(3L, 50.0, SimilarityCacheTest::sample);
        assertSame(a, b, "应该拿到同一个实例（说明真的走了缓存）");
    }

    @Test
    void 容差用浮点做键也能命中_不会因为精度漏缓存() {
        // 5.0 和 5.00 是同一个 double，但 0.1+0.2 != 0.3 这类问题要防住
        SimilarityCache cache = new SimilarityCache();
        AtomicInteger calls = new AtomicInteger();
        cache.get(7L, 0.1 + 0.2, () -> { calls.incrementAndGet(); return sample(); });
        cache.get(7L, 0.30000000000000004, () -> { calls.incrementAndGet(); return sample(); });
        assertEquals(1, calls.get(), "相等的 double 应该命中同一个键");
    }
}
