package com.calcite.service;

import com.calcite.domain.Track;
import com.calcite.domain.TrackPoint;
import com.calcite.repository.TrackPointRepository;
import com.calcite.repository.TrackRepository;
import com.calcite.service.importer.FormatDetector;
import com.calcite.service.importer.GeoLifeImporter;
import com.calcite.service.importer.GpxImporter;
import com.calcite.service.importer.Importer;
import com.calcite.service.importer.ParsedTrack;
import com.calcite.service.importer.RawPoint;
import com.calcite.web.dto.ImportResult;
import org.locationtech.jts.geom.Coordinate;
import org.locationtech.jts.geom.GeometryFactory;
import org.locationtech.jts.geom.LineString;
import org.locationtech.jts.geom.Point;
import org.locationtech.jts.geom.PrecisionModel;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * 导入编排：识别格式 → 解析 → 清洗 → 入库。
 *
 * <p>两个入口（网页上传单文件、目录批量）共用这一套流程。
 */
@Service
public class ImportService {

    /** WGS84。JTS 默认 SRID 是 0，必须显式指定，否则 PostGIS 会拒绝写入 */
    private static final int SRID = 4326;
    private static final GeometryFactory GEOMETRY_FACTORY =
            new GeometryFactory(new PrecisionModel(), SRID);
    /** 判定格式时只看开头这么多字节 */
    private static final int HEAD_BYTES = 4096;

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final TrackCleaner cleaner;
    private final GpxImporter gpxImporter;
    private final GeoLifeImporter geoLifeImporter;
    private final TransactionTemplate txTemplate;

