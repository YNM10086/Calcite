# -*- coding: utf-8 -*-
"""在线底图（天地图）开关的浏览器验收。

要证明的四件事（对应设计里的"不拖性能"与"打开真的能看到东西"）：
  ① 开关存在、**默认关**，文案是「离线底图」
  ② **关闭状态下对 tianditu.gov.cn 的请求数 = 0**（这是"不拖性能"的硬证据，不是感觉）
  ③ 打开后：Cesium 的影像图层数从 1 变成 3（离线底图 + vec + cva），并真的向天地图取了瓦片
  ④ 再关掉：图层数回到 1，且**不再产生新的天地图请求**

另有一条优雅降级：没有配 key 时（`/api/map/tianditu` 返回 enabled=false），
点开关必须**给出提示且不创建图层**——这一条在没有 key 的机器上也能验，所以 ③④ 会 SKIP 而不是假绿。

跑法（需提权；后端 8080 + 前端 5173 都要在跑）：
    & "E:\\python\\python_address\\python.exe" scripts\\acceptance\\check-basemap.py
"""
import json
import re
import sys
import urllib.request
from playwright.sync_api import sync_playwright
from PIL import Image

URL = "http://localhost:5173"
API = "http://127.0.0.1:8080"
VIEWPORT = {"width": 1600, "height": 900}
SHOT_OFF = ".tmp/basemap-off.png"
SHOT_ON = ".tmp/basemap-on.png"

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


# 取 Cesium 的影像图层数：走 Vue 的 dev 内部态找到地球组件实例（与 check-within.py 同一套做法）
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


def shot_stats(path):
    """截图的像素指纹：平均亮度 + 颜色种数（底图换没换，这两个数必然变）

    用 tobytes() 而不是 getdata()：后者在 Pillow 14 会被移除（跑起来就一个 DeprecationWarning），
    而且逐像素 tuple 也更慢。
    """
    im = Image.open(path).convert("RGB")
    raw = im.tobytes()
    avg = sum(raw) / len(raw)
    colors = len(set(zip(raw[0::3], raw[1::3], raw[2::3])))
    return round(avg, 2), colors


