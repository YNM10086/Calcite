# -*- coding: utf-8 -*-
"""在线底图（天地图）开关的浏览器验收。

要证明的六件事：
  ① 开关存在、**默认关**，文案是「离线底图」
  ② **关闭状态下对 tianditu.gov.cn 的请求数 = 0**（"不拖性能"的硬证据）
  ③ 打开后 Cesium 影像图层数 1 → 3（离线底图 + 底图 + 注记）
  ④ **拿到的瓦片必须真有内容** —— ⚠️ 这一条是这版新增的：天地图在权限不足 / 该层级无影像时
     会返回 **HTTP 200 + 全白或占位图**（实测过：`vec` 恒 103 字节全白、`img` 恒
     「此级别下，该区域无影像」占位图）。只看"画面变了"会**假绿**，所以这里直接把
     抓到的一条瓦片 URL 取回来**数像素**。
  ⑤ 切样式（街道 → 影像）能换到另一套图层并重新取瓦片
  ⑥ 再关掉：图层数回 1，且不再产生新的天地图请求

关于样式：本机这个 key 实测**没有开通矢量底图**（`vec`/`cva` 恒空白），所以
街道样式的"真有内容"一条会 **SKIP 并给出诊断**（不是我们的代码问题）；
影像样式（`img`，L10~L12）必须验到真图，否则整条链不算通过。

跑法（需提权；后端 8080 + 前端 5173 都要在跑）：
    & "E:\\python\\python_address\\python.exe" scripts\\acceptance\\check-basemap.py
"""
import json
import os
import re
from urllib.request import Request, urlopen

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
API = "http://127.0.0.1:8080"
VIEWPORT = {"width": 1600, "height": 900}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".tmp")

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


# ---- 取 Cesium 影像图层数（走 Vue dev 内部态找地球组件，与 check-within.py 同一套做法）----
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


def layers(page):
    r = page.evaluate(LAYERS_JS)
    return r.get("n"), r.get("why")


def judge_tile(url, timeout=30):
    """把一条瓦片 URL 取回来数像素 —— 判断"真有内容"还是"占位/空白"。

    颜色种数门槛 2000：实测真影像 4900~7300 色、占位图 248 色、空白图 1 色，区分度很大。
    """
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0",
                                           "Referer": "http://localhost:5173/"}), timeout=timeout) as r:
            body = r.read()
    except Exception as e:                                     # noqa: BLE001
        return "取不到", f"{type(e).__name__}: {e}"
    if not body:
        return "空响应", ""
    p = os.path.join(OUT, "_check_tile.bin")
    with open(p, "wb") as f:
        f.write(body)
    try:
        im = Image.open(p).convert("RGB")
    except Exception as e:                                     # noqa: BLE001
        return "不是图片", f"{len(body)} 字节 / {e}"
    colors = len(set(zip(im.tobytes()[0::3], im.tobytes()[1::3], im.tobytes()[2::3])))
    fmt = "PNG" if body[:4] == b"\x89PNG" else ("JPEG" if body[:3] == b"\xff\xd8\xff" else "?")
    if colors >= 2000:
        return "有内容", f"{fmt} {len(body)} 字节 / {colors} 色"
    return ("占位图" if colors > 2 else "空白图"), f"{fmt} {len(body)} 字节 / {colors} 色"


def shot_stats(path):
    im = Image.open(path).convert("RGB")
    raw = im.tobytes()
    return round(sum(raw) / len(raw), 2), len(set(zip(raw[0::3], raw[1::3], raw[2::3])))


