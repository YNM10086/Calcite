package com.calcite.service.importer;

import java.io.InputStream;

/**
 * 一种轨迹文件格式的解析器。
 *
 * <p>实现类必须无状态、可复用（不要往实现类里存字段）——
 * 它们会被注册成 Spring Bean 反复使用。
 */
public interface Importer {

    /** 格式标识，与 {@link FormatDetector#detect} 的返回值一致：{@code "gpx"} / {@code "geolife"} */
    String format();

    /**
     * 从字节流解析。
     *
     * <p>实现应该容忍个别坏点（跳过并继续），
     * 但整体格式不对、或一个有效点都没有时，抛 {@link IllegalArgumentException}。
     */
    ParsedTrack parse(InputStream in) throws Exception;
}
