package com.calcite.web;

import com.calcite.domain.Track;
import com.calcite.domain.TrackPoint;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.service.DensityService;
import com.calcite.service.Hotspot;
import com.calcite.service.HotspotService;
import com.calcite.service.StayPoint;
import com.calcite.service.StayPointCache;
import com.calcite.service.StayPointService;
import com.calcite.service.TrackedStay;
import com.calcite.service.importer.RawPoint;
import com.calcite.web.dto.DensityResponse;
import com.calcite.web.dto.HotspotDto;
import com.calcite.web.dto.HotspotResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 跨轨迹的分析接口。
 *
 * <p>为什么不塞进 {@link TrackController}：那个类管的是<b>单条轨迹</b>
 * （列表 / 详情 / 停留点），而这里是<b>跨轨迹</b>的分析。
 * 职责不同，将来 {@code density}（网格密度）、{@code similarity}（相似度）
 * 这些接口也往这里加。
 */
@RestController
@RequestMapping("/api/analysis")
public class AnalysisController {

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final StayPointService stayPointService;
    private final HotspotService hotspotService;
    private final DensityService densityService;
    private final StayPointCache stayPointCache;
    private final double defaultRadiusM;
    private final int defaultMinVisits;

    public AnalysisController(TrackRepository trackRepository,
                              TrackPointRepository trackPointRepository,
                              StayPointService stayPointService,
                              HotspotService hotspotService,
                              DensityService densityService,
                              StayPointCache stayPointCache,
                              @Value("${calcite.hotspot.radius-m:200}") double defaultRadiusM,
                              @Value("${calcite.hotspot.min-visits:2}") int defaultMinVisits) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.stayPointService = stayPointService;
        this.hotspotService = hotspotService;
        this.densityService = densityService;
        this.stayPointCache = stayPointCache;
        this.defaultRadiusM = defaultRadiusM;
        this.defaultMinVisits = defaultMinVisits;
    }

    /**
     * 停留热点（跨轨迹聚类）。
     *
     * <p><b>数据流</b>：一次批量查出所有轨迹的点 → 按轨迹分组 →
     * 逐条调 {@link StayPointService#detect} → 组装成 {@link TrackedStay} →
     * 按时间窗筛 → {@link HotspotService#cluster}。
     *
     * <p><b>⚠️ 时间窗不是性能优化</b>：停留点必须先由完整轨迹算出来才知道起止时间，
     * 所以无论有没有 from/to，所有轨迹的点都要读一遍。时间窗只影响
     * "哪些停留点参与聚类"，不影响 IO 开销。
     *
     * <p>没有任何停留点 / 没有任何热点 → 200 + 空列表，<b>不是错误</b>。
     */
    @GetMapping("/hotspots")
    public HotspotResponse hotspots(
            @RequestParam(required = false) Double radiusM,
            @RequestParam(required = false) Integer minVisits,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to) {

        double radius = radiusM == null ? defaultRadiusM : radiusM;
        int minPts = minVisits == null ? defaultMinVisits : minVisits;

        // 参数非法 → 400，而不是让 HotspotService 抛 500。
        // 判据必须和 HotspotService.cluster 一致：用 !(radius > 0) 而不是 radius <= 0，
        // 否则 ?radiusM=NaN 会绕过 400（NaN <= 0 是 false，NaN 是无序的），
        // 落到 service 抛 IllegalArgumentException 被 Spring 映射成 500 —— 与设计要求的 400 不符。
        if (!(radius > 0) || !Double.isFinite(radius) || minPts < 1) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "参数非法：radiusM 必须是有限正数，minVisits 必须 >= 1");
        }

        List<Track> tracks = trackRepository.findAll();
        List<Long> trackIds = tracks.stream().map(Track::getId).toList();

        List<TrackedStay> stays = new ArrayList<>();
        if (!trackIds.isEmpty()) {
            // 一次批量查询，不是逐条查
            Map<Long, List<RawPoint>> byTrack = new LinkedHashMap<>();
            for (TrackPoint p : trackPointRepository.findAllByTrackIds(trackIds)) {
                byTrack.computeIfAbsent(p.getTrackId(), k -> new ArrayList<>())
                        .add(new RawPoint(
                                p.getGeom().getY(),   // JTS 的 getY 是纬度
                                p.getGeom().getX(),   // getX 是经度，别写反
                                p.getElevationM(),
                                p.getRecordedAt()));
            }

            for (Map.Entry<Long, List<RawPoint>> e : byTrack.entrySet()) {
                Long trackId = e.getKey();
                List<RawPoint> points = e.getValue();
                // 走缓存：轨迹导入后不再变，所以同一个 trackId 的结果恒定，缓存永不失效
                for (StayPoint s : stayPointCache.get(trackId,
                        () -> stayPointService.detect(points))) {
                    stays.add(new TrackedStay(trackId, s));
                }
            }
        }

        // 时间窗：只看 begin 在 from 之后、end 在 to 之前的停留
        List<TrackedStay> filtered = stays.stream()
                .filter(ts -> from == null || !ts.stay().startTime().isBefore(from))
                .filter(ts -> to == null || !ts.stay().endTime().isAfter(to))
                .toList();

        List<Hotspot> clusters = hotspotService.cluster(filtered, radius, minPts);

        List<HotspotDto> dtos = new ArrayList<>(clusters.size());
        for (int i = 0; i < clusters.size(); i++) {
            dtos.add(HotspotDto.of(i + 1, clusters.get(i)));
        }

        return new HotspotResponse(
                tracks.size(),
                stays.size(),
                new HotspotResponse.Params(radius, minPts, from, to),
                dtos);
    }

    /**
     * 网格密度（M2 第三阶段）：按固定边长方格统计轨迹点密度。
     *
     * <p>和 {@code /hotspots} 的分工：那个吃<b>停留点</b>（264 个，回答"哪里总有人停"），
     * 这个吃<b>原始轨迹点</b>（28.6 万个，回答"哪些路段总有人经过"）。
     */
    @GetMapping("/density")
    public DensityResponse density(
            @RequestParam String bbox,
            @RequestParam double cellSize,
            @RequestParam(required = false) String metric,
            @RequestParam(required = false) Integer hourFrom,
            @RequestParam(required = false) Integer hourTo,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to) {

        try {
            return densityService.density(bbox, cellSize, metric, hourFrom, hourTo, from, to);
        } catch (IllegalArgumentException e) {
            // 参数问题一律 400，并把原因原样告诉调用方（这些错误都是给人看的）
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        }
    }
}
