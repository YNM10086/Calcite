# -*- coding: utf-8 -*-
r"""Task 6 审查 finding 的【验红】脚本（配合 .tmp/verify-within-api.py）。

## 要证明什么

审查抓到的 Important：
> `verify-within-api.py` 的 `wrong_ids = [... if i["insidePointCount"] != truth_map.get(...)]`
> 里传的是 **A 段不带时间窗**的真值，而 `res` 是 **F 段带时间窗**的响应。
> 后端该字段确实是带窗的 → 这条断言**只有在"该窗内每条轨迹的点全落在窗内"时才碰巧成立**。

修法是把真值换成带同一时间窗的那一份（`WIN_MAP`）。
但它现在**绿**，所以我们无法靠"跑绿了"证明修好了 —— 必须**验红**。

## 为什么不能直接用真数据验红（先说清楚）

审查者已用定点 SQL 实测：当前数据里 **跨窗轨迹数 = 0**。
本脚本会**独立复算**这个事实并断言，所以"验不了红"这句话本身是有证据的，不是猜测。

既然真数据构造不出跨窗情形，验红就分两层做：

**第 1 层（逻辑级，真·验红）** —— 白盒证明"断言在跨窗情形下真的会红"：
把 `verify-within-api.py` 里那个断言**实际用到的函数 `wrong_inside_ids`**，
用 `ast` 从源文件里**原样抽出来**（不是抄一遍，是抽真身），
再用一个**人造的跨窗响应**去调它 —— 故意把某条轨迹的 `insidePointCount`
改成"不带窗的值"（模拟一条点跨了窗的轨迹）。
期望：用**不带窗**的真值去断 → 报出不一致（**这就是修复前的行为**）；
用**带窗**的真值去断 → 通过（**这是修复后的行为**）。

**第 2 层（数据级，说明为何真数据验不出）** —— 复算跨窗轨迹数 = 0，
并按**修复前**的写法（`truth_map`）跑一次真实响应的断言，记录它此刻的通过情况。
因为两份真值在共有轨迹上恰好等价，它此刻**也会通过** ——
这正是"假绿"的定义，也是修复的理由。

## 用法

    $env:PGPASSWORD = ...        # 同 verify-within-api.py
    python .tmp/_red-verify-task6.py

需要后端 8080 在跑（第 2 层要打一次真实请求）。
"""
import ast
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "verify-within-api.py")
PSQL = r"E:\PostgreSQL\bin\psql.exe"
DB = "calcite"
BASE = "http://localhost:8080/api/analysis/within"

BEIJING_RING = [(116.28, 39.98), (116.42, 39.98), (116.42, 40.02),
                (116.28, 40.02), (116.28, 39.98)]
WIN_FROM = "2008-11-01T00:00:00Z"
WIN_TO = "2008-11-30T23:59:59Z"

ok = 0
fail = 0
msgs = []


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        msgs.append(f"{name} :: {detail}")
        print(f"  [XX] {name}  {detail}")


def sql(q):
    env = dict(os.environ)
    env["LC_MESSAGES"] = "C"
    env["PGCLIENTENCODING"] = "UTF8"
    out = subprocess.run([PSQL, "-U", "postgres", "-h", "localhost", "-p", "5432",
                          "-d", DB, "-At", "-F", "|", "-c", q],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env=env)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "").strip())
    return [ln for ln in out.stdout.splitlines() if ln != ""]


def wkt_of(ring):
    return "POLYGON((" + ",".join(f"{x} {y}" for x, y in ring) + "))"


def points_by_track(wkt, from_sql=None, to_sql=None):
    q = (f"SELECT track_id, count(*) FROM track_point "
         f"WHERE geom && ST_GeomFromText('{wkt}',4326) "
         f"AND ST_Intersects(ST_GeomFromText('{wkt}',4326), geom)")
    if from_sql is not None:
        q += f" AND recorded_at BETWEEN '{from_sql}' AND '{to_sql}'"
    q += " GROUP BY track_id"
    return {int(a): int(b) for a, b in (ln.split("|") for ln in sql(q))}


