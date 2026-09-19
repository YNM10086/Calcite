package com.calcite.service;

import com.calcite.config.SimilarityProperties;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.web.dto.SimilarityMatch;
import com.calcite.web.dto.SimilarityResponse;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 轨迹相似度的编排层：校验参数 → 查基线 → 查双向重合度 → 补元数据 → 截断。
 *
 * <p>参数校验与数学全部委托给 {@link SimilarityMath}（静态工具），
 * 这个类只负责"把它们串起来"。
 */
@Service
public class SimilarityService {

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final SimilarityCache cache;
    private final SimilarityProperties props;

    public SimilarityService(TrackRepository trackRepository,
                             TrackPointRepository trackPointRepository,
                             SimilarityCache cache,
                             SimilarityProperties props) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.cache = cache;
        this.props = props;
    }

    /**
     * 查询和某条主线相似的全部轨迹。
     *
     * @param trackId    主线轨迹 id
     * @param toleranceM 容差（米），null 用默认值
     * @param limit      最多返回几条，null 用默认值
     */
    public SimilarityResponse similarity(Long trackId, Double toleranceM, Integer limit) {
        if (trackId == null) {
            throw new IllegalArgumentException("缺少 trackId 参数");
        }
        double tol = toleranceM == null ? props.getDefaultToleranceM() : toleranceM;
        int lim = limit == null ? props.getDefaultLimit() : limit;

        SimilarityMath.requireTolerance(tol, props.getMinToleranceM(), props.getMaxToleranceM());
        SimilarityMath.requireLimit(lim, props.getMaxLimit());

        // --- 主线的元数据（不存在就是 404）---
        List<Object[]> metaRows = trackRepository.findBaselineMeta(trackId);
        if (metaRows.isEmpty()) {
            throw new TrackNotFoundException(trackId);
        }
        Object[] meta = metaRows.get(0);
        String name = (String) meta[0];
        int pointCount = meta[2] == null ? 0 : ((Number) meta[2]).intValue();
        // native query 里 start_time 是 to_char 出来的 ISO 字符串，这里解析回 OffsetDateTime，
        // 供 daysBetween 使用（见 TrackRepository.findBaselineMeta 的注释）
        String baselineStartIso = (String) meta[3];
        SimilarityMath.requirePointCount(pointCount);

        // --- 几何统计：纬度范围（算 eps 用）+ 长度（米）---
        List<Object[]> geoRows = trackRepository.findBaselineGeometryStats(trackId);
        Object[] geo = geoRows.get(0);
        double latMin = ((Number) geo[0]).doubleValue();
        double latMax = ((Number) geo[1]).doubleValue();
        long lengthM = Math.round(((Number) geo[2]).doubleValue());
        double latMaxAbs = Math.max(Math.abs(latMin), Math.abs(latMax));

        // eps 按主线实际纬度算（不能用一个固定常数 —— 见 SimilarityMath 的注释）
        double eps = SimilarityMath.epsDegrees(tol, latMaxAbs);

        OffsetDateTime baselineStart = baselineStartIso == null
                ? null : OffsetDateTime.parse(baselineStartIso);

        // --- 走缓存：缓存里存【全部】匹配（不截断），limit 只在返回时截 ---
        List<SimilarityMatch> all = cache.get(trackId, tol, () -> compute(trackId, tol, eps, baselineStart));

        List<SimilarityMatch> page = all.size() > lim ? all.subList(0, lim) : all;

        return new SimilarityResponse(trackId, name, tol, pointCount, lengthM, all.size(), page);
    }

    /** 真正算一次：查 SQL → 补元数据 → 组装 → 排序。结果<b>不截断</b>。 */
    private List<SimilarityMatch> compute(Long trackId, double tol, double eps,
                                          OffsetDateTime baselineStart) {
        List<Object[]> rows = trackPointRepository.findSimilarityScores(trackId, tol, eps);
        if (rows.isEmpty()) {
            return List.of();
        }

        // 收集 id，一次批量取元数据（不要逐条查）
        List<Long> ids = new ArrayList<>(rows.size());
        for (Object[] r : rows) {
            ids.add(((Number) r[0]).longValue());
        }
        Map<Long, Object[]> metaById = new HashMap<>();
        for (Object[] m : trackRepository.findSummariesByIds(ids)) {
            metaById.put(((Number) m[0]).longValue(), m);
        }

        List<SimilarityMatch> out = new ArrayList<>(rows.size());
        for (Object[] r : rows) {
            long id = ((Number) r[0]).longValue();
            long fwdHits = ((Number) r[1]).longValue();
            long fwdTotal = ((Number) r[2]).longValue();
            long revHits = ((Number) r[3]).longValue();
            long revTotal = ((Number) r[4]).longValue();

            double fwdPct = SimilarityMath.pct(fwdHits, fwdTotal);
            double revPct = SimilarityMath.pct(revHits, revTotal);
            double sim = SimilarityMath.similarity(fwdPct, revPct);

            Object[] m = metaById.get(id);
            String name = m == null ? ("track-" + id) : (String) m[1];
            String source = m == null ? null : (String) m[2];
            int pc = (m == null || m[3] == null) ? 0 : ((Number) m[3]).intValue();
            long lenM = (m == null || m[4] == null) ? 0L : Math.round(((Number) m[4]).doubleValue());
            String stIso = m == null ? null : (String) m[5];

            // 日期差用 ISO 字符串解析回来，避免 timestamptz 的类型映射歧义
            long daysAway = 0L;
            if (stIso != null && baselineStart != null) {
                daysAway = SimilarityMath.daysBetween(baselineStart, OffsetDateTime.parse(stIso));
            }

            out.add(new SimilarityMatch(id, name, source, fwdPct, revPct, sim, pc, lenM,
                    stIso, daysAway));
        }

        // 按相似度倒序；相同则按 id 升序，保证结果稳定可复现
        out.sort(Comparator.comparingDouble(SimilarityMatch::similarity).reversed()
                .thenComparing(SimilarityMatch::trackId));
        return out;
    }

    /** 主线不存在时抛这个 —— 控制器会映射成 404 */
    public static class TrackNotFoundException extends RuntimeException {
        public TrackNotFoundException(Long trackId) {
            super("轨迹不存在：" + trackId);
        }
    }
}
