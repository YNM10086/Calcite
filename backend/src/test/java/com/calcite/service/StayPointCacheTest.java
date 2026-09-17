package com.calcite.service;

import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

/**
 * {@link StayPointCache} 的单元测试。纯内存，不需要数据库。
 */
class StayPointCacheTest {

    private static StayPoint stay() {
        OffsetDateTime t = OffsetDateTime.parse("2008-10-23T09:50:00Z");
        return new StayPoint(0, 9, t, t.plusSeconds(300), 300, 116.3, 40.0, 20.0, 10);
    }

    @Test
    void 同一个trackId只计算一次() {
        StayPointCache cache = new StayPointCache();
        AtomicInteger calls = new AtomicInteger();
        for (int i = 0; i < 5; i++) {
            cache.get(7L, () -> {
                calls.incrementAndGet();
                return List.of(stay());
            });
        }
        assertEquals(1, calls.get(), "第二次开始应该直接命中缓存");
    }

    @Test
    void 不同trackId各算各的() {
        StayPointCache cache = new StayPointCache();
        AtomicInteger calls = new AtomicInteger();
        cache.get(1L, () -> { calls.incrementAndGet(); return List.of(stay()); });
        cache.get(2L, () -> { calls.incrementAndGet(); return List.of(stay()); });
        assertEquals(2, calls.get());
    }

    @Test
    void 返回的是缓存里同一个对象() {
        StayPointCache cache = new StayPointCache();
        List<StayPoint> a = cache.get(3L, () -> List.of(stay()));
        List<StayPoint> b = cache.get(3L, () -> List.of(stay()));
        assertSame(a, b, "应该拿到同一个列表实例（说明真的走了缓存）");
    }

    @Test
    void invalidate之后会重新计算() {
        /*
         * 这个方法当前没有生产代码调用 —— 它是为【将来】准备的：
         * 如果哪天加了"删除轨迹"或"重新导入覆盖同名轨迹"，那时必须调用它清理。
         * 现在先写好并测住，免得到时候忘了这个缓存的存在。
         */
        StayPointCache cache = new StayPointCache();
        AtomicInteger calls = new AtomicInteger();
        cache.get(9L, () -> { calls.incrementAndGet(); return List.of(stay()); });
        cache.invalidate(9L);
        cache.get(9L, () -> { calls.incrementAndGet(); return List.of(stay()); });
        assertEquals(2, calls.get(), "清理之后应该重算");
    }
}