def main():
    # 先看后端有没有配 key（决定 ③④ 是真验还是 SKIP）
    try:
        with urllib.request.urlopen(API + "/api/map/tianditu", timeout=10) as r:
            cfg = json.loads(r.read().decode())
        has_key = bool(cfg.get("enabled"))
        print(f"后端 /api/map/tianditu -> enabled={has_key}，maxLevel={cfg.get('maxLevel')}")
    except Exception as e:                                     # noqa: BLE001
        print(f"!! 取不到 /api/map/tianditu（{type(e).__name__}: {e}）—— 后端在跑吗")
        return 1

    tianditu_urls = []
    tianditu_status = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport=VIEWPORT)
        page.on("request", lambda r: tianditu_urls.append(r.url) if "tianditu.gov.cn" in r.url else None)
        # 记瓦片响应的状态码：只有真的 200 了，"画面变化"那条判据才有意义
        page.on("response", lambda r: tianditu_status.append(r.status)
                if "tianditu.gov.cn" in r.url else None)
        page.goto(URL, wait_until="load")
        for _ in range(40):                    # 等轨迹列表（后端活着）
            if page.locator(".track-list .item").count() > 0:
                break
            page.wait_for_timeout(500)

        print("\n=== ① 开关存在且默认关 ===")
        toggle = page.locator('[data-testid="basemap-toggle"]')
        check("开关存在（basemap-toggle）", toggle.count() == 1, f"实际 {toggle.count()} 个")
        label_off = toggle.inner_text() if toggle.count() == 1 else ""
        check("默认文案是「离线底图」", "离线" in label_off, f"实际 {label_off!r}")
        check("默认不是按下状态（aria-pressed=false）",
              toggle.get_attribute("aria-pressed") == "false", str(toggle.get_attribute("aria-pressed")))

        print("\n=== ② 关闭状态下零天地图请求（不拖性能的硬证据）===")
        page.wait_for_timeout(2000)            # 给页面足够时间去"犯错"：真发了请求就会出现在这里
        check("页面加载 + 静置 2 秒，天地图请求数 = 0", len(tianditu_urls) == 0,
              f"实际 {len(tianditu_urls)} 条：{tianditu_urls[:3]}")
        n_off, why_off = layers(page)
        check("地球只有 1 个影像图层（离线底图）", n_off == 1, f"实际 {n_off}（{why_off}）")
        page.screenshot(path=SHOT_OFF)
        off_stats = shot_stats(SHOT_OFF)
        print(f"       关闭态截图指纹：平均亮度={off_stats[0]}，颜色种数={off_stats[1]}")

        print("\n=== 点一下开关 ===")
        toggle.click()
        page.wait_for_timeout(2500)
        hint = page.locator('[data-testid="basemap-hint"]')
        hint_text = hint.inner_text() if hint.count() > 0 else ""

        if not has_key:
            print("\n=== ③④（本机没配 key，改验优雅降级）===")
            check("没配 key 时给出提示", hint.count() == 1 and len(hint_text) > 0, f"提示={hint_text!r}")
            check("提示里说清未配置与去哪配", ("未配置" in hint_text or "没配" in hint_text)
                  and "天地图" in hint_text, hint_text[:80])
            n_no_key, why_no_key = layers(page)
            check("没配 key 时**不创建**图层（仍是 1）", n_no_key == 1, f"实际 {n_no_key}（{why_no_key}）")
            check("没配 key 时也不会发天地图请求", len(tianditu_urls) == 0, f"实际 {len(tianditu_urls)} 条")
            skip("③ 打开后图层变 3 且真取到瓦片", "本机 application-local.yml 未配 tianditu-token")
            skip("④ 关掉后图层回 1 且不再新增请求", "同上")
        else:
            print("\n=== ③ 打开后：图层 3 个 + 真的取瓦片 ===")
            n_on, why_on = layers(page)
            check("影像图层数 = 3（离线底图 + vec + cva）", n_on == 3, f"实际 {n_on}（{why_on}）")
            check("向天地图发了瓦片请求", len(tianditu_urls) > 0, "一条都没发")
            check("瓦片 URL 走的是 t{s}.tianditu.gov.cn 的 WMTS 模板",
                  any(re.search(r"/t\d\.tianditu\.gov\.cn/(vec|cva)_w/wmts", u) for u in tianditu_urls),
                  str(tianditu_urls[:2]))
            check("瓦片 URL 带上了 TILEMATRIX/TILEROW/TILECOL",
                  any(("TILEMATRIX=" in u and "TILEROW=" in u and "TILECOL=" in u) for u in tianditu_urls),
                  str(tianditu_urls[:2]))
            n_before_shot = len(tianditu_urls)
            page.screenshot(path=SHOT_ON)
            on_stats = shot_stats(SHOT_ON)
            print(f"       打开态截图指纹：平均亮度={on_stats[0]}，颜色种数={on_stats[1]}"
                  f"（关闭态 {off_stats[0]} / {off_stats[1]}）")
            # ⚠️ 只有瓦片真的 200 了，"画面变了"才是对底图的判断；
            #    否则 403/404 的画面当然也不一样，但那是"没加载出来"，不能算通过。
            codes = sorted(set(tianditu_status))
            if 200 in tianditu_status:
                check("瓦片有 200 响应", True)
                check("画面确实变了（平均亮度或颜色种数不同）",
                      on_stats[0] != off_stats[0] or on_stats[1] != off_stats[1],
                      f"关闭 {off_stats} vs 打开 {on_stats}")
            else:
                check("向天地图发了瓦片请求（但没拿到 200）", len(tianditu_urls) > 0,
                      "一条都没发")
                skip("画面变化（瓦片真的贴到地球上）",
                     f"天地图没回 200，实际状态码 {codes[:5]} —— key 无效 / 域名白名单不认 localhost / 网络")
            check("（信息）打开后请求数在增长", len(tianditu_urls) >= n_before_shot)

            print("\n=== ④ 再关掉：图层回 1、不再新增请求 ===")
            toggle.click()
            page.wait_for_timeout(1500)
            n_back, why_back = layers(page)
            check("影像图层数回到 1", n_back == 1, f"实际 {n_back}（{why_back}）")
            frozen = len(tianditu_urls)
            page.wait_for_timeout(2500)        # 给被撤掉的图层"最后一次机会"去请求瓦片
            check("关掉后不再产生新的天地图请求", len(tianditu_urls) == frozen,
                  f"关掉后从 {frozen} 涨到 {len(tianditu_urls)}")

        browser.close()

    print(f"\n结果：{ok} 项通过，{fail} 项失败，{len(skipped)} 项跳过")
    for name, why in skipped:
        print(f"  跳过：{name} —— {why}")
    print("提醒：截图留在 .tmp/basemap-off.png 与 .tmp/basemap-on.png，可肉眼对比")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
