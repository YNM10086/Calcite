# -*- coding: utf-8 -*-
r"""数据管理（添加 / 替换 / 改名 / 删除）的浏览器验收（任务要求的 11 项 + 8 项护栏）。

用法（需要提权 danger-full-access，Playwright 的浏览器子进程要管道通信）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp/check-data-edit.py

前置条件：后端 8080 + 前端 5173 都在跑。

结构与 `check-density.py` 一脉相承：check() / note() / 面板右边界 / 四视口溢出 / 控制台零报错。

⚠️ 两条**刻意画的边界**（不要"顺手补上"）：

  1. **本脚本绝不真的删轨迹。** 删除的**成功路径**由 `.tmp/verify-data-edit-api.py` 覆盖；
     而且当前会话里回收站目录 `D:\Calcite-note\backups\deleted` 写不进去 ——
     后端的设计是"导出失败就不删"（fail-safe），所以真的点「删除」只会拿到 500。
     于是第 7、8 项只验证「弹窗出现 + 文案带接口给的真实点数 + 取消有效」，
     并额外断言**全程一次 DELETE 请求都没发出去**（取消必须连请求都不发，不只是"结果没变"）。

  2. **改名是本脚本唯一会写数据的动作**，跑完一定改回原名 ——
     界面路径走一遍（顺带证明改名可逆），失败时兜底走一次 HTTP PATCH，
     保证不管中途怎么失败，库里那条轨迹的名字都回到进场时的样子。

判据一律**当场问接口要期望值**，脚本里不写死任何条数 / 点数 / 名字：
    - 行数  → `GET /api/tracks?limit=<界面上选的那个上限>` 的 items 条数
    - 总数  → 同一个响应的 total
    - 改名目标 / 删除弹窗里的点数 → 锚点那条轨迹在接口里的 name / pointCount

锚点行怎么钉：先用 `?track=<接口第一条的 id>` 打开页面（App 支持深链接），
进管理视图后**带「已加载」徽章的那一行**就是它 —— 不靠"列表第 N 行"这种会被数据顺序打破的假设。

本文件用到的 testid（都从源码里核对过，不是猜的）：
    TrackList.vue      open-data-manager
    DataManager.vue    data-manager / data-manager-back / data-manager-rows /
                       dm-row / dm-rename / dm-delete / rename-input /
                       source-filter / limit-filter
    ConfirmDialog.vue  confirm-dialog / confirm-cancel / confirm-alt / confirm-ok
    App.vue            mode-switch / mode-stay / mode-hotspot / mode-density / mode-similar
"""
import asyncio
import json
import sys
import traceback
import urllib.request

from playwright.async_api import async_playwright

BASE = "http://localhost:8080"
# ⚠️ 必须带 ?track=<id>：App 的深链接会把它选中，管理视图里那一行就带「已加载」徽章，
# 锚点行于是可以被**精确定位**（而不是"列表第一行"）。
URL_TMPL = "http://localhost:5173/?track={tid}"
VIEW_W, VIEW_H = 1600, 900
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


def note(text):
    print("    · " + text)


async def try_(what, fn):
    """交互动作的兜底：失败只 note 一句，**不让后面的判据整个跑不到**。

    浏览器脚本最烦的失败形态是"第 5 项点空 → 抛异常 → 后面 8 项一条都没跑"，
    报告上只剩一句 traceback。这里把每个交互都包起来，红就红在那一条上。
    """
    try:
        return await fn()
    except Exception as e:
        note(f"{what} 失败（{type(e).__name__}: {e}）")
        return None


def _get(path, timeout=180):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_listing(limit):
    """`GET /api/tracks?limit=` —— 界面列表用的就是它，所以它就是行数的期望值来源。"""
    return _get("/api/tracks?limit=" + str(limit))


def fetch_total():
    return fetch_listing(1)["total"]


def fetch_item(track_id, limit=500):
    """按 id 找一条轨迹（列表接口的 limit 上限是 500，见 TrackController 的 Math.min）。"""
    for it in fetch_listing(limit)["items"]:
        if it["id"] == track_id:
            return it
    return None


