package com.calcite.service.importer;

import java.time.OffsetDateTime;

/**
 * 解析器统一输出的中间结构：一个原始点。
 *
 * <p>存在的意义：GPX 和 .plt 的格式差异在各自的解析器里消化掉，
 * 吐出来全是这一种东西 —— 于是清洗规则（TrackCleaner）只需要写一份。
 *
 * @param lat        纬度
 * @param lon        经度
 * @param elevationM 海拔（米）；数据源没有就是 null
 * @param recordedAt 记录时刻（带时区）
 */
public record RawPoint(double lat, double lon, Double elevationM, OffsetDateTime recordedAt) {
}