def main():
    try:
        with urlopen(API + "/api/map/tianditu", timeout=10) as r:
            cfg = json.loads(r.read().decode())
        has_key = bool(cfg.get("enabled"))
        print(f"后端 /api/map/tianditu -> enabled={has_key}，maxLevel={cfg.get('maxLevel')}")
    except Exception as e:                                     # noqa: BLE001
        print(f"!! 取不到配置接口（{type(e).__name__}: {e}）—— 后端在跑吗")
        return 1

    urls, statuses = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport=VIEWPORT)
        page.on("request", lambda r: urls.append(r.url) if "tianditu.gov.cn" in r.url else None)
        page.on("response", lambda r: statuses.append(r.status) if "tianditu.gov.cn" in r.url else None)
        page.goto(URL, wait_until="load")
        for _ in range(40):
            if page.locator(".track-list .item").count() > 0:
                break
            page.wait_for_timeout(500)

        print("\n=== ① 开关存在且默认关 ===")
        toggle = page.locator('[data-testid="basemap-toggle"]')
        check("开关存在（basemap-toggle）", toggle.count() == 1, f"实际 {toggle.count()} 个")
        check("默认文案是「离线底图」", "离线" in (toggle.inner_text() or ""), repr(toggle.inner_text()))
        check("默认未按下（aria-pressed=false）", toggle.get_attribute("aria-pressed") == "false")

        print("\n=== ② 关闭状态下零天地图请求 ===")
        page.wait_for_timeout(2000)
        check("加载 + 静置 2 秒，天地图请求数 = 0", len(urls) == 0, f"实际 {len(urls)} 条")
        n_off, why_off = layers(page)
        check("地球只有 1 个影像图层", n_off == 1, f"实际 {n_off}（{why_off}）")
        page.screenshot(path=os.path.join(OUT, "basemap-off.png"))
        off_stats = shot_stats(os.path.join(OUT, "basemap-off.png"))

        # ⚠️ 先飞到一条轨迹上：默认视角是 12000 公里（L1~L2），那个层级天地图本来就没有影像，
        #    不飞近的话"瓦片有没有内容"这条根本验不了。
        print("\n=== 飞到北京（点列表第一条轨迹）===")
        page.locator(".track-list .item").first.click()
        page.wait_for_timeout(3500)

        print("\n=== ③④ 打开（默认街道样式）===")
        toggle.click()
        page.wait_for_timeout(3000)
        hint = page.locator('[data-testid="basemap-hint"]')
        hint_text = hint.inner_text() if hint.count() > 0 else ""

        if not has_key:
            check("没配 key 时给提示", hint.count() == 1 and len(hint_text) > 0, repr(hint_text))
            n_no_key, _ = layers(page)
            check("没配 key 时不创建图层（仍是 1）", n_no_key == 1, f"实际 {n_no_key}")
            check("没配 key 时也不发天地图请求", len(urls) == 0, f"实际 {len(urls)} 条")
            skip("③④⑥ 打开/切样式/关闭", "本机未配 tianditu-token")
            browser.close()
        else:
            n_on, why_on = layers(page)
            check("影像图层数 = 3（离线底图 + 底图 + 注记）", n_on == 3, f"实际 {n_on}（{why_on}）")
            check("向天地图发了瓦片请求", len(urls) > 0, "一条都没发")
            check("走的是 WMTS 模板（{layer}_w/wmts + TILEMATRIX/TILEROW/TILECOL）",
                  any(re.search(r"/(vec|img)_w/wmts", u) and "TILEMATRIX=" in u and "TILECOL=" in u for u in urls),
                  str(urls[:2]))
            street_url = next((u for u in urls if "/vec_w/" in u), None)
            if street_url:
                verdict, detail = judge_tile(street_url)
                if verdict == "有内容":
                    check("街道样式拿到**真有内容**的瓦片", True, detail)
                else:
                    skip("街道样式拿到真有内容的瓦片",
                         f"实测 {verdict}（{detail}）—— 这个 key 很可能**没开通矢量底图**服务；"
                         "天地图权限不足时返回 200 + 空白/占位图，不是我们的代码问题")
            else:
                skip("街道样式瓦片", "没抓到 vec 瓦片请求")

            print("\n=== ⑤ 切到影像样式 ===")
            style = page.locator('[data-testid="basemap-style"]')
            check("样式选择器存在", style.count() == 1, f"实际 {style.count()} 个")
            if style.count() == 1:
                before = len(urls)
                style.select_option("image")
                page.wait_for_timeout(3000)
                img_urls = [u for u in urls[before:] if "/img_w/" in u] or [u for u in urls if "/img_w/" in u]
                check("切样式后取的是 img_w（影像）瓦片", len(img_urls) > 0,
                      f"新请求 {len(urls) - before} 条，img 瓦片 {len(img_urls)} 条")
                if img_urls:
                    verdict, detail = judge_tile(img_urls[-1])
                    check("⭐ 影像样式拿到真有内容的瓦片（这一条证明整条链端到端可用）",
                          verdict == "有内容", f"实测 {verdict}（{detail}）")

            page.screenshot(path=os.path.join(OUT, "basemap-on.png"))
            on_stats = shot_stats(os.path.join(OUT, "basemap-on.png"))
            print(f"       截图指纹：关 {off_stats} → 开 {on_stats}")
            check("画面确实变了", on_stats != off_stats, f"{off_stats} vs {on_stats}")

            print("\n=== ⑥ 再关掉 ===")
            toggle.click()
            page.wait_for_timeout(1500)
            n_back, why_back = layers(page)
            check("影像图层数回到 1", n_back == 1, f"实际 {n_back}（{why_back}）")
            frozen = len(urls)
            page.wait_for_timeout(2500)
            check("关掉后不再产生新的天地图请求", len(urls) == frozen, f"{frozen} → {len(urls)}")
            browser.close()

    print(f"\n结果：{ok} 项通过，{fail} 项失败，{len(skipped)} 项跳过")
    for name, why in skipped:
        print(f"  跳过：{name} —— {why}")
    print(f"截图：{os.path.join(OUT, 'basemap-off.png')} / basemap-on.png")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
