package com.calcite.web;

import com.calcite.config.ImportProperties;
import com.calcite.service.ImportService;
import com.calcite.web.dto.ImportResult;
import com.calcite.web.dto.TrackConflictResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Map;

/**
 * 轨迹导入接口。
 *
 * <p>两个入口：
 * <ul>
 *   <li>{@code POST /api/tracks/import} —— 网页上传单个文件；
 *       带 {@code mode=replace} + {@code replaceTrackId} 时是"替换已有轨迹"，
 *       撞同名 / 撞同内容返回 <b>409</b> 让用户决定</li>
 *   <li>{@code POST /api/import/geolife} —— 批量导入本地目录（GeoLife .plt）</li>
 * </ul>
 */
@RestController
public class ImportController {

    private final ImportService importService;
    private final ImportProperties properties;

    public ImportController(ImportService importService, ImportProperties properties) {
        this.importService = importService;
        this.properties = properties;
    }

    /** 网页上传单个文件（{@code mode=append} 新增 / {@code mode=replace} 替换） */
    @PostMapping("/api/tracks/import")
    public ImportResult upload(@RequestParam("file") MultipartFile file,
                               @RequestParam(defaultValue = "append") String mode,
                               @RequestParam(required = false) Long replaceTrackId)
            throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("上传的文件是空的");
        }
        // 名字兜底必须用【去掉扩展名】的文件名：同名检测就是拿这个名字去和库里比，
        // 带着 ".gpx" 后缀反而永远比不上已有的「资料一」→ 409 那条路就废了
        return importService.importUpload(file.getBytes(),
                stripExtension(file.getOriginalFilename()), mode, replaceTrackId);
    }

    /** 批量导入本地 GeoLife 目录 */
    @PostMapping("/api/import/geolife")
    public ImportService.GeoLifeImportResult importGeoLife(@RequestBody GeoLifeRequest request) {
        if (request.path() == null || request.path().isBlank()) {
            throw new IllegalArgumentException("必须提供 path");
        }
        int max = request.maxTracks() == null ? properties.getMaxTracksPerCall() : request.maxTracks();
        return importService.importGeoLifeDirectory(
                Path.of(request.path()), max, properties.getAllowedRoots());
    }

    /** 请求体：{"path": "D:\\GeoLife\\Data", "maxTracks": 50} */
    public record GeoLifeRequest(String path, Integer maxTracks) {
    }

    /** 文件名去掉扩展名，用作轨迹名兜底 */
    private static String stripExtension(String filename) {
        if (filename == null || filename.isBlank()) {
            return "未命名轨迹";
        }
        int dot = filename.lastIndexOf('.');
        return dot > 0 ? filename.substring(0, dot) : filename;
    }

    /** 参数问题一律 400，并把原因原样告诉前端（这些错误都是给人看的） */
    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Map<String, String> handleBadRequest(IllegalArgumentException e) {
        return Map.of("error", e.getMessage() == null ? "导入失败" : e.getMessage());
    }

    /**
     * 同名 / 同内容冲突 → <b>409</b> + 说清楚冲突的是什么。
     *
     * <p><b>为什么是 409 而不是 400</b>：请求本身没问题，是<b>和库里已有的东西冲突了</b> ——
     * 语义上就该是 409 Conflict。前端靠这个码来决定"弹出替换 / 新增的选择"。
     *
     * <p><b>为什么响应体直接来自异常</b>：冲突的细节（是哪条轨迹、各多少点）
     * 是导入过程中算出来的，异常里带着 {@link TrackConflictResponse}，
     * 这里原样返回即可 —— 控制器不重新查库、不拼装业务数据。
     */
    @ExceptionHandler(ImportService.TrackConflictException.class)
    public ResponseEntity<TrackConflictResponse> handleConflict(
            ImportService.TrackConflictException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(e.getBody());
    }
}
