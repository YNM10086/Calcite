package com.calcite.service;

import com.calcite.config.DataProperties;
import com.calcite.domain.Track;
import com.calcite.domain.TrackPoint;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.DeleteTrackResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 数据管理的编排层：改名 / 删除 / 同名检测。
 *
 * <p><b>⚠️ 这个类兑现了两处欠账</b>：{@link StayPointCache} 和 {@link SimilarityCache}
 * 的 javadoc 里都写着「将来加了"删除轨迹 / 重新导入覆盖同名轨迹"，<b>必须调用 invalidate 清理</b>」。
 * 这里就是那些调用点。
 */
@Service
public class TrackEditService {

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final TrackExporter exporter;
    private final StayPointCache stayPointCache;
    private final SimilarityCache similarityCache;
    private final DataProperties props;

    public TrackEditService(TrackRepository trackRepository,
                            TrackPointRepository trackPointRepository,
                            TrackExporter exporter,
                            StayPointCache stayPointCache,
                            SimilarityCache similarityCache,
                            DataProperties props) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.exporter = exporter;
        this.stayPointCache = stayPointCache;
        this.similarityCache = similarityCache;
        this.props = props;
    }

    // ------------------------------------------------------------ 纯逻辑（可无库单测）

    /**
     * 校验并规整轨迹名（<b>纯静态</b>）。
     *
     * <p>换行必须清掉 —— 它会同时毁掉前端的行内编辑和列表渲染。
     */
    public static String validateName(String raw, int maxLength) {
        if (raw == null) {
            throw new IllegalArgumentException("名字不能为空");
        }
        String s = raw.replaceAll("[\\r\\n\\t]+", " ").trim();
        if (s.isEmpty()) {
            throw new IllegalArgumentException("名字不能为空");
        }
        if (s.length() > maxLength) {
            throw new IllegalArgumentException("名字最长 " + maxLength + " 个字符，收到 " + s.length());
        }
        return s;
    }

    /**
     * 判断"改成 newName"会不会和别的轨迹重名（<b>纯静态</b>）。
     *
     * <p>{@code excludeTrackId} 是<b>必须的</b>：改名时要排除自己，
     * 否则"把名字改成和现在一样"会被误判成冲突。
     *
     * @param currentName   被改的那条现在的名字
     * @param newName       想改成的新名字
     * @param currentId     被改的那条的 id
     * @param otherTrackId  库里另一条同名轨迹的 id（没有同名就传 null）
     * @return true = 会和别人撞名
     */
    public static boolean isNameConflict(String currentName, String newName,
                                         Long currentId, Long otherTrackId) {
        if (otherTrackId == null) {
            return false;
        }
        return !otherTrackId.equals(currentId);
    }

    // ------------------------------------------------------------ 改名

    /**
     * 改名。
     *
     * <p><b>⚠️ 为什么改名也要清相似度缓存</b>：看起来"只是改个显示名、数据一点没变"，
     * 但 {@code SimilarityMatch} 里<b>带了 name</b> —— 不清的话，
     * 把「资料一」改名成「第一次跑步」，再去点别的主线的相似度，列表里还是写着「资料一」。
     *
     * <p>停留点缓存<b>不用清</b>：它只依赖轨迹的点，改名不影响。
     */
    @Transactional
    public String rename(Long id, String newName) {
        Track track = trackRepository.findById(id)
                .orElseThrow(() -> new TrackNotFoundException(id));
        String name = validateName(newName, props.getMaxNameLength());
        track.setName(name);
        trackRepository.save(track);

        similarityCache.invalidateAll();       // ← 因为 SimilarityMatch 里带 name
        return name;
    }

    // ------------------------------------------------------------ 删除

    /**
     * 删除一条轨迹。
     *
     * <p><b>⚠️ 顺序不能变</b>：
     * <ol>
     *   <li>查存在（不存在 → 404）</li>
     *   <li><b>先导出到回收站</b> —— <b>失败就抛异常中止，绝不执行删除</b></li>
     *   <li>删 track（它的点由 FK {@code ON DELETE CASCADE} 自动删）</li>
     *   <li>清缓存</li>
     * </ol>
     *
     * <p><b>为什么第 ② 步必须是 fail-safe</b>：如果是"尽力导出、失败也照删"，
     * 那这个保险就是<b>假的</b> —— 用户以为有回收站，结果某次磁盘满了就静默没了。
     */
    @Transactional
    public DeleteTrackResponse delete(Long id) {
        Track track = trackRepository.findById(id)
                .orElseThrow(() -> new TrackNotFoundException(id));

        List<TrackPoint> points = trackPointRepository.findByTrackIdOrderBySeqAsc(id);
        List<TrackExporter.Point3D> pts = new ArrayList<>(points.size());
        for (TrackPoint p : points) {
            pts.add(new TrackExporter.Point3D(
                    p.getGeom().getX(), p.getGeom().getY(),
                    p.getElevationM() == null ? 0.0 : p.getElevationM(),
                    p.getRecordedAt()));
        }

        int pointCount = pts.size();
        String geojson = TrackExporter.buildGeoJson(id, track.getName(), track.getSource(),
                track.getExternalId(), track.getStartTime(), track.getEndTime(),
                pointCount, track.getDistanceM(), pts);

        Path saved;
        try {
            saved = exporter.exportToFile(geojson, track.getName(), pointCount, OffsetDateTime.now());
        } catch (IOException e) {
            // ⚠️ 导出失败 → 绝不删除。宁可删不掉，也不要"删了没备份"。
            throw new RecycleExportFailedException(
                    "导出到回收站失败，未执行删除：" + e.getMessage(), e);
        }

        trackRepository.delete(track);          // 点由 FK CASCADE 自动删
        stayPointCache.invalidate(id);
        similarityCache.invalidateAll();        // 别的主线的结果里可能把它算进去了

        return new DeleteTrackResponse(id, track.getName(), pointCount, saved.toString());
    }

    // ------------------------------------------------------------ 同名检测

    /**
     * 库里有没有另一条同名轨迹（没有就返回 empty）。
     *
     * <p>用派生查询 {@code findFirstByName} 而不是"把前 500 条拉回来在内存里筛" ——
     * 后者只看了最新的 500 条，是有边界 bug 的写法。
     */
    public java.util.Optional<Long> findNameConflict(String name, Long excludeTrackId) {
        return trackRepository.findFirstByName(name)
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId);
    }

    // ------------------------------------------------------------ 异常

    /** 轨迹不存在 → 控制器映射成 404 */
    public static class TrackNotFoundException extends RuntimeException {
        public TrackNotFoundException(Long id) {
            super("轨迹不存在：" + id);
        }
    }

    /** 导出回收站失败 → 控制器映射成 500，且<b>轨迹原样保留</b> */
    public static class RecycleExportFailedException extends RuntimeException {
        public RecycleExportFailedException(String msg, Throwable cause) {
            super(msg, cause);
        }
    }
}
