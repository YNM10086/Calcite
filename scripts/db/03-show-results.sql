\encoding UTF8
-- ============================================================================
-- Calcite 一键查看示例轨迹（不会刷屏、不会进分页器）
--
-- 两个编码陷阱（中文版 Windows 特有）：
--   ① 文件是 UTF-8，但 psql 默认按 GBK 读 → 报「编码 GBK 的字符 0x.. 没有相对应值」
--      解决：本文件第一行的 \encoding UTF8
--   ② psql 自己的提示信息（如 "(1 行记录)"）按系统语言 GBK 输出，和数据(UTF-8)混在一起 → 乱码
--      解决：跑之前设 $env:LC_MESSAGES='C'，让 psql 说英文
--
-- 用法（推荐，中文一定能正常显示）：输出到文件，用 VS Code 打开
--   $env:PGPASSWORD='你的密码'
--   $env:LC_MESSAGES='C'
--   & "E:\PostgreSQL\bin\psql.exe" -U postgres -d calcite -P pager=off -o "E:\JAVA_IDEA_package\JAVA_Project\Calcite\.tmp\result.txt" -f "E:\JAVA_IDEA_package\JAVA_Project\Calcite\scripts\db\03-show-results.sql"
--   code "E:\JAVA_IDEA_package\JAVA_Project\Calcite\.tmp\result.txt"
--
-- 用法 B（直接看，但中文数据可能在控制台里乱码）：把 -o 那一段去掉即可
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
