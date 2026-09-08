-- ============================================================================
-- Calcite 一键查看示例轨迹（不会刷屏、不会进分页器）
-- 用法（直接复制到 PowerShell，路径写全，在任何目录都能跑）：
--   $env:PGPASSWORD='557096138Cc'
--   & "E:\PostgreSQL\bin\psql.exe" -U postgres -d calcite -P pager=off -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\scripts\db\03-show-results.sql"
-- ============================================================================

-- 关掉分页器：否则输出超过一屏时 psql 会打开 less/more，看起来就像"卡住了"
\pset pager off

\echo '=========== 1) 轨迹列表 ==========='
SELECT id,
       name,
       source,
       point_count                   AS 点数,
       round(distance_m::numeric, 1) AS 距离米,
       duration_s                    AS 时长秒
FROM track
ORDER BY id;

\echo ''
\echo '=========== 2) 前 5 个点（经纬度拆成两列，比 ST_AsText 好读）==========='
SELECT seq,
       recorded_at,
       round(ST_X(geom)::numeric, 6) AS 经度,
       round(ST_Y(geom)::numeric, 6) AS 纬度,
       round(elevation_m::numeric, 2) AS 高程米
FROM track_point
WHERE track_id = (SELECT id FROM track WHERE external_id = 'SAMPLE-001')
ORDER BY seq
LIMIT 5;

\echo ''
\echo '=========== 3) 轨迹线的顶点数 / 起点 / 终点 ==========='
SELECT ST_NPoints(geom)                  AS 顶点数,
       ST_AsText(ST_StartPoint(geom))    AS 起点,
       ST_AsText(ST_EndPoint(geom))      AS 终点
FROM track
WHERE external_id = 'SAMPLE-001';

\echo ''
\echo '=========== 4) 距天安门 1 公里内有几个点 ==========='
-- 注意：ST_MakePoint 造出来的点是 SRID 0（无坐标系），必须显式 ST_SetSRID 成 4326，
--      否则报 "Operation on mixed SRID geometries (Point, 4326) != (Point, 0)"
SELECT count(*) AS 天安门1公里内的点数
FROM track_point
WHERE track_id = (SELECT id FROM track WHERE external_id = 'SAMPLE-001')
  AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint(116.3974, 39.9093), 4326), 0.01);

\echo ''
