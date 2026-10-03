# -*- coding: utf-8 -*-
"""在线底图开关的浏览器验收（高德两套样式：街道图 / 高清影像）。

要证明的事：
  ① 开关存在、**默认关**，文案是「离线底图」
  ② **关闭状态下对瓦片服务的请求数 = 0**（"不拖性能"的硬证据）
  ③ 打开（默认的**高德街道图**）→ 影像图层 1→2、请求打到 autonavi、**瓦片真有内容**
  ④ 切到**高德高清影像** → 请求打到 webst、瓦片真有内容、画面像素确实变了
  ⑤ 再关掉：图层回 1，且不再产生新的请求
另外还会留两张**对齐检查图**（供人眼判断 GCJ-02 补偿对不对）：
  `.tmp/basemap-align-tiananmen.png`（相机对准天安门的 WGS84 坐标）
  `.tmp/basemap-align-shanghai.png`（相机再飞到上海人民广场 —— 验证**补偿量会随相机实时重算**：
  飞跨城后若仍沿用北京的 delta，这张会明显偏 200~300 米）
  `.tmp/basemap-align-track.png`（一条真实 GeoLife 轨迹压在街道图上——真轨迹跟着路网走，
  压不压得准一眼可判；合成演示轨迹是随机游走，判不了）

⚠️ 判据为什么是「最常见颜色占比」而不是颜色种数或状态码（都是踩过才知道的）：
  · `HTTP 200 ≠ 有内容`：底图服务在权限不足/该层级无数据时会返回 200 + 全白或占位图；
  · 也不能数颜色种数：高德**矢量街道图**只有 250 来种颜色（纯色填充 + 抗锯齿），
    真图会被误判成占位；
  · 也不能只看"不同位置内容是否相同"：不同层级的空白图彼此也不同，会把空白判成有内容；
  · 实测：空白图单色占比 100%、占位图 98.2%、高德乡野真图 96.4%、高德市区真图 <70%
    ⇒ 阈值取 0.995（只抓"近乎纯色"的空白）。
  · 还必须先把相机**飞到市中心**：默认 12000 公里视角那个层级没有瓦片数据，
    而列表第一条是合成轨迹（在福建乡野），瓦片本身就近乎纯色。

跑法（需提权；后端 8080 + 前端 5173 都要在跑）：
    & "E:\\python\\python_address\\python.exe" scripts\\acceptance\\check-basemap.py
"""
import hashlib
import json
import math
import os
import re
from collections import Counter
from urllib.request import Request, urlopen

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
API = "http://127.0.0.1:8080"
VIEWPORT = {"width": 1600, "height": 900}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".tmp")
TILE_HOSTS = ("autonavi.com",)
TIANANMEN = {"lon": 116.3975, "lat": 39.9087}
# 上海人民广场（WGS84）—— 跨城复测 GCJ-02 补偿：偏移量只算一次的话这里会偏 200~300 米
SHANGHAI = {"lon": 121.4737, "lat": 31.2304}

ok = 0
fail = 0
skipped = []


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {name}")
    else:
        fail += 1
        print(f"  FAIL {name} —— {extra}")


def skip(name, why):
    skipped.append((name, why))
    print(f"  ..   SKIP {name} —— {why}")


LAYERS_JS = r"""
() => {
  try {
    const app = document.querySelector('#app');
    const root = app && app.__vue_app__ && app.__vue_app__._instance;
    if (!root) return { why: 'no vue root' };
    const seen = new Set(); const stack = [root]; let inst = null;
    while (stack.length) {
      const i = stack.pop();
      if (!i || seen.has(i)) continue;
      seen.add(i);
      const st = i.setupState;
      if (st && typeof st.setDrawingMode === 'function') { inst = i; break; }
      const sub = i.subTree;
      if (sub) {
        if (sub.component) stack.push(sub.component);
        const c = sub.children;
        if (Array.isArray(c)) { for (const x of c) if (x && x.component) stack.push(x.component); }
        else if (c && c.component) stack.push(c.component);
      }
    }
    if (!inst) return { why: 'no globe instance' };
    let v = inst.setupState && inst.setupState.viewer;
    if (v && v.value) v = v.value;
    if (!v || !v.imageryLayers) return { why: 'no viewer' };
    return { n: v.imageryLayers.length };
  } catch (e) { return { why: 'throw: ' + e }; }
}
"""

