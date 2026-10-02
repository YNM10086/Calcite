# -*- coding: utf-8 -*-
"""天地图接入探针（**先验，不靠博客配方**）。

要回答三个问题，答案决定实现形态：
  1. key 有效吗？（HTTP 200 + 真 PNG 字节）
  2. 坐标系/矩阵集对不对？—— 把瓦片**存成 PNG**，人来肉眼确认"这确实是北京"
     （行列写反会拿到别处的瓦片，光看 200 看不出来）
  3. CORS 通不通？—— 带 `Origin: http://localhost:5173` 请求，看有没有
     `Access-Control-Allow-Origin`；没有的话浏览器里 WebGL 贴图会失败，就得改成后端代理

跑法（需提权；token 从 application-local.yml 读，**不打印**）：
    & "E:\\python\\python_address\\python.exe" .tmp\\probe-tianditu.py
"""
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_YML = os.path.join(ROOT, "backend", "src", "main", "resources", "application-local.yml")
OUT = os.path.join(ROOT, ".tmp")
HOSTS = {"vec": "街道矢量底图", "cva": "注记（路名/地名）"}
BEIJING = (116.397, 39.909)      # 天安门附近，取瓦片用


def load_token():
    if not os.path.exists(LOCAL_YML):
        print(f"!! 找不到 {LOCAL_YML}")
        return None
    text = open(LOCAL_YML, encoding="utf-8").read()
    m = re.search(r"tianditu-token:\s*(\S+)", text)
    if not m or not m.group(1).strip():
        return None
    return m.group(1).strip()


def tile_xy(lon, lat, level):
    """天地图 _w（经纬度）矩阵集：level 0 = 2 列 × 1 行，每级翻倍。"""
    cols = 2 ** (level + 1)
    rows = 2 ** level
    col = int((lon + 180.0) / 360.0 * cols)
    row = int((90.0 - lat) / 180.0 * rows)
    return min(col, cols - 1), min(row, rows - 1)


def probe(layer, level, col, row, token, subdomain="1"):
    url = (f"https://t{subdomain}.tianditu.gov.cn/{layer}_w/wmts"
           f"?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={layer}&STYLE=default"
           f"&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={level}&TILEROW={row}&TILECOL={col}"
           f"&tk={token}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (calcite-probe)",
        # ⚠️ 必须带 Origin 才测得出 CORS：不带的话服务器可能不回 CORS 头
        "Origin": "http://localhost:5173",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            cors = r.headers.get("Access-Control-Allow-Origin")
            ctype = r.headers.get("Content-Type")
            print(f"  {layer} L{level} col={col} row={row}: HTTP {r.status} | {ctype} | "
                  f"{len(body)} B | PNG={body[:4] == b'\\x89PNG'} | CORS={cors!r}")
            return body, cors
    except Exception as e:                                     # noqa: BLE001
        print(f"  {layer} L{level} col={col} row={row}: 失败 {type(e).__name__}: {str(e)[:160]}")
        return None, None


def main():
    token = load_token()
    if not token:
        print("!! application-local.yml 里还没配 calcite.map.tianditu-token（或为空）")
        print("   填好后重跑本探针（key 不会被打出来）。")
        return 2
    print(f"key 已读到（长度 {len(token)}，不显示内容）\n")

    print("=== 1) 取真瓦片（北京天安门附近）===")
    for w in ("**注意** 若下面出现 403/401，说明 key 无效或域名白名单不认 localhost"):
        pass
    best = None
    for layer in ("vec", "cva"):
        for level in (14, 16, 18):
            col, row = tile_xy(*BEIJING, level)
            body, cors = probe(layer, level, col, row, token)
            if body and layer == "vec" and level == 16:
                best = (body, cors, level, col, row)
    print("\n（403/401 = key 或域名白名单问题；404 = 行列算错或超范围）")

    print("\n=== 2) 把一张 16 级瓦片存成 PNG，供人眼确认'这确实是北京' ===")
    if best:
        body, cors, level, col, row = best
        path = os.path.join(OUT, f"tianditu-probe-vec-L{level}-{col}-{row}.png")
        with open(path, "wb") as f:
            f.write(body)
        print(f"  已存 {path}（{len(body)} 字节）")
        print(f"  CORS 头: {cors!r}")
        if cors is None:
            print("  ⚠️ 没有 Access-Control-Allow-Origin ⇒ 浏览器里 WebGL 贴图可能失败 ⇒ 需要后端代理瓦片")
        else:
            print("  ✅ 有 CORS 头 ⇒ 前端可以直连天地图")
    else:
        print("  没拿到瓦片，跳过")

    print("\n=== 3) 结论怎么用 ===")
    print("  · 全部 200 + 是真 PNG + 图上是北京 ⇒ 前端直连可行")
    print("  · 有 CORS 头 ⇒ 不需要后端代理")
    return 0


if __name__ == "__main__":
    sys.exit(main())
