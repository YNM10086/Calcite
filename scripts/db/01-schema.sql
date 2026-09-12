\encoding UTF8
-- ============================================================================
-- Calcite 数据库结构 v1 —— 对应设计文档 3.2
-- 用法：psql -U postgres -d calcite -f scripts/db/01-schema.sql
-- 特点：可重复执行（全部 IF NOT EXISTS），不会误删数据
-- ============================================================================

-- 空间扩展：postgis 提供 ST_ 函数和 geometry 类型
-- btree_gist 让 GIST 索引能同时容纳「空间列 + 普通列（时间）」
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;

\echo ''
\echo '########## 建表：track（一条轨迹 = 一次出行）##########'
CREATE TABLE IF NOT EXISTS track (
  id          BIGSERIAL PRIMARY KEY,
  name        VARCHAR(200) NOT NULL,
  source      VARCHAR(20)  NOT NULL,        -- geolife | gpx | csv | sample
  external_id VARCHAR(100),                 -- 原始数据集里的编号
  start_time  TIMESTAMPTZ  NOT NULL,
  end_time    TIMESTAMPTZ  NOT NULL,
  distance_m  DOUBLE PRECISION,             -- 派生：由点算出的总距离（米）
  duration_s  INTEGER,                      -- 派生：总时长（秒）
  point_count INTEGER,                      -- 派生：点数
  geom        GEOMETRY(LineString, 4326),   -- 派生：由点生成的轨迹线
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

\echo '########## 建表：track_point（一个 GPS 点 = 原始真相）##########'
CREATE TABLE IF NOT EXISTS track_point (
  id          BIGSERIAL PRIMARY KEY,
  track_id    BIGINT      NOT NULL REFERENCES track(id) ON DELETE CASCADE,
  seq         INTEGER     NOT NULL,         -- 在轨迹中的顺序
  recorded_at TIMESTAMPTZ NOT NULL,
  elevation_m DOUBLE PRECISION,
  speed_mps   DOUBLE PRECISION,
  is_outlier  BOOLEAN     NOT NULL DEFAULT false, -- 疑似 GPS 漂移点（导入时标记）
  geom        GEOMETRY(Point, 4326) NOT NULL
);

\echo '########## 建表：stay_point（一次停留，M2 由算法生成）##########'
CREATE TABLE IF NOT EXISTS stay_point (
  id          BIGSERIAL PRIMARY KEY,
  track_id    BIGINT      NOT NULL REFERENCES track(id) ON DELETE CASCADE,
  start_time  TIMESTAMPTZ NOT NULL,
  end_time    TIMESTAMPTZ NOT NULL,
  duration_s  INTEGER     NOT NULL,
  radius_m    DOUBLE PRECISION,
  geom        GEOMETRY(Point, 4326) NOT NULL
);

\echo ''
\echo '########## 建索引（面试重点）##########'
-- 时空联合索引：空间和时间放在同一个 GIST 索引里，一次扫描过滤两个条件
CREATE INDEX IF NOT EXISTS idx_track_point_st  ON track_point USING GIST (geom, recorded_at);
-- 按轨迹取点、按顺序排序
CREATE INDEX IF NOT EXISTS idx_track_point_seq ON track_point (track_id, seq);
-- 轨迹线本身的空间检索
CREATE INDEX IF NOT EXISTS idx_track_geom      ON track USING GIST (geom);
-- 按时间段查轨迹
CREATE INDEX IF NOT EXISTS idx_track_time      ON track (start_time, end_time);
-- 停留点的时空检索
CREATE INDEX IF NOT EXISTS idx_stay_point_st   ON stay_point USING GIST (geom, start_time);

\echo ''
\echo '########## 验收：三张表 + 全部索引 ##########'
SELECT table_name, column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('track', 'track_point', 'stay_point')
ORDER BY table_name, ordinal_position;

\echo ''
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('track', 'track_point', 'stay_point')
ORDER BY tablename, indexname;

\echo ''
\echo '########## 补列（对已存在的老库生效）##########'
-- CREATE TABLE IF NOT EXISTS 不会给已存在的表加列，所以新加的列必须在这里单独补一句。
-- 加上它就保持了「整个脚本重跑一遍就和代码对齐」这个特性。
ALTER TABLE track_point ADD COLUMN IF NOT EXISTS is_outlier BOOLEAN NOT NULL DEFAULT false;

\echo ''