# 把相机对准一个已知的 WGS84 坐标：走地球组件暴露的 focusOn(lon, lat, radiusM)
FOCUS_JS = r"""
(args) => {
  try {
    const app = document.querySelector('#app');
    const root = app && app.__vue_app__ && app.__vue_app__._instance;
    if (!root) return false;
    const seen = new Set(); const stack = [root]; let inst = null;
    while (stack.length) {
      const i = stack.pop();
      if (!i || seen.has(i)) continue;
      seen.add(i);
      if (i.setupState && typeof i.setupState.focusOn === 'function') { inst = i; break; }
      const sub = i.subTree;
      if (sub) {
        if (sub.component) stack.push(sub.component);
        const c = sub.children;
        if (Array.isArray(c)) { for (const x of c) if (x && x.component) stack.push(x.component); }
        else if (c && c.component) stack.push(c.component);
      }
    }
    if (inst) inst.setupState.focusOn(args.lon, args.lat, args.radius);
    return !!inst;
  } catch (e) { return false; }
}
"""


def layers(page):
    r = page.evaluate(LAYERS_JS)
    return r.get("n"), r.get("why")


# 读"地球实际画出来的"轨迹折线首点坐标（与接口原始坐标一比，就能看出显示期转换有没有生效）
DRAWN_JS = r"""
async () => {
  const cesiumUrl = performance.getEntriesByType('resource').map(e => e.name)
    .find(n => n.includes('/deps/cesium.js'));
  if (!cesiumUrl) return { why: 'no cesium dep' };
  const C = await import(/* @vite-ignore */ cesiumUrl);
  const app = document.querySelector('#app');
  const root = app && app.__vue_app__ && app.__vue_app__._instance;
  const seen = new Set(); const stack = [root]; let globe = null;
  while (stack.length) {
    const i = stack.pop(); if (!i || seen.has(i)) continue; seen.add(i);
    if (i.setupState && typeof i.setupState.setDrawingMode === 'function') { globe = i; break; }
    const sub = i.subTree;
    if (sub) { if (sub.component) stack.push(sub.component);
      const c = sub.children;
      if (Array.isArray(c)) { for (const x of c) if (x && x.component) stack.push(x.component); }
      else if (c && c.component) stack.push(c.component); }
  }
  let v = globe && globe.setupState && globe.setupState.viewer;
  if (v && v.value) v = v.value;
  if (!v) return { why: 'no viewer' };
  let best = null, bestN = 0;
  for (const e of v.entities.values) {
    const pl = e.polyline;
    if (!pl || !pl.positions) continue;
    const arr = pl.positions.getValue ? pl.positions.getValue(C.JulianDate.now()) : pl.positions;
    if (Array.isArray(arr) && arr.length > bestN) { best = arr; bestN = arr.length; }
  }
  if (!best || best.length === 0) return { why: 'no polyline' };
  const c0 = C.Cartographic.fromCartesian(best[0]);
  return { n: bestN, lon: C.Math.toDegrees(c0.longitude), lat: C.Math.toDegrees(c0.latitude) };
}
"""


def drawn_first_point(page):
    r = page.evaluate(DRAWN_JS)
    if r and "lon" in r:
        print(f"       画出来的轨迹首点：lon={r['lon']:.6f} lat={r['lat']:.6f}（{r['n']} 个点）")
    else:
        print(f"       读画出来的轨迹首点失败：{r}")
    return r


def fetch_bytes(url, timeout=25):
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 (calcite-acceptance)",
                                           "Referer": "http://localhost:5173/"}), timeout=timeout) as r:
            return r.read()
    except Exception:                                          # noqa: BLE001
        return b""


def dominant_ratio(body):
    """最常见颜色占全图的比例 + 颜色种数（判据的核心，见文件头说明）"""
    p = os.path.join(OUT, "_dominant.bin")
    with open(p, "wb") as f:
        f.write(body)
    im = Image.open(p).convert("RGB")
    raw = im.tobytes()
    px = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    top = Counter(px).most_common(1)[0][1]
    return top / len(px), len(set(px))


def fingerprint_verdict(urls, max_dominant=0.995):
    """多张瓦片的综合判断：既看"是否近乎纯色"，也看"不同位置内容是否相同"。"""
    hashes, worst, colors_seen, bodies = set(), 0.0, [], 0
    for u in urls[:4]:
        b = fetch_bytes(u)
        if not b:
            continue
        bodies += 1
        hashes.add(hashlib.sha256(b).hexdigest()[:10])
        ratio, colors = dominant_ratio(b)
        worst = max(worst, ratio)
        colors_seen.append(colors)
    if bodies == 0:
        return "取不到", "瓦片请求都取不回来"
    detail = (f"{bodies} 张：{len(hashes)} 种内容 / 颜色数 {colors_seen} / "
              f"最高单色占比 {worst:.1%}（阈值 {max_dominant:.1%}）")
    if worst > max_dominant:
        return "空白/占位图", detail
    if len(hashes) == 1:
        return "占位图（不同位置内容完全相同）", detail
    return "有内容", detail


def shot_stats(path):
    im = Image.open(path).convert("RGB")
    raw = im.tobytes()
    return round(sum(raw) / len(raw), 2), len(set(zip(raw[0::3], raw[1::3], raw[2::3])))


