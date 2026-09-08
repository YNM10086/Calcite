-- ============================================================================
-- Calcite 学习脚本 01：PostGIS 初体验
-- ----------------------------------------------------------------------------
-- 目的：不写一行 Java / Vue，直接在数据库里感受「会算地理的数据库」
-- 用法：psql -U postgres -d calcite -f scripts/learning/01-postgis-basics.sql
-- 说明：只操作 demo 模式，可反复运行，不影响正式表
-- 清理：DROP SCHEMA demo CASCADE;
-- ============================================================================

DROP SCHEMA IF EXISTS demo CASCADE;
CREATE SCHEMA demo;

\echo ''
\echo '########## 1) PostGIS 装好了吗 ##########'
SELECT PostGIS_Version() AS postgis_version;

\echo ''
\echo '########## 2) 造一个点：PostGIS 有自己的数据类型 ##########'
-- 普通数据库只有 数字/字符串/时间；PostGIS 多了一种类型叫 geometry
SELECT ST_MakePoint(116.3184, 39.9847)                              AS 裸点,
       ST_AsText(ST_SetSRID(ST_MakePoint(116.3184, 39.9847), 4326)) AS 带坐标系标签的点;

\echo ''
\echo '########## 3) 算距离：同一段距离，三种写法，差别巨大 ##########'
-- 写法 A：直接在 4326 上算 —— 结果是「度」，不是米！
SELECT 'A 直接算 4326' AS 写法,
       ST_Distance(a, b)::numeric(20,10) AS 结果
FROM (SELECT ST_SetSRID(ST_MakePoint(116.318417, 39.984702), 4326) a,
             ST_SetSRID(ST_MakePoint(116.320000, 39.985000), 4326) b) t;

-- 写法 B：转成 geography（地理类型）—— 结果单位是米
SELECT 'B 转 geography' AS 写法,
       ST_Distance(a::geography, b::geography)::numeric(20,3) AS 结果米
FROM (SELECT ST_SetSRID(ST_MakePoint(116.318417, 39.984702), 4326) a,
             ST_SetSRID(ST_MakePoint(116.320000, 39.985000), 4326) b) t;

-- 写法 C：转成投影坐标系 EPSG:4547（CGCS2000 高斯投影）—— 结果单位也是米
SELECT 'C 转 EPSG:4547' AS 写法,
       ST_Distance(ST_Transform(a, 4547), ST_Transform(b, 4547))::numeric(20,3) AS 结果米
FROM (SELECT ST_SetSRID(ST_MakePoint(116.318417, 39.984702), 4326) a,
             ST_SetSRID(ST_MakePoint(116.320000, 39.985000), 4326) b) t;

\echo ''
\echo '########## 4) 准备数据：30 万个随机 GPS 点 ##########'
CREATE TABLE demo.pt (
  id          BIGSERIAL PRIMARY KEY,
  geom        geometry(Point, 4326) NOT NULL,
  recorded_at timestamptz           NOT NULL
);

INSERT INTO demo.pt (geom, recorded_at)
SELECT ST_SetSRID(ST_MakePoint(116.2 + random() * 0.4,
                               39.8 + random() * 0.3), 4326),
       now() - (random() * interval '30 days')
FROM generate_series(1, 300000);

ANALYZE demo.pt;
SELECT count(*) AS 总点数 FROM demo.pt;

\echo ''
\echo '########## 5) 没索引：查「某点附近约 1 公里」 ##########'
\echo '注意看 Execution Time 和 Seq Scan'
EXPLAIN (ANALYZE, TIMING OFF)
SELECT count(*) FROM demo.pt
WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(116.4, 39.95), 4326), 0.01);

\echo ''
\echo '########## 6) 建 GiST 空间索引 ##########'
CREATE INDEX idx_demo_pt_geom ON demo.pt USING GIST (geom);
ANALYZE demo.pt;

\echo ''
\echo '########## 7) 有索引：同一个查询，再看一次 ##########'
\echo '注意看 Bitmap Index Scan 和 Execution Time 的变化'
EXPLAIN (ANALYZE, TIMING OFF)
SELECT count(*) FROM demo.pt
WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(116.4, 39.95), 4326), 0.01);

\echo ''
\echo '########## 8) 时空联合索引：区域 + 时间段一起查 ##########'
\echo '需要 btree_gist 扩展（已在 calcite 库安装）'
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE INDEX idx_demo_pt_st ON demo.pt USING GIST (geom, recorded_at);
ANALYZE demo.pt;

EXPLAIN (ANALYZE, TIMING OFF)
SELECT count(*) FROM demo.pt
WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(116.4, 39.95), 4326), 0.01)
  AND recorded_at BETWEEN now() - interval '7 days' AND now();

\echo ''
\echo '########## 9) 收尾：demo 模式留着做练习，想删就执行 ##########'
\echo '   DROP SCHEMA demo CASCADE;'
\echo ''
