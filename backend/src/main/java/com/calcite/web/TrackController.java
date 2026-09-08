package com.calcite.web;

import com.calcite.domain.Track;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.TrackDetail;
import com.calcite.web.dto.TrackPointDto;
import com.calcite.web.dto.TrackSummary;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
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
     * 查全部轨迹。
     *
     * <p>{@code stream().map(TrackSummary::from)} 是"把每个实体转成 DTO"的写法，
     * {@code TrackSummary::from} 是方法引用，等价于 {@code t -> TrackSummary.from(t)}。
     */
    @GetMapping
    public List<TrackSummary> list() {
        return trackRepository.findAll()
                .stream()
                .map(TrackSummary::from)
                .toList();
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