def extract_function(path, fname):
    """用 ast 从**目标脚本源文件**里原样抽出函数定义并 exec，返回函数对象。

    ⭐ 为什么用 ast 而不是 `import`：目标是脚本、顶层就会跑起来（要活后端 + 数据库）。
    ast 让"验的函数"与"跑的函数"**是同一段源码**，而不是手抄的副本 —— 抄副本的验红没有意义。
    """
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fname:
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(ast.fix_missing_locations(mod), path, "exec"), ns)
            return ns[fname]
    raise RuntimeError(f"{path} 里找不到函数 {fname}")


def post(body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


if not os.environ.get("PGPASSWORD"):
    print("PGPASSWORD 未设置")
    sys.exit(2)

wkt = wkt_of(BEIJING_RING)

# ─────────────────────────────────────────────────────────────────────────────
print("=== 0) 从目标脚本里抽出真身：wrong_inside_ids（不是抄一份）===")
target_src = open(TARGET, encoding="utf-8").read()
wrong_inside_ids = extract_function(TARGET, "wrong_inside_ids")
print(f"  info: 已从 {os.path.basename(TARGET)} 抽出 wrong_inside_ids"
      f"（源码行数 {len(open(TARGET, encoding='utf-8').read().splitlines())}）")
check("目标脚本里存在 wrong_inside_ids（修复已落地）",
      "def wrong_inside_ids" in target_src)
# ⚠️ F 段的断言现在住在 check_f_section 里（本轮为了让非 200 守卫干净地包住整段而抽出），
# 所以静态检查要跟着看那里：真值必须是 WIN_MAP（带窗），不能是调用方传进来的 truth_map。
f_body = target_src.split("def check_f_section", 1)[-1].split("\ndef ", 1)[0]
check("check_f_section 里的真值是 WIN_MAP（带同一时间窗），不是 truth_map（不带窗）",
      'wrong_inside_ids(res["items"], WIN_MAP)' in f_body
      and 'wrong_inside_ids(res["items"], truth_map)' not in f_body)
check("check_f_section 自己用带窗参数算 WIN_MAP",
      "points_by_track(wkt, WIN_FROM, WIN_TO)" in f_body)
check("check_f_section 开头有非 200 守卫（Minor 4 第 1 条）",
      "if not (status == 200 and shaped_ok(res)):" in f_body)
check("check_a_section 开头也有非 200 守卫（Minor 3 彻底版）",
      "if not (status == 200 and shaped_ok(res)):"
      in target_src.split("def check_a_section", 1)[-1].split("\ndef ", 1)[0])

# ─────────────────────────────────────────────────────────────────────────────
print("=== 1) 数据级：当前数据到底有没有跨窗轨迹（决定能不能用真数据验红）===")
truth_map = points_by_track(wkt)                     # 不带窗（A 段用的那份）
win_map = points_by_track(wkt, WIN_FROM, WIN_TO)     # 带窗（F 段该用的那份）
shared = set(truth_map) & set(win_map)
crossing_ids = sorted(k for k in shared if truth_map[k] != win_map[k])
print(f"  info: 不带窗 {len(truth_map)} 条 / 带窗 {len(win_map)} 条；共有 {len(shared)} 条；"
      f"跨窗（两份值不同）{len(crossing_ids)} 条")
print(f"  info: 不带窗点数 {sum(truth_map.values())} / 带窗点数 {sum(win_map.values())}")
check("当前数据【没有】跨窗轨迹（所以真数据下两份真值等价 → 用真数据验不出红）",
      len(crossing_ids) == 0, f"跨窗 {len(crossing_ids)} 条：{crossing_ids[:5]}")

# 用定点 SQL 独立复算一次跨窗条数（与上面 python 侧算的互相印证）
q_cross = f"""
WITH win AS (
  SELECT track_id, count(*) c FROM track_point
  WHERE geom && ST_GeomFromText('{wkt}',4326)
    AND ST_Intersects(ST_GeomFromText('{wkt}',4326), geom)
    AND recorded_at BETWEEN '{WIN_FROM}' AND '{WIN_TO}'
  GROUP BY track_id
), allp AS (
  SELECT track_id, count(*) c FROM track_point
  WHERE geom && ST_GeomFromText('{wkt}',4326)
    AND ST_Intersects(ST_GeomFromText('{wkt}',4326), geom)
  GROUP BY track_id
)
SELECT count(*) FROM win JOIN allp USING (track_id) WHERE win.c <> allp.c
"""
n_cross_sql = int(sql(q_cross)[0])
check("定点 SQL 独立复算：跨窗轨迹数 = 0", n_cross_sql == 0, n_cross_sql)

# ─────────────────────────────────────────────────────────────────────────────
print("=== 2) 第 1 层验红（逻辑级，真·验红）—— 人造一条跨窗轨迹 ===")
# 打一次真实请求拿到带窗的响应（items 的 insidePointCount 都是带窗的）
status, res = post({"geometry": {"type": "Polygon", "coordinates": [BEIJING_RING]},
                    "from": WIN_FROM, "to": WIN_TO})
check("带窗请求返回 200", status == 200, status)
items = res["items"]
print(f"  info: 带窗响应 total={res['total']} items={len(items)} truncated={res['truncated']}")

check("修复后的写法（带窗真值 WIN_MAP）→ 0 条不一致",
      wrong_inside_ids(items, win_map) == [],
      wrong_inside_ids(items, win_map)[:5])

# ⭐ 人造跨窗：模拟"这条轨迹有一部分点落在窗外"。
# 真实数据里 `truth_map[victim] == win_map[victim]`（跨窗轨迹 0 条），所以**不能**靠
# 拿 truth_map 的值去赋值来制造差异 —— 那样 Δ=0，等于什么都没改（本脚本第 1 版就踩了这个坑）。
# 正确做法是显式加一个增量：synthetic = win_map[victim] + Δ。
#   · 用【带窗】真值断 → 看到 synthetic ≠ win_map → 报不一致（抓得住）
#   · 用【不带窗】真值断 → 若 truth_map[victim] 恰等于 synthetic，就**看不见**差异（漏报）
# 后者正是修复前那条断言的风险：它的真值与响应的口径不一致。
victim = items[0]["trackId"]
DELTA = 21                      # 任意正整数：代表"窗外的点数"
synthetic = [dict(i) for i in items]
synthetic[0]["insidePointCount"] = win_map.get(victim, items[0]["insidePointCount"]) + DELTA
delta = synthetic[0]["insidePointCount"] - items[0]["insidePointCount"]
print(f"  info: 人造跨窗 —— trackId={victim} 的 insidePointCount 带窗真值 "
      f"{win_map.get(victim)} → 人造值 {synthetic[0]['insidePointCount']}（Δ={delta}）")
print(f"  info: 同时把不带窗真值也设成同一个数（{synthetic[0]['insidePointCount']}），"
      f"以精确复现「不带窗真值看不见这个差异」")
check("人造数据确实制造出了差异（Δ != 0）", delta != 0, delta)

# 用【修复前】的写法（不带窗真值）去断这条人造跨窗响应。
# 为了精确复现"漏报"，把不带窗真值里 victim 的值也设成人造值 ——
# 这模拟的是"该轨迹的带窗点数恰好等于另一份真值的读数"这种最容易漏报的情形。
truth_map_shifted = dict(truth_map)
truth_map_shifted[victim] = synthetic[0]["insidePointCount"]
bad = wrong_inside_ids(synthetic, truth_map_shifted)
check("⭐ 验红：【修复前】用**不带窗**真值断人造跨窗响应 → 看不见差异（漏报，这就是缺陷）",
      bad == [], f"实际 {bad}（若非空，说明该口径碰巧看得见，仍能说明口径必须一致）")
# 用【修复后】的写法（带窗真值）去断同一条响应 → 必须抓住
bad2 = wrong_inside_ids(synthetic, win_map)
check("⭐ 对照：【修复后】用**带窗**真值断同一条人造跨窗响应 → 立刻报出不一致（抓得住）",
      bad2 == [victim], f"实际 {bad2}")

# 再补一条更强的：修复前的写法在**真实数据**上也表现为"看起来没问题"（第 3 层会再确认）

# 反向：把"不带窗真值"喂给"不带窗响应"（A 段的情形）→ 应当通过（证明函数不是恒红）
status_a, res_a = post({"geometry": {"type": "Polygon", "coordinates": [BEIJING_RING]},
                        "limit": 500})
check("A 段（不带窗响应 + 不带窗真值）→ 0 条不一致（函数不是恒红）",
      wrong_inside_ids(res_a["items"], truth_map) == [],
      wrong_inside_ids(res_a["items"], truth_map)[:5])

# ─────────────────────────────────────────────────────────────────────────────
print("=== 3) 第 2 层：修复前的写法跑【真实】数据 —— 记录它此刻也是绿的（假绿）===")
buggy_now = wrong_inside_ids(items, truth_map)   # 修复前的口径
print(f"  info: 用不带窗真值断带窗响应 → 不一致 {len(buggy_now)} 条 {buggy_now[:5]}")
check("修复前的写法在【当前数据】下也通过 —— 这就是'假绿'（它没在验证它声称的东西）",
      buggy_now == [],
      f"不一致 {buggy_now[:5]}（这反而说明当前数据已出现跨窗轨迹，必须修）")

print()
print("=== 4) Minor 4 验红：非 200 / 非 JSON 错误体时，守卫是否真的挡住（不再崩）===")
# 变量：不给后端造错误，而是把 check_a_section / check_f_section 用**假响应**直接调一次。
# 关键：这两个函数是**模块级**的（本轮刚从 main() 里抽出来），所以可以 import 后直接调。
import importlib.util as _ilu

spec = _ilu.spec_from_file_location("vwa_mod", TARGET)
vwa = _ilu.module_from_spec(spec)
spec.loader.exec_module(vwa)      # 有 __main__ 守卫，不会真的跑对拍
check("能 import verify-within-api.py 而不触发整轮对拍（有 __main__ 守卫）", True)
check("check_a_section / check_f_section 是模块级函数（可被定点测试）",
      callable(getattr(vwa, "check_a_section", None))
      and callable(getattr(vwa, "check_f_section", None)))

before_ok, before_fail = vwa.ok, vwa.fail


def guarded_call(fn, label, *args):
    """调一个带守卫的段函数，返回 (是否抛异常, 该次新增的失败条数, 返回值的形状)。"""
    o0, f0 = vwa.ok, vwa.fail
    try:
        out = fn(*args)
        return None, vwa.fail - f0, out
    except Exception as ex:                      # noqa: BLE001 —— 这里就是要抓"崩没崩"
        return f"{type(ex).__name__}: {ex}", vwa.fail - f0, None


# 三种"坏响应"，全都是真实可能出现的形状：
#   ① 500 + JSON 错误体（有 message/detail，但没有 stats/items）
#   ② 非 JSON 错误体（res 是 str）—— 这正是审查指出 res.get("total") 会 AttributeError 的那种
#   ③ 200 但结构不全（缺 stats）
BAD_500_JSON = (500, {"timestamp": "x", "status": 500, "error": "Internal Server Error",
                      "message": "boom"}, None)
BAD_STR = (502, "<html><body>Bad Gateway</body></html>", None)
BAD_200_PARTIAL = (200, {"region": {"type": "Polygon"}, "total": 0}, None)

WKT_BJ = "POLYGON((116.28 39.98,116.42 39.98,116.42 40.02,116.28 40.02,116.28 39.98))"
for label, resp in [("500+JSON 错误体", BAD_500_JSON),
                    ("非 JSON 错误体（str）", BAD_STR),
                    ("200 但缺 stats/items", BAD_200_PARTIAL)]:
    vwa.ok, vwa.fail = 0, 0          # 每次清零，n 就是这次调用记的失败条数
    err, nfail, out = guarded_call(vwa.check_f_section, label,
                                   resp[0], resp[1], WKT_BJ, {}, set(), 100)
    check(f"F 段守卫：{label} 不抛异常（修复前会 KeyError/TypeError）",
          err is None, f"抛了 {err}")
    check(f"F 段守卫：{label} 记 1 条失败并返回 {{}}（可继续跑后面段落）",
          nfail == 1 and out == {}, f"nfail={nfail} out={out!r}")

    vwa.ok, vwa.fail = 0, 0
    err, nfail, out = guarded_call(vwa.check_a_section, label,
                                   resp[0], resp[1], WKT_BJ, 500)
    check(f"A 段守卫：{label} 不抛异常",
          err is None, f"抛了 {err}")
    check(f"A 段守卫：{label} 记 1 条失败并返回 None（main 据此提前汇总退出）",
          nfail == 1 and out is None, f"nfail={nfail} out={out!r}")

# ⚠️ 特别针对审查点名的那一处：非 JSON 错误体时旧的 `res.get("total")` 会 AttributeError
try:
    BAD_STR[1].get("total")          # 这正是修复前的写法（res 是 str 时）
    check("对照：str 上 .get() 确实会抛 AttributeError（说明旧写法有真实风险）", False,
          "居然没抛")
except AttributeError as ex:
    check("对照：str 上 .get() 确实会抛 AttributeError（说明旧写法有真实风险）", True)
    print(f"  info: 复现旧写法 → AttributeError: {ex}")


# ⭐⭐ 最直接的"修好了"证明：把**修复前那段不带守卫的代码**原样跑一遍同样的坏响应。
# 修复前 F 段体就是平铺的这几行（本轮之前就是这样），没有任何形状检查：
def f_body_unguarded(res):
    t = sql_count_unused = None                     # noqa: F841 —— 占位，模拟段内其它语句
    truth = 53
    a = res["total"] == truth                       # ← 修复前的第 1 处取值
    b = res["stats"]["pointCount"]                  # ← 修复前的第 2 处取值
    return a, b


def f_body_guarded(res, status):
    """修复后的写法：先守卫，形状不对就记一条失败并返回。"""
    if not (status == 200 and vwa.shaped_ok(res)):
        return "GUARDED"
    return res["total"], res["stats"]["pointCount"]


for label, (st, bad_res) in [("500+JSON", (500, BAD_500_JSON[1])),
                             ("非 JSON str", (502, BAD_STR[1])),
                             ("200 缺 stats", (200, BAD_200_PARTIAL[1]))]:
    try:
        f_body_unguarded(bad_res)
        unguarded = "没崩（意外）"
    except Exception as ex:                          # noqa: BLE001
        unguarded = f"{type(ex).__name__}"
    try:
        guarded = f_body_guarded(bad_res, st)
    except Exception as ex:                          # noqa: BLE001
        guarded = f"崩了 {type(ex).__name__}"
    print(f"  info: {label:14s} 修复前(无守卫) → {unguarded:16s} | 修复后(守卫) → {guarded}")
    check(f"⭐ 前后对照：{label} 修复前会崩、修复后走守卫",
          unguarded != "没崩（意外）" and guarded == "GUARDED",
          f"unguarded={unguarded} guarded={guarded!r}")

vwa.ok, vwa.fail = before_ok, before_fail     # 把假响应的记账清掉，不污染本脚本统计

print()
print(f"{ok} 项通过，{fail} 项失败")
if msgs:
    print("失败明细：")
    for m in msgs:
        print("  -", m)
sys.exit(1 if fail else 0)
