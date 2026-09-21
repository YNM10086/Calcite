package com.calcite.service;

import com.calcite.domain.Track;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.service.importer.GeoLifeImporter;
import com.calcite.service.importer.GpxImporter;
import com.calcite.web.dto.ImportResult;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ImportServiceTest {

    /** 造一个最小可用的 GPX（3 个点，向北匀速） */
    private static byte[] smallGpx() {
        StringBuilder sb = new StringBuilder("<?xml version='1.0' encoding='UTF-8'?><gpx><trk><trkseg>");
        for (int i = 0; i < 3; i++) {
            sb.append("<trkpt lat=\"").append(25.0 + i * 0.000027).append("\" lon=\"117.0\">")
              .append("<ele>30.0</ele>")
              .append("<time>2026-06-22T11:00:0").append(i).append("Z</time>")
              .append("</trkpt>");
        }
        return sb.append("</trkseg></trk></gpx>").toString().getBytes(StandardCharsets.UTF_8);
    }

    private ImportService newService(TrackRepository tracks, TrackPointRepository points) {
        return new ImportService(tracks, points,
                new TrackCleaner(8.0, 3.0),
                new GpxImporter(),
                new GeoLifeImporter(),
                // 这些测试只走单文件路径，批量导入用的事务模板用不到，给个 mock 就够
                mock(org.springframework.transaction.PlatformTransactionManager.class),
                // 三个新协作者一律用 mock。
                // ⚠️ 这里【故意不用真实实例】：以前 ImportService 里有个 6 参兼容构造器，
                // 它在生产类内部自己 new StayPointCache()/SimilarityCache() —— 那些实例和 Spring 容器里的
                // 不是同一个对象，走到那条路径就会出现"清缓存清的不是真缓存"（界面继续显示旧数据且不报错）。
                // 那个构造器已经删掉了，所以缺什么依赖就在这里补 mock，绝不回头去放松生产类。
                // 这 7 个用例只走 importBytes/解析路径，TrackEditService 的同名检测不会被触发。
                mock(TrackEditService.class),
                mock(StayPointCache.class),
                mock(SimilarityCache.class));
    }

    @Test
    void 导入新文件_保存轨迹和点() {
        TrackRepository tracks = mock(TrackRepository.class);
        TrackPointRepository points = mock(TrackPointRepository.class);
        when(tracks.findByExternalId(anyString())).thenReturn(Optional.empty());
        when(tracks.save(any(Track.class))).thenAnswer(inv -> inv.getArgument(0));

        ImportResult r = newService(tracks, points).importBytes(smallGpx(), "晨跑");

        assertEquals(3, r.pointCount());
        assertFalse(r.skippedDuplicate());
        assertEquals("导入成功", r.message());
        verify(tracks, times(1)).save(any(Track.class));
        verify(points, times(1)).saveAll(any());
    }

    @Test
    void 重复导入同一内容_不新建轨迹() {
        TrackRepository tracks = mock(TrackRepository.class);
        TrackPointRepository points = mock(TrackPointRepository.class);

        Track existing = new Track("老轨迹", "gpx", "x", null, null);
        when(tracks.findByExternalId(anyString())).thenReturn(Optional.of(existing));

        ImportResult r = newService(tracks, points).importBytes(smallGpx(), "晨跑");

        assertTrue(r.skippedDuplicate());
        assertEquals("这条轨迹已经导入过了", r.message());
        verify(tracks, never()).save(any(Track.class));
        verify(points, never()).saveAll(any());
    }

    @Test
    void 同一份内容两次调用_用同一个_externalId_查重() {
        TrackRepository tracks = mock(TrackRepository.class);
        TrackPointRepository points = mock(TrackPointRepository.class);
        when(tracks.findByExternalId(anyString())).thenReturn(Optional.empty());
        when(tracks.save(any(Track.class))).thenAnswer(inv -> inv.getArgument(0));

        ImportService svc = newService(tracks, points);
        svc.importBytes(smallGpx(), "a");
        svc.importBytes(smallGpx(), "b");

        // 两次都拿 externalId 去查过重（内容相同 → 哈希相同）
        verify(tracks, times(2)).findByExternalId(anyString());
    }

    @Test
    void 无法识别的格式抛异常() {
        TrackRepository tracks = mock(TrackRepository.class);
        TrackPointRepository points = mock(TrackPointRepository.class);
        ImportService svc = newService(tracks, points);

        IllegalArgumentException e = assertThrows(IllegalArgumentException.class,
                () -> svc.importBytes("这不是轨迹".getBytes(StandardCharsets.UTF_8), "x"));
        assertTrue(e.getMessage().contains("无法识别"), "错误信息应说明是格式问题：" + e.getMessage());
    }

    @Test
    void 空内容抛异常() {
        ImportService svc = newService(mock(TrackRepository.class), mock(TrackPointRepository.class));
        assertThrows(IllegalArgumentException.class, () -> svc.importBytes(new byte[0], "x"));
    }

    @Test
    void 名字缺失时用兜底名() {
        TrackRepository tracks = mock(TrackRepository.class);
        TrackPointRepository points = mock(TrackPointRepository.class);
        when(tracks.findByExternalId(anyString())).thenReturn(Optional.empty());
        when(tracks.save(any(Track.class))).thenAnswer(inv -> inv.getArgument(0));

        ImportResult r = newService(tracks, points)
                .importBytes(smallGpx(), "2026年6月22日户外跑步");
        assertEquals("2026年6月22日户外跑步", r.name());
    }

    @Test
    void 同一份内容哈希稳定() {
        assertEquals(ImportService.sha256Hex(smallGpx()), ImportService.sha256Hex(smallGpx()));
        assertEquals(32, ImportService.sha256Hex(smallGpx()).length());
    }
}
