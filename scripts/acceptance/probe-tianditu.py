# -*- coding: utf-8 -*-
r"""天地图接入探针：一次跑完就能知道"现在这个 key 能不能用、要用哪种请求方式"。

为什么要有它（三个都踩过）：
  1. **HTTP 200 ≠ 有内容**：天地图在权限不足时会返回 **200 + 全白/占位瓦片**（实测：`vec_w` 每级
     都返回恒定 103 字节全白图、`img_w` 恒定 4769 字节占位图）。所以判据必须**看像素**，不能只看状态码。
  2. **请求方式必须匹配 key 类型**：
     - 「浏览器端」key → 请求要带 `Referer`（授权域名），走 `t{s}.tianditu.gov.cn`；
     - 「服务端」key → 请求**不能**带 `Origin`/`Referer`（带了会被判成浏览器请求并 403）。
     本脚本两种风格各试一次，直接告诉你该用哪种。
  3. **403 的响应体里写着原因**（别只看状态码）。实测原文：
     `{"resolve":"Key权限类型为:服务器端，请使用服务器端访问！","code":301013,"msg":"权限类型错误"}`

跑法（从仓库根目录；token 从 application-local.yml 读，**不打印**）：
    & "E:\python\python_address\python.exe" scripts\acceptance\probe-tianditu.py
"""
import os
import re
import sys
import hashlib
import urllib.error
import urllib.request

from PIL import Image


def find_repo_root(start):
    """向上找含 backend/src/main/resources 的那一级（不写死层级数，搬家也不会失效）"""
    d = start
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "backend", "src", "main", "resources")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return start


ROOT = find_repo_root(os.path.dirname(os.path.abspath(__file__)))
LOCAL_YML = os.path.join(ROOT, "backend", "src", "main", "resources", "application-local.yml")
OUT = os.path.join(ROOT, ".tmp")
BEIJING = (116.397, 39.909)          # 天安门附近

# 两种请求风格：区别只在带不带 Origin/Referer（天地图据此区分浏览器端 / 服务端 key）
STYLES = {
    "浏览器端风格（带 Origin+Referer）": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Origin": "http://localhost:5173",
        "Referer": "http://localhost:5173/",
    },
    "服务端风格（不带 Origin/Referer）": {"User-Agent": "calcite-backend/1.0"},
}


def load_token():
    if not os.path.exists(LOCAL_YML):
        print(f"!! 找不到 {LOCAL_YML}")
        return None
    m = re.search(r"tianditu-token:\s*(\S+)", open(LOCAL_YML, encoding="utf-8").read())
    return m.group(1).strip() if m and m.group(1).strip() else None


def tile_xy(lon, lat, level):
    """天地图 _w（经纬度）矩阵集：level 0 = 2 列 × 1 行，每级翻倍"""
    cols, rows = 2 ** (level + 1), 2 ** level
    return (min(int((lon + 180) / 360 * cols), cols - 1),
            min(int((90 - lat) / 180 * rows), rows - 1))


