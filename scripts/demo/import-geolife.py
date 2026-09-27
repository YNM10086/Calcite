# -*- coding: utf-8 -*-
"""批量导入 GeoLife 数据集（**自己下载之后**用；仓库不打包第三方数据）。

为什么要有这个脚本：仓库里带的 `scripts/db/04-demo-data.sql` 是**合成**数据，够看效果但不够大。
想看"几十万点"的真实数据，请自己去官方下载 GeoLife（微软亚洲研究院的公开数据集），
然后用本脚本一次灌进去——它只做三件事：**确认后端在跑 → 检查目录是否在白名单内 → 调批量导入接口**。

⚠️ 两个必须知道的点：
  1. 后端配置 `calcite.import.allowed-roots` 是**目录白名单**（安全设计，不是 bug）：
     要导入的目录必须在它下面，否则接口返回 400「路径不在允许的导入目录内」。
     改 `backend/src/main/resources/application.yml` 后**要重启后端**才生效。
  2. 接口的 `maxTracks` 是「最多处理几个**文件**」，**不是几条轨迹**（数据管理阶段踩过这个坑：
     传 400 会把 400 个文件都扫进来）。

用法（从仓库根目录；后端需在 http://localhost:8080 运行）：

    # 先下好数据集，例如解压到 D:\\GeoLife\\Geolife Trajectories 1.3
    & "E:\\python\\python_address\\python.exe" scripts\\demo\\import-geolife.py `
        --data-dir "D:\\GeoLife\\Geolife Trajectories 1.3\\Data" --user 000 --max-tracks 15

    # 不加 --user 就导入 data-dir 本身；--dry-run 只检查不导入
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8080"
WHITELIST_HINT = (
    "\n提示：该目录不在后端的 calcite.import.allowed-roots 白名单里。\n"
    "  改 backend/src/main/resources/application.yml 的 allowed-roots（加一行你的目录），\n"
    "  然后**重启后端**再试。"
)


def post(base, path, body):
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=1800) as r:   # 大目录可能要跑很久
        return json.loads(r.read().decode("utf-8"))


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="批量导入本地 GeoLife 目录")
    ap.add_argument("--data-dir", required=True, help="GeoLIFE 的 Data 目录（或它的某个用户目录）")
    ap.add_argument("--user", default=None, help="只导入某个用户子目录，例如 000")
    ap.add_argument("--max-tracks", type=int, default=15,
                    help="最多处理几个【文件】（不是轨迹数！默认 15，先小批量试）")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"后端地址（默认 {DEFAULT_BASE}）")
    ap.add_argument("--dry-run", action="store_true", help="只做检查，不真的导入")
    args = ap.parse_args()

    target = os.path.join(args.data_dir, args.user) if args.user else args.data_dir
    target = os.path.abspath(target)
    if not os.path.isdir(target):
        print(f"!! 目录不存在：{target}")
        return 2
    n_plt = sum(1 for root, _dirs, files in os.walk(target)
                for f in files if f.lower().endswith(".plt"))
    print(f"目标目录：{target}")
    print(f"里面找到 .plt 文件：{n_plt} 个（本次最多处理 {args.max_tracks} 个）")

    try:
        health = get(args.base, "/api/health")
        print(f"后端：{health.get('status')}；{str(health.get('postgis'))[:60]}")
    except Exception as e:                                   # noqa: BLE001
        print(f"!! 后端没起来（{args.base}）—— 先 `mvn -f backend/pom.xml spring-boot:run`")
        print(f"   详细：{type(e).__name__}: {e}")
        return 1

    if args.dry_run:
        print("--dry-run：只检查，不导入。")
        return 0

    print(f"开始导入（maxTracks={args.max_tracks} 个文件）……")
    try:
        res = post(args.base, "/api/import/geolife",
                   {"path": target, "maxTracks": args.max_tracks})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"!! HTTP {e.code}: {body[:400]}")
        if "允许" in body or e.code == 400:
            print(WHITELIST_HINT)
        return 1

    print("导入完成：")
    for k in ("scanned", "imported", "skipped", "failed", "totalPoints", "elapsedMs"):
        if k in res:
            print(f"  {k} = {res[k]}")
    if res.get("errorSamples"):
        print("  失败样例（前几条）：")
        for s in res["errorSamples"][:5]:
            print(f"    - {s}")
    print("\n看结果：打开 http://localhost:5173 ，或 GET /api/tracks?limit=5")
    return 0 if not res.get("failed") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("已中断")
        sys.exit(130)
