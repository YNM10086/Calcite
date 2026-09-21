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
import com.calcite.web.dto.TrackConflictResponse;
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
 * <p>三个入口（网页上传单文件、目录批量、以及上传时的"新增 / 替换"两种模式）共用这一套流程，
 * 所以解析（{@link #parse}）、判重（{@link #skipped}）、落库（{@link #persist}）、
 * 写点（{@link #savePoints}）都抽成了私有方法 —— <b>不复制粘贴第二份</b>。
 */
@Service
public class ImportService {

    /** WGS84。JTS 默认 SRID 是 0，必须显式指定，否则 PostGIS 会拒绝写入 */
    private static final int SRID = 4326;
    private static final GeometryFactory GEOMETRY_FACTORY =
            new GeometryFactory(new PrecisionModel(), SRID);
    /** 结果里最多带回几个失败样例（够定位问题就行，不用把几万条错误全塞进响应） */
    private static final int MAX_ERROR_SAMPLES = 5;
    /** 判定格式时只看开头这么多字节 */
    private static final int HEAD_BYTES = 4096;
    private static final org.slf4j.Logger log =
            org.slf4j.LoggerFactory.getLogger(ImportService.class);

    private final TrackRepository trackRepository;
    private final TrackPointRepository trackPointRepository;
    private final TrackCleaner cleaner;
    private final GpxImporter gpxImporter;
    private final GeoLifeImporter geoLifeImporter;
    private final TransactionTemplate txTemplate;
    /** 同名检测（"这个名字是不是已经被别人占了"） */
    private final TrackEditService trackEditService;
    /** 替换某条轨迹后要清它自己的停留点缓存 */
    private final StayPointCache stayPointCache;
    /**
     * 相似度缓存。<b>任何"让库里的轨迹集合或某条轨迹的几何发生变化"的操作都会让它整体失效</b>：
     * <ul>
     *   <li><b>替换</b>一条轨迹 → 别的轨迹与它的匹配结果变了 → 全清（见 {@link #replaceInPlace}）</li>
     *   <li><b>新增</b>一条轨迹 → 所有主线的候选集都多了一条
     *       （主线 20 原来是"和 197 条比过"，加一条就该是 198 条）→ 同样必须全清</li>
     * </ul>
     *
     * <p>新增那一路的清理点<b>放在 {@link #persist} 里</b>（唯一的"新增入库"漏斗），
     * 而不是分别写在 {@code importUpload} 与 {@code importBytes} 两处 —— 后者容易只改一处，
     * 将来再加导入入口也会自动覆盖。
     *
     * <p><b>{@link StayPointCache} 则不需要为"新增"做任何事</b>：新轨迹在它里面本来就没有条目，
     * 下次请求自然算出来。
     */
    private final SimilarityCache similarityCache;

    /**
     * 唯一的构造器（Spring 注入；只有一个构造器时 Spring 会自动用它，不必标 {@code @Autowired}）。
     *
     * <p><b>⚠️ 为什么本类【只允许存在这一个】构造器</b>：
     * 这里曾经有一个"6 参兼容构造器"（为了不改单测而存在），它在类<b>内部</b>自己
     * {@code new StayPointCache()} / {@code new SimilarityCache()} / {@code new TrackEditService(...)}
     * —— 那几个实例和 Spring 容器里管理的<b>根本不是同一个对象</b>。
     * 后果非常隐蔽：一旦有代码路径走到那个构造器，就会"<b>清了缓存，但清的不是真的那个</b>"，
     * 界面继续显示已经被删掉/被替换掉的旧数据，<b>而且不报任何错、日志里也没有痕迹</b>，
     * 只能靠肉眼发现数据不对。所以它不是一个"方便测试"的小技巧，而是一颗<b>静默的数据正确性地雷</b>。
     *
     * <p>正确做法就是现在这样：<b>依赖全部从外面传进来</b> ——
     * 生产由容器注入真 Bean，测试注入 mock。
     * 单测需要新的依赖时，<b>改单测</b>（{@code ImportServiceTest} 就是这么改的），
     * 而不是在生产类里留一个自己拼依赖的后门。
     */
    public ImportService(TrackRepository trackRepository,
                         TrackPointRepository trackPointRepository,
                         TrackCleaner cleaner,
                         GpxImporter gpxImporter,
                         GeoLifeImporter geoLifeImporter,
                         PlatformTransactionManager txManager,
                         TrackEditService trackEditService,
                         StayPointCache stayPointCache,
                         SimilarityCache similarityCache) {
        this.trackRepository = trackRepository;
        this.trackPointRepository = trackPointRepository;
        this.cleaner = cleaner;
        this.gpxImporter = gpxImporter;
        this.geoLifeImporter = geoLifeImporter;
        this.txTemplate = new TransactionTemplate(txManager);
        this.trackEditService = trackEditService;
        this.stayPointCache = stayPointCache;
        this.similarityCache = similarityCache;
    }

    /**
     * 从文件字节导入一条轨迹。
     *
     * <p>这是"只新增"的入口（批量导入 GeoLife 目录也走它）：内容已存在就跳过，行为与以前完全一致。
     * 网页上传走的是下面那个能选"替换"的 {@link #importUpload} 重载。
     *
     * @param fallbackName 文件里没有轨迹名时用它（通常传文件名去掉扩展名）
     */
    @Transactional
    public ImportResult importBytes(byte[] content, String fallbackName) {
        requireNotEmpty(content);

        String externalId = sha256Hex(content);
        Optional<Track> existing = trackRepository.findByExternalId(externalId);
        if (existing.isPresent()) {
            return skipped(existing.get());
        }

        Parsed parsed = parse(content, fallbackName);
        return persist(parsed.name(), parsed.format(), externalId, parsed.points());
    }

    /**
     * 上传导入（扩展版）：支持"新增"与"替换"两种模式，并做同名检测。
     *
     * <p><b>三种结果</b>：
     * <ol>
     *   <li>内容哈希已存在 → <b>跳过</b>（幂等，原有行为不变）
     *   <li>哈希是新的、但<b>名字已存在</b> → 抛 {@link TrackConflictException}（409，SAME_NAME）
     *   <li>{@code mode=replace} 且新内容的哈希<b>已属于另一条轨迹</b>
     *       → 抛 {@link TrackConflictException}（409，SAME_CONTENT）</li>
     * </ol>
     *
     * <p><b>⚠️ 第 ③ 条是自查时发现的边界</b>：先导入「资料一」（hash A），
     * 再拿同一个文件去"替换"「资料二」→ 新的 {@code external_id} 也是 A，
     * 但 A 已经是「资料一」的 → 撞唯一约束 → <b>500</b>。
     * 正确行为是<b>再返回一次 409</b>，说清"这份内容已经在库里了"。
     *
     * <p><b>⚠️ 为什么替换模式下【不查】同名</b>：重名在设计上就是允许的（用户可以故意留两个同名版本），
     * 替换时用户已经明确指定了"替换哪一条"，此时再拦一次同名只会让人没法操作。
     * （替换本身<b>不改名</b>，名字永远是库里原来那个 —— 见 {@link #replaceInPlace}。）
     *
     * @param mode           {@code append}（默认，新增）或 {@code replace}（替换已有的）
     * @param replaceTrackId 当 {@code mode=replace} 时，要替换哪一条
     */
    @Transactional
    public ImportResult importUpload(byte[] content, String fallbackName,
                                     String mode, Long replaceTrackId) {
        requireNotEmpty(content);

        String externalId = sha256Hex(content);
        Optional<Track> byHash = trackRepository.findByExternalId(externalId);
        boolean replace = "replace".equals(mode);

        // ② 幂等：内容一模一样，且不是在替换
        if (byHash.isPresent() && !replace) {
            return skipped(byHash.get());
        }

        // ③ 替换模式下，新内容属于【另一条】轨迹 → 409 SAME_CONTENT（否则会撞 external_id 唯一约束变成 500）
        if (byHash.isPresent()) {
            Track other = byHash.get();
            if (!other.getId().equals(replaceTrackId)) {
                throw new TrackConflictException(
                        TrackConflictResponse.sameContent(other.getId(), other.getName()));
            }
        }

        Parsed parsed = parse(content, fallbackName);

        // ④ 哈希是新的、但名字已存在 → 409 SAME_NAME
        //    （把"要替换的那条"排除掉：它是本次操作的目标，不该被当成"抢了别人的名字"）
        Optional<Long> conflict = trackEditService.findNameConflict(parsed.name(), replaceTrackId);
        if (conflict.isPresent() && !replace) {
            Track existing = trackRepository.findById(conflict.get()).orElseThrow();
            throw new TrackConflictException(TrackConflictResponse.sameName(
                    existing.getId(), existing.getName(),
                    existing.getPointCount(), parsed.points().size()));
        }

        if (replace) {
            if (replaceTrackId == null) {
                throw new IllegalArgumentException("mode=replace 时必须提供 replaceTrackId");
            }
            return replaceInPlace(replaceTrackId, externalId, parsed);
        }
        return persist(parsed.name(), parsed.format(), externalId, parsed.points());
    }

    /** 上传的文件是空的就直说 —— 空内容算哈希也能算出个值，会一路走到"导入成功一条 0 点的轨迹" */
    private static void requireNotEmpty(byte[] content) {
        if (content == null || content.length == 0) {
            throw new IllegalArgumentException("上传的文件是空的");
        }
    }

    /**
     * "这份内容已经在库里了" —— 幂等跳过。
     *
     * <p>抽出来是为了让新增与替换两条路径<b>给出同一句话、同一套字段兜底</b>；
     * 顺带把 {@code null} 的点数/距离/时长统一成 0（数据库里老数据可能是 NULL）。
     */
    private static ImportResult skipped(Track t) {
        return new ImportResult(t.getId(), t.getName(),
                t.getPointCount() == null ? 0 : t.getPointCount(),
                t.getDistanceM() == null ? 0 : t.getDistanceM(),
                t.getDurationS() == null ? 0 : t.getDurationS(),
                0, true, "这条轨迹已经导入过了");
    }

    /**
     * 解析结果（本类内部用）。
     *
     * <p><b>为什么不直接用 {@link ParsedTrack}</b>：解析实际产出<b>三</b>样东西 —— 格式、名字、点，
     * 而 {@link ParsedTrack} 只有后两样（格式来自 {@code Importer.format()}）。
     * 打包成一条 record，格式就能从"解析"这一步传到"入库"那一步，
     * 不必让 {@link #persist} 自己再选一次解析器。
     *
     * <p>名字在这里<b>已经兜过底</b>（文件里没有 {@code <name>} 时用文件名）：
     * 同名检测和真正入库用的必须是同一个名字。
     */
    private record Parsed(String format, String name, List<RawPoint> points) {
    }

    /**
     * 识别格式 → 选解析器 → 解析 → 名字兜底。
     *
     * <p>新增、替换、批量导入三条路径都走这里。
     */
    private Parsed parse(byte[] content, String fallbackName) {
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

        return new Parsed(importer.format(), name, parsed.points());
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

    /** 清洗 + 新增一条轨迹，返回给前端的摘要 */
    private ImportResult persist(String name, String source, String externalId, List<RawPoint> raw) {
        CleanedTrack cleaned = cleaner.clean(raw);
        List<RawPoint> pts = cleaned.points();
        int n = pts.size();

        OffsetDateTime start = pts.get(0).recordedAt();
        OffsetDateTime end = pts.get(n - 1).recordedAt();

        Track track = new Track(name, source, externalId, start, end);
        applyCleaned(track, cleaned);
        Track saved = trackRepository.save(track);

        savePoints(saved.getId(), cleaned);

        // ⚠️ 新增一条轨迹会让【所有主线】的相似度结果失效 —— 候选集从 N 变成 N+1，
        // 旧缓存里的 compared / 名次全是过期的（SimilarityCache 的类注释里本来就写着
        // "导入新轨迹之后应该调用 invalidateAll()"，这条欠账在这里兑现）。
        // 放在 persist 里而不是 importUpload 的"纯新增"分支：persist 是唯一的"新增入库"出口，
        // 网页上传的 append 与 importBytes（含 GeoLife 目录批量导入）都从这里过，一处覆盖全部。
        // 注意：StayPointCache 不用清 —— 新轨迹在缓存里本来就没有条目，下次请求自然会算。
        similarityCache.invalidateAll();

        return summarize(saved.getId(), saved.getName(), cleaned, false, "导入成功");
    }

    /**
     * 用新文件<b>原地替换</b>一条已有轨迹（{@code trackId} 不变）。
     *
     * <p><b>为什么"保持 trackId 不变"而不是删了重建</b>：
     * <ul>
     *   <li>前端此刻可能正选中着这条轨迹 —— 删了重建，选中态和地球上的线都会失效</li>
     *   <li>缓存失效范围更小（只需清这一条 + 相似度全清）</li>
     * </ul>
     *
     * <p><b>为什么要校验来源一致</b>：GPX（个人采集）和 GeoLife（公开数据集）语义不同，
     * 允许互相替换会让 {@code source} 这个筛选维度失去意义。
     *
     * <p><b>⚠️ 替换不改名字</b>：更新的是数据（geom / 点数 / 时长 / external_id / 时间范围，
     * 见设计文档 §2.3），名字保持库里原样 —— 详见方法体里的注释。
     *
     * <p><b>⚠️ 为什么删旧点、写新点必须在同一个事务里</b>：中间任何一步失败都要整体回滚，
     * 否则会留下一条<b>没有点的轨迹</b>（列表里还在、点开是空的）。
     * 本方法由 {@link #importUpload} 上的 {@code @Transactional} 罩着。
     */
    private ImportResult replaceInPlace(Long trackId, String externalId, Parsed parsed) {
        Track track = trackRepository.findById(trackId)
                .orElseThrow(() -> new IllegalArgumentException("要替换的轨迹不存在：" + trackId));

        if (!track.getSource().equals(parsed.format())) {
            throw new IllegalArgumentException(
                    "来源不一致：原轨迹是 " + track.getSource() + "，上传的是 " + parsed.format());
        }

        CleanedTrack cleaned = cleaner.clean(parsed.points());
        List<RawPoint> pts = cleaned.points();

        // 一条 SQL 删掉旧点（不是把几万个实体查出来逐个删 —— 见 TrackPointRepository.deleteByTrackId）
        trackPointRepository.deleteByTrackId(trackId);

        // ⚠️ 这里【故意不 setName】—— 替换是"换数据"，不是"改名字"。
        // 设计文档 §2.3 规定替换更新的字段是：geom、点数、时长、external_id、时间范围，【没有 name】。
        // 反例：拿「资料三.gpx」去替换「资料二」，名字必须仍然是「资料二」，
        // 否则用户只是想把内容换掉，却连带把名字改了（前端选中态还停在这条 id 上，看不出改名）。
        track.setExternalId(externalId);
        track.setStartTime(pts.get(0).recordedAt());
        track.setEndTime(pts.get(pts.size() - 1).recordedAt());
        applyCleaned(track, cleaned);
        trackRepository.save(track);

        savePoints(trackId, cleaned);

        // 数据变了 → 两个缓存都要清：停留点是"这条轨迹的点"的函数，
        // 而相似度结果里也带着这条轨迹的几何
        stayPointCache.invalidate(trackId);
        similarityCache.invalidateAll();

        // 名字用【库里原有的】，与上面"不改名"保持一致（返回给前端的摘要不能报出一个并不存在的名字）
        return summarize(trackId, track.getName(), cleaned, false, "替换成功");
    }

    /** 把清洗结果写进 track 的派生字段与几何（新增与替换<b>共用</b>，免得两处各写一遍还漏字段） */
    private static void applyCleaned(Track track, CleanedTrack cleaned) {
        track.setDistanceM(cleaned.distanceM());
        track.setDurationS(cleaned.durationS());
        track.setPointCount(cleaned.points().size());
        track.setGeom(buildLineString(cleaned.points()));
    }

    /** 把清洗后的点批量写进 {@code track_point}（新增与替换共用） */
    private void savePoints(Long trackId, CleanedTrack cleaned) {
        List<RawPoint> pts = cleaned.points();
        List<TrackPoint> entities = new ArrayList<>(pts.size());
        for (int i = 0; i < pts.size(); i++) {
            RawPoint p = pts.get(i);
            entities.add(new TrackPoint(
                    trackId,
                    i,
                    p.recordedAt(),
                    p.elevationM(),
                    cleaned.speeds().get(i),
                    buildPoint(p),
                    cleaned.outliers().get(i)));
        }
        trackPointRepository.saveAll(entities);
    }

    /** 导入 / 替换成功后的摘要（两条路径同一套算法，包括异常点计数） */
    private static ImportResult summarize(Long id, String name, CleanedTrack cleaned,
                                          boolean skippedDuplicate, String message) {
        long outlierCount = cleaned.outliers().stream().filter(Boolean::booleanValue).count();
        return new ImportResult(id, name, cleaned.points().size(), cleaned.distanceM(),
                cleaned.durationS(), outlierCount, skippedDuplicate, message);
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
        List<String> errorSamples = new ArrayList<>();
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
                failed++;
                // 必须记下来！曾经这里只加了个计数，导致 171 个文件全部失败却查不出原因
                String msg = file.getFileName() + " -> " + e.getClass().getSimpleName()
                        + (e.getMessage() == null ? "" : (": " + e.getMessage()));
                if (errorSamples.size() < MAX_ERROR_SAMPLES) {
                    errorSamples.add(msg);
                }
                log.warn("轨迹导入失败: {}", msg);
            }
        }

        return new GeoLifeImportResult(root.toString(), pltFiles.size(), imported, skipped, failed,
                totalPoints, System.currentTimeMillis() - started, errorSamples);
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

    // ------------------------------------------------------------ 冲突异常

    /**
     * 同名 / 同内容冲突 → 由 {@code ImportController} 映射成 <b>409 Conflict</b>，
     * 并把 {@link #getBody()} 原样作为响应体。
     *
     * <p><b>为什么是 409 而不是 400</b>：请求本身没毛病，是<b>和库里已有的东西撞了</b> ——
     * 语义上就该是 409。前端靠这个码决定"弹出替换 / 新增的选择"。
     *
     * <p><b>为什么把响应体（{@link TrackConflictResponse}）挂在异常上</b>：
     * "冲突的是什么"是导入过程中才算得出来的（要点数、要名字），
     * 挂在异常上控制器就不用再查一遍库 —— catch 一次，原样吐回去。
     */
    public static class TrackConflictException extends RuntimeException {

        private final transient TrackConflictResponse body;

        public TrackConflictException(TrackConflictResponse body) {
            super(body.message());
            this.body = body;
        }

        public TrackConflictResponse getBody() {
            return body;
        }
    }

    /** 批量导入的汇总结果 */
    public record GeoLifeImportResult(
            String path, int scanned, int imported, int skipped, int failed,
            int totalPoints, long elapsedMs, List<String> errorSamples) {
    }
}