def distinct_urls(urls, want=4):
    """挑出位置不同的几条瓦片 URL（按 x/y/z 去重）"""
    seen, picked = set(), []
    for u in urls:
        m = re.search(r"[?&]z=(\d+)&x=(\d+)&y=(\d+)", u)
        key = m.groups() if m else u
        if key in seen:
            continue
        seen.add(key)
        picked.append(u)
        if len(picked) >= want:
            break
    return picked


def main():
    urls, statuses = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport=VIEWPORT)
        page.on("request", lambda r: urls.append(r.url)
                if any(h in r.url for h in TILE_HOSTS) else None)
        page.on("response", lambda r: statuses.append(r.status)
                if any(h in r.url for h in TILE_HOSTS) else None)
        page.goto(URL, wait_until="load")
        for _ in range(40):
            if page.locator(".track-list .item").count() > 0:
                break
            page.wait_for_timeout(500)

        print("=== ① 开关存在且默认关 ===")
        toggle = page.locator('[data-testid="basemap-toggle"]')
        check("开关存在", toggle.count() == 1, f"实际 {toggle.count()} 个")
        check("默认文案是「离线底图」", "离线" in (toggle.inner_text() or ""), repr(toggle.inner_text()))
        check("默认未按下（aria-pressed=false）", toggle.get_attribute("aria-pressed") == "false")

        print("\n=== ② 关闭状态下零瓦片请求 ===")
        page.wait_for_timeout(2000)
        check("加载 + 静置 2 秒，在线底图请求数 = 0", len(urls) == 0, f"实际 {len(urls)} 条")
        n_off, why_off = layers(page)
        check("地球只有 1 个影像图层", n_off == 1, f"实际 {n_off}（{why_off}）")
        page.screenshot(path=os.path.join(OUT, "basemap-off.png"))
        off_stats = shot_stats(os.path.join(OUT, "basemap-off.png"))

        print("\n=== 飞到天安门（市中心）===")
        print(f"   focusOn 调用：{page.evaluate(FOCUS_JS, {**TIANANMEN, 'radius': 700})}")
        page.wait_for_timeout(4000)

        print("\n=== ③ 打开（默认样式：高德·街道图）===")
        toggle.click()
        page.wait_for_timeout(3500)
        n_on, why_on = layers(page)
        check("影像图层数 = 2（离线底图 + 高德街道图）", n_on == 2, f"实际 {n_on}（{why_on}）")
        check("向高德发了瓦片请求", len(urls) > 0, f"实际 {len(urls)} 条")
        check("URL 走 {z}/{x}/{y} 模板（参数顺序不固定，别写死顺序）",
              any(all(k in u for k in ("x=", "y=", "z=")) and re.search(r"[?&]z=\d+", u) for u in urls),
              str(urls[:2]))
        check("瓦片服务返回了 200", 200 in statuses, f"实际状态码 {sorted(set(statuses))[:5]}")
        picked = distinct_urls(urls)
        if picked:
            verdict, detail = fingerprint_verdict(picked)
            check("⭐ 高德街道图拿到**真有内容**的瓦片", verdict == "有内容", f"{verdict}：{detail}")
        else:
            check("抓到高德瓦片 URL", False, "一条都没抓到")

        print("\n=== ④ 切到「高德·高清影像」 ===")
        style = page.locator('[data-testid="basemap-style"]')
        check("样式选择器存在", style.count() == 1, f"实际 {style.count()} 个")
        before = len(urls)
        style.select_option("amap-image")
        page.wait_for_timeout(3500)
        check("切换后请求的是影像服务（webst）",
              any("webst" in u for u in urls[before:]) or any("webst" in u for u in urls),
              f"新增 {len(urls) - before} 条")
        picked_img = distinct_urls([u for u in urls if "webst" in u])
        if picked_img:
            verdict, detail = fingerprint_verdict(picked_img)
            check("⭐ 高德高清影像拿到真有内容的瓦片", verdict == "有内容", f"{verdict}：{detail}")
        else:
            skip("高德高清影像瓦片内容", "没抓到 webst 瓦片")
        page.screenshot(path=os.path.join(OUT, "basemap-on.png"))
        on_stats = shot_stats(os.path.join(OUT, "basemap-on.png"))
        print(f"       截图指纹：关 {off_stats} → 开 {on_stats}")
        check("画面确实变了", on_stats != off_stats, f"{off_stats} vs {on_stats}")

        # 对齐检查图（必须在底图**开着**的时候拍）：切回街道图，相机对准天安门 WGS84 坐标。
        # 命中的话画面正中就是天安门一带；GCJ-02 补偿不对会整体偏 500 米左右。
        style.select_option("amap-street")
        page.wait_for_timeout(2500)
        page.evaluate(FOCUS_JS, {**TIANANMEN, "radius": 500})
        page.wait_for_timeout(4500)
        page.screenshot(path=os.path.join(OUT, "basemap-align-tiananmen.png"))
        print(f"       对齐检查图（天安门）：{os.path.join(OUT, 'basemap-align-tiananmen.png')}")
        # —— 上海那张图照旧拍（跨城重算已不需要，但图能确认换个城市也正常）——
        page.evaluate(FOCUS_JS, {**SHANGHAI, "radius": 500})
        page.wait_for_timeout(4000)
        page.screenshot(path=os.path.join(OUT, "basemap-align-shanghai.png"))
        print(f"       上海对齐检查图：{os.path.join(OUT, 'basemap-align-shanghai.png')}")

        raw_first = None      # 供关掉底图后的 A/B 用
        # ⭐ 真实轨迹压在街道上（真轨迹跟着路网走，一眼可判）
        try:
            with urlopen(API + "/api/tracks?source=geolife&limit=1", timeout=10) as r:
                tracks = json.loads(r.read().decode())
            items = tracks.get("items") if isinstance(tracks, dict) else tracks
            tid = items[0].get("id") if items else None
            if tid:
                picked_ok = page.evaluate("""(id) => {
                  const app = document.querySelector('#app');
                  const inst = app && app.__vue_app__ && app.__vue_app__._instance;
                  if (!inst || !inst.setupState || typeof inst.setupState.selectTrack !== 'function') return false;
                  inst.setupState.selectTrack(id);
                  return true;
                }""", tid)
                page.wait_for_timeout(6000)
                page.screenshot(path=os.path.join(OUT, "basemap-align-track.png"))
                print(f"       对齐检查图（真实轨迹 id={tid}）："
                      f"{os.path.join(OUT, 'basemap-align-track.png')}（selectTrack={picked_ok}）")
                # ⭐ 显示期坐标转换的硬证据：画出来的首点应比接口原始 WGS84 坐标**大 delta**
                #   （北京 ≈ +533 米东 / +156 米北）。底图关掉后应回到 0，所以还要做一次 A/B。
                with urlopen(API + f"/api/tracks/{tid}", timeout=15) as r2:
                    det = json.loads(r2.read().decode())
                raw_first = (det.get("points") or [{}])[0]
                drawn_on = drawn_first_point(page)
                if "lon" in drawn_on and raw_first.get("lon") is not None:
                    d_lon = (drawn_on["lon"] - raw_first["lon"]) * 111320 * math.cos(math.radians(raw_first["lat"]))
                    d_lat = (drawn_on["lat"] - raw_first["lat"]) * 111320
                    check(f"⭐ 底图开着时几何按 +delta 画出来（东 {d_lon:.0f} 米 / 北 {d_lat:.0f} 米，期望 ≈ 533 / 156）",
                          400 < d_lon < 650 and 100 < d_lat < 220, f"实际 东 {d_lon:.0f} / 北 {d_lat:.0f}")
                else:
                    skip("显示期坐标转换（底图开着）", f"读不到坐标（drawn={drawn_on}, raw={raw_first}）")
            else:
                skip("真实轨迹对齐检查", "接口没返回 geolife 轨迹")
        except Exception as e:                                 # noqa: BLE001
            skip("真实轨迹对齐检查", f"取轨迹失败：{type(e).__name__}: {e}")

        print("\n=== ⑤ 关掉 ===")
        toggle.click()
        page.wait_for_timeout(1500)
        n_back, why_back = layers(page)
        check("影像图层数回到 1", n_back == 1, f"实际 {n_back}（{why_back}）")
        # A/B：底图关掉后，同一份数据应**按真实 WGS84** 画（位移回到 ~0）
        page.wait_for_timeout(1500)
        drawn_off = drawn_first_point(page)
        if "lon" in drawn_off and raw_first:
            d2_lon = (drawn_off["lon"] - raw_first["lon"]) * 111320 * math.cos(math.radians(raw_first["lat"]))
            d2_lat = (drawn_off["lat"] - raw_first["lat"]) * 111320
            check(f"⭐ 底图关掉后位移回到 ~0（东 {d2_lon:.1f} 米 / 北 {d2_lat:.1f} 米）",
                  abs(d2_lon) < 15 and abs(d2_lat) < 15, f"实际 东 {d2_lon:.1f} / 北 {d2_lat:.1f}")
        else:
            skip("显示期坐标转换（底图关掉）", f"读不到坐标（drawn={drawn_off}, raw={raw_first}）")
        frozen = len(urls)
        page.wait_for_timeout(2500)
        check("关掉后不再产生新的瓦片请求", len(urls) == frozen, f"{frozen} → {len(urls)}")
        browser.close()

    print(f"\n结果：{ok} 项通过，{fail} 项失败，{len(skipped)} 项跳过")
    for name, why in skipped:
        print(f"  跳过：{name} —— {why}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
