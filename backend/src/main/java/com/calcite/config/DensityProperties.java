package com.calcite.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 网格密度配置，对应 {@code application.yml} 里的 {@code calcite.density.*}。
 *
 * <p>为什么用 {@code @ConfigurationProperties} 而不是 {@code @Value}：
 * {@code cell-ladder} 是 YAML <b>列表</b>，而 {@code @Value} 只能读单个标量属性 ——
 * 写 {@code @Value("${calcite.density.cell-ladder}")} 会直接报占位符解析失败。
 * 这个坑在做轨迹导入功能时踩过一次（见 {@link ImportProperties}）。
 */
@Component
@ConfigurationProperties(prefix = "calcite.density")
public class DensityProperties {

    /**
     * 格边长阶梯（度），**从粗到细**排列。
     *
     * <p>只允许这些值，是为了让"换一档"成为可复现的<b>离散事件</b>：
     * 只要格边长不变，`ST_SnapToGrid` 的网格锚点就不变，
     * 于是拖动地图时格子<b>纹丝不动</b>。如果按视野宽度实时算一个任意小数，
     * 网格锚点会跟着变，缩放时整个网格就"抖"。
     *
     * <p>最粗一档为什么是 <b>5°</b> 而不是 0.05°：
     * 最粗档 × 目标格数 = 能覆盖的最大视野宽度，5° × 80 = 400° &gt; 地球一圈 360°，
     * 于是全球视野下也挑得出档来。若最粗档只有 0.05°，用户一打开地图（全球视野）
     * 点"密度"就会拿到 400。
     */
    // 注意：前三个字面量写成 5.0 / 2.0 / 1.0 —— 不能写 5 / 2 / 1。
    // List.of(5, 2, 1, 0.5, ...) 里 Integer 和 Double 混在一起，
    // javac 推断出的公共类型不是 Double，赋给 List<Double> 会直接编译失败。
    private List<Double> cellLadder = new ArrayList<>(List.of(
            5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001));

    /** 视野内目标格数（挑档时用：格边长 = 阶梯里 ≥ 视野宽度 ÷ 这个数 的最小档） */
    private int targetCellsAcross = 80;

    /** 单次请求的格子数上限（估算值超过它直接 400） */
    private long maxCells = 20_000;

    /** 时区：库里存 UTC，但"早高峰"是人理解的北京时间，SQL 里显式转换 */
    private String timeZone = "Asia/Shanghai";

    public List<Double> getCellLadder() {
        return cellLadder;
    }

    public void setCellLadder(List<Double> cellLadder) {
        this.cellLadder = cellLadder;
    }

    public int getTargetCellsAcross() {
        return targetCellsAcross;
    }

    public void setTargetCellsAcross(int targetCellsAcross) {
        this.targetCellsAcross = targetCellsAcross;
    }

    public long getMaxCells() {
        return maxCells;
    }

    public void setMaxCells(long maxCells) {
        this.maxCells = maxCells;
    }

    public String getTimeZone() {
        return timeZone;
    }

    public void setTimeZone(String timeZone) {
        this.timeZone = timeZone;
    }

    /** 给 {@link com.calcite.service.DensityGrid} 用的原始 double 数组 */
    public double[] ladderArray() {
        double[] a = new double[cellLadder.size()];
        for (int i = 0; i < a.length; i++) {
            a[i] = cellLadder.get(i);
        }
        return a;
    }
}
