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
        // 改名时不排除自己，就会把"改成和现在一样的名字"误判成冲突
        //
        // ⚠️ 期望值的极性以【断言消息】和 isNameConflict 的契约（true = 会和别人撞名）为准：
        // "不算冲突 / 才可能是冲突"对应 false，"和别人同名才是冲突"对应 true。
        // 实施计划 Task 2 Step 1 里这一列的布尔字面量写反了（它同时与同一任务 Step 3 的实现、
        // 以及计划末尾对照表"改名不排除自己 → 会误报冲突"互相矛盾）。
        // 这里按契约修正，实测报错原文：改回自己原来的名字不算冲突 ==> expected: <true> but was: <false>
        assertEquals(false, TrackEditService.isNameConflict("资料一", "资料一", 3L, 3L),
                "改回自己原来的名字不算冲突");
        assertEquals(false, TrackEditService.isNameConflict("资料一", "资料二", 3L, 3L),
                "改成别的名字才可能是冲突");
        assertEquals(true, TrackEditService.isNameConflict("资料一", "资料一", 3L, 4L),
                "和别人同名才是冲突");
    }
}
