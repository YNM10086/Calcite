package com.calcite.service.importer;

import java.util.List;

/**
 * 一个解析器的产出。
 *
 * @param name   轨迹名。可能为 null —— GPX 常常没有 &lt;name&gt;，.plt 根本没有名字字段。
 *               为 null 时由 ImportService 用文件名兜底。
 * @param points 原始点，**未排序、未清洗**
 */
public record ParsedTrack(String name, List<RawPoint> points) {
}
