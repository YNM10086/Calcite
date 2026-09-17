package com.calcite.service;

import com.calcite.config.DensityProperties;
import com.calcite.repository.TrackPointRepository;
import com.calcite.web.dto.DensityCell;
import com.calcite.web.dto.DensityResponse;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

/**
 * 网格密度的编排层：校验参数 → 查 SQL → 组装响应。
 *
 * <p><b>参数校验与换算全部委托给 {@link DensityGrid}</b>（静态工具），
 * 这个类只负责"把它们串起来"。这样校验逻辑能脱离 Spring 和数据库单测。
 */
@Service
public class DensityService {

    /** 不传日期范围时用的兜底值：足够宽，等于不过滤 */
    private static final OffsetDateTime MIN_TIME =
            OffsetDateTime.of(1970, 1, 1, 0, 0, 0, 0, ZoneOffset.UTC);
    private static final OffsetDateTime MAX_TIME =
            OffsetDateTime.of(9999, 12, 31, 23, 59, 59, 0, ZoneOffset.UTC);

    private final TrackPointRepository trackPointRepository;
    private final DensityProperties props;

    public DensityService(TrackPointRepository trackPointRepository, DensityProperties props) {
        this.trackPointRepository = trackPointRepository;
        this.props = props;
    }

    /**
     * 查询视野内的网格密度。
     *
     * @param bboxRaw    "西经,南纬,东经,北纬"
     * @param cellSize   格边长（度），必须在配置的阶梯里
     * @param metric     tracks 或 points，空则 tracks
     * @param hourFrom   一天内时段的起点（北京时间），可空
     * @param hourTo     一天内时段的终点（北京时间），可空
     * @param from       日期范围起点，可空
     * @param to         日期范围终点，可空
     */
    public DensityResponse density(String bboxRaw, double cellSize, String metric,
                                   Integer hourFrom, Integer hourTo,
                                   OffsetDateTime from, OffsetDateTime to) {

        double[] ladder = props.ladderArray();
        DensityGrid.Bbox bbox = DensityGrid.parseBbox(bboxRaw);
        DensityGrid.requireKnownCellSize(cellSize, ladder);
        DensityGrid.requireHourRange(hourFrom, hourTo);
        String m = DensityGrid.requireMetric(metric);

        long estimated = DensityGrid.estimateCells(bbox, cellSize);
        if (estimated > props.getMaxCells()) {
            throw new IllegalArgumentException(
                    "视野内格子数约 " + estimated + " 个，超过上限 " + props.getMaxCells()
                            + "。请放大视野或换更粗的格子。");
        }

        int[] hours = DensityGrid.passThroughHourRange(hourFrom, hourTo);
        OffsetDateTime dFrom = from == null ? MIN_TIME : from;
        OffsetDateTime dTo = to == null ? MAX_TIME : to;

        List<Object[]> rows = trackPointRepository.aggregateDensity(
                bbox.west(), bbox.south(), bbox.east(), bbox.north(),
                cellSize, props.getTimeZone(), hours[0], hours[1], dFrom, dTo);

        List<DensityCell> cells = new ArrayList<>(rows.size());
        long totalPoints = 0;
        long maxTracks = 0;
        for (Object[] r : rows) {
            int nx = ((Number) r[0]).intValue();
            int ny = ((Number) r[1]).intValue();
            long points = ((Number) r[2]).longValue();
            long tracks = ((Number) r[3]).longValue();
            totalPoints += points;
            maxTracks = Math.max(maxTracks, tracks);
            cells.add(new DensityCell(
                    DensityGrid.indexToLon(nx, cellSize),
                    DensityGrid.indexToLat(ny, cellSize),
                    points, tracks,
                    "points".equals(m) ? points : tracks));
        }

        return new DensityResponse(
                new double[]{bbox.west(), bbox.south(), bbox.east(), bbox.north()},
                cellSize, m,
                new DensityResponse.Scanned(cells.size(), totalPoints, maxTracks),
                new DensityResponse.Params(m, hourFrom, hourTo,
                        from == null ? null : from.toString(),
                        to == null ? null : to.toString()),
                cells);
    }
}
