package com.calcite.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * {@link TrackEditService} 里<b>纯逻辑</b>部分的单元测试。
 *
 * <p>带数据库的路径（真的改库、真的清缓存）由 {@code .tmp/verify-data-edit-api.py} 对拍验证 ——
 * 这里只测不碰 Spring、不碰库的那几个静态方法，保证 {@code mvn test} 依然不需要数据库。
 */
class TrackEditServiceTest {

    @Test
    void 名字去首尾空格() {
        assertEquals("第一次跑步", TrackEditService.validateName("  第一次跑步  ", 200));
    }

    @Test
    void 名字为空或全空白要拒绝() {
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName(null, 200));
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName("", 200));
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName("   ", 200));
    }

    @Test
    void 名字超长要拒绝() {
        String ok = "x".repeat(200);
        assertEquals(ok, TrackEditService.validateName(ok, 200));
        assertThrows(IllegalArgumentException.class,
                () -> TrackEditService.validateName("x".repeat(201), 200));
    }

    @Test
    void 名字里的换行要清掉() {
        // 换行会让前端的行内编辑、列表渲染都错位
        assertEquals("第一行 第二行", TrackEditService.validateName("第一行\n第二行", 200));
    }

    @Test
    void 同名判定_排除自己() {
        assertEquals(false, TrackEditService.isNameConflict(3L, 3L),
                "找到的『同名那条』就是我自己 → 不算冲突");
        assertEquals(true, TrackEditService.isNameConflict(3L, 4L),
                "找到的『同名那条』是别人的 → 冲突");
        assertEquals(false, TrackEditService.isNameConflict(3L, null),
                "库里没有同名 → 不冲突");
    }
}