def fetch(layer, level, col, row, token, headers):
    url = (f"https://t1.tianditu.gov.cn/{layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
           f"&LAYER={layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
           f"&TILEMATRIX={level}&TILEROW={row}&TILECOL={col}&tk={token}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as r:
            return r.status, r.read(), r.headers.get("Access-Control-Allow-Origin"), ""
    except urllib.error.HTTPError as e:
        return e.code, b"", e.headers.get("Access-Control-Allow-Origin"), e.read().decode("utf-8", "replace")[:200]
    except Exception as e:                                     # noqa: BLE001
        return 0, b"", None, f"{type(e).__name__}: {e}"


def judge(body):
    """判断一张瓦片到底有没有内容 —— 这是本探针最重要的判据。

    返回 (结论, 说明)。空白图（1~2 种颜色）与"占位图"都会被判成不可用，
    哪怕它的 HTTP 状态码是 200、Content-Type 是 image/png。
    """
    if not body:
        return "无响应", ""
    if body[:4] != b"\x89PNG":
        return "不是 PNG", f"{len(body)} 字节"
    p = os.path.join(OUT, "_probe_tmp.png")
    with open(p, "wb") as f:
        f.write(body)
    im = Image.open(p).convert("RGB")
    colors = len(set(zip(im.tobytes()[0::3], im.tobytes()[1::3], im.tobytes()[2::3])))
    if colors <= 2:
        return "空白图（权限/服务问题）", f"{len(body)} 字节 / {colors} 种颜色"
    return "有内容 ✓", f"{len(body)} 字节 / {colors} 种颜色"


def fingerprint(layer, level, token, headers, points):
    """同一图层取多个**相距很远**的位置，返回内容哈希集合。

    ⚠️ 这是本探针最狠的一条判据：真实瓦片在不同城市必然不同；
    若不同位置返回**逐字节相同**的图，那它一定是占位图/空白图 ——
    与"坐标算得对不对"无关。实测（2026-09-27）就是这么定性的：
    `img_w` 四个城市共 1 种内容（4769 B 占位图）、`vec_w` 共 1 种空白（103 B）。
    """
    hashes = set()
    for lon, lat in points:
        col, row = tile_xy(lon, lat, level)
        _, body, _, _ = fetch(layer, level, col, row, token, headers)
        hashes.add(hashlib.sha256(body).hexdigest()[:10] if body else "empty")
    return hashes


def main():
    token = load_token()
    if not token:
        print("!! application-local.yml 里还没配 calcite.map.tianditu-token（或为空）")
        return 2
    print(f"key 已读到（长度 {len(token)}，不显示内容）\n")

    # 四个相距很远的城市：真实瓦片必然各不相同
    far_apart = [(116.397, 39.909), (121.473, 31.230), (113.264, 23.129), (87.617, 43.792)]
    usable = {}
    for style_name, headers in STYLES.items():
        print(f"=== {style_name} ===")
        content_ok = 0
        for layer, level, tag in (("vec", 12, "街道 L12"), ("vec", 16, "街道 L16"), ("img", 12, "卫星 L12")):
            col, row = tile_xy(*BEIJING, level)
            status, body, cors, err = fetch(layer, level, col, row, token, headers)
            verdict, detail = judge(body)
            print(f"  {tag:10} HTTP {status:<4} CORS={cors!r:6} -> {verdict} {detail}")
            if err:
                print(f"             响应体：{err}")
            if verdict.startswith("有内容"):
                out = os.path.join(OUT, f"tianditu-{layer}-L{level}-{style_name[:4]}.png")
                with open(out, "wb") as f:
                    f.write(body)
                print(f"             已存 {out}（可肉眼确认是不是北京）")
        # 位置指纹：四个城市是否返回同一张图
        for layer, level in (("vec", 12), ("img", 12)):
            hs = fingerprint(layer, level, token, headers, far_apart)
            if len(hs) == 1:
                print(f"  {layer}_w L{level} 位置指纹：四个城市**内容完全相同**（{list(hs)[0]}）"
                      f" ⇒ 这是占位图/空白图，与坐标无关")
            else:
                print(f"  {layer}_w L{level} 位置指纹：{len(hs)} 种内容 ⇒ 有真实瓦片 ✓")
                content_ok += 1
        usable[style_name] = content_ok
        print()

    print("=== 结论 ===")
    best = [k for k, v in usable.items() if v > 0]
    if not best:
        print("两种请求方式都拿不到**有内容**的瓦片 ⇒ 问题在 key 本身（不是代码、也不是请求写法）。")
        print("请到天地图控制台核对：")
        print("  1. key 的「应用类型 / 权限类型」——本项目走前端直连，需要**浏览器端** key；")
        print("     服务端 key 要配后端代理，且通常还要绑调用方 IP 白名单；")
        print("  2. 「浏览器端」key 的**授权域名**要包含 localhost（或你本地用的域名）；")
        print("  3. 账号**实名认证**状态与配额（未实名/超额时会返回 200 + 空白瓦片）。")
        return 1
    print(f"可用：{'；'.join(best)} ⇒ 按这种方式接入即可（本项目的实现按浏览器端风格走）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