def patch_name(track_id, name):
    """兜底清理用：直接 PATCH 改名（正常路径应该走界面，这里只保证现场干净）。"""
    body = json.dumps({"name": name}).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/tracks/" + str(track_id), data=body, method="PATCH",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


# 量面板布局：overflow=内容溢出，spill=最后一个子元素越过面板下边界（视觉上被裁）
MEASURE = """() => {
    const panel = document.querySelector('.panel');
    const pr = panel.getBoundingClientRect();
    const kids = [...panel.children];
    const last = kids[kids.length - 1].getBoundingClientRect();
    const rows = document.querySelector('[data-testid="data-manager-rows"]');
    return {
        overflow: panel.scrollHeight - panel.clientHeight,
        spill: Math.round(last.bottom - pr.bottom),
        rowsH: rows ? Math.round(rows.getBoundingClientRect().height) : null,
        panelRight: Math.round(pr.right),
    };
}"""


async def main():
    total_in = fetch_total()          # 进场前的总数（收尾要断言它没变）
    print(f"[参考] 接口当前轨迹总数 {total_in} 条")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})

        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # 记下所有**写请求**。第 5b / 8 项要用它证明"取消"连请求都没发。
        writes = []

        def on_request(req):
            if req.method in ("POST", "PATCH", "PUT", "DELETE") and "/api/tracks" in req.url:
                writes.append((req.method, req.url))

        page.on("request", on_request)

        # 先问接口要"第一条轨迹"，用它的 id 做深链接 —— 锚点行就此钉死
        head = fetch_listing(1)["items"][0]
        note(f"锚点轨迹 id={head['id']} name={head['name']!r} pointCount={head['pointCount']}")

        await page.goto(URL_TMPL.format(tid=head["id"]), wait_until="load")
        await page.wait_for_selector('[data-testid="open-data-manager"]', timeout=30000)
        await page.wait_for_timeout(2500)     # 等列表拉回来 + flyTo 停稳

        # ---------- 1. 「数据编辑」按钮存在 ----------
        n_open = await page.eval_on_selector_all(
            '[data-testid="open-data-manager"]', "els => els.length")
        check("1. 「数据编辑」入口按钮存在", n_open == 1, f"节点数 {n_open}")

        # ---------- 2. 点了进管理视图，且四档切换条消失 ----------
        await try_("点「数据编辑」", lambda: page.click('[data-testid="open-data-manager"]'))
        await try_("等 data-manager 出现",
                   lambda: page.wait_for_selector('[data-testid="data-manager"]', timeout=15000))
        n_dm = await page.eval_on_selector_all('[data-testid="data-manager"]', "els => els.length")
        n_switch = await page.eval_on_selector_all('[data-testid="mode-switch"]', "els => els.length")
        check("2. 管理视图出现，且四档切换条消失", n_dm == 1 and n_switch == 0,
              f"data-manager={n_dm} mode-switch={n_switch}")

        panel_right = await page.eval_on_selector(
            ".panel", "el => Math.round(el.getBoundingClientRect().right)")
        note(f"面板右边界 {panel_right}px（视口 {VIEW_W}x{VIEW_H}）")

        # ---------- 3. 表格行数 == 接口条数 ----------
        # 上限从界面读（不写死 50）：界面选了什么，接口就按什么取，两边必须逐条对齐。
        ui_limit = int(await page.eval_on_selector(
            '[data-testid="limit-filter"]', "el => el.value"))
        listing = fetch_listing(ui_limit)
        items, total = listing["items"], listing["total"]
        n_rows = await page.eval_on_selector_all('[data-testid="dm-row"]', "els => els.length")
        back_count = (await page.text_content(".back-bar .count") or "").strip()
        want_count = f"共 {total} 条"
        check("3. 表格行数 == 接口条数（limit 与界面一致）",
              n_rows == len(items) and want_count in back_count and len(items) == min(total, ui_limit),
              f"界面 {n_rows} 行 / 接口 {len(items)} 条（total={total}，界面上限 {ui_limit}）"
              f"｜条数文案 {back_count!r}")

        # ---------- 4. 每行都有改名 / 删除按钮 ----------
        n_ren = await page.eval_on_selector_all('[data-testid="dm-rename"]', "els => els.length")
        n_del = await page.eval_on_selector_all('[data-testid="dm-delete"]', "els => els.length")
        check("4. 每行都有改名 / 删除按钮",
              n_rows > 0 and n_ren == n_rows and n_del == n_rows,
              f"行 {n_rows} / 改名按钮 {n_ren} / 删除按钮 {n_del}")

        # ---------- 锚点行：带「已加载」徽章的那一行 ----------
        anchor_idx = -1
        for i in range(n_rows):
            if await page.locator('[data-testid="dm-row"]').nth(i).locator(".badge").count() > 0:
                anchor_idx = i
                break
        anchor_name = ""
        if anchor_idx >= 0:
            anchor_name = ((await page.locator('[data-testid="dm-row"]')
                            .nth(anchor_idx).locator(".name").text_content()) or "").strip()
        # 期望值也来自接口（同一个 id），不是"列表第一条"这种会被顺序打破的假设
        entry = next((it for it in items if it["id"] == head["id"]), None)
        check("4b. 锚点行（?track= 深链接选中的那条）与接口同 id 那条一致",
              entry is not None and anchor_idx >= 0 and anchor_name == entry["name"],
              f"锚点行下标 {anchor_idx} 名字 {anchor_name!r} / 接口 id={head['id']} "
              f"name={(entry or {}).get('name')!r}")
        if anchor_idx < 0:
            # 徽章没找到（比如深链接没生效）→ 退回第一行继续把后面的判据跑完，
            # 不要在这里崩掉，否则只剩一句 traceback、看不到别的判据。
            anchor_idx = 0
            note("⚠️ 找不到「已加载」徽章行 —— 退回第一行当锚点")
        if entry is None:
            entry = items[0]
            note("⚠️ 深链接那条不在本页里 —— 退回接口第一条当锚点，后续判据可能对不上")

        row = page.locator('[data-testid="dm-row"]').nth(anchor_idx)
        inp = page.locator('[data-testid="rename-input"]')

        # ---------- 5. 点改名出行内输入框 ----------
        await try_(f"点第 {anchor_idx} 行的改名按钮",
                   lambda: row.locator('[data-testid="dm-rename"]').click())
        await try_("等 rename-input 出现", lambda: inp.wait_for(state="visible", timeout=8000))
        n_inp = await page.eval_on_selector_all('[data-testid="rename-input"]', "els => els.length")
        inp_val = await inp.input_value() if n_inp == 1 else ""
        # 编辑态下按钮区整块收起 —— 顺带钉住（否则误点删除就成了真事故）
        n_ren_edit = await page.eval_on_selector_all('[data-testid="dm-rename"]', "els => els.length")
        check("5. 点改名出现行内输入框（初值 = 原名，且按钮区收起）",
              n_inp == 1 and inp_val == entry["name"] and n_ren_edit == n_rows - 1,
              f"输入框 {n_inp} 个、初值 {inp_val!r}（期望 {entry['name']!r}）；"
              f"编辑态下改名按钮 {n_ren_edit} 个（期望 {n_rows - 1}）")

        # Esc 取消：输入框收起且**不发 PATCH**
        await try_("Esc 取消改名", lambda: inp.press("Escape"))
        await page.wait_for_timeout(700)
        n_inp_after = await page.eval_on_selector_all('[data-testid="rename-input"]', "els => els.length")
        n_patch_esc = len([w for w in writes if w[0] == "PATCH"])
        check("5b. Esc 取消改名：输入框收起，且没有发出 PATCH 请求",
              n_inp_after == 0 and n_patch_esc == 0,
              f"残留输入框 {n_inp_after} 个、PATCH {n_patch_esc} 次")

        # ---------- 6. 改名后显示新名字（DOM + 接口），跑完改回原名 ----------
        NEW_NAME = entry["name"] + "-验收改名"

        async def do_rename(new_name):
            # row / inp 都是惰性定位器，每次用都会重新解析 —— 列表被重拉过也照样对得上
            await row.locator('[data-testid="dm-rename"]').click()
            await inp.wait_for(state="visible", timeout=8000)
            await inp.fill(new_name)
            await inp.press("Enter")

        await try_(f"界面改名为 {NEW_NAME!r}", lambda: do_rename(NEW_NAME))

        # 保存后 DataManager 只 emit('changed')，由 App 重拉列表 —— 所以这里轮询等新名字进 DOM
        dom_ok = False
        for _ in range(30):
            await page.wait_for_timeout(500)
            names = await page.eval_on_selector_all(
                '[data-testid="dm-row"] .name', "els => els.map(e => e.textContent.trim())")
            if NEW_NAME in names:
                dom_ok = True
                break
        api_now = fetch_item(entry["id"])
        check("6. 改名后界面与接口都显示新名字",
              dom_ok and api_now is not None and api_now["name"] == NEW_NAME,
              f"界面出现新名={dom_ok}；接口 name={None if api_now is None else api_now['name']!r}"
              f"（期望 {NEW_NAME!r}）")

        # ---- 清理现场：改回原名（同样走界面，顺带证明改名可逆）----
        reverted = False
        try:
            await do_rename(entry["name"])
            for _ in range(30):
                await page.wait_for_timeout(500)
                names = await page.eval_on_selector_all(
                    '[data-testid="dm-row"] .name', "els => els.map(e => e.textContent.trim())")
                if entry["name"] in names and NEW_NAME not in names:
                    reverted = True
                    break
        except Exception as e:
            note(f"界面路径改回原名失败（{type(e).__name__}: {e}）")
        api_back = fetch_item(entry["id"])
        back_ok = api_back is not None and api_back["name"] == entry["name"]
        if not back_ok:
            # 兜底：不管前面怎么失败，都不许把库里的名字留在"验收改名"上
            try:
                note("兜底：直接 PATCH 改回原名")
                patch_name(entry["id"], entry["name"])
                api_back = fetch_item(entry["id"])
                back_ok = api_back is not None and api_back["name"] == entry["name"]
            except Exception as e:
                note(f"兜底 PATCH 也失败（{type(e).__name__}: {e}）")
        check("6b. 跑完已改回原名（清理现场）",
              reverted and back_ok,
              f"界面回原名={reverted}；接口 name={None if api_back is None else api_back['name']!r}"
              f"（期望 {entry['name']!r}）")

        # ---------- 7. 点删除弹确认框，文案含接口给的真实点数（⚠️ 不点确认）----------
        rows_before = await page.eval_on_selector_all('[data-testid="dm-row"]', "els => els.length")
        await try_("点删除按钮",
                   lambda: page.locator('[data-testid="dm-row"]').nth(anchor_idx)
                   .locator('[data-testid="dm-delete"]').click())
        dlg = page.locator('[data-testid="confirm-dialog"]')
        await try_("等确认弹窗出现", lambda: dlg.wait_for(state="visible", timeout=8000))
        n_dlg = await page.eval_on_selector_all('[data-testid="confirm-dialog"]', "els => els.length")
        body = (await dlg.inner_text()) if n_dlg == 1 else ""
        pc = entry.get("pointCount")
        # 点数已知时必须逐字带上真实点数；后端给 null 时前端的兜底文案是"名下的所有轨迹点"
        # —— 两个分支都是**确定的期望值**，不是"含'个点'就算过"。
        want_pts = f"{pc} 个轨迹点" if pc is not None else "名下的所有轨迹点"
        ok_text = ((await page.text_content('[data-testid="confirm-ok"]')) or "").strip() if n_dlg == 1 else ""
        check("7. 删除确认弹窗出现，且文案带接口给的真实点数",
              n_dlg == 1 and entry["name"] in body and want_pts in body and ok_text == "删除",
              f"弹窗 {n_dlg} 个｜点数 {pc} → 正文需含 {want_pts!r}｜确认按钮 {ok_text!r}"
              f"｜正文 {body[:60]!r}")

        # ---------- 8. 取消删除 → 条数不变（且一次 DELETE 都没发）----------
        await try_("点取消", lambda: page.click('[data-testid="confirm-cancel"]'))
        await page.wait_for_timeout(1500)
        n_dlg_after = await page.eval_on_selector_all('[data-testid="confirm-dialog"]', "els => els.length")
        rows_after = await page.eval_on_selector_all('[data-testid="dm-row"]', "els => els.length")
        total_after = fetch_total()
        n_delete_req = len([w for w in writes if w[0] == "DELETE"])
        check("8. 取消删除：弹窗关闭、条数不变、且没有发出 DELETE 请求",
              n_dlg_after == 0 and rows_after == rows_before
              and total_after == total and n_delete_req == 0,
              f"弹窗 {n_dlg_after}｜行 {rows_before}→{rows_after}｜"
              f"接口 total {total}→{total_after}｜DELETE 请求 {n_delete_req} 次")

        # ---------- 9. 「← 返回」回到四档分析 ----------
        await try_("点「← 返回」", lambda: page.click('[data-testid="data-manager-back"]'))
        await try_("等 mode-switch 回来",
                   lambda: page.wait_for_selector('[data-testid="mode-switch"]', timeout=15000))
        n_switch2 = await page.eval_on_selector_all('[data-testid="mode-switch"]', "els => els.length")
        n_dm2 = await page.eval_on_selector_all('[data-testid="data-manager"]', "els => els.length")
        modes = await page.eval_on_selector_all(
            '[data-testid="mode-switch"] button', "els => els.map(e => e.textContent.trim())")
        check("9. 「← 返回」回到四档分析（四档都在，管理视图退出）",
              n_switch2 == 1 and n_dm2 == 0 and len(modes) == 4,
              f"mode-switch={n_switch2} data-manager={n_dm2} 档位={modes}")

        # ---------- 10. 四个视口下面板都不溢出（管理视图）----------
        await try_("重新进管理视图", lambda: page.click('[data-testid="open-data-manager"]'))
        await try_("等 data-manager 回来",
                   lambda: page.wait_for_selector('[data-testid="data-manager"]', timeout=15000))
        await page.wait_for_timeout(1500)
        for w, h in ((1600, 900), (1600, 600), (1366, 660), (1280, 720)):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(1200)
            m = await page.evaluate(MEASURE)
            check(f"10.{w}x{h} 管理视图面板不溢出",
                  m["overflow"] <= 0 and m["spill"] <= 0,
                  f'overflow={m["overflow"]} spill={m["spill"]} '
                  f'行列表高={m["rowsH"]} 面板右边界={m["panelRight"]}')
        await page.set_viewport_size({"width": VIEW_W, "height": VIEW_H})
        await page.wait_for_timeout(1000)

        # ---------- 11. 控制台零报错 ----------
        check("11. 控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        # ---------- 收尾：整个过程一次写请求都没有漏出去 ----------
        total_end = fetch_total()
        note(f"写请求：{[(m, u.split('/api')[1]) for m, u in writes]}")
        check("12. 全程没有 DELETE / POST（只允许改名那两次 PATCH）",
              len([w for w in writes if w[0] == "DELETE"]) == 0
              and len([w for w in writes if w[0] == "POST"]) == 0
              and len([w for w in writes if w[0] == "PATCH"]) == 2,
              f"PATCH {len([w for w in writes if w[0] == 'PATCH'])} 次 / "
              f"DELETE {len([w for w in writes if w[0] == 'DELETE'])} 次 / "
              f"POST {len([w for w in writes if w[0] == 'POST'])} 次")
        check("13. 收尾时接口总数与进场一致（没删没加）",
              total_end == total_in, f"{total_in} → {total_end}")

        await browser.close()

    print("")
    print("截图：无（本脚本只读 DOM / 接口，不做像素判据 —— 管理视图的验证靠 testid）")


def report():
    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败（共 {len(results)} 项）")
    if failed:
        print("失败项：" + "; ".join(r[0] for r in failed))
    return 1 if failed else 0


try:
    asyncio.run(main())
except Exception as e:
    # 不静默：异常也要把已经跑出来的判据打出来，否则调试时只看到一句 traceback
    traceback.print_exc()
    print(f"\n⚠️ 脚本异常中止：{type(e).__name__}: {e}")
    print("   （改名的清理现场逻辑在正常路径里；若在这里中断，请用")
    print("     .tmp/verify-data-edit-api.py 的改名用例核对库里那条轨迹的名字）")
sys.exit(report())
