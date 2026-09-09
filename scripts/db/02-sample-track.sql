\encoding UTF8
-- ============================================================================
-- Calcite 示例数据：一条北京城区骑行轨迹（天安门 → 奥林匹克公园）
-- 用法：psql -U postgres -d calcite -f scripts/db/02-sample-track.sql
-- 特点：可重复执行（先删掉旧的 SAMPLE-001）
-- ============================================================================

\echo ''
\echo '########## 0) 清理旧数据 ##########'
DELETE FROM track WHERE external_id = 'SAMPLE-001';

\echo ''
\echo '########## 1) 插入轨迹元数据 ##########'
INSERT INTO track (name, source, external_id, start_time, end_time)
VALUES ('北京城区骑行 · 天安门→奥林匹克公园', 'sample', 'SAMPLE-001',
        TIMESTAMPTZ '2026-09-08 07:30:00+08',
        TIMESTAMPTZ '2026-09-08 08:20:00+08');

\echo ''
\echo '########## 2) 用折线插值生成 121 个轨迹点（每 25 秒一个）##########'
-- 思路：先画一条经过 7 个途经点的折线，再沿线等距离取 121 个点
--       ST_LineInterpolatePoint(line, 0..1) 就是「取线上第 x% 处的点」
WITH route AS (
  SELECT ST_MakeLine(ARRAY[
    ST_MakePoint(116.3974, 39.9093),   -- 天安门
    ST_MakePoint(116.3948, 39.9245),   -- 景山
    ST_MakePoint(116.3880, 39.9400),   -- 什刹海
    ST_MakePoint(116.3900, 39.9550),   -- 鼓楼
    ST_MakePoint(116.3920, 39.9700),   -- 北土城
    ST_MakePoint(116.3900, 39.9850),   -- 奥体
    ST_MakePoint(116.3880, 39.9930)    -- 奥林匹克公园
  ]) AS line
),
pts AS (
  SELECT g AS seq,
         ST_LineInterpolatePoint(r.line, g / 120.0) AS p
  FROM route r, generate_series(0, 120) AS g
)
INSERT INTO track_point (track_id, seq, recorded_at, elevation_m, geom)
SELECT (SELECT id FROM track WHERE external_id = 'SAMPLE-001'),
       seq,
       TIMESTAMPTZ '2026-09-08 07:30:00+08' + (seq * interval '25 seconds'),
       -- 高程：40 米上下小幅起伏，看起来像真实 GPS 数据
       40 + 8 * sin(seq / 20.0),
       -- 加一点随机抖动（约 ±2 米），模拟 GPS 噪声
       ST_SetSRID(
         ST_Translate(p, (random() - 0.5) * 0.00002, (random() - 0.5) * 0.00002),
         4326)
FROM pts;

\echo ''
\echo '########## 3) 回填派生字段（线、距离、时长、点数、逐点速度）##########'
UPDATE track t SET
  point_count = (SELECT count(*) FROM track_point WHERE track_id = t.id),
  -- 线由点生成，且必须按时间/顺序排好，否则线会乱连
  geom        = (SELECT ST_MakeLine(geom ORDER BY seq) FROM track_point WHERE track_id = t.id),
  -- ST_Length 对 geography 返回米；对 geometry(4326) 只会返回度数
  distance_m  = (SELECT ST_Length(ST_MakeLine(geom ORDER BY seq)::geography)
                 FROM track_point WHERE track_id = t.id),
  duration_s  = EXTRACT(EPOCH FROM (t.end_time - t.start_time))::int
WHERE t.external_id = 'SAMPLE-001';

-- 逐点速度：到前一个点的球面距离 ÷ 两点时间差（单位 米/秒）。
-- 第一个点没有「前一个点」，所以它的 speed_mps 保持 NULL —— 真实 GPS 数据也是这样，
-- 前端画曲线时要能跳过空值。
UPDATE track_point tp
SET speed_mps = s.v
FROM (
  SELECT seq,
         ST_Distance(geom::geography, prev_geom::geography)
           / NULLIF(EXTRACT(EPOCH FROM (recorded_at - prev_at)), 0) AS v
  FROM (
    SELECT seq, recorded_at, geom,
           LAG(geom) OVER (ORDER BY seq)        AS prev_geom,
           LAG(recorded_at) OVER (ORDER BY seq) AS prev_at
    FROM track_point
    WHERE track_id = (SELECT id FROM track WHERE external_id = 'SAMPLE-001')
  ) o
  WHERE prev_geom IS NOT NULL
) s
WHERE tp.track_id = (SELECT id FROM track WHERE external_id = 'SAMPLE-001')
  AND tp.seq = s.seq;

\echo ''
\echo '########## 4) 验收：轨迹概览 ##########'
SELECT id,
       name,
       point_count                              AS 点数,
       round(distance_m::numeric, 1)            AS 总距离米,
       duration_s                               AS 时长秒,
       round((distance_m / NULLIF(duration_s, 0) * 3.6)::numeric, 2) AS 均速公里每小时,
       ST_NumPoints(geom)                       AS 线的顶点数
FROM track
WHERE external_id = 'SAMPLE-001';

\echo ''
\echo '########## 5) 验收：前 5 个点 ##########'
SELECT seq, recorded_at, round(elevation_m::numeric, 2) AS 高程米, ST_AsText(geom) AS 坐标
FROM track_point
WHERE track_id = (SELECT id FROM track WHERE external_id = 'SAMPLE-001')
ORDER BY seq
LIMIT 5;

\echo ''
\echo '########## 6) 验收：回填的速度 vs 现算的速度（应当完全一致）##########'
WITH ordered AS (
  SELECT seq, recorded_at, geom, speed_mps,
         LAG(geom) OVER (ORDER BY seq)        AS prev_geom,
         LAG(recorded_at) OVER (ORDER BY seq) AS prev_at
  FROM track_point
  WHERE track_id = (SELECT id FROM track WHERE external_id = 'SAMPLE-001')
),
calc AS (
  SELECT seq, speed_mps,
         ST_Distance(geom::geography, prev_geom::geography)
           / NULLIF(EXTRACT(EPOCH FROM (recorded_at - prev_at)), 0) AS v
  FROM ordered
  WHERE prev_geom IS NOT NULL
)
SELECT count(*)                                          AS 参与比对点数,
       count(*) FILTER (WHERE abs(speed_mps - v) < 1e-9) AS 完全一致,
       round(max(abs(speed_mps - v))::numeric, 12)       AS 最大偏差
FROM calc;

\echo ''
