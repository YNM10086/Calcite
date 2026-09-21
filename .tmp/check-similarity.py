# -*- coding: utf-8 -*-
r"""轨迹相似度（M2 第四阶段）的浏览器验收。

用法（**必须提权 danger-full-access** —— Playwright 的浏览器子进程靠命名管道通信，
沙箱内 launch 直接 `PermissionError: [WinError 5] 拒绝访问`，和上一阶段一模一样）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp/check-similarity.py

前置条件：后端 8080 + 前端 5173 都在跑。

⚠️ 所有期望值都**从接口现取**，脚本里不写死任何条数（轨迹一多一少，"15 条"就废了 ——
第三阶段的教训：验收基线里写死的数字会随数据量一起失效）。

和第三阶段 `check-density.py` 一脉相承的四条规矩：
  ① 入口用 `http://localhost:5173/?track=20`（裸 URL 没选轨迹，第四档只会显示提示）
  ② 像素统计从**面板右边界**（问 DOM 要，不写死 x>=400）起算
  ③ 面板溢出 / 四视口 / 控制台零报错
  ④ 等"真的画出来"再断言：Cesium 的几何是异步 Primitive，必须给真实时间，
     不能用虚拟时钟（M1 的教训）

本脚本对实施计划原文的三处**必要偏离**（每一处都有实测依据）：

① 空态有两支，testid 不同（`SimilarityList.vue`）：
     matches 为空            → `similarity-empty`          （一个邻居都没有）
     matches 非空但被筛光    → `similarity-none-in-filter` （有匹配，只是没到阈值）
   `similarity-empty` 在当前真实数据上**不可达** —— 实测容差 50 米下
   **每一条都至少有一个邻居**（把容差压到 1 米才有个别孤立的），所以**不写那条注定红的断言**，
   只用 note() 说明。第二种空态则**真的造出来**：先从接口找一条「matches 非空、但最高相似度 < 90%」
   的主线，用 `?track=<aux>` 打开它，再把筛选切到 90% —— 这时列表里一条都不显示，
   应该出现的是 `similarity-none-in-filter` **而不是** `similarity-empty`。

② 第 11 项「点一条会飞」用 **warm 像素的包围盒**，并且带**静止对照**：
   先连拍两张量出相机静止时包围盒的自然漂移，再点第 2 条量变化量，判据是
   「变化量 > max(40px, 4×漂移)」。上一阶段的教训是**像素均值判据无齿**，所以这里不碰均值。

③ 第 12 项「切走相似档后叠加消失」不写"绝对归零"：停留点是**橙色**的
   （`Color.ORANGE`），本身就会贡献暖色像素（track 20 有 1 个停留点）。
   判据改成**同一相机下**暖色回落到"停留点档自己的基线 + 200px"，并且切走前必须真的
   有 > 1000 个暖色像素（否则这条判据本身是空的）。

像素判据用的「暖色」（覆盖色带浅米黄→深红里的橙/红段，排除地球底色的绿/蓝）：
    r > 170 and b < 150 and r - g > 45
它和匹配轨迹的实际颜色对得上：相似度 55%~91% 经 `simColor` → `rampColor` 得到
r∈[204,250]、g∈[29,142]、b∈[14,29]，全部命中；而主线是亮蓝 `rgb(127,209,255)`（r-g<0，不命中）。
"""
import asyncio
import json
import re
import sys
import urllib.parse
import urllib.request

from PIL import Image, ImageChops
from playwright.async_api import async_playwright

BARE_URL = "http://localhost:5173/"
URL = "http://localhost:5173/?track=20"
TRACK_ID = 20
# ⚠️ 必须和 App.vue 里 loadSimilarity 的 limit 一致，否则"期望条数"和列表对不上
LIMIT = 200
API = "http://localhost:8080"
SIM_API = "/api/analysis/similarity"
VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/similarity-shot.png"
# 曲线区上边界 = 播放条 46px + 曲线 140px。像素统计到这里截断，
# 免得把底部曲线/播放条的元件算成"地球上的暖色像素"。
MAP_BOTTOM = VIEW_H - 186

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


def note(text):
    print("    · " + text)


