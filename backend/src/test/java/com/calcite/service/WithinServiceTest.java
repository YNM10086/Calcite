package com.calcite.service;

import com.calcite.config.WithinProperties;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.WithinRequest;
import com.calcite.web.dto.WithinResponse;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

class WithinServiceTest {

    private static final ObjectMapper M = new ObjectMapper();

    private TrackRepository tracks;
    private TrackPointRepository points;
    private WithinService service;

    private static JsonNode rect() {
        try {
            return M.readTree("""
                {"type":"Polygon","coordinates":[[[116.30,39.90],[116.40,39.90],[116.40,40.00],[116.30,40.00],[116.30,39.90]]]}
                """);
        } catch (Exception e) { throw new RuntimeException(e); }
    }

    /**
     * 仓储返回的"区域准备"行：[valid, geojson, wkt]
     *
     * <p>⚠️ 必须写 {@code List.<Object[]>of(...)} 这个<b>显式类型见证</b>：只有一行时
     * {@code List.of(Object[])} 会选中定长重载 {@code of(E)}，把 E 解成 {@code Object}
     * （得到 {@code List<Object>}），而不是我们想要的 {@code List<Object[]>}，
     * javac 25 直接报"推断变量 E 具有不兼容的上界"。
     */
    private static List<Object[]> prepared() {
        return List.<Object[]>of(new Object[]{Boolean.TRUE,
                "{\"type\":\"Polygon\",\"coordinates\":[[[116.3,39.9],[116.4,39.9],[116.4,40],[116.3,40],[116.3,39.9]]]}",
                "POLYGON((116.3 39.9,116.4 39.9,116.4 40,116.3 40,116.3 39.9))"});
    }

    /** items 行：[id, name, source, pointCount, durationS, distanceM, start, end] */
    private static Object[] summary(long id, double dist) {
        return new Object[]{id, "t" + id, "geolife", 100, 600, dist,
                "2008-11-15T01:01:33Z", "2008-11-15T01:11:33Z"};
    }

    @BeforeEach
    void setUp() {
        tracks = mock(TrackRepository.class);
        points = mock(TrackPointRepository.class);
        WithinProperties props = new WithinProperties();
        service = new WithinService(tracks, points, props);

        when(tracks.prepareRegion(anyString())).thenReturn(prepared());
        when(tracks.prepareBufferRegion(anyString(), anyDouble())).thenReturn(prepared());
    }

    private WithinRequest req(Integer limit, OffsetDateTime from, OffsetDateTime to) {
        return new WithinRequest(rect(), null, from, to, limit);
    }

    @Test
    void 空结果返回全零统计且不再查点与统计() {
        when(tracks.findIdsIntersecting(anyString(), any(), any())).thenReturn(List.of());

        WithinResponse r = service.within(req(null, null, null));

        assertEquals(0, r.total());
        assertEquals(0, r.stats().trackCount());
        assertEquals(0, r.stats().pointCount());
        assertEquals(0.0, r.stats().distanceM());
        assertTrue(r.items().isEmpty());
        assertFalse(r.truncated());
        assertTrue(r.stats().sourceCounts().isEmpty());

        // ⭐ 关键：没有命中就不该再跑那条最贵的点统计（180~456 ms）
        verify(points, never()).countPointsInsideGrouped(anyString());
        verify(tracks, never()).aggregateWithinStats(any());
        verify(tracks, never()).findWithinSummariesByIds(any());
    }

    @Test
    void 按来源分组汇总出五个统计数字() {
        when(tracks.findIdsIntersecting(anyString(), any(), any())).thenReturn(List.of(1L, 2L, 3L));
        when(points.countPointsInsideGrouped(anyString()))
                .thenReturn(List.of(new Object[]{1L, 10L}, new Object[]{2L, 20L}));
        when(tracks.aggregateWithinStats(any())).thenReturn(List.<Object[]>of(
                new Object[]{"geolife", 2L, 3000.0, "2008-11-15T01:01:33Z", "2008-11-15T02:00:00Z"},
                new Object[]{"gpx", 1L, 500.0, "2008-10-01T00:00:00Z", "2008-10-01T00:10:00Z"}));
        when(tracks.findWithinSummariesByIds(any())).thenReturn(new ArrayList<>(List.of(
                summary(1L, 1500.0), summary(2L, 1500.0), summary(3L, 500.0))));

        WithinResponse r = service.within(req(null, null, null));

        assertEquals(3, r.total());
        assertEquals(3, r.stats().trackCount());
        assertEquals(30, r.stats().pointCount());
        assertEquals(3500.0, r.stats().distanceM());
        assertEquals(2L, r.stats().sourceCounts().get("geolife").longValue());
        assertEquals(1L, r.stats().sourceCounts().get("gpx").longValue());
        assertEquals("2008-10-01T00:00:00Z", r.stats().earliest());
        assertEquals("2008-11-15T02:00:00Z", r.stats().latest());
        assertEquals(3, r.items().size());
    }

