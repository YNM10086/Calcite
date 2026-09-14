package com.calcite.web;

import com.calcite.domain.Track;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.TrackDetail;
import com.calcite.web.dto.TrackPage;
import com.calcite.web.dto.TrackPointDto;
import com.calcite.web.dto.TrackSummary;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

/**
 * 轨迹查询接口（M1 第一个真正的业务接口）。
 *
 * <p>两个端点：
 * <ul>
 *   <li>{@code GET /api/tracks} —— 轨迹列表（不含坐标）</li>
 *   <li>{@code GET /api/tracks/{id}} —— 单条轨迹详情（含全部点的经纬度）</li>
 * </ul>
 *
 * <p>{@code @RequestMapping("/api/tracks")} 加在类上 = 这个类里所有接口的公共前缀。
 */
@RestController
@RequestMapping("/api/tracks")
public class TrackController {

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;

    // 构造器注入：两个 Repository 由 Spring 自动传入
    public TrackController(TrackRepository trackRepository,
                           TrackPointRepository trackPointRepository) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
    }

    /**
     * 查轨迹列表（支持按来源筛选 + 限制条数）。
     *
     * <p>为什么要限制条数：GeoLife 一个用户就有上百条轨迹，一次性全返回会让前端列表卡死。
     * 项目设计文档第 319 行本来就规划了「轨迹列表（分页）」，这里是把它补上。
     *
     * @param source 来源筛选，留空 = 全部（{@code geolife} / {@code gpx} / {@code sample}）
     * @param limit  最多返回多少条（默认 50，上限 500 —— 防止有人传个天文数字把库拖垮）
     */
    @GetMapping
    public TrackPage list(@RequestParam(required = false) String source,
                          @RequestParam(defaultValue = "50") int limit) {
        int size = Math.max(1, Math.min(limit, 500));
        Pageable page = PageRequest.of(0, size);
        boolean filtered = source != null && !source.isBlank();

        List<TrackSummary> items = (filtered
                ? trackRepository.findRecentBySource(source, page)
                : trackRepository.findRecent(page))
                .stream()
                .map(TrackSummary::from)
                .toList();

        long total = filtered ? trackRepository.countBySource(source) : trackRepository.count();
        return new TrackPage(total, items);
    }

    /**
     * 查单条轨迹 + 它的所有点。
     *
     * <p>{@code @PathVariable} 把 URL 里的 {id} 绑定到方法参数上。
     * 找不到时抛 404，而不是返回 null —— 这样前端能明确知道"没有这条轨迹"。
     */
    @GetMapping("/{id}")
    public TrackDetail detail(@PathVariable Long id) {
        Track track = trackRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "轨迹不存在: id=" + id));

        List<TrackPointDto> points = trackPointRepository.findByTrackIdOrderBySeqAsc(id)
                .stream()
                .map(TrackPointDto::from)
                .toList();

        return TrackDetail.from(track, points);
    }
}
