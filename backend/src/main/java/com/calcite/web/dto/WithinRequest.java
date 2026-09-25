package com.calcite.web.dto;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.OffsetDateTime;

/**
 * {@code POST /api/analysis/within} 的请求体。
 *
 * <p><b>为什么 {@code geometry} 用 {@link JsonNode} 而不是强类型</b>：
 * 类型是否合法由 {@code RegionGeometry} 判定 —— 我们要给出"人能看懂的 400 原因"，
 * 而不是 Jackson 的一句反序列化异常。
 *
 * <p>{@code from}/{@code to} 用 {@link OffsetDateTime}：JSON body 里走 ISO-8601
 * （spring-boot-starter-web 自带 JSR-310 支持）。注意这与 query 参数用
 * {@code @DateTimeFormat} 是两条不同的路。
 */
public record WithinRequest(
        JsonNode geometry,
        Double bufferM,
        OffsetDateTime from,
        OffsetDateTime to,
        Integer limit) {
}
