package com.calcite.web;

import com.calcite.config.ImportProperties;
import com.calcite.service.ImportService;
import com.calcite.web.dto.ImportResult;
import org.springframework.http.HttpStatus;
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
 *   <li>{@code POST /api/tracks/import} —— 网页上传单个文件（GPX）</li>
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

    /** 网页上传单个文件 */
    @PostMapping("/api/tracks/import")
    public ImportResult upload(@RequestParam("file") MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("上传的文件是空的");
        }
        return importService.importBytes(file.getBytes(), stripExtension(file.getOriginalFilename()));
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
}
