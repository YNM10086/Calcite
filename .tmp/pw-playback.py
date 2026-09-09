"""端到端验证 M1 回放：点播放 → 三张截图。需要前端 :5173 在跑。"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"E:\JAVA_IDEA_package\JAVA_Project\Calcite\.tmp\playback-shots")
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://localhost:5173/?track=1"

errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("response", lambda r: errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)

    page.goto(URL, wait_until="load")
    # 等轨迹列表加载出来，再等地球把轨迹画上去
    page.wait_for_selector(".track-list .item", timeout=30000)
    page.wait_for_timeout(8000)

    # 关键断言 1：播放条出现了
    page.wait_for_selector('[data-testid="player"]', timeout=10000)
    print("OK 播放条已出现")

    clock_before = page.inner_text('[data-testid="clock"]')
    print("OK 时刻文字：" + clock_before)

    # 关键断言 2：点播放
    page.click('[data-testid="play-toggle"]')
    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / "shot1.png"))
    clock_1 = page.inner_text('[data-testid="clock"]')

    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / "shot2.png"))
    clock_2 = page.inner_text('[data-testid="clock"]')

    # 关键断言 3：暂停
    page.click('[data-testid="play-toggle"]')
    page.wait_for_timeout(2000)
    page.screenshot(path=str(OUT / "shot3.png"))
    clock_3 = page.inner_text('[data-testid="clock"]')

    print("时刻1 = " + clock_1)
    print("时刻2 = " + clock_2)
    print("时刻3 = " + clock_3)

    # 关键断言 4：拖动进度条能跳到别的时刻
    page.eval_on_selector(
        '[data-testid="seek"]',
        "el => { el.value = 800; el.dispatchEvent(new Event('input', { bubbles: true })) }",
    )
    page.wait_for_timeout(600)
    clock_4 = page.inner_text('[data-testid="clock"]')
    print("拖动后时刻 = " + clock_4)
    if clock_4 == clock_3:
        print("FAIL 拖动进度条后时刻没变")
        sys.exit(5)

    if clock_1 == clock_before:
        print("FAIL 点了播放，时刻文字没有变化")
        sys.exit(2)
    if clock_2 == clock_1:
        print("FAIL 还在播放，但时刻文字没有继续走")
        sys.exit(3)

    browser.close()

if errors:
    print("---- 浏览器报错 ----")
    for e in errors:
        print(e)
    sys.exit(4)

print("OK 三张截图已保存到 " + str(OUT))