    public ImportService(TrackRepository trackRepository,
                         TrackPointRepository trackPointRepository,
                         TrackCleaner cleaner,
                         GpxImporter gpxImporter,
                         GeoLifeImporter geoLifeImporter,
                         PlatformTransactionManager txManager) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.cleaner = cleaner;
        this.gpxImporter = gpxImporter;
        this.geoLifeImporter = geoLifeImporter;
        this.txTemplate = new TransactionTemplate(txManager);
    }

    /**
     * 从文件字节导入一条轨迹。
     *
     * @param fallbackName 文件里没有轨迹名时用它（通常传文件名去掉扩展名）
     */
    @Transactional
    public ImportResult importBytes(byte[] content, String fallbackName) {
        if (content == null || content.length == 0) {
            throw new IllegalArgumentException("上传的文件是空的");
        }

        String externalId = sha256Hex(content);
        Optional<Track> existing = trackRepository.findByExternalId(externalId);
        if (existing.isPresent()) {
            Track t = existing.get();
            return new ImportResult(t.getId(), t.getName(),
                    t.getPointCount() == null ? 0 : t.getPointCount(),
                    t.getDistanceM() == null ? 0 : t.getDistanceM(),
                    t.getDurationS() == null ? 0 : t.getDurationS(),
                    0, true, "这条轨迹已经导入过了");
        }

        Importer importer = pickImporter(content);
        ParsedTrack parsed;
        try {
            parsed = importer.parse(new ByteArrayInputStream(content));
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException(
                    "文件内容不是合法的 " + importer.format() + "：" + e.getMessage(), e);
        }

        String name = (parsed.name() == null || parsed.name().isBlank())
                ? (fallbackName == null || fallbackName.isBlank() ? "未命名轨迹" : fallbackName)
                : parsed.name();

        return persist(name, importer.format(), externalId, parsed.points());
    }

    /** 按内容选解析器 */
    private Importer pickImporter(byte[] content) {
        byte[] head = new byte[Math.min(HEAD_BYTES, content.length)];
        System.arraycopy(content, 0, head, 0, head.length);
        String format = FormatDetector.detect(head);
        return switch (format) {
            case "gpx" -> gpxImporter;
            case "geolife" -> geoLifeImporter;
            default -> throw new IllegalArgumentException(
                    "无法识别的文件格式（只支持 GPX 和 GeoLife .plt）");
        };
    }

    /** 清洗 + 入库，返回给前端的摘要 */
    private ImportResult persist(String name, String source, String externalId, List<RawPoint> raw) {
        CleanedTrack cleaned = cleaner.clean(raw);
        List<RawPoint> pts = cleaned.points();
        int n = pts.size();

        OffsetDateTime start = pts.get(0).recordedAt();
        OffsetDateTime end = pts.get(n - 1).recordedAt();

        Track track = new Track(name, source, externalId, start, end);
        track.setDistanceM(cleaned.distanceM());
        track.setDurationS(cleaned.durationS());
        track.setPointCount(n);
        track.setGeom(buildLineString(pts));
        Track saved = trackRepository.save(track);

        List<TrackPoint> entities = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            RawPoint p = pts.get(i);
            entities.add(new TrackPoint(
                    saved.getId(),
                    i,
                    p.recordedAt(),
                    p.elevationM(),
                    cleaned.speeds().get(i),
                    buildPoint(p),
                    cleaned.outliers().get(i)));
        }
        trackPointRepository.saveAll(entities);

        long outlierCount = cleaned.outliers().stream().filter(Boolean::booleanValue).count();
        return new ImportResult(saved.getId(), saved.getName(), n, cleaned.distanceM(),
                cleaned.durationS(), outlierCount, false, "导入成功");
    }

    private static LineString buildLineString(List<RawPoint> pts) {
        Coordinate[] coords = new Coordinate[pts.size()];
        for (int i = 0; i < pts.size(); i++) {
            // JTS 的 Coordinate 是 (x, y) = (经度, 纬度)，别写反
            coords[i] = new Coordinate(pts.get(i).lon(), pts.get(i).lat());
        }
        return GEOMETRY_FACTORY.createLineString(coords);
    }

    private static Point buildPoint(RawPoint p) {
        return GEOMETRY_FACTORY.createPoint(new Coordinate(p.lon(), p.lat()));
    }

    /**
     * 批量导入一个 GeoLife 数据目录。
     *
     * <p>每调用一次最多处理 {@code maxTracks} 条；因为幂等，重复调用会自动跳过已导入的、
     * 继续往后取 —— 脚本循环调用即可分批灌完全部数据。
     *
     * <p><b>故意不加 {@code @Transactional}</b>：本方法内部会调用同一个类的
     * {@link #importBytes}，而 Spring 的事务靠代理生效、类内部自调用不走代理。
     * 若外层标了事务，整批会退化成一个巨型事务 —— 一条坏数据把事务标记成
     * "只能回滚"之后，后面所有文件的保存都会失败，{@code catch} 也救不回来。
     * 所以这里改为**每个文件单独开一个事务**。
     */
    public GeoLifeImportResult importGeoLifeDirectory(Path root, int maxTracks,
                                                      List<String> allowedRoots) {
        if (root == null || !Files.isDirectory(root)) {
            throw new IllegalArgumentException("目录不存在：" + root);
        }
        if (!isUnderAllowedRoot(root, allowedRoots)) {
            throw new IllegalArgumentException("路径不在允许的导入目录内，允许：" + allowedRoots);
        }

        List<Path> pltFiles;
        try (var stream = Files.walk(root)) {
            pltFiles = stream.filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().toLowerCase().endsWith(".plt"))
                    .sorted()
                    .toList();
        } catch (IOException e) {
            throw new IllegalArgumentException("扫描目录失败：" + e.getMessage(), e);
        }

        int imported = 0;
        int skipped = 0;
        int failed = 0;
        int totalPoints = 0;
        long started = System.currentTimeMillis();

        for (Path file : pltFiles) {
            if (imported >= maxTracks) {
                skipped++;
                continue;
            }
            try {
                byte[] content = Files.readAllBytes(file);
                String fallback = file.getFileName().toString().replaceAll("(?i)\\.plt$", "");
                ImportResult r = txTemplate.execute(status -> importBytes(content, fallback));
                if (r == null || r.skippedDuplicate()) {
                    skipped++;
                } else {
                    imported++;
                    totalPoints += r.pointCount();
                }
            } catch (Exception e) {
                failed++; // 单条失败不中断整批
            }
        }

        return new GeoLifeImportResult(root.toString(), pltFiles.size(), imported, skipped, failed,
                totalPoints, System.currentTimeMillis() - started);
    }

    private static boolean isUnderAllowedRoot(Path path, List<String> allowedRoots) {
        if (allowedRoots == null || allowedRoots.isEmpty()) {
            return false;
        }
        Path real = path.toAbsolutePath().normalize();
        for (String r : allowedRoots) {
            if (r == null || r.isBlank()) {
                continue;
            }
            Path allowed = Path.of(r).toAbsolutePath().normalize();
            if (real.startsWith(allowed)) {
                return true;
            }
        }
        return false;
    }

    /** 文件内容的 SHA-256 十六进制（取前 32 位够用），用来判重 —— 改文件名也认得出来 */
    static String sha256Hex(byte[] content) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(content);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 16; i++) {
                sb.append(String.format("%02x", digest[i]));
            }
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException("算哈希失败", e);
        }
    }

    /** 批量导入的汇总结果 */
    public record GeoLifeImportResult(
            String path, int scanned, int imported, int skipped, int failed,
            int totalPoints, long elapsedMs) {
    }
}