def get_json(path, timeout=300):
    with urllib.request.urlopen(API + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def warm(path, x_from, y_from=0, y_to=MAP_BOTTOM):
    """数暖色像素，并返回它的包围盒 (x0, y0, x1, y1)（没有就 None）。

    ⚠️ 面板必须排除（`x < x_from`）：真实截图里面板的相似度百分比是红/橙色的，
    实测贡献 360 个暖色像素，而且会把包围盒拖到 x=38（面板里面）。

    实现用 ImageChops 做通道运算（C 层，快），不是 Python 双层循环。
    等价性已用真实截图对拍过：与逐像素循环的**像素数与包围盒完全一致**
    （.tmp/sim-list.png / sim-filter90.png / sim-need-track.png / density-shot.png）。
    """
    img = Image.open(path).convert("RGB")
    w, h = img.size
    sub = img.crop((x_from, y_from, w, min(y_to, h)))
    r, g, b = sub.split()
    mask = ImageChops.multiply(
        ImageChops.multiply(
            r.point(lambda v: 255 if v > 170 else 0),
            ImageChops.subtract(r, g).point(lambda v: 255 if v > 45 else 0),
        ),
        b.point(lambda v: 255 if v < 150 else 0),
    )
    bb = mask.getbbox()
    if bb:
        bb = (bb[0] + x_from, bb[1] + y_from, bb[2] + x_from, bb[3] + y_from)
    return mask.histogram()[255], bb


def bbox_delta(a, b):
    """两个包围盒之间的最大边位移（任一为空 → None）。"""
    if not a or not b:
        return None
    return max(abs(a[i] - b[i]) for i in range(4))


def _first_int(text, pattern):
    m = re.search(pattern, text)
    return int(m.group(1).replace(",", "")) if m else None


READ_DOM = r"""() => {
    const pick = (sel) => {
        const el = document.querySelector(sel);
        return el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
    };
    const has = (sel) => !!document.querySelector(sel);
    const panel = document.querySelector('.panel');
    const pr = panel.getBoundingClientRect();
    const kids = [...panel.children];
    const last = kids.length ? kids[kids.length - 1].getBoundingClientRect() : null;
    const ms = document.querySelector('.mode-switch');
    const btns = [...document.querySelectorAll('.mode-switch button')];
    const tops = btns.map((b) => b.getBoundingClientRect().top);
    const h2s = [...document.querySelectorAll('.panel > h2')];
    const sel = document.querySelector('[data-testid="similarity-filter"]');
    return {
        baseline: pick('[data-testid="similarity-baseline"]'),
        compared: pick('[data-testid="similarity-compared"]'),
        listText: pick('[data-testid="similarity-list"]'),
        hasNeed: has('[data-testid="similarity-need-track"]'),
        hasList: has('[data-testid="similarity-list"]'),
        hasEmpty: has('[data-testid="similarity-empty"]'),
        hasNoneInFilter: has('[data-testid="similarity-none-in-filter"]'),
        // ⚠️ 只取这一条的文本，不能拿 .similarity-list 的 textContent：
        // 下拉框的 option 文案里本来就有「≥ 90%」，那样断言"提示语含 90"永远为真
        noneText: pick('[data-testid="similarity-none-in-filter"]'),
        items: document.querySelectorAll('[data-testid="similarity-item"]').length,
        filter: sel ? String(sel.value) : null,
        // 相似档的 h2 是面板的最后一个小标题（第一个是「轨迹列表」）
        title: h2s.length ? h2s[h2s.length - 1].textContent.replace(/\s+/g, ' ').trim() : '',
        panelRight: Math.round(pr.right),
        overflow: panel.scrollHeight - panel.clientHeight,
        spill: last ? Math.round(last.bottom - pr.bottom) : 0,
        // 四个按钮挤爆的两种表现：横向溢出（scrollWidth）与换行（不在同一行）
        modeOverflow: ms ? ms.scrollWidth - ms.clientWidth : null,
        modeCount: btns.length,
        modeRowSpread: tops.length ? Math.round(Math.max(...tops) - Math.min(...tops)) : null,
    };
}"""


async def read(page):
    return await page.evaluate(READ_DOM)


async def open_similar(page, url, settle_ms=6000):
    """打开页面 → 进相似档 → 等列表和地球都画完。

    不在这里断言：元素等不到的时候判据会红出来并带上面板提示语，
    比直接抛异常崩掉更有信息量（第三阶段同一条规矩）。
    """
    await page.goto(url, wait_until="load")
    await page.wait_for_selector('[data-testid="mode-similar"]', timeout=30000)
    await page.wait_for_timeout(4000)          # 相机 flyTo(1.5s) + 首屏稳定
    await page.click('[data-testid="mode-similar"]')
    try:
        await page.wait_for_selector('[data-testid="similarity-list"]', timeout=30000)
    except Exception as e:
        note(f"等列表超时（{type(e).__name__}），继续读面板看提示语")
    await page.wait_for_timeout(settle_ms)     # 逐条取点 + Primitive 异步几何
    return await read(page)


def pick_aux_baseline(max_probe=8):
    """找一条「matches 非空、但一条都没到 90%」的主线，用来造第二种空态。

    顺手把探测统计带出来（探了几条、matches 最少几条、有几条是 0）——
    第 13 项旁边那句"similarity-empty 在当前数据上不可达"就有了**本次运行**的证据，
    而不是只靠上一阶段的口述。

    找不到合适的就返回 id=None —— 调用处 note 跳过，**绝不写注定红的断言**。
    """
    listing = get_json("/api/tracks?limit=20")
    out = {"id": None, "n": 0, "max": 0.0, "probed": 0, "min_matches": None, "zero": 0}
    for t in listing.get("items", [])[:max_probe]:
        tid = t.get("id")
        if tid is None or tid == TRACK_ID:
            continue
        try:
            r = get_json(f"{SIM_API}?trackId={tid}&limit={LIMIT}")
        except Exception as e:
            note(f"探主线 track {tid} 失败（{e}）")
            continue
        ms = r.get("matches") or []
        out["probed"] += 1
        out["min_matches"] = (len(ms) if out["min_matches"] is None
                              else min(out["min_matches"], len(ms)))
        if not ms:
            out["zero"] += 1
        if out["id"] is None and ms and all(float(m.get("similarity", 0)) < 90 for m in ms):
            out.update(id=tid, n=len(ms), max=max(float(m["similarity"]) for m in ms))
    return out


async def main():
    sim_reqs = []          # 按顺序记录每一次相似度请求的查询参数（诊断用）

    def on_request(req):
        if SIM_API in req.url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(req.url).query)
            sim_reqs.append({k: (v[0] if v else "") for k, v in q.items()})

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})
        page.on("request", on_request)
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # ================= 阶段 A：裸 URL（没有选中轨迹）=================
        await page.goto(BARE_URL, wait_until="load")
        await page.wait_for_selector('[data-testid="mode-similar"]', timeout=30000)
        await page.wait_for_timeout(3000)      # 列表加载 + 面板布局稳定
        dom = await read(page)

        visible = await page.is_visible('[data-testid="mode-similar"]')
        check("1. 第四档「相似」按钮存在且可见", visible and dom["modeCount"] == 4,
              f"按钮可见={visible}｜mode-switch 里按钮 {dom['modeCount']} 个")

        await page.click('[data-testid="mode-similar"]')
        await page.wait_for_timeout(2000)
        dom = await read(page)

        # ⚠️ 判据同时要横向不溢出 + 四个按钮在同一行：
        # 现在 .mode-switch 是 flex 不换行 + overflow:hidden，溢出了 scrollWidth 才变大；
        # 万一将来有人加 flex-wrap，"挤爆"会表现为**换行**而 scrollWidth 依然相等 ——
        # 那条判据就废了，所以同一行这件事必须单独量一次。
        check("2. 四档按钮不折行（不横向溢出 + 四个在同一行）",
              dom["modeOverflow"] is not None and dom["modeOverflow"] <= 0
              and dom["modeRowSpread"] is not None and dom["modeRowSpread"] <= 1,
              f"scrollWidth-clientWidth={dom['modeOverflow']}｜四个按钮 top 差="
              f"{dom['modeRowSpread']}px")

        need = dom["hasNeed"] and not dom["hasList"]
        check("3. 没选轨迹时给出提示（similarity-need-track）", need,
              f"有提示={dom['hasNeed']}｜列表存在={dom['hasList']}")

        # ================= 阶段 B：?track=20 正常路径 =================
        dom = await open_similar(page, URL)
        panel_right = dom["panelRight"]
        x0 = panel_right + 8
        note(f"面板右边界 {panel_right}px，像素统计从 x={x0} 起，y 截到 {MAP_BOTTOM}")

        # 期望值全部从接口现取（和 App.vue 用同一个 trackId / limit）
        api = get_json(f"{SIM_API}?trackId={TRACK_ID}&limit={LIMIT}")
        ms = api.get("matches") or []
        exp = {
            "name": api.get("name"),
            "pointCount": api.get("pointCount"),
            "compared": api.get("compared"),
            "toleranceM": api.get("toleranceM"),
            "total": len(ms),
            "ge90": sum(1 for m in ms if float(m["similarity"]) >= 90),
            "ge70": sum(1 for m in ms if float(m["similarity"]) >= 70),
            "ge50": sum(1 for m in ms if float(m["similarity"]) >= 50),
        }
        # ⚠️ 后端返回的 toleranceM 是 JSON 浮点（50.0），而面板按 JS 的写法渲染成「50 米」。
        # 直接 str(50.0) = '50.0' 会查不到 → 这条判据假红。
        tol_s = (str(int(exp["toleranceM"]))
                 if float(exp["toleranceM"]).is_integer() else str(exp["toleranceM"]))
        note(f"接口期望：{exp['name']} · {exp['pointCount']} 点 · compared={exp['compared']}"
             f" · 容差 {tol_s}m · matches={exp['total']}"
             f"（≥90%: {exp['ge90']}｜≥70%: {exp['ge70']}｜≥50%: {exp['ge50']}）")

        check("4. 主线信息与接口一致（name + pointCount）",
              bool(exp["name"]) and str(exp["name"]) in dom["baseline"]
              and str(exp["pointCount"]) in dom["baseline"],
              f"接口 {exp['name']} / {exp['pointCount']} 点｜面板「{dom['baseline']}」")

        check("5. 比对分母与容差与接口一致（compared + toleranceM）",
              str(exp["compared"]) in dom["compared"] and tol_s in dom["compared"],
              f"接口 compared={exp['compared']} 容差={tol_s}m｜面板「{dom['compared']}」")

        n_default = dom["items"]
        check("6. 默认筛选下条数 == 接口 similarity>=50 的条数",
              n_default == exp["ge50"] and dom["filter"] == "50",
              f"列表 {n_default} 条｜接口 ≥50% 有 {exp['ge50']} 条｜筛选档位={dom['filter']}")

        title_n = _first_int(dom["title"], r"(\d+)\s*条")
        check("7. 面板标题条数 == 列表条数", title_n == n_default,
              f"标题「{dom['title']}」→ {title_n}｜列表 {n_default}")

        # ---------- 筛选：三档都拿接口当期望值（不是"看起来变少了"）----------
        await page.select_option('[data-testid="similarity-filter"]', "90")
        await page.wait_for_timeout(1200)
        d90 = await read(page)
        # "变少"必须是**接口自己给的关系**（≥90% 确实比 ≥50% 少），不是写死的假设
        fewer = exp["ge90"] < exp["ge50"]
        if not fewer:
            note("接口里 ≥90% 与 ≥50% 条数相同 → 「变少」这半条不成立，只比绝对值")
        check("8. 筛到 ≥90% 后条数变少且 == 接口 ≥90% 的条数",
              d90["items"] == exp["ge90"] and (d90["items"] < n_default if fewer else True),
              f"列表 {n_default} → {d90['items']} 条（接口 ≥90% 有 {exp['ge90']} 条）"
              f"｜筛选档位={d90['filter']}")

        # 这条主线自己就能造出第二种空态时，顺手在**真实路径**上验一次
        # （track 20 实测 ≥90% 还有 1 条，所以这里通常不可达 → 不写注定红的断言）
        if exp["ge90"] == 0 and exp["total"] > 0:
            check("8b. 这条主线在 ≥90% 档下是「有匹配但被筛掉」（none-in-filter）",
                  d90["hasNoneInFilter"] and not d90["hasEmpty"] and d90["items"] == 0,
                  f"匹配 {exp['total']} 条、全部 < 90%｜none-in-filter={d90['hasNoneInFilter']}"
                  f"｜empty={d90['hasEmpty']}｜条数={d90['items']}")
        else:
            note(f"这条主线上 ≥90% 还有 {exp['ge90']} 条 → none-in-filter 在这里不可达，"
                 "改在阶段 C 用另一条主线造（见第 13 项）")

        await page.select_option('[data-testid="similarity-filter"]', "0")
        await page.wait_for_timeout(1500)
        d_all = await read(page)
        more = exp["total"] > exp["ge50"]
        if not more:
            note("接口里「全部」与 ≥50% 条数相同 → 「变多」这半条不成立，只比绝对值")
        check("9. 切到「全部」后条数变多且 == 接口全部条数",
              d_all["items"] == exp["total"] and (d_all["items"] > n_default if more else True),
              f"列表 {n_default} → {d_all['items']} 条（接口 matches {exp['total']} 条）"
              f"｜筛选档位={d_all['filter']}")

        # 回到默认档位：后面四项视口检查和像素检查都在"面板真实默认状态"下做
        await page.select_option('[data-testid="similarity-filter"]', "50")
        await page.wait_for_timeout(1200)

        # ---------- 10. 四视口面板不溢出 ----------
        for w, h in ((1600, 900), (1600, 600), (1366, 660), (1280, 720)):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(1500)
            m = await read(page)
            check(f"10.{w}x{h} 相似档面板不溢出且四档不折行",
                  m["overflow"] <= 0 and m["spill"] <= 0
                  and m["modeOverflow"] is not None and m["modeOverflow"] <= 0
                  and m["modeRowSpread"] is not None and m["modeRowSpread"] <= 1,
                  f'overflow={m["overflow"]} spill={m["spill"]} '
                  f'modeOverflow={m["modeOverflow"]} rowSpread={m["modeRowSpread"]}px')
        await page.set_viewport_size({"width": VIEW_W, "height": VIEW_H})
        await page.wait_for_timeout(3000)

        # ---------- 11. 点第 2 条会飞（包围盒变化 vs 静止漂移）----------
        # 静止对照：相机不动时连拍两张，量包围盒的自然漂移（噪声底）
        await page.screenshot(path=SHOT + ".idle-a.png")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=SHOT + ".idle-b.png")
        n_a, bb_a = warm(SHOT + ".idle-a.png", x0)
        n_b, bb_b = warm(SHOT + ".idle-b.png", x0)
        drift = bbox_delta(bb_a, bb_b)

        rows = page.locator('[data-testid="similarity-item"]')
        n_c, bb_c, click_err = 0, None, ""
        try:
            row2 = (await rows.nth(1).inner_text()).replace("\n", " ")
            row2 = re.sub(r"\s+", " ", row2).strip()
            note(f"第 2 条 = 「{row2}」"
                 + (f"（接口第 2 名 = {ms[1]['name']}）" if len(ms) > 1 else ""))
            await rows.nth(1).click()
            await page.wait_for_timeout(1000 + 3500)   # flyTo duration=1.0s + 停稳 + 重画
            await page.screenshot(path=SHOT + ".after-click.png")
            n_c, bb_c = warm(SHOT + ".after-click.png", x0)
        except Exception as e:
            # 列表不足 2 条时 nth(1) 会抛异常 —— 这里不让它崩掉整轮，
            # 而是让判据红出来并带上原因（第三阶段同一条规矩）
            click_err = f"{type(e).__name__}: {e}"
        moved = bbox_delta(bb_a, bb_c)

        check("11. 点第 2 条会飞（trackline 包围盒变化 > max(40px, 4×静止漂移)）",
              not click_err and n_c > 300 and moved is not None
              and moved > max(40, 4 * (drift or 0)),
              f"包围盒 {bb_a} → {bb_c}（最大边位移 {moved}px，静止漂移 {drift}px）"
              f"｜暖色像素 {n_a} → {n_c}"
              + (f"｜点击失败：{click_err}" if click_err else ""))

        # ---------- 12. 切走相似档后叠加消失 ----------
        # ⚠️ 不写"绝对归零"：停留点是橙色的，本身可能就是暖色像素。
        # 判据 = 同一相机下回落到"停留点档自己的基线 + 200px"，且切走前真的有东西。
        await page.click('[data-testid="mode-stay"]')
        await page.wait_for_timeout(2500)
        await page.screenshot(path=SHOT + ".stay-base.png")
        n_stay_base, _ = warm(SHOT + ".stay-base.png", x0)

        await page.click('[data-testid="mode-similar"]')
        try:
            await page.wait_for_selector('[data-testid="similarity-list"]', timeout=30000)
        except Exception as e:
            note(f"切回相似档时等列表超时（{type(e).__name__}）")
        await page.wait_for_timeout(6000)
        await page.screenshot(path=SHOT + ".similar-again.png")
        n_sim2, bb_sim2 = warm(SHOT + ".similar-again.png", x0)

        await page.click('[data-testid="mode-stay"]')
        await page.wait_for_timeout(2500)
        await page.screenshot(path=SHOT + ".stay-after.png")
        n_stay_after, _ = warm(SHOT + ".stay-after.png", x0)

        limit = max((n_stay_base or 0) + 200, 300)
        check("12. 切走相似档后匹配轨迹的暖色像素消失（回落到停留点档基线）",
              n_sim2 > 1000 and n_stay_after <= limit,
              f"切走前 {n_sim2} px（包围盒 {bb_sim2}）→ 切走后 {n_stay_after} px"
              f"｜停留点档基线 {n_stay_base} px｜容许上限 {limit}")

        # ================= 阶段 C：第二种空态（有匹配但被筛掉）=================
        aux = pick_aux_baseline()
        note(f"探了 {aux['probed']} 条主线找「一个邻居都没有」的情形："
             f"matches 最少 {aux['min_matches']} 条、其中 0 条的有 {aux['zero']} 条")
        if aux["id"] is None:
            note("接口里找不到「matches 非空且全部 < 90%」的主线 → 第 13 项跳过"
                 "（不写注定红的断言）")
        else:
            note(f"造第二种空态的主线：track {aux['id']}"
                 f"（接口 {aux['n']} 条匹配，最高 {aux['max']}%）")
            aux_dom = await open_similar(page, f"http://localhost:5173/?track={aux['id']}")
            note(f"这条主线打开时的默认筛选档位 = {aux_dom['filter']}")
            try:
                await page.select_option('[data-testid="similarity-filter"]', "90")
            except Exception as e:
                note(f"设置筛选失败（{type(e).__name__}: {e}）")
            await page.wait_for_timeout(1200)
            aux_dom = await read(page)
            check("13. 「有匹配但被筛掉」→ similarity-none-in-filter（不是 similarity-empty）",
                  aux_dom["hasNoneInFilter"] and not aux_dom["hasEmpty"]
                  and aux_dom["items"] == 0 and "90" in aux_dom["noneText"],
                  f"track {aux['id']}（接口 {aux['n']} 条匹配、最高 {aux['max']}%，全部 < 90%）"
                  f"｜none-in-filter={aux_dom['hasNoneInFilter']}"
                  f"｜empty={aux_dom['hasEmpty']}｜条数={aux_dom['items']}"
                  f"｜提示「{aux_dom['noneText'][:44]}」")
        note("另一支 similarity-empty（一个邻居都没有）在真实数据上不可达：容差 50 米下"
             "每条轨迹至少 1 个邻居（要压到 1 米才有个别孤立的），"
             "而前端固定不传 toleranceM —— 所以它只在第二阶段的接口级脚本里被覆盖，"
             "这里不写注定红的断言。")

        # ================= 14. 控制台零报错 =================
        check("14. 控制台零报错", len(errors) == 0, "; ".join(errors[:3]))
        await browser.close()

    print("")
    print("相似度请求轨迹（trackId / limit / toleranceM）：")
    for i, q in enumerate(sim_reqs):
        print(f"  [{i}] trackId={q.get('trackId')} limit={q.get('limit')} "
              f"toleranceM={q.get('toleranceM', '(默认)')}")
    print("")
    print("截图：.tmp/similarity-shot.png.idle-a/.idle-b/.after-click/.stay-base/"
          ".similar-again/.stay-after")
    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败（共 {len(results)} 项）")
    if failed:
        print("失败项：" + "; ".join(r[0] for r in failed))
        sys.exit(1)


asyncio.run(main())