    @Test
    void items按区域内点数降序再按id升序() {
        when(tracks.findIdsIntersecting(anyString(), any(), any())).thenReturn(List.of(9L, 3L, 7L));
        when(points.countPointsInsideGrouped(anyString())).thenReturn(List.of(
                new Object[]{9L, 5L}, new Object[]{3L, 5L}, new Object[]{7L, 1L}));
        when(tracks.aggregateWithinStats(any())).thenReturn(List.<Object[]>of(
                new Object[]{"geolife", 3L, 0.0, "2008-11-15T01:01:33Z", "2008-11-15T01:01:33Z"}));
        when(tracks.findWithinSummariesByIds(any())).thenReturn(new ArrayList<>(List.of(
                summary(9L, 1.0), summary(3L, 1.0), summary(7L, 1.0))));

        WithinResponse r = service.within(req(null, null, null));

        // 5 点并列时按 id 升序 → 3 在前；然后 9；最后 1 点的 7
        assertEquals(List.of(3L, 9L, 7L), r.items().stream().map(WithinResponse.Item::trackId).toList());
        assertEquals(List.of(5L, 5L, 1L), r.items().stream().map(WithinResponse.Item::insidePointCount).toList());
    }

    @Test
    void 没有区域内点数的轨迹算0而不是报错() {
        when(tracks.findIdsIntersecting(anyString(), any(), any())).thenReturn(List.of(1L));
        when(points.countPointsInsideGrouped(anyString())).thenReturn(List.of()); // 一条都没匹配到点
        when(tracks.aggregateWithinStats(any())).thenReturn(List.<Object[]>of(
                new Object[]{"geolife", 1L, 10.0, "2008-11-15T01:01:33Z", "2008-11-15T01:01:33Z"}));
        when(tracks.findWithinSummariesByIds(any()))
                .thenReturn(new ArrayList<>(List.<Object[]>of(summary(1L, 10.0))));

        WithinResponse r = service.within(req(null, null, null));

        assertEquals(0, r.stats().pointCount());
        assertEquals(0, r.items().get(0).insidePointCount());
    }

    @Test
    void limit截断生效且统计仍是全量() {
        when(tracks.findIdsIntersecting(anyString(), any(), any())).thenReturn(List.of(1L, 2L, 3L));
        when(points.countPointsInsideGrouped(anyString())).thenReturn(List.of(
                new Object[]{1L, 30L}, new Object[]{2L, 20L}, new Object[]{3L, 10L}));
        when(tracks.aggregateWithinStats(any())).thenReturn(List.<Object[]>of(
                new Object[]{"geolife", 3L, 60.0, "2008-11-15T01:01:33Z", "2008-11-15T01:01:33Z"}));
        when(tracks.findWithinSummariesByIds(any())).thenReturn(new ArrayList<>(List.of(
                summary(1L, 10.0), summary(2L, 20.0), summary(3L, 30.0))));

        WithinResponse r = service.within(req(2, null, null));

        assertEquals(2, r.items().size());
        assertTrue(r.truncated());
        assertEquals(3, r.total());          // total 是全量
        assertEquals(60, r.stats().pointCount()); // 统计也是全量
    }

    @Test
    void limit超范围要拒绝() {
        assertThrows(IllegalArgumentException.class, () -> service.within(req(0, null, null)));
        assertThrows(IllegalArgumentException.class, () -> service.within(req(501, null, null)));
    }

    @Test
    void from晚于to要拒绝() {
        assertThrows(IllegalArgumentException.class, () -> service.within(
                req(null, OffsetDateTime.parse("2009-01-01T00:00:00Z"), OffsetDateTime.parse("2008-01-01T00:00:00Z"))));
    }

    @Test
    void 时间窗为空时传无限宽边界() {
        when(tracks.findIdsIntersecting(anyString(), any(), any())).thenReturn(List.of());

        service.within(req(null, null, null));

        var cap = org.mockito.ArgumentCaptor.forClass(OffsetDateTime.class);
        verify(tracks).findIdsIntersecting(anyString(), cap.capture(), cap.capture());
        List<OffsetDateTime> vals = cap.getAllValues();
        assertEquals(2, vals.size());
        assertTrue(vals.get(0).getYear() < 2000, "from 应该是无限宽的下界，实际 " + vals.get(0));
        assertTrue(vals.get(1).getYear() > 2500, "to 应该是无限宽的上界，实际 " + vals.get(1));
    }

    @Test
    void 区域不合法要拒绝并说明原因() {
        when(tracks.prepareRegion(anyString())).thenReturn(List.<Object[]>of(
                new Object[]{Boolean.FALSE, "{}", "POLYGON((0 0,1 1,1 0,0 1,0 0))"}));

        var e = assertThrows(IllegalArgumentException.class, () -> service.within(req(null, null, null)));
        assertTrue(e.getMessage().contains("交叉") || e.getMessage().contains("面积"), e.getMessage());
    }

    @Test
    void Point走缓冲区那条准备查询() throws Exception {
        when(tracks.findIdsIntersecting(anyString(), any(), any())).thenReturn(List.of());
        var pointReq = new WithinRequest(
                M.readTree("{\"type\":\"Point\",\"coordinates\":[116.32,40.00]}"), 500.0, null, null, null);

        service.within(pointReq);

        verify(tracks).prepareBufferRegion(anyString(), eq(500.0));
        verify(tracks, never()).prepareRegion(anyString());
    }
}
